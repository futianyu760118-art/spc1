"""上线前数据范围 dry-run：按用户输出有效组织范围与订单/物料/品质可见量。

用法（backend 目录）:
  python scripts/agent_scope_dry_run.py --username manager01
  python scripts/agent_scope_dry_run.py --user-id 12 --sample 10
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.basicdata.user import SysUser  # noqa: E402
from app.models.exception.quality_issue import QualityIssue  # noqa: E402
from app.models.material.kitting import KittingResult  # noqa: E402
from app.models.order.sale_order import SaleOrder  # noqa: E402
from app.services.agent.context import load_agent_context  # noqa: E402


async def _resolve_user(db, username: str, user_id: int):
    if user_id:
        return await db.get(SysUser, int(user_id))
    return (await db.execute(
        select(SysUser).where(SysUser.username == username)
    )).scalars().first()


async def dry_run(username: str, user_id: int, sample: int) -> dict:
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(db, username, user_id)
        if not user:
            raise SystemExit(f"用户不存在: username={username} user_id={user_id}")
        ctx = await load_agent_context(db, user, use_cache=False)
        scope = ctx.scope
        order_cond = scope.order_condition()
        order_total = int((await db.execute(
            select(func.count()).select_from(SaleOrder).where(order_cond)
        )).scalar() or 0)
        sample_orders = (await db.execute(
            select(SaleOrder.order_no).where(order_cond).order_by(SaleOrder.id.desc()).limit(sample)
        )).scalars().all()
        kitting_total = int((await db.execute(
            select(func.count()).select_from(KittingResult).where(
                KittingResult.is_deleted == 0,
                KittingResult.demand_no.in_(scope.visible_order_no_select()),
            )
        )).scalar() or 0)
        quality_total = int((await db.execute(
            select(func.count()).select_from(QualityIssue).where(
                QualityIssue.is_deleted == False,  # noqa: E712
                scope.quality_condition(),
            )
        )).scalar() or 0)
        return {
            "user": {"id": user.id, "username": user.username, "emp_code": user.emp_code},
            "agent": {"id": ctx.agent.id, "status": ctx.agent.status},
            "scope": {
                "summary": scope.summary(),
                "org_ids": sorted(scope.org_ids),
                "org_names": sorted(scope.org_names),
                "member_usernames": sorted(scope.member_usernames),
                "member_names": sorted(scope.member_names),
            },
            "visible": {
                "orders": order_total,
                "kitting_results": kitting_total,
                "quality_issues": quality_total,
                "sample_orders": sample_orders,
            },
            "effective_capabilities": sorted(ctx.effective_capabilities),
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="智能体数据范围 dry-run")
    parser.add_argument("--username", default="")
    parser.add_argument("--user-id", type=int, default=0)
    parser.add_argument("--sample", type=int, default=5)
    args = parser.parse_args()
    if not args.username and not args.user_id:
        parser.error("必须提供 --username 或 --user-id")
    result = await dry_run(args.username, args.user_id, args.sample)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
