"""主管/管理员配置智能体能力与数据范围，含不越权校验与审计。"""

import logging
from typing import Dict, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent.agent import Agent, AgentConfigLog
from app.models.basicdata.user import SysUser
from app.services.agent import cache
from app.services.agent.capabilities import ALL_CONFIGURABLE_CODES
from app.services.agent.context import AgentContext
from app.services.agent.errors import AgentError
from app.services.agent.notify import notify_user

logger = logging.getLogger(__name__)


DEFAULT_POLICY = {
    "granted": [],
    "disabled": [],
}

class PolicyError(AgentError):
    pass


def normalize_policy(policy: Optional[dict]) -> dict:
    value = dict(policy or {})
    return {
        "granted": sorted({str(x) for x in (value.get("granted") or []) if x}),
        "disabled": sorted({str(x) for x in (value.get("disabled") or []) if x}),
    }


def _validate_codes(codes: Set[str], field: str) -> None:
    invalid = codes - ALL_CONFIGURABLE_CODES
    if invalid:
        raise PolicyError(f"{field} 含不可配置能力：{', '.join(sorted(invalid))}", 400)


async def update_agent_policy(
    db: AsyncSession,
    *,
    operator_ctx: AgentContext,
    target_agent: Agent,
    granted: Optional[List[str]] = None,
    disabled: Optional[List[str]] = None,
    reason: str = "",
    is_admin: bool = False,
) -> dict:
    """校验并写入目标智能体策略；成功返回归一化后的策略。"""
    if operator_ctx.role_code == "supplier":
        raise PolicyError("供应商用户不能配置智能体", 403)
    if operator_ctx.agent.status != "active":
        raise PolicyError("当前智能体已禁用", 403)

    if is_admin:
        # 管理员默认全量能力；管理员自身能力仍作为授予上限
        grant_ceiling = set(operator_ctx.effective_capabilities) or set(ALL_CONFIGURABLE_CODES)
    else:
        if target_agent.parent_agent_id != operator_ctx.agent.id:
            raise PolicyError("只能配置直属子智能体", 403)
        grant_ceiling = set(operator_ctx.effective_capabilities)

    policy = normalize_policy(target_agent.capability_policy)
    if granted is not None:
        granted_set = {str(x) for x in granted if x}
        _validate_codes(granted_set, "granted")
        if not granted_set <= grant_ceiling:
            raise PolicyError("授予能力超出当前可授权范围", 403)
        policy["granted"] = sorted(granted_set)
    if disabled is not None:
        disabled_set = {str(x) for x in disabled if x}
        _validate_codes(disabled_set, "disabled")
        policy["disabled"] = sorted(disabled_set)

    old_policy = target_agent.capability_policy or {}
    target_agent.capability_policy = policy
    target_agent.config_version = int(target_agent.config_version or 1) + 1
    db.add(AgentConfigLog(
        agent_id=target_agent.id,
        changed_by_user_id=int(operator_ctx.user.id),
        old_policy=old_policy,
        new_policy=policy,
        reason=(reason or "")[:2000] or None,
    ))
    cache.invalidate_agent(target_agent.id)
    await db.flush()

    target_user = await db.get(SysUser, target_agent.user_id)
    if target_user:
        await notify_user(
            db,
            user_id=target_user.id,
            title="[智能体配置]你的智能体能力已更新",
            content=f"操作人：{operator_ctx.user.display_name or operator_ctx.user.username}；配置版本 {target_agent.config_version}",
            notif_type="agent_config",
            ref_type="agent",
            ref_id=target_agent.id,
            sender_id=operator_ctx.user.id,
            sender_name=operator_ctx.user.display_name or operator_ctx.user.username,
        )
    return policy
