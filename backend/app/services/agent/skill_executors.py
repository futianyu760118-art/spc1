"""技能执行器注册表：工程师注册只读执行体，管理员在技能库中选用。

执行器不是上传脚本：它随后端代码发布、经过代码评审，只能以只读方式复用既有权限/数据范围服务。
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.agent.errors import AgentError

logger = logging.getLogger(__name__)

_EXECUTOR_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,63}$")
_EXECUTORS: Dict[str, "SkillExecutorDef"] = {}


@dataclass(frozen=True)
class SkillExecutorContext:
    """执行器运行上下文：只读执行器必须复用既有权限/数据范围服务。"""

    db: Any = None
    user_context: Any = None
    trace_id: str = ""
    task_id: str = ""
    step_id: int = 0
    session_id: str = ""


@dataclass(frozen=True)
class SkillExecutorDef:
    name: str
    display_name: str
    description: str
    parameters: Dict[str, Any]
    required_capabilities: Tuple[str, ...] = field(default_factory=tuple)
    timeout_s: float = 30.0
    max_output_chars: int = 8000
    read_only: bool = True
    execute: Optional[Callable] = None

    def to_catalog_item(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "parameters": self.parameters,
            "required_capabilities": list(self.required_capabilities),
            "timeout_s": self.timeout_s,
            "max_output_chars": self.max_output_chars,
            "read_only": self.read_only,
        }


def register_skill_executor(
    name: str,
    display_name: str,
    description: str,
    parameters: Dict[str, Any],
    *,
    required_capabilities: Tuple[str, ...] = (),
    timeout_s: float = 30.0,
    max_output_chars: int = 8000,
    read_only: bool = True,
):
    """装饰器：注册只读技能执行器；重名或写执行器直接报错。"""

    if not _EXECUTOR_NAME_RE.match(name or ""):
        raise ValueError(f"非法执行器名：{name}（需字母开头，仅字母/数字/_.-，2-64 字符）")
    if not read_only:
        raise ValueError(f"执行器 {name} 必须声明 read_only=True（写操作走能力 + 写确认）")
    if not isinstance(parameters, dict):
        raise ValueError(f"执行器 {name} 的 parameters 必须是 JSON Schema 对象")
    if name in _EXECUTORS:
        raise ValueError(f"执行器重复注册：{name}")

    def decorator(func: Callable):
        _EXECUTORS[name] = SkillExecutorDef(
            name=name,
            display_name=display_name or name,
            description=description or "",
            parameters=parameters,
            required_capabilities=tuple(required_capabilities or ()),
            timeout_s=max(1.0, min(float(timeout_s), 120.0)),
            max_output_chars=max(1000, min(int(max_output_chars), 40000)),
            read_only=True,
            execute=func,
        )
        logger.info("Skill executor registered: %s", name)
        return func

    return decorator


def get_skill_executor(name: str) -> Optional[SkillExecutorDef]:
    return _EXECUTORS.get(name)


def list_skill_executors() -> List[SkillExecutorDef]:
    return list(_EXECUTORS.values())


def executor_catalog() -> List[dict]:
    return [executor.to_catalog_item() for executor in _EXECUTORS.values()]


def validate_executor_for_member(executor: SkillExecutorDef, member: Any) -> Optional[str]:
    """校验技能所属智能体具备执行器声明的能力；合法返回 None。"""
    if member is None:
        return "技能所属智能体不在你的团队中"
    owned = set(getattr(member, "capabilities", []) or [])
    missing = [code for code in executor.required_capabilities if code not in owned]
    if missing:
        return f"执行器需要能力 {'、'.join(missing)}，技能所属智能体不具备"
    return None


def _limit_output(result: Any, max_chars: int) -> Any:
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"error": "执行器返回值无法序列化"}
    if len(text) <= max_chars:
        return result
    return {"_truncated": True, "preview": text[:max_chars]}


async def run_skill_executor(
    executor: SkillExecutorDef, params: Dict[str, Any], ctx: SkillExecutorContext
) -> Dict[str, Any]:
    """执行只读执行器：统一超时、异常与输出上限，绝不抛错。"""
    if executor.execute is None:
        return {"ok": False, "error": "执行器未实现"}
    if not isinstance(params, dict):
        return {"ok": False, "error": "params 必须是对象"}
    try:
        result = await asyncio.wait_for(
            executor.execute(params, ctx), timeout=executor.timeout_s
        )
    except asyncio.TimeoutError:
        return {"ok": False, "error": f"执行器执行超时（{executor.timeout_s:g}s）"}
    except AgentError as exc:
        return {"ok": False, "error": exc.message}
    except Exception as exc:
        logger.exception("[skill-executor] %s 执行失败", executor.name)
        return {"ok": False, "error": f"执行器执行失败：{str(exc)[:200]}"}
    if not isinstance(result, dict):
        result = {"result": result}
    return {"ok": True, "result": _limit_output(result, executor.max_output_chars)}
