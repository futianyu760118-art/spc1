"""编排器技能闸门单测：先加载后执行、次数上限与未绑定执行器拦截。"""

from types import SimpleNamespace

from app.services.agent.context import TeamMemberInfo, UserContext
from app.services.ai.base import ChatWithToolsResult, ToolCall
from app.services.assistant import orchestrator
from app.services.agent.skills import TeamSkillInfo


class ScriptedLLM:
    def __init__(self, results):
        self.results = list(results)

    async def chat_with_tools(self, messages, tools, options):
        return self.results.pop(0)


def tool_call(name, arguments):
    return ChatWithToolsResult(
        text="", tool_calls=[ToolCall(id=f"call-{name}", name=name, arguments=arguments)],
    )


def direct_reply(text):
    return ChatWithToolsResult(text=text, tool_calls=[])


async def _collect(gen):
    return [event async for event in gen]


def _skill(skill_id, has_executor=True, has_scripts=False):
    return TeamSkillInfo(
        skill_id=skill_id, name=f"技能{skill_id}", description="说明",
        agent_id=1, agent_name="订单专员",
        has_executor=has_executor, executor_name="orders.risk" if has_executor else None,
        has_scripts=has_scripts,
    )


def _context(skills, permissions=None):
    user = SimpleNamespace(id=1, username="u1", display_name="测试用户", role_id=1)
    return UserContext(
        user=user, role_code="admin", permissions=permissions or {},
        members=[TeamMemberInfo(
            agent_id=1, agent_no="AG-1", display_name="订单专员",
            capabilities=["query.orders"], description=None, status="active", config_version=1,
        )],
        effective_capabilities={"query.orders"},
        allowed_tools={"call_query_agent"},
        skills=skills,
    )


async def _run(monkeypatch, script, *, skills, limits=None, execute=None, permissions=None):
    llm = ScriptedLLM(script)
    monkeypatch.setattr(orchestrator.ai_service, "chat_with_tools", llm.chat_with_tools)
    monkeypatch.setattr(orchestrator.ai_service, "chat", _fake_chat())
    monkeypatch.setattr(orchestrator, "maybe_summarize", _identity_summarize)
    monkeypatch.setattr(orchestrator, "report_assistant_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "report_model_call", lambda *a, **k: None)

    calls = []

    async def fake_execute(tool_name, args, **kwargs):
        calls.append((tool_name, args))
        if execute is not None:
            return execute(tool_name, args)
        return {"ok": True, "online": True, "error": None, "item_count": 1, "result": {}}

    monkeypatch.setattr(orchestrator, "execute_agent_tool", fake_execute)

    events = await _collect(orchestrator.run_reaction(
        "用技能查订单", [],
        system_prompt="sys", model_override=None, temperature=0.1, max_tokens=4096,
        max_tool_rounds=6, max_agent_calls=8, disabled_tools=None,
        session_id="", trace_id="", user_id="u1", run_logger=None, provider_name="test",
        limits=limits, stream_final=False,
        user_context=_context(skills, permissions=permissions), with_plan=False,
    ))
    return events, calls


def _fake_chat():
    async def chat(messages, options):
        return "总结"
    return chat


async def _identity_summarize(messages, run_logger, session_id=""):
    return messages


def _steps(events):
    return [data["step"] for event, data in events if event == "step_completed"]


async def test_run_executor_before_load_is_blocked(monkeypatch):
    events, calls = await _run(
        monkeypatch,
        [tool_call("run_skill_executor", {"skill_id": 1, "params": {}}), direct_reply("结束")],
        skills=[_skill(1)],
    )
    assert calls == []
    steps = _steps(events)
    assert steps[0]["status"] == "blocked"
    assert "请先调用 use_skill" in steps[0]["error"]


async def test_read_file_before_load_is_blocked(monkeypatch):
    events, calls = await _run(
        monkeypatch,
        [
            tool_call("read_skill_file", {"skill_id": 1, "path": "references/guide.md"}),
            direct_reply("结束"),
        ],
        skills=[_skill(1)],
    )
    assert calls == []
    steps = _steps(events)
    assert steps[0]["status"] == "blocked"
    assert "请先调用 use_skill" in steps[0]["error"]


async def test_read_file_after_load(monkeypatch):
    def execute(tool_name, args):
        if tool_name == "use_skill":
            return {
                "ok": True, "online": True, "error": None, "item_count": 0,
                "result": {"skill": {"id": 1, "name": "技能1"}, "instructions": "步骤"},
            }
        return {
            "ok": True, "online": True, "error": None, "item_count": 0,
            "result": {"path": args["path"], "content": "参考内容", "size": 4},
        }

    events, calls = await _run(
        monkeypatch,
        [
            tool_call("use_skill", {"skill_id": 1}),
            tool_call("read_skill_file", {"skill_id": 1, "path": "references/guide.md"}),
            direct_reply("完成"),
        ],
        skills=[_skill(1)],
        execute=execute,
    )
    steps = _steps(events)
    assert [step["status"] for step in steps] == ["completed", "completed"]
    assert steps[1]["summary"] == "读取技能文件 references/guide.md"
    assert [name for name, _ in calls] == ["use_skill", "read_skill_file"]


def test_generated_file_footer_is_appended_once():
    files = [{"name": "orders.docx", "url": "/uploads/orders.docx"}]
    text = orchestrator._with_generated_files("已完成", files)
    assert "已完成" in text
    assert "[orders.docx](/uploads/orders.docx)" in text
    again = orchestrator._with_generated_files(text, files)
    assert again == text


async def test_skill_admin_gate(monkeypatch):
    tool = tool_call("create_skill", {"skill_key": "demo", "content": "x"})
    events, calls = await _run(
        monkeypatch, [tool, direct_reply("结束")], skills=[],
    )
    steps = _steps(events)
    assert calls == []
    assert steps[0]["status"] == "blocked"
    assert "没有技能管理权限" in steps[0]["error"]

    events, calls = await _run(
        monkeypatch, [tool, direct_reply("结束")], skills=[],
        permissions={"ai.skill.manage": ["update"]},
    )
    steps = _steps(events)
    assert steps[0]["status"] == "completed"
    assert calls and calls[0][0] == "create_skill"


async def test_run_script_before_load_is_blocked(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_sandbox_enabled", lambda: True)
    events, calls = await _run(
        monkeypatch,
        [
            tool_call("run_skill_script", {"skill_id": 1, "script": "scripts/run.py"}),
            direct_reply("结束"),
        ],
        skills=[_skill(1, has_scripts=True)],
    )
    assert calls == []
    steps = _steps(events)
    assert steps[0]["status"] == "blocked"
    assert "请先调用 use_skill" in steps[0]["error"]


async def test_run_script_after_load(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_sandbox_enabled", lambda: True)

    def execute(tool_name, args):
        if tool_name == "use_skill":
            return {
                "ok": True, "online": True, "error": None, "item_count": 0,
                "result": {"skill": {"id": 1, "name": "技能1"}, "instructions": "步骤"},
            }
        return {
            "ok": True, "online": True, "error": None, "item_count": 0,
            "result": {"exit_code": 0, "stdout": "done", "stderr": "", "duration_ms": 1},
        }

    events, calls = await _run(
        monkeypatch,
        [
            tool_call("use_skill", {"skill_id": 1}),
            tool_call("run_skill_script", {"skill_id": 1, "script": "scripts/run.py", "params": {}}),
            direct_reply("完成"),
        ],
        skills=[_skill(1, has_scripts=True)],
        execute=execute,
    )
    steps = _steps(events)
    assert [step["status"] for step in steps] == ["completed", "completed"]
    assert steps[1]["summary"] == "执行技能脚本 scripts/run.py"
    assert [name for name, _ in calls] == ["use_skill", "run_skill_script"]


async def test_use_skill_then_execute(monkeypatch):
    def execute(tool_name, args):
        if tool_name == "use_skill":
            return {
                "ok": True, "online": True, "error": None, "item_count": 0,
                "result": {"skill": {"id": 1, "name": "技能1"}, "instructions": "步骤"},
            }
        return {"ok": True, "online": True, "error": None, "item_count": 1, "result": {"items": [1]}}

    events, calls = await _run(
        monkeypatch,
        [
            tool_call("use_skill", {"skill_id": 1}),
            tool_call("run_skill_executor", {"skill_id": 1, "params": {"days": 3}}),
            direct_reply("完成"),
        ],
        skills=[_skill(1)],
        execute=execute,
    )
    steps = _steps(events)
    assert [step["status"] for step in steps] == ["completed", "completed"]
    assert steps[0]["capability"] == "skill"
    assert steps[0]["agent_label"] == "订单专员"
    assert [name for name, _ in calls] == ["use_skill", "run_skill_executor"]
    done = next(data for event, data in events if event == "done")
    assert done["stats"]["tools_called"] == ["use_skill", "run_skill_executor"]


async def test_skill_load_limit_blocks_second_load(monkeypatch):
    events, calls = await _run(
        monkeypatch,
        [
            tool_call("use_skill", {"skill_id": 1}),
            tool_call("use_skill", {"skill_id": 2}),
            direct_reply("结束"),
        ],
        skills=[_skill(1), _skill(2)],
        limits={"max_skill_loads": 1},
    )
    steps = _steps(events)
    assert steps[0]["status"] == "completed"
    assert steps[1]["status"] == "blocked"
    assert "加载次数已达上限" in steps[1]["error"]
    assert len(calls) == 1


async def test_skill_without_executor_blocks_run(monkeypatch):
    events, calls = await _run(
        monkeypatch,
        [
            tool_call("use_skill", {"skill_id": 1}),
            tool_call("run_skill_executor", {"skill_id": 1, "params": {}}),
            direct_reply("结束"),
        ],
        skills=[_skill(1, has_executor=False)],
    )
    assert len(calls) == 1
    steps = _steps(events)
    assert steps[1]["status"] == "blocked"
    assert "未绑定执行器" in steps[1]["error"]
