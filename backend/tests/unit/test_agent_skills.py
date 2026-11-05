"""技能库单测：SKILL.md 解析、提示词索引、工具 schema 与执行器注册表。"""

import asyncio
import base64
import io
import shutil
import zipfile

import pytest

from app.models.agent.skill import AgentSkill
from app.services.agent.context import TeamSkillInfo, UserContext
from app.services.agent.errors import AgentError
from app.services.agent.prompt import build_agent_system_prompt
from app.services.agent import skill_executors
from app.services.agent import skills as skill_service
from app.services.agent.skills import (
    package_skill_folder,
    parse_skill_markdown,
    read_skill_text_file,
    scan_skill_folder,
)
from app.services.assistant.agent_tools import build_agent_tools_schema


def test_parse_skill_markdown_frontmatter_and_body():
    parsed = parse_skill_markdown(
        "---\n"
        "name: 订单交期风险排查\n"
        "description: 用户询问订单交期或延期风险时加载\n"
        "---\n\n"
        "1. 先查订单\n2. 再看齐套\n"
    )
    assert parsed.name == "订单交期风险排查"
    assert parsed.description == "用户询问订单交期或延期风险时加载"
    assert parsed.instructions.startswith("1. 先查订单")


def test_parse_skill_markdown_folded_chomping_description():
    parsed = parse_skill_markdown(
        "---\nname: demo\ndescription: >-\n  第一行\n  第二行\n---\n正文"
    )
    assert parsed.description == "第一行 第二行"


def test_parse_skill_markdown_folded_description():
    parsed = parse_skill_markdown(
        "---\nname: demo\ndescription: >\n  第一行\n  第二行\n---\n正文"
    )
    assert parsed.description == "第一行 第二行"
    assert parsed.instructions == "正文"


@pytest.mark.parametrize("content", [
    "name: demo\ndescription: x\n---\n正文",
    "---\ndescription: x\n---\n正文",
    "---\nname: demo\n---\n正文",
    "---\nname: demo\ndescription: x\n---\n",
])
def test_parse_skill_markdown_rejects_invalid(content):
    with pytest.raises(AgentError):
        parse_skill_markdown(content)


def test_parse_skill_markdown_optional_executor():
    parsed = parse_skill_markdown(
        "---\nname: demo\ndescription: x\nexecutor: orders.risk\n---\n正文"
    )
    assert parsed.executor_name == "orders.risk"


def test_parse_skill_markdown_allows_long_description_and_instructions():
    description = "说明" * 1000
    instructions = "步骤" * 30000
    parsed = parse_skill_markdown(
        f"---\nname: long-skill\ndescription: {description}\n---\n{instructions}"
    )
    assert parsed.description == description
    assert parsed.instructions == instructions


def test_parse_skill_markdown_rejects_over_limit():
    with pytest.raises(AgentError):
        parse_skill_markdown(
            f"---\nname: long-skill\ndescription: {'说' * 2001}\n---\n正文"
        )
    with pytest.raises(AgentError):
        parse_skill_markdown(
            f"---\nname: long-skill\ndescription: x\n---\n{'步' * 60001}"
        )


def test_scan_skill_folder_lists_files(tmp_path):
    folder = tmp_path / "demo-skill"
    (folder / "references").mkdir(parents=True)
    (folder / "scripts").mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: x\n---\n正文", encoding="utf-8"
    )
    (folder / "references" / "guide.md").write_text("guide", encoding="utf-8")
    (folder / "scripts" / "run.py").write_text("print(1)", encoding="utf-8")
    parsed = scan_skill_folder(folder)
    assert parsed.skill_key == "demo-skill"
    assert {item.path for item in parsed.files} == {
        "SKILL.md", "references/guide.md", "scripts/run.py",
    }


def test_scan_skill_folder_rejects_bad_slug(tmp_path):
    folder = tmp_path / "Bad Slug"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: Bad Slug\ndescription: x\n---\n正文", encoding="utf-8"
    )
    with pytest.raises(AgentError):
        scan_skill_folder(folder)


def test_read_skill_text_file_rejects_traversal():
    root = skill_service.builtin_skills_root()
    folder = root / "traversal-test"
    try:
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            "---\nname: traversal-test\ndescription: x\n---\n正文", encoding="utf-8"
        )
        (folder / "references").mkdir()
        (folder / "references" / "guide.md").write_text("guide", encoding="utf-8")
        skill = AgentSkill(
            skill_key="traversal-test", name="traversal-test", description="x",
            instructions="", source="builtin", status="active",
        )
        result = read_skill_text_file(skill, "references/guide.md")
        assert result["content"] == "guide"
        with pytest.raises(AgentError):
            read_skill_text_file(skill, "../../SKILL.md")
    finally:
        if folder.exists():
            shutil.rmtree(folder)


def test_package_skill_folder_contains_directory_contents():
    root = skill_service.builtin_skills_root()
    folder = root / "package-test"
    try:
        (folder / "scripts").mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            "---\nname: package-test\ndescription: x\n---\n正文", encoding="utf-8"
        )
        (folder / "scripts" / "run.py").write_text("print(1)", encoding="utf-8")
        skill = AgentSkill(
            skill_key="package-test", name="package-test", description="x",
            instructions="", source="builtin", status="active",
        )
        data = package_skill_folder(skill)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert set(archive.namelist()) == {"SKILL.md", "scripts/run.py"}
    finally:
        if folder.exists():
            shutil.rmtree(folder)


def _user_context(skills=None) -> UserContext:
    from types import SimpleNamespace

    return UserContext(
        user=SimpleNamespace(id=1, username="u1", display_name="测试用户"),
        role_code="admin",
        permissions={},
        members=[],
        effective_capabilities=set(),
        allowed_tools=set(),
        skills=list(skills or []),
    )


def test_prompt_lists_team_skills_and_rules():
    ctx = _user_context([
        TeamSkillInfo(
            skill_id=12, name="交期排查", description="交期风险时使用",
            agent_id=3, agent_name="订单专员", has_executor=True, executor_name="orders.risk",
        ),
    ])
    prompt = build_agent_system_prompt("base", ctx)
    assert "#12 交期排查" in prompt
    assert "订单专员" in prompt
    assert "含执行器" in prompt
    assert "use_skill" in prompt
    assert "run_skill_executor" in prompt


def test_prompt_states_no_skills():
    prompt = build_agent_system_prompt("base", _user_context())
    assert "无（团队成员未配置技能）" in prompt


def test_prompt_truncates_long_skill_description():
    description = "前" * 300 + "后" * 200
    ctx = _user_context([
        TeamSkillInfo(
            skill_id=1, name="长说明技能", description=description,
            agent_id=1, agent_name="订单专员", has_executor=False,
        ),
    ])
    prompt = build_agent_system_prompt("base", ctx)
    assert "…" in prompt
    assert "后后后" not in prompt


def _skill(skill_id=1, has_executor=False):
    return TeamSkillInfo(
        skill_id=skill_id, name=f"技能{skill_id}", description="说明",
        agent_id=1, agent_name="订单专员", has_executor=has_executor,
    )


def test_tool_schema_contains_skill_tools_only_when_skills_exist():
    base_names = {s["function"]["name"] for s in build_agent_tools_schema(include_order=False)}
    assert "use_skill" not in base_names
    assert "run_skill_executor" not in base_names

    names = {s["function"]["name"] for s in build_agent_tools_schema(
        include_order=False, skills=[_skill(1, has_executor=False)],
    )}
    assert "use_skill" in names
    assert "run_skill_executor" not in names

    names = {s["function"]["name"] for s in build_agent_tools_schema(
        include_order=False, skills=[_skill(1, has_executor=True)],
    )}
    assert {"use_skill", "run_skill_executor"} <= names


def test_admin_skill_tools_only_when_requested():
    names = {s["function"]["name"] for s in build_agent_tools_schema()}
    assert "create_skill" not in names and "install_skill" not in names
    names = {
        s["function"]["name"]
        for s in build_agent_tools_schema(include_skill_admin=True)
    }
    assert {"create_skill", "install_skill", "uninstall_skill"} <= names
    names = {
        s["function"]["name"]
        for s in build_agent_tools_schema(
            include_skill_admin=True, skill_admin_tools={"create_skill"},
        )
    }
    assert "create_skill" in names
    assert "install_skill" not in names and "uninstall_skill" not in names


def test_allowed_skill_admin_tools_from_permission_or_capability():
    from app.services.agent.capabilities import allowed_skill_admin_tools

    all_tools = {"create_skill", "install_skill", "uninstall_skill"}
    assert allowed_skill_admin_tools({"ai.agent.admin": ["update"]}, set()) == all_tools
    assert allowed_skill_admin_tools({}, {"skill.install"}) == {"install_skill"}
    assert allowed_skill_admin_tools({}, {"query.orders"}) == set()


def test_skill_tools_not_filtered_by_capability_allowed_tools():
    names = {s["function"]["name"] for s in build_agent_tools_schema(
        include_order=False, allowed_tools={"call_query_agent"}, skills=[_skill(1, True)],
    )}
    assert {"use_skill", "run_skill_executor"} <= names


def test_register_skill_executor_rejects_duplicate_and_write():
    name = "test.skill.executor.duplicate"

    @skill_executors.register_skill_executor(
        name, "测试执行器", "测试", {"type": "object", "properties": {}},
    )
    async def _executor(params, ctx):
        return {"ok": True}

    with pytest.raises(ValueError):
        skill_executors.register_skill_executor(
            name, "重复", "测试", {"type": "object", "properties": {}},
        )(lambda params, ctx: None)

    with pytest.raises(ValueError):
        skill_executors.register_skill_executor(
            "test.skill.executor.write", "写执行器", "测试", {"type": "object"},
            read_only=False,
        )(lambda params, ctx: None)


def test_run_skill_executor_handles_timeout_and_output_limit():
    name = "test.skill.executor.slow"

    @skill_executors.register_skill_executor(
        name, "慢执行器", "测试", {"type": "object", "properties": {}},
        timeout_s=1.0, max_output_chars=1000,
    )
    async def _slow(params, ctx):
        await asyncio.sleep(5)
        return {}

    executor = skill_executors.get_skill_executor(name)
    outcome = asyncio.run(skill_executors.run_skill_executor(
        executor, {}, skill_executors.SkillExecutorContext(),
    ))
    assert outcome["ok"] is False
    assert "超时" in outcome["error"]

    name2 = "test.skill.executor.big"

    @skill_executors.register_skill_executor(
        name2, "大输出", "测试", {"type": "object", "properties": {}},
        max_output_chars=1000,
    )
    async def _big(params, ctx):
        return {"text": "x" * 5000}

    executor2 = skill_executors.get_skill_executor(name2)
    outcome2 = asyncio.run(skill_executors.run_skill_executor(
        executor2, {}, skill_executors.SkillExecutorContext(),
    ))
    assert outcome2["ok"] is True
    assert outcome2["result"]["_truncated"] is True


def test_install_url_rejects_http_and_private():
    with pytest.raises(AgentError):
        asyncio.run(skill_service._validate_install_url("http://example.com/a.zip"))
    with pytest.raises(AgentError):
        asyncio.run(skill_service._validate_install_url("https://127.0.0.1/a.zip"))
    with pytest.raises(AgentError):
        asyncio.run(skill_service._validate_install_url("https://localhost/a.zip"))


def test_save_skill_artifacts_filters_blocked_suffix(monkeypatch):
    from types import SimpleNamespace

    from app.services.assistant import agent_tools

    class FakeStorage:
        def save(self, content, original_name, mime, namespace):
            return SimpleNamespace(
                name=original_name, size=len(content), mime=mime,
                url=f"/uploads/{original_name}",
            )

    monkeypatch.setattr(agent_tools, "get_storage", lambda: FakeStorage())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("orders.docx", b"docx")
        archive.writestr("evil.exe", b"exe")
        archive.writestr("nested/report.pdf", b"pdf")
    payload = {"artifacts": base64.b64encode(buffer.getvalue()).decode("ascii")}
    files, error = agent_tools._save_skill_artifacts(payload)
    assert error is None
    assert {item["name"] for item in files} == {"orders.docx", "report.pdf"}
