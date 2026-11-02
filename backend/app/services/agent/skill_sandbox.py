"""技能脚本沙箱客户端：通过 UDS（生产）或 HTTP（本地调试）调用独立 sandbox。"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import get_settings
from app.models.agent.skill import AgentSkill
from app.services.agent.errors import AgentError
from app.services.agent.skills import package_skill_folder

logger = logging.getLogger(__name__)


def _sandbox_config() -> Tuple[str, str, str]:
    settings = get_settings()
    return (
        (settings.SKILL_SANDBOX_UDS or "").strip(),
        (settings.SKILL_SANDBOX_URL or "").strip(),
        (settings.SKILL_SANDBOX_TOKEN or "").strip(),
    )


def is_sandbox_enabled() -> bool:
    uds, url, token = _sandbox_config()
    return bool(token and (uds or url))


async def run_skill_script(
    skill: AgentSkill,
    script: str,
    params: Optional[Dict[str, Any]] = None,
    script_args: Optional[list] = None,
    input_files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """把技能目录打包后交给 sandbox 执行脚本；返回 sandbox 原始结果。"""
    if not is_sandbox_enabled():
        raise AgentError("脚本沙箱未配置，无法执行技能脚本")
    uds, url, token = _sandbox_config()
    timeout_s = int(get_settings().SKILL_SCRIPT_TIMEOUT_S or 30)
    package = package_skill_folder(skill)
    headers = {"X-Sandbox-Token": token}
    data = {
        "script": script,
        "params": json.dumps(params or {}, ensure_ascii=False),
        "args": json.dumps(script_args or [], ensure_ascii=False),
        "input_files": json.dumps(input_files or {}, ensure_ascii=False),
        "timeout_s": str(max(1, timeout_s)),
    }
    files = {"package": ("skill.zip", package, "application/zip")}
    try:
        if uds:
            transport = httpx.AsyncHTTPTransport(uds=uds)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://sandbox", timeout=timeout_s + 10
            ) as client:
                response = await client.post("/run", data=data, files=files, headers=headers)
        else:
            async with httpx.AsyncClient(
                base_url=url.rstrip("/"), timeout=timeout_s + 10
            ) as client:
                response = await client.post("/run", data=data, files=files, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("[skill-sandbox] 调用失败: %s", exc)
        raise AgentError(f"技能沙箱不可用：{str(exc)[:200]}") from exc

    if response.status_code != 200:
        detail = ""
        try:
            payload = response.json()
            detail = payload.get("detail") or payload.get("message") or ""
        except ValueError:
            detail = response.text[:200]
        raise AgentError(f"技能沙箱拒绝执行：{detail or response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise AgentError("技能沙箱返回非法响应") from exc
    if not isinstance(payload, dict):
        raise AgentError("技能沙箱返回非法响应")
    return payload
