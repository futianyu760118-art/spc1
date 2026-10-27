"""本地编排器单测 — ReAct 循环三道硬闸门与写操作确认（脚本化 LLM，不依赖真实模型 / agent）"""

from app.services.ai.base import ChatWithToolsResult, ToolCall
from app.services.assistant import orchestrator


class ScriptedLLM:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def chat_with_tools(self, messages, tools, options):
        self.calls.append(list(messages))
        return self.results.pop(0)


def tool_call(name, arguments):
    return ChatWithToolsResult(text="", tool_calls=[ToolCall(id=f"call-{name}", name=name, arguments=arguments)])


def direct_reply(text):
    return ChatWithToolsResult(text=text, tool_calls=[])


async def _collect(gen):
    events = []
    async for event in gen:
        events.append(event)
    return events


def _done(events):
    return next(d for e, d in reversed(events) if e == "done")


async def _run(monkeypatch, script, *, limits=None, include_order=True, max_tool_rounds=6,
               max_agent_calls=8, gap_notify=True):
    """执行一轮 run_reaction 并返回 (事件列表, LLM实例, execute调用记录)。"""
    llm = ScriptedLLM(script)
    monkeypatch.setattr(orchestrator.ai_service, "chat_with_tools", llm.chat_with_tools)
    monkeypatch.setattr(orchestrator.ai_service, "chat", _fake_chat())
    monkeypatch.setattr(orchestrator, "maybe_summarize", _identity_summarize)
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)

    exec_calls = []

    async def fake_execute(
        tool_name, args, *, operator_user_id="", trace_id="", hub_trace_id="", caller=None,
        task_id=None, step_id=None,
    ):
        exec_calls.append({"tool": tool_name, "args": args})
        return {
            "ok": True, "online": True, "error": None, "item_count": 1,
            "result": {"items": [{"order_no": "HJ-1"}], "total": 1},
        }

    monkeypatch.setattr(orchestrator, "execute_agent_tool", fake_execute)
    events = await _collect(orchestrator.run_reaction(
        "查订单", [],
        system_prompt="sys", model_override=None, temperature=0.1, max_tokens=4096,
        max_tool_rounds=max_tool_rounds, max_agent_calls=max_agent_calls,
        disabled_tools=None, session_id="", trace_id="", user_id="u1",
        run_logger=None, provider_name="test",
        limits=limits, include_order_tool=include_order, stream_final=False,
        gap_notify=gap_notify,
    ))
    return events, llm, exec_calls


def _fake_chat():
    async def chat(messages, options):
        return "总结文本"
    return chat


async def _identity_summarize(messages, run_logger, session_id=""):
    return messages


def _steps(events):
    return [d for e, d in events if e == "step_completed"]


class TestReadOnlyReAct:
    async def test_query_then_reasoning_then_reply(self, monkeypatch):
        script = [
            tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": "HJ-1"}}),
            tool_call("call_reasoning_agent", {
                "task_type": "order_delivery_analysis", "prompt": "分析交期",
                "businessObjectRef": "business://order/HJ-1",
            }),
            direct_reply("订单 HJ-1 交期风险较高"),
        ]
        events, llm, exec_calls = await _run(monkeypatch, script)
        assert len(exec_calls) == 2
        assert exec_calls[0]["tool"] == "call_query_agent"
        assert exec_calls[1]["tool"] == "call_reasoning_agent"

        steps = _steps(events)
        assert [s["step"]["status"] for s in steps] == ["completed", "completed"]
        done = _done(events)
        assert done["text"] == "订单 HJ-1 交期风险较高"
        assert len(done["steps"]) == 2
        assert done["stats"]["tools_called"] == ["call_query_agent", "call_reasoning_agent"]

        deltas = [d["text"] for e, d in events if e == "delta"]
        assert "订单 HJ-1 交期风险较高" in deltas


class TestCards:
    async def test_cards_event_is_json_serializable(self, monkeypatch):
        script = [
            tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": "HJ-1"}}),
            direct_reply("完成"),
        ]
        events, _, _ = await _run(monkeypatch, script)
        cards_events = [data for event, data in events if event == "cards"]
        assert len(cards_events) == 1
        card = cards_events[0]["cards"][0]
        assert isinstance(card, dict)
        assert card["type"] == "search_result_list"


class TestReasoningRoundTrip:
    async def test_reasoning_content_passed_back_with_tool_calls(self, monkeypatch):
        """DeepSeek thinking 模式：带 tool_calls 的 assistant 消息必须回传 reasoning_content。"""
        script = [
            ChatWithToolsResult(
                text="", thinking="先查订单",
                tool_calls=[ToolCall(
                    id="call-1", name="call_query_agent",
                    arguments={"path": "/external/orders/list", "params": {"keyword": "HJ-1"}},
                )],
            ),
            direct_reply("完成"),
        ]
        # _run 内部创建 LLM，这里通过返回实例取第二轮请求
        _, llm, _ = await _run(monkeypatch, script)
        second_round = llm.calls[1]
        assistant_msg = second_round[-2]
        assert assistant_msg.role == "assistant"
        assert assistant_msg.tool_calls
        assert assistant_msg.reasoning_content == "先查订单"


class TestSystemPromptResolution:
    def test_legacy_prompt_falls_back_to_builtin(self):
        resolved = orchestrator.resolve_system_prompt("可用工具：search_orders 查询订单")
        assert resolved == orchestrator.SYSTEM_PROMPT

    def test_custom_prompt_kept(self):
        assert orchestrator.resolve_system_prompt("自定义提示词") == "自定义提示词"

    def test_empty_prompt_falls_back_to_builtin(self):
        assert orchestrator.resolve_system_prompt("") == orchestrator.SYSTEM_PROMPT


class TestGates:
    async def test_duplicate_tool_call_blocked(self, monkeypatch):
        args = {"path": "/external/orders/list", "params": {"keyword": "HJ-1"}}
        script = [
            tool_call("call_query_agent", args),
            tool_call("call_query_agent", args),
            direct_reply("查到了"),
        ]
        events, llm, exec_calls = await _run(monkeypatch, script)
        assert len(exec_calls) == 1
        steps = _steps(events)
        assert [s["step"]["status"] for s in steps] == ["completed", "blocked"]
        assert "重复调用被拦截" in steps[1]["step"]["error"]

    async def test_same_tool_new_params_allowed(self, monkeypatch):
        script = [
            tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": "A"}}),
            tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": "B"}}),
            direct_reply("查到了"),
        ]
        events, llm, exec_calls = await _run(monkeypatch, script)
        assert len(exec_calls) == 2
        assert [s["step"]["status"] for s in _steps(events)] == ["completed", "completed"]

    async def test_max_agent_calls_blocked(self, monkeypatch):
        script = [
            tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": "A"}}),
            tool_call("call_query_agent", {"path": "/external/materials/list", "params": {"keyword": "B"}}),
            direct_reply("结束"),
        ]
        events, llm, exec_calls = await _run(
            monkeypatch, script, limits={"max_agent_calls": 1, "max_llm_rounds": 3}
        )
        assert len(exec_calls) == 1
        steps = _steps(events)
        assert steps[1]["step"]["status"] == "blocked"
        assert "调用次数已达上限" in steps[1]["step"]["error"]

    async def test_unknown_tool_blocked(self, monkeypatch):
        script = [
            tool_call("fly_to_moon", {"x": 1}),
            direct_reply("不存在的工具"),
        ]
        events, llm, exec_calls = await _run(monkeypatch, script)
        assert len(exec_calls) == 0
        steps = _steps(events)
        assert steps[0]["step"]["status"] == "blocked"
        assert "不在能力目录" in steps[0]["step"]["error"]

    async def test_consecutive_same_agent_prompted_to_change(self, monkeypatch):
        script = [
            tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": f"K{i}"}})
            for i in range(4)
        ] + [direct_reply("结束")]
        events, llm, exec_calls = await _run(
            monkeypatch, script, limits={"max_consecutive_same_agent": 3, "max_llm_rounds": 6}
        )
        assert len(exec_calls) == 3
        steps = _steps(events)
        assert steps[3]["step"]["status"] == "blocked"
        assert "连续调用同一智能体" in steps[3]["step"]["error"]

    async def test_rounds_exhausted_partial_summary(self, monkeypatch):
        script = [
            tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": f"K{i}"}})
            for i in range(2)
        ]
        events, llm, exec_calls = await _run(monkeypatch, script, max_tool_rounds=2)
        done = _done(events)
        assert done["partial"] is True
        assert "轮数已达上限" in done["partial_reason"]
        assert done["text"] == "总结文本"

    async def test_llm_failure_emits_error_done(self, monkeypatch):
        async def boom(messages, tools, options):
            raise RuntimeError("llm down")

        monkeypatch.setattr(orchestrator.ai_service, "chat_with_tools", boom)
        monkeypatch.setattr(orchestrator, "maybe_summarize", _identity_summarize)
        monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
        monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)
        events = await _collect(orchestrator.run_reaction(
            "查订单", [], system_prompt="sys", model_override=None, temperature=0.1,
            max_tokens=4096, max_tool_rounds=6, max_agent_calls=8, disabled_tools=None,
            session_id="", trace_id="", user_id="u1", run_logger=None, provider_name="test",
        ))
        assert any(e == "error" for e, _ in events)
        assert _done(events)["failed"] is True


class TestWriteConfirmation:
    async def test_order_tool_intercepted_with_confirmation(self, monkeypatch):
        script = [tool_call("call_order_agent", {
            "order_no": "HJ-1", "fields": {"shipping_plan": "2026-11-01"},
        })]

        async def fake_old(order_no, *, operator_user_id="", trace_id="", task_id=None, step_id=None):
            return {
                "values": {
                    "shipping_plan": "2026-10-28",
                    "delivery_completed_date": None,
                    "customer_inspection_date": None,
                    "planned_start_date": None,
                },
                "missing": False, "error": None,
            }

        created = {}

        async def fake_create(record):
            created.update(record)
            return {
                **record,
                "confirmation_id": "wc-test",
                "created_at": "2026-10-21T00:00:00+00:00",
                "expires_at": "2026-10-21T00:10:00+00:00",
                "ttl_s": 600,
            }

        monkeypatch.setattr(orchestrator, "query_order_current_fields", fake_old)
        monkeypatch.setattr(orchestrator.write_confirmation, "create_confirmation", fake_create)

        events, llm, exec_calls = await _run(monkeypatch, script)
        assert len(exec_calls) == 0
        conf_events = [d for e, d in events if e == "confirmation_required"]
        assert len(conf_events) == 1
        conf = conf_events[0]
        assert conf["confirmation_id"] == "wc-test"
        assert conf["order_no"] == "HJ-1"
        assert conf["status"] == "pending"
        assert conf["fields"] == [{"field": "shipping_plan", "old_value": "2026-10-28", "new_value": "2026-11-01"}]
        assert created["old_values"]["shipping_plan"] == "2026-10-28"

        done = _done(events)
        assert done["confirmation"]["confirmation_id"] == "wc-test"
        assert done["confirmation"]["status"] == "pending"
        steps = _steps(events)
        assert steps[-1]["step"]["status"] == "pending_confirmation"
        assert created["task_id"].startswith("task-")
        assert created["next_step_id"] == created["order_step_id"] + 1

    async def test_order_tool_invalid_args_blocked_no_confirmation(self, monkeypatch):
        script = [
            tool_call("call_order_agent", {
                "order_no": "HJ-1", "fields": {"status": "closed"},
            }),
            direct_reply("该字段不支持修改"),
        ]
        created = []

        async def fake_create(record):
            created.append(record)
            return {"confirmation_id": "wc-x", **record}

        monkeypatch.setattr(orchestrator.write_confirmation, "create_confirmation", fake_create)
        events, llm, exec_calls = await _run(monkeypatch, script)
        assert len(created) == 0
        assert not any(e == "confirmation_required" for e, _ in events)
        steps = _steps(events)
        assert steps[0]["step"]["status"] == "blocked"
        assert "参数非法" in steps[0]["step"]["error"]


class TestResolveConfirmation:
    RECORD = {
        "confirmation_id": "wc-1",
        "session_id": "s1",
        "trace_id": "",
        "task_id": "task-1",
        "order_step_id": 3,
        "next_step_id": 4,
        "user_id": "u1",
        "order_no": "HJ-1",
        "fields": {"shipping_plan": "2026-11-01"},
        "old_values": {"shipping_plan": "2026-10-28"},
    }

    def _patch_common(self, monkeypatch):
        monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
        monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)
        monkeypatch.setattr(orchestrator, "get_scope_config", _fake_scope_config)
        monkeypatch.setattr(orchestrator, "render_system_prompt", lambda template, disabled=None: template)
        monkeypatch.setattr(orchestrator.session_store, "get_history", _fake_get_history)
        monkeypatch.setattr(orchestrator, "notify_agent_change", lambda **k: None)
        monkeypatch.setattr(orchestrator, "notify_agent_gap", lambda **k: None)
        appended = []
        monkeypatch.setattr(orchestrator.session_store, "append_messages", _fake_append(appended))
        return appended

    async def test_consume_missing_returns_404(self, monkeypatch):
        monkeypatch.setattr(orchestrator.write_confirmation, "consume_confirmation", _fake_consume(None))
        outcome = await orchestrator.resolve_confirmation(None, "wc-x", "confirm", "u1")
        assert outcome["code"] == 404

    async def test_wrong_user_returns_403(self, monkeypatch):
        monkeypatch.setattr(
            orchestrator.write_confirmation, "consume_confirmation", _fake_consume(self.RECORD)
        )
        outcome = await orchestrator.resolve_confirmation(None, "wc-1", "confirm", "u9")
        assert outcome["code"] == 403

    async def test_cancel_no_write(self, monkeypatch):
        appended = self._patch_common(monkeypatch)
        monkeypatch.setattr(
            orchestrator.write_confirmation, "consume_confirmation", _fake_consume(self.RECORD)
        )
        dispatched = []

        async def fake_dispatch(spec, input, *, timeout=30.0, operator_user_id="", trace_id="", caller=None):
            dispatched.append(input)
            return {"online": True, "ok": True, "result": {}}

        monkeypatch.setattr(orchestrator, "call_agent_run", fake_dispatch)
        outcome = await orchestrator.resolve_confirmation(None, "wc-1", "cancel", "u1")
        assert outcome["code"] == 0
        assert outcome["data"]["confirmation"]["status"] == "cancelled"
        assert outcome["data"]["reply"]["text"] == "已取消订单 HJ-1 的写操作，订单未做任何修改。"
        assert any("已取消订单 HJ-1" in m["content"] for m in appended)
        assert dispatched == []

    async def test_confirm_success_executes_and_continues(self, monkeypatch):
        appended = self._patch_common(monkeypatch)
        monkeypatch.setattr(
            orchestrator.write_confirmation, "consume_confirmation", _fake_consume(self.RECORD)
        )
        dispatched = []

        async def fake_dispatch(spec, input, *, timeout=30.0, operator_user_id="", trace_id="", caller=None):
            dispatched.append((input, operator_user_id))
            return {"online": True, "ok": True, "runId": "r1", "result": {
                "order_no": input["order_no"],
                "fields": {"shipping_plan": "2026-11-01"},
            }}

        monkeypatch.setattr(orchestrator, "call_agent_run", fake_dispatch)

        async def fake_reaction(*args, **kwargs):
            assert kwargs["include_order_tool"] is False
            assert kwargs["limits"]["max_agent_calls"] == 3
            assert kwargs["task_id"] == "task-1"
            assert kwargs["step_id_base"] == 3
            yield ("delta", {"text": "已回查"})
            yield ("delta", {"text": "验证成功"})
            yield ("cards", {"cards": []})
            yield ("done", {"steps": [], "text": "已回查验证成功"})

        monkeypatch.setattr(orchestrator, "run_reaction", fake_reaction)
        outcome = await orchestrator.resolve_confirmation(None, "wc-1", "confirm", "u1")
        assert outcome["code"] == 0
        assert len(dispatched) == 1
        assert dispatched[0][0] == {"order_no": "HJ-1", "fields": {"shipping_plan": "2026-11-01"}}
        assert dispatched[0][1] == "u1"
        conf = outcome["data"]["confirmation"]
        assert conf["status"] == "executed"
        assert conf["write_result"]["order_no"] == "HJ-1"
        assert outcome["data"]["reply"]["text"] == "已回查验证成功"
        assert any("已回查验证成功" in m["content"] for m in appended)

    async def test_confirm_write_failure_no_retry_no_continuation(self, monkeypatch):
        appended = self._patch_common(monkeypatch)
        monkeypatch.setattr(
            orchestrator.write_confirmation, "consume_confirmation", _fake_consume(self.RECORD)
        )
        dispatched = []

        async def fake_dispatch(spec, input, *, timeout=30.0, operator_user_id="", trace_id="", caller=None):
            dispatched.append(input)
            return {"online": True, "ok": False, "reason": "订单已关闭"}

        monkeypatch.setattr(orchestrator, "call_agent_run", fake_dispatch)
        reaction_called = {"v": False}

        async def fake_reaction(*args, **kwargs):
            reaction_called["v"] = True
            yield ("done", {"text": ""})
            return

        monkeypatch.setattr(orchestrator, "run_reaction", fake_reaction)
        outcome = await orchestrator.resolve_confirmation(None, "wc-1", "confirm", "u1")
        assert outcome["code"] == 0
        conf = outcome["data"]["confirmation"]
        assert conf["status"] == "failed"
        assert "订单已关闭" in conf["error"]
        assert outcome["data"]["reply"] is None
        assert reaction_called["v"] is False
        assert len(dispatched) == 1
        assert any("写操作执行失败" in m["content"] for m in appended)


def _fake_consume(record):
    async def consume(confirmation_id):
        return dict(record) if record else None
    return consume


async def _fake_scope_config(db, scope):
    return {
        "system_prompt": "", "intent_prompt": "", "model_name": "", "temperature": 0.1,
        "max_tokens": 4096, "max_tool_rounds": 6, "max_agent_calls": 8, "disabled_tools": [],
    }


async def _fake_get_history(session_id):
    return []


def _fake_append(collector):
    async def append(session_id, messages):
        collector.extend(messages)
        return messages
    return append


async def test_query_path_injects_completeness_and_notifies(monkeypatch):
    notifications = []

    async def fake_refresh(*_args, **_kwargs):
        return None

    def fake_check(**_kwargs):
        return [("promised_date", "合同交期")]

    def fake_notify(**kwargs):
        notifications.append(kwargs)

    monkeypatch.setattr(orchestrator, "refresh_rules", fake_refresh)
    monkeypatch.setattr(orchestrator, "check_completeness", fake_check)
    monkeypatch.setattr(orchestrator, "notify_agent_gap", fake_notify)

    script = [
        tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": "HJ-1"}}),
        direct_reply("订单缺少合同交期"),
    ]
    events, llm, _ = await _run(monkeypatch, script)
    assert notifications and notifications[0]["biz_no"] == "HJ-1"
    assert any("completeness" in (getattr(m, "content", "") or "") for m in llm.calls[1])


async def test_query_path_skipped_when_gap_notify_false(monkeypatch):
    notifications = []
    monkeypatch.setattr(orchestrator, "notify_agent_gap", lambda **kw: notifications.append(kw))
    script = [
        tool_call("call_query_agent", {"path": "/external/orders/list", "params": {"keyword": "HJ-1"}}),
        direct_reply("ok"),
    ]
    events, _, _ = await _run(monkeypatch, script, gap_notify=False)
    assert notifications == []


async def test_query_path_detail_route_not_checked(monkeypatch):
    notifications = []
    monkeypatch.setattr(orchestrator, "notify_agent_gap", lambda **kw: notifications.append(kw))
    result = await orchestrator._check_query_gaps(
        {"path": "/external/order-details/list", "params": {"keyword": "HJ-1"}},
        {"items": [{"order_no": "HJ-1"}]},
        "u1",
    )
    assert result is None
    assert notifications == []


async def test_notify_write_result_skips_gap_when_snapshot_untrusted(monkeypatch):
    calls = {"change": [], "gap": []}
    monkeypatch.setattr(orchestrator, "notify_agent_change", lambda **kw: calls["change"].append(kw))
    monkeypatch.setattr(orchestrator, "notify_agent_gap", lambda **kw: calls["gap"].append(kw))
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)

    async def fake_refresh():
        return None

    monkeypatch.setattr(orchestrator, "refresh_rules", fake_refresh)
    record = {
        "old_values_missing": True,
        "old_row": {"promised_date": None},
        "trace_id": "",
        "task_id": None,
        "order_step_id": None,
        "confirmation_id": None,
    }
    await orchestrator._notify_write_result(
        record=record, write_result=None, fields={},
        biz_type="order", action="update", biz_no="HJ-1", operator_user_id="u1",
    )
    assert calls["change"]
    assert calls["gap"] == []


async def test_notify_write_result_create_uses_write_result_biz_no(monkeypatch):
    calls = []
    monkeypatch.setattr(orchestrator, "notify_agent_change", lambda **kw: calls.append(kw))
    monkeypatch.setattr(orchestrator, "notify_agent_gap", lambda **kw: None)
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)

    async def fake_refresh():
        return None

    monkeypatch.setattr(orchestrator, "refresh_rules", fake_refresh)
    await orchestrator._notify_write_result(
        record={}, write_result={"order_no": "HJ-NEW"}, fields={},
        biz_type="order", action="create", biz_no="", operator_user_id="u1",
    )
    assert calls and calls[0]["biz_no"] == "HJ-NEW"
