"""技能库 API 集成测试：zip 导入、磁盘同步、预览、启停、删除与绑定。"""

import io
import json
import zipfile
from pathlib import Path

from app.core.database import AsyncSessionLocal
from app.models.basicdata.user import SysUser
from app.services.agent.context import load_user_context
from app.services.agent.skill_executors import register_skill_executor
from app.services.assistant.agent_tools import execute_agent_tool
from tests.conftest import (
    SKILLS_TEST_BUILTIN,
    get_user_id_by_username,
    login,
)

SKILLS = "/api/v1/agents/admin/skills"
AGENTS = "/api/v1/agents/admin/agents"
TEAM = "/api/v1/agents/me/team"


@register_skill_executor(
    "pytest.skill.echo",
    "回显执行器",
    "测试用只读执行器",
    {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "关键字"}},
        "required": ["keyword"],
    },
    required_capabilities=("query.orders",),
)
async def _echo_executor(params, ctx):
    return {"items": [{"keyword": params.get("keyword", "")}]}


def _skill_md(name="order-risk", description="交期风险时加载", executor=None):
    executor_line = f"executor: {executor}\n" if executor else ""
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"{executor_line}"
        "---\n\n"
        "1. 查询订单\n2. 分析风险\n"
    )


def _zip_bytes(files: dict, top: str = "order-risk") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for relative, content in files.items():
            archive.writestr(f"{top}/{relative}" if top else relative, content)
    return buffer.getvalue()


async def _import_skill(client, headers, data: bytes):
    return await client.post(
        f"{SKILLS}/import",
        files={"file": ("skill.zip", data, "application/zip")},
        headers=headers,
    )


async def _create_agent(client, headers, name, skill_ids):
    r = await client.post(
        AGENTS,
        json={"name": name, "capabilities": ["query.orders"], "skill_ids": skill_ids},
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0, r.text
    return body["data"]


async def test_import_preview_status_and_delete(client):
    headers = await login(client, "admin")
    data = _zip_bytes({
        "SKILL.md": _skill_md(),
        "references/guide.md": "# 参考\n先查订单再分析。",
        "scripts/run.py": "print('ok')",
    })
    r = await _import_skill(client, headers, data)
    body = r.json()
    assert body["code"] == 0, r.text
    skill = body["data"]
    assert skill["skill_key"] == "order-risk"
    assert skill["source"] == "imported"
    assert skill["file_count"] == 3
    assert skill["has_scripts"] is True
    assert skill["instructions"].startswith("1. 查询订单")
    assert skill["script_execution_available"] is False

    duplicate = await _import_skill(client, headers, data)
    assert duplicate.json()["code"] == 400
    assert "已存在" in duplicate.json()["message"]

    r = await client.get(SKILLS, headers=headers)
    assert r.json()["code"] == 0
    assert any(item["skill_key"] == "order-risk" for item in r.json()["data"]["items"])

    r = await client.get(
        f"{SKILLS}/{skill['id']}/file",
        params={"path": "references/guide.md"}, headers=headers,
    )
    assert r.json()["code"] == 0, r.text
    assert "先查订单" in r.json()["data"]["content"]

    r = await client.get(
        f"{SKILLS}/{skill['id']}/file",
        params={"path": "../SKILL.md"}, headers=headers,
    )
    assert r.json()["code"] == 400

    r = await client.put(
        f"{SKILLS}/{skill['id']}/status",
        json={"status": "disabled"}, headers=headers,
    )
    assert r.json()["code"] == 0, r.text
    assert r.json()["data"]["status"] == "disabled"

    r = await client.delete(f"{SKILLS}/{skill['id']}", headers=headers)
    assert r.json()["code"] == 0, r.text
    assert not (Path(SKILLS_TEST_BUILTIN).parent / "imported" / "order-risk").exists()
    r = await client.get(f"{SKILLS}/{skill['id']}", headers=headers)
    assert r.json()["code"] == 404


def _write_builtin_skill(folder: str, description: str):
    path = Path(SKILLS_TEST_BUILTIN) / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(_skill_md(folder, description), encoding="utf-8")
    return path


async def test_sync_builtin_folder_and_removal(client):
    headers = await login(client, "admin")
    folder = _write_builtin_skill("builtin-demo", "内置说明")

    r = await client.post(f"{SKILLS}/sync", headers=headers)
    body = r.json()
    assert body["code"] == 0, r.text
    assert body["data"]["synced"] >= 1

    r = await client.get(SKILLS, params={"source": "builtin"}, headers=headers)
    item = next(i for i in r.json()["data"]["items"] if i["skill_key"] == "builtin-demo")
    assert item["source"] == "builtin"

    (folder / "SKILL.md").write_text(_skill_md("builtin-demo", "更新后的说明"), encoding="utf-8")
    r = await client.post(f"{SKILLS}/sync", headers=headers)
    assert r.json()["code"] == 0
    r = await client.get(f"{SKILLS}/{item['id']}", headers=headers)
    assert "更新后的说明" in r.json()["data"]["description"]

    r = await client.delete(f"{SKILLS}/{item['id']}", headers=headers)
    assert r.json()["code"] == 400
    assert "内置技能不能删除" in r.json()["message"]

    import shutil
    shutil.rmtree(folder)
    r = await client.post(f"{SKILLS}/sync", headers=headers)
    assert r.json()["code"] == 0
    r = await client.get(f"{SKILLS}/{item['id']}", headers=headers)
    assert r.json()["code"] == 404


async def test_import_rejects_bad_zips(client):
    headers = await login(client, "admin")

    r = await _import_skill(client, headers, _zip_bytes({"SKILL.md": _skill_md()}, top=""))
    assert r.json()["code"] == 0, r.text

    r = await _import_skill(client, headers, _zip_bytes({"README.md": "x"}))
    assert r.json()["code"] == 400
    assert "SKILL.md" in r.json()["message"]

    r = await _import_skill(client, headers, _zip_bytes({"SKILL.md": _skill_md()}, top="Bad Slug"))
    assert r.json()["code"] == 400

    r = await _import_skill(client, headers, _zip_bytes({
        "SKILL.md": _skill_md("bad-executor", executor="nope"),
    }))
    assert r.json()["code"] == 400
    assert "未知执行器" in r.json()["message"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.txt", "x")
        archive.writestr("ok/SKILL.md", _skill_md())
    r = await _import_skill(client, headers, buffer.getvalue())
    assert r.json()["code"] == 400


async def test_agent_bind_skill_and_delete_unbinds(client):
    admin_headers = await login(client, "admin")
    r = await _import_skill(client, admin_headers, _zip_bytes({"SKILL.md": _skill_md()}))
    skill = r.json()["data"]

    agent = await _create_agent(client, admin_headers, "技能订单查询员", [skill["id"]])
    assert agent["skill_count"] == 1

    user_headers = await login(client, "qa_mgr")
    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=user_headers)
    assert r.json()["code"] == 0, r.text
    r = await client.get(TEAM, headers=user_headers)
    item = next(i for i in r.json()["data"]["items"] if i["id"] == agent["id"])
    assert item["skills"][0]["skill_key"] == "order-risk"

    r = await client.delete(f"{SKILLS}/{skill['id']}", headers=admin_headers)
    assert r.json()["code"] == 0, r.text
    r = await client.get(AGENTS, headers=admin_headers)
    agent_row = next(i for i in r.json()["data"]["items"] if i["id"] == agent["id"])
    assert agent_row["skill_count"] == 0


async def test_execute_skill_reads_disk_and_registered_executor(client):
    admin_headers = await login(client, "admin")
    data = _zip_bytes({
        "SKILL.md": _skill_md("executable-skill", executor="pytest.skill.echo"),
        "references/guide.md": "先查订单，再执行。",
    })
    r = await _import_skill(client, admin_headers, data)
    skill = r.json()["data"]
    agent = await _create_agent(client, admin_headers, "技能执行员", [skill["id"]])

    user_headers = await login(client, "qa_mgr")
    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=user_headers)
    assert r.json()["code"] == 0, r.text

    user_id = await get_user_id_by_username("qa_mgr")
    async with AsyncSessionLocal() as session:
        user = await session.get(SysUser, user_id)
        ctx = await load_user_context(session, user, use_cache=False)
        loaded = await execute_agent_tool(
            "use_skill", {"skill_id": skill["id"]}, db=session, user_context=ctx,
        )
        assert loaded["ok"], loaded
        assert loaded["result"]["instructions"].startswith("1. 查询订单")
        assert any(item["path"] == "references/guide.md" for item in loaded["result"]["files"])
        assert loaded["result"]["executor"]["parameters"]["properties"]["keyword"]

        file_result = await execute_agent_tool(
            "read_skill_file",
            {"skill_id": skill["id"], "path": "references/guide.md"},
            db=session, user_context=ctx,
        )
        assert file_result["ok"], file_result
        assert "先查订单" in file_result["result"]["content"]

        traversal = await execute_agent_tool(
            "read_skill_file",
            {"skill_id": skill["id"], "path": "../../SKILL.md"},
            db=session, user_context=ctx,
        )
        assert traversal["ok"] is False

        run = await execute_agent_tool(
            "run_skill_executor",
            {"skill_id": skill["id"], "params": {"keyword": "HJ-1"}},
            db=session, user_context=ctx,
        )
        assert run["ok"], run
        assert run["result"]["items"] == [{"keyword": "HJ-1"}]


async def test_create_and_uninstall_skill_tool(client):
    headers = await login(client, "admin")
    user_id = await get_user_id_by_username("admin")
    content = (
        "---\nname: created-demo\ndescription: 测试创建技能\n---\n\n"
        "# 使用步骤\n1. 先查询数据\n2. 再生成结论\n"
    )
    async with AsyncSessionLocal() as session:
        user = await session.get(SysUser, user_id)
        ctx = await load_user_context(session, user, use_cache=False)
        created = await execute_agent_tool(
            "create_skill",
            {
                "skill_key": "created-demo",
                "content": content,
                "files": {"references/guide.md": "# 参考\n"},
            },
            db=session, user_context=ctx,
        )
        assert created["ok"], created
        assert created["result"]["skill_key"] == "created-demo"
        await session.commit()

        r = await client.get(f"{SKILLS}/{created['result']['skill_id']}", headers=headers)
        assert r.json()["code"] == 0
        assert any(item["path"] == "references/guide.md" for item in r.json()["data"]["files"])

        removed = await execute_agent_tool(
            "uninstall_skill",
            {"skill_id": created["result"]["skill_id"]},
            db=session, user_context=ctx,
        )
        assert removed["ok"], removed
        await session.commit()

    r = await client.get(f"{SKILLS}/{created['result']['skill_id']}", headers=headers)
    assert r.json()["code"] == 404


async def test_skill_admin_tools_require_permission(client):
    user_id = await get_user_id_by_username("qa_mgr")
    async with AsyncSessionLocal() as session:
        user = await session.get(SysUser, user_id)
        ctx = await load_user_context(session, user, use_cache=False)
        result = await execute_agent_tool(
            "create_skill",
            {"skill_key": "no-perm", "content": "---\nname: x\ndescription: x\n---\n正文"},
            db=session, user_context=ctx,
        )
        assert result["ok"] is False
        assert "没有技能管理权限" in result["error"]


async def test_uninstall_pack_removes_children_from_sidecar(client):
    headers = await login(client, "admin")
    user_id = await get_user_id_by_username("admin")
    async with AsyncSessionLocal() as session:
        user = await session.get(SysUser, user_id)
        ctx = await load_user_context(session, user, use_cache=False)
        meta = await execute_agent_tool(
            "create_skill",
            {
                "skill_key": "pack-demo",
                "content": "---\nname: pack-demo\ndescription: 测试专家包\n---\n主技能",
                "files": {
                    "_pack.json": json.dumps({"pack": "pack-demo", "children": ["child-demo"]}),
                },
            },
            db=session, user_context=ctx,
        )
        child = await execute_agent_tool(
            "create_skill",
            {
                "skill_key": "child-demo",
                "content": "---\nname: child-demo\ndescription: 子技能\n---\n子技能",
            },
            db=session, user_context=ctx,
        )
        assert meta["ok"] and child["ok"]
        await session.commit()

        removed = await execute_agent_tool(
            "uninstall_skill", {"skill_key": "pack-demo"},
            db=session, user_context=ctx,
        )
        assert removed["ok"], removed
        assert {item["skill_key"] for item in removed["result"]["removed"]} == {
            "pack-demo", "child-demo",
        }
        await session.commit()

    for skill_id in (meta["result"]["skill_id"], child["result"]["skill_id"]):
        r = await client.get(f"{SKILLS}/{skill_id}", headers=headers)
        assert r.json()["code"] == 404


async def test_create_skill_scripts_require_explicit_flag(client):
    user_id = await get_user_id_by_username("admin")
    content = "---\nname: script-demo\ndescription: 测试脚本开关\n---\n正文"
    async with AsyncSessionLocal() as session:
        user = await session.get(SysUser, user_id)
        ctx = await load_user_context(session, user, use_cache=False)
        denied = await execute_agent_tool(
            "create_skill",
            {
                "skill_key": "script-demo",
                "content": content,
                "files": {"scripts/run.py": "print(1)"},
            },
            db=session, user_context=ctx,
        )
        assert denied["ok"] is False
        assert "allow_scripts" in denied["error"]

        allowed = await execute_agent_tool(
            "create_skill",
            {
                "skill_key": "script-demo",
                "content": content,
                "files": {"scripts/run.py": "print(1)"},
                "allow_scripts": True,
            },
            db=session, user_context=ctx,
        )
        assert allowed["ok"], allowed
        await execute_agent_tool(
            "uninstall_skill",
            {"skill_key": "script-demo"},
            db=session, user_context=ctx,
        )


async def test_run_skill_script_tool_with_fake_sandbox(monkeypatch, client):
    from app.services.assistant import agent_tools

    admin_headers = await login(client, "admin")
    data = _zip_bytes({
        "SKILL.md": _skill_md("script-skill"),
        "scripts/run.py": "print('ok')",
    })
    r = await _import_skill(client, admin_headers, data)
    skill = r.json()["data"]
    agent = await _create_agent(client, admin_headers, "技能脚本员", [skill["id"]])

    user_headers = await login(client, "qa_mgr")
    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=user_headers)
    assert r.json()["code"] == 0, r.text

    async def fake_run(skill_row, script, params, script_args, input_files):
        return {
            "ok": True, "exit_code": 0,
            "stdout": json.dumps({
                "params": params, "args": script_args,
                "input_files": sorted(input_files),
            }, ensure_ascii=False),
            "stderr": "", "duration_ms": 1, "truncated": False,
        }

    monkeypatch.setattr(agent_tools, "run_sandbox_script", fake_run)
    user_id = await get_user_id_by_username("qa_mgr")
    async with AsyncSessionLocal() as session:
        user = await session.get(SysUser, user_id)
        ctx = await load_user_context(session, user, use_cache=False)
        run = await execute_agent_tool(
            "run_skill_script",
            {
                "skill_id": skill["id"], "script": "scripts/run.py",
                "params": {"a": 1}, "args": ["--title", "测试"],
                "input_files": {"orders.md": "# 测试"},
            },
            db=session, user_context=ctx,
        )
        assert run["ok"], run
        assert json.loads(run["result"]["stdout"]) == {
            "params": {"a": 1}, "args": ["--title", "测试"],
            "input_files": ["orders.md"],
        }

        wrong = await execute_agent_tool(
            "run_skill_script",
            {"skill_id": skill["id"], "script": "references/nope.md", "params": {}},
            db=session, user_context=ctx,
        )
        assert wrong["ok"] is False
