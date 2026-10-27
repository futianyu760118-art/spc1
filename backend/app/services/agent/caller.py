"""caller 元数据构造：只允许 PDF 五个字段，不含任何令牌。"""

from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.models.agent.agent import Agent
from app.models.basicdata.user import SysUser


def user_id_value(user: Optional[SysUser]) -> Optional[str]:
    if user is None:
        return None
    field = (get_settings().GATEWAY_CALLER_USER_ID_FIELD or "emp_code").strip()
    value = getattr(user, field, None)
    return None if value is None or str(value).strip() == "" else str(value).strip()


def build_caller(
    *,
    user: Optional[SysUser],
    agent: Optional[Agent],
    task_no: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    caller = {
        "systemId": get_settings().AEOS_SYSTEM_ID or "",
        "agentId": agent.agent_no if agent else "",
        "userId": user_id_value(user) or "",
        "taskId": (task_no or "").strip(),
        "traceId": (trace_id or "").strip(),
    }
    return {key: value for key, value in caller.items() if value}
