#!/usr/bin/env python3
"""将指定盘点单号的状态强制设置为已取消 (cancelled)。

用法（在 backend/ 目录下运行）：
    python cancel_inventory_checks.py

注意：本脚本会绕过"已完结不可取消"的业务规则，对所有目标单据一律置为 cancelled。
"""

import asyncio
from pathlib import Path
import sys

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.material.inventory_check import StockCheck


TARGET_CHECK_NOS = [
    "PD20260716-003",
    "PD20260716-002",
    "PD20260716-001",
    "PD20260714-003",
]

NEW_STATUS = "cancelled"


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StockCheck).where(StockCheck.check_no.in_(TARGET_CHECK_NOS))
        )
        rows = result.scalars().all()

        if not rows:
            print(f"未找到任何匹配的盘点单: {TARGET_CHECK_NOS}")
            return

        found_nos = {r.check_no for r in rows}
        missing = set(TARGET_CHECK_NOS) - found_nos
        if missing:
            print(f"警告: 以下单号在数据库中不存在: {sorted(missing)}")

        updated = []
        for row in rows:
            before = row.status
            row.status = NEW_STATUS
            updated.append((row.check_no, before))
            print(f"  {row.check_no}  {before} -> {NEW_STATUS}")

        await session.commit()

        print("\n========== 结果 ==========")
        for no, before in updated:
            print(f"  {no}: {before} -> {NEW_STATUS}")
        print(f"共更新 {len(updated)} 张盘点单。")


if __name__ == "__main__":
    asyncio.run(main())