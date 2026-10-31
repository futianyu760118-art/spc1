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
        task_id=None, step_id=None, actor_token="", db=None, user_context=None,
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

        async def fake_dispatch(spec, input, *, timeout=30.0, operator_user_id="", trace_id="",
                                caller=None, actor_token=""):
            dispatched.append((input, operator_user_id, actor_token))
            return {"online": True, "ok": True, "runId": "r1", "result": {
                "ok": True,
                "operation": "order.update_schedule_fields",
                "target": {"orderNo": input["orderNo"]},
                "before": {"shipping_plan": "2026-10-28"},
                "after": {"shipping_plan": "2026-11-01"},
                "appliedAt": "2026-10-28T00:00:00+00:00",
                "idempotent_replay": False,
            }}

        async def fake_prepare(db, user_id, order_no, fields):
            return "actor-token-1"

        monkeypatch.setattr(orchestrator, "_prepare_order_write_actor", fake_prepare)
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
        assert dispatched[0][0] == {
            "operation": "order.update_schedule_fields",
            "orderNo": "HJ-1",
            "changes": {"fields": {"shipping_plan": "2026-11-01"}},
            "idempotencyKey": "wc-1",
        }
        assert dispatched[0][1] == "u1"
        assert dispatched[0][2] == "actor-token-1"
        conf = outcome["data"]["confirmation"]
        assert conf["status"] == "executed"
        assert conf["write_result"]["target"] == {"orderNo": "HJ-1"}
        assert outcome["data"]["reply"]["text"] == "已回查验证成功"
        assert any("已回查验证成功" in m["content"] for m in appended)

    async def test_confirm_write_failure_no_retry_no_continuation(self, monkeypatch):
        appended = self._patch_common(monkeypatch)
        monkeypatch.setattr(
            orchestrator.write_confirmation, "consume_confirmation", _fake_consume(self.RECORD)
        )
        dispatched = []

        async def fake_dispatch(spec, input, *, timeout=30.0, operator_user_id="", trace_id="",
                                caller=None, actor_token=""):
            dispatched.append(input)
            return {"online": True, "ok": False, "reason": "订单已关闭"}

        async def fake_prepare(db, user_id, order_no, fields):
            return "actor-token-2"

        monkeypatch.setattr(orchestrator, "_prepare_order_write_actor", fake_prepare)
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


def test_new_step_prefers_member_label_and_falls_back_to_tool_label():
    """团队制：成员路由命中时步骤展示承接成员名，未命中回退工具类型标签。"""
    step = orchestrator._new_step(
        1, "call_query_agent", {"path": "/external/orders/list"},
        status="running", summary="查询 销售订单列表", agent_label="订单专员",
    )
    assert step["agent_label"] == "订单专员"

    fallback = orchestrator._new_step(2, "call_query_agent", {}, status="blocked")
    assert fallback["agent_label"] == "查询智能体"


async def test_generate_plan_cleans_prefixes_and_caps(monkeypatch):
    """计划解析：去编号/项目符号、去重、上限 5 条；失败返回空列表。"""
    from types import SimpleNamespace

    async def fake_chat(messages, options):
        return "1. 查询订单\n- 查询齐套\n• 分析交期风险\n2) 汇总结论\n- 查询订单\n5. 生成建议\n6. 多余步骤"

    monkeypatch.setattr(orchestrator.ai_service, "chat", fake_chat)
    ctx = SimpleNamespace(effective_capabilities={"query.orders", "reason.orders"})
    steps = await orchestrator._generate_plan(ctx, "这批订单交期风险怎么样")
    assert steps == ["查询订单", "查询齐套", "分析交期风险", "汇总结论", "生成建议"]

    async def failing_chat(messages, options):
        raise RuntimeError("boom")

    monkeypatch.setattr(orchestrator.ai_service, "chat", failing_chat)
    assert await orchestrator._generate_plan(ctx, "x") == []


async def test_plan_events_precede_first_step(monkeypatch):
    """流式事件：plan_started/plan 恒在首个 step_started 之前。"""
    from types import SimpleNamespace

    from app.services.agent.context import TeamMemberInfo, UserContext

    user = SimpleNamespace(id=1, username="u1", display_name="测试用户", role_id=1)
    user_ctx = UserContext(
        user=user, role_code="admin", permissions={},
        members=[TeamMemberInfo(
            agent_id=1, agent_no="AG-1", display_name="订单专员",
            capabilities=["query.orders"], description=None, status="active", config_version=1,
        )],
        effective_capabilities={"query.orders"},
        allowed_tools={"call_query_agent"},
    )
    llm = ScriptedLLM([
        tool_call("call_query_agent", {"path": "/external/orders/list"}),
        direct_reply("好的"),
    ])
    monkeypatch.setattr(orchestrator.ai_service, "chat_with_tools", llm.chat_with_tools)
    monkeypatch.setattr(orchestrator.ai_service, "chat", _fake_chat())
    monkeypatch.setattr(orchestrator, "maybe_summarize", _identity_summarize)
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)

    async def fake_execute(tool_name, args, **kwargs):
        return {"ok": True, "online": True, "error": None, "item_count": 1,
                "result": {"items": [{"order_no": "HJ-1"}], "total": 1}}

    monkeypatch.setattr(orchestrator, "execute_agent_tool", fake_execute)

    events = await _collect(orchestrator.run_reaction(
        "查订单", [],
        system_prompt="sys", model_override=None, temperature=0.1, max_tokens=4096,
        max_tool_rounds=6, max_agent_calls=8,
        disabled_tools=None, session_id="", trace_id="", user_id="u1",
        run_logger=None, provider_name="test", stream_final=False,
        user_context=user_ctx,
    ))
    names = [e for e, _ in events]
    assert names[0] == "plan_started"
    assert names[1] == "plan"
    assert next(d for e, d in events if e == "plan")["steps"]
    assert names.index("plan") < names.index("step_started")


async def test_order_field_gate_blocks_ungranted_fields(monkeypatch):
    """字段级门控：团队仅有客户验货时间能力时，提交上线时间必须被拦截。"""
    from types import SimpleNamespace

    from app.services.agent.context import TeamMemberInfo, UserContext

    user = SimpleNamespace(id=1, username="u1", display_name="测试用户", role_id=1)
    user_ctx = UserContext(
        user=user, role_code="admin", permissions={},
        members=[TeamMemberInfo(
            agent_id=1, agent_no="AG-1", display_name="计划写入员",
            capabilities=["write.order_customer_inspection"],
            description=None, status="active", config_version=1,
        )],
        effective_capabilities={"write.order_customer_inspection"},
        allowed_tools={"call_order_agent"},
    )
    llm = ScriptedLLM([
        tool_call("call_order_agent", {
            "operation": "order.update_schedule_fields",
            "order_no": "HJ-1",
            "fields": {"planned_start_date": "2026-11-01"},
        }),
        direct_reply("好的"),
    ])
    monkeypatch.setattr(orchestrator.ai_service, "chat_with_tools", llm.chat_with_tools)
    monkeypatch.setattr(orchestrator.ai_service, "chat", _fake_chat())
    monkeypatch.setattr(orchestrator, "maybe_summarize", _identity_summarize)
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)

    events = await _collect(orchestrator.run_reaction(
        "把上线时间改一下", [],
        system_prompt="sys", model_override=None, temperature=0.1, max_tokens=4096,
        max_tool_rounds=6, max_agent_calls=8, disabled_tools=None,
        session_id="", trace_id="", user_id="u1", run_logger=None, provider_name="test",
        stream_final=False, user_context=user_ctx, with_plan=False,
    ))
    blocked = [d["step"] for e, d in events if e == "step_started" and d["step"]["status"] == "blocked"]
    assert blocked, "未授权字段必须产生 blocked 步骤"
    assert "planned_start_date" in blocked[0]["error"]


async def test_order_field_gate_allows_granted_fields(monkeypatch):
    """字段级门控：团队具备该字段能力时进入写确认流程（确认单步骤生成）。"""
    from types import SimpleNamespace

    from app.services.agent.context import TeamMemberInfo, UserContext

    user = SimpleNamespace(id=1, username="u1", display_name="测试用户", role_id=1)
    user_ctx = UserContext(
        user=user, role_code="admin", permissions={},
        members=[TeamMemberInfo(
            agent_id=1, agent_no="AG-1", display_name="计划写入员",
            capabilities=["write.order_planned_start"],
            description=None, status="active", config_version=1,
        )],
        effective_capabilities={"write.order_planned_start"},
        allowed_tools={"call_order_agent"},
    )
    llm = ScriptedLLM([
        tool_call("call_order_agent", {
            "operation": "order.update_schedule_fields",
            "order_no": "HJ-1",
            "fields": {"planned_start_date": "2026-11-01"},
        }),
        direct_reply("好的"),
    ])
    monkeypatch.setattr(orchestrator.ai_service, "chat_with_tools", llm.chat_with_tools)
    monkeypatch.setattr(orchestrator.ai_service, "chat", _fake_chat())
    monkeypatch.setattr(orchestrator, "maybe_summarize", _identity_summarize)
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)

    async def fake_readback(order_no, **kwargs):
        return {"values": {}, "missing": True, "row": None, "error": None}

    async def fake_create_confirmation(record):
        return {
            **record,
            "confirmation_id": "wc-test",
            "created_at": "2026-10-29T00:00:00+00:00",
            "expires_at": "2026-10-29T00:10:00+00:00",
        }

    monkeypatch.setattr(orchestrator, "query_order_current_fields", fake_readback)
    monkeypatch.setattr(orchestrator.write_confirmation, "create_confirmation", fake_create_confirmation)

    events = await _collect(orchestrator.run_reaction(
        "把上线时间改一下", [],
        system_prompt="sys", model_override=None, temperature=0.1, max_tokens=4096,
        max_tool_rounds=6, max_agent_calls=8, disabled_tools=None,
        session_id="", trace_id="", user_id="u1", run_logger=None, provider_name="test",
        stream_final=False, user_context=user_ctx, with_plan=False,
    ))
    states = [d["step"]["status"] for e, d in events if e == "step_started"]
    assert "pending_confirmation" in states
    confirmations = [d for e, d in events if e == "confirmation_required"]
    assert confirmations and confirmations[0]["confirmation_id"] == "wc-test"


async def test_plan_degrades_to_empty_steps_on_failure(monkeypatch):
    """计划生成失败：仍先发 plan_started + 空 plan，任务继续执行。"""
    from types import SimpleNamespace

    from app.services.agent.context import TeamMemberInfo, UserContext

    user = SimpleNamespace(id=1, username="u1", display_name="测试用户", role_id=1)
    user_ctx = UserContext(
        user=user, role_code="admin", permissions={},
        members=[TeamMemberInfo(
            agent_id=1, agent_no="AG-1", display_name="订单专员",
            capabilities=["query.orders"], description=None, status="active", config_version=1,
        )],
        effective_capabilities={"query.orders"},
        allowed_tools={"call_query_agent"},
    )

    async def failing_chat(messages, options):
        raise RuntimeError("llm down")

    monkeypatch.setattr(orchestrator.ai_service, "chat_with_tools", ScriptedLLM([direct_reply("好的")]).chat_with_tools)
    monkeypatch.setattr(orchestrator.ai_service, "chat", failing_chat)
    monkeypatch.setattr(orchestrator, "maybe_summarize", _identity_summarize)
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)

    events = await _collect(orchestrator.run_reaction(
        "查订单", [],
        system_prompt="sys", model_override=None, temperature=0.1, max_tokens=4096,
        max_tool_rounds=6, max_agent_calls=8, disabled_tools=None,
        session_id="", trace_id="", user_id="u1", run_logger=None, provider_name="test",
        stream_final=False, user_context=user_ctx,
    ))
    names = [e for e, _ in events]
    assert names[0] == "plan_started"
    plan = next(d for e, d in events if e == "plan")
    assert plan["steps"] == []
    assert "done" in names


def test_query_step_summary_shows_page():
    """步骤摘要展示页码，翻页调用在时间线上可区分。"""
    assert orchestrator._step_summary(
        "call_query_agent", {"path": "/external/orders/list", "params": {"page": 2}},
    ) == "查询 销售订单列表（第2页）"
    assert orchestrator._step_summary(
        "call_query_agent", {"path": "/external/orders/list", "params": {}},
    ) == "查询 销售订单列表"


async def test_identical_page_query_calls_blocked(monkeypatch):
    """完全相同的页码与参数重复拉取会被重复调用拦截。"""
    def same_call():
        return tool_call(
            "call_query_agent",
            {"path": "/external/orders/list", "params": {"keyword": "HJ", "page": 1}},
        )

    events, _, exec_calls = await _run(monkeypatch, [
        same_call(),
        same_call(),
        direct_reply("好的"),
    ])
    assert len(exec_calls) == 1, "完全相同参数的第二次查询不应执行"
    blocked = [d["step"] for e, d in events if e == "step_started" and d["step"]["status"] == "blocked"]
    assert blocked and "重复调用被拦截" in blocked[0]["error"]
