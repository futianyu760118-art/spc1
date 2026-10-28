"""订单外部写接口共享辅助。"""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.user import SysUser


async def resolve_operator(db: AsyncSession, request: Request) -> str:
    """审计操作人：SPC 用户优先；Hub caller 次之；最后回退 order-agent:runId。"""
    op_user_id = (request.headers.get("X-Operator-User-Id") or "").strip()
    if op_user_id.isdigit():
        user = (
            await db.execute(select(SysUser).where(SysUser.id == int(op_user_id)))
        ).scalar_one_or_none()
        name = (user.display_name or user.username) if user else f"user:{op_user_id}"
        return f"{name}（智能体）"
    hub_caller_id = (request.headers.get("X-Hub-Caller-User-Id") or "").strip()
    if hub_caller_id:
        return f"hub:{hub_caller_id}"[:64]
    run_id = request.headers.get("X-Agent-Run-Id", "")
    return f"order-agent:{run_id}" if run_id else "order-agent"
