"""技能沙箱核心逻辑单测：包校验、路径安全与子进程执行（不依赖 Docker）。"""

import asyncio
import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sandbox import app as sandbox_app  # noqa: E402


def _zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_normalize_name_rejects_traversal():
    assert sandbox_app._normalize_name("scripts/run.py") == "scripts/run.py"
    assert sandbox_app._normalize_name("__MACOSX/x") is None
    with pytest.raises(HTTPException):
        sandbox_app._normalize_name("../evil.py")
    with pytest.raises(HTTPException):
        sandbox_app._normalize_name("/etc/passwd")


def test_extract_package_requires_skill_md(tmp_path):
    with pytest.raises(HTTPException):
        sandbox_app._extract_package(_zip({"scripts/run.py": "print(1)"}), tmp_path)


def test_extract_package_writes_files(tmp_path):
    data = _zip({"SKILL.md": "---\nname: demo\ndescription: x\n---\n正文", "scripts/run.py": "print(1)"})
    sandbox_app._extract_package(data, tmp_path)
    assert (tmp_path / "SKILL.md").is_file()
    assert (tmp_path / "scripts" / "run.py").is_file()


def test_write_input_files_and_reject_skill_overwrite(tmp_path):
    sandbox_app._write_input_files(tmp_path, {"orders.md": "# 订单"})
    assert (tmp_path / "orders.md").read_text(encoding="utf-8") == "# 订单"
    with pytest.raises(HTTPException):
        sandbox_app._write_input_files(tmp_path, {"scripts/run.py": "x"})
    with pytest.raises(HTTPException):
        sandbox_app._write_input_files(tmp_path, {"../evil.md": "x"})


async def test_execute_python_script_with_stdin(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("import sys\nprint(sys.stdin.read().strip())", encoding="utf-8")
    result = await sandbox_app._execute(
        [sys.executable, str(script)], script, tmp_path, '{"a": 1}', 10,
    )
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == '{"a": 1}'
