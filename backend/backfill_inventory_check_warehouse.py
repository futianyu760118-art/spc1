#!/usr/bin/env python3
"""老盘点单按仓库拆行回填脚本。

将 wh_id IS NULL 的老明细行，按 scm_inventory 当前库存填充仓库信息。
- 1 仓库：UPDATE 原行写 wh_id/wh_code/wh_name
- ≥2 仓库：UPDATE 原行（库存最大的仓库）+ INSERT 新行（其余仓库）

用法（在 backend/ 目录下）：
    python backfill_inventory_check_warehouse.py <订单号> [<订单号>...] [--apply]

不带 --apply = 干跑（只打印不写库）；--apply 才真正提交。
"""

import sys
import asyncio
from collections import defaultdict
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.material.inventory_check import StockCheck, StockCheckItem


# ---------------------------------------------------------------------------
# DB 查询
# ---------------------------------------------------------------------------

async def _load_checks(db: AsyncSession, order_nos: list[str]) -> list[StockCheck]:
    """按 order_no 查盘点单头，跳过 cancelled。"""
    result = await db.execute(
        select(StockCheck)
        .where(StockCheck.order_no.in_(order_nos))
        .order_by(StockCheck.order_no, StockCheck.check_date)
    )
    return [r for r in result.scalars().all() if r.status != "cancelled"]


async def _load_old_items(db: AsyncSession, check_ids: list[int]) -> list[StockCheckItem]:
    """查 wh_id IS NULL 且 material_id IS NOT NULL 的老明细行。"""
    result = await db.execute(
        select(StockCheckItem)
        .where(
            StockCheckItem.check_id.in_(check_ids),
            StockCheckItem.wh_id.is_(None),
            StockCheckItem.material_id.isnot(None),
        )
        .order_by(StockCheckItem.check_id, StockCheckItem.material_id)
    )
    return list(result.scalars().all())


async def _get_warehouse_map(
    db: AsyncSession, material_ids: set[int]
) -> dict[int, list[dict]]:
    """查 scm_inventory，按 material_id 聚合仓库信息。

    返回 {material_id: [{"wh_id": int, "wh_code": str, "wh_name": str,
                          "qty": Decimal, "updated_at": datetime}, ...]}
    按 qty_on_hand 降序排列。
    """
    if not material_ids:
        return {}
    result = await db.execute(
        text("""
            SELECT material_id, wh_id,
                   MAX(wh_code) AS wh_code,
                   MAX(wh_name) AS wh_name,
                   COALESCE(SUM(qty_on_hand), 0) AS qty,
                   MAX(updated_at) AS updated_at
            FROM scm_inventory
            WHERE material_id = ANY(:mids)
            GROUP BY material_id, wh_id
            ORDER BY material_id, qty DESC
        """),
        {"mids": list(material_ids)},
    )
    wh_map: dict[int, list[dict]] = defaultdict(list)
    for r in result.all():
        wh_map[int(r.material_id)].append({
            "wh_id": int(r.wh_id),
            "wh_code": r.wh_code or "",
            "wh_name": r.wh_name or f"WH#{r.wh_id}",
            "qty": float(r.qty or 0),
            "updated_at": r.updated_at,
        })
    return wh_map


# ---------------------------------------------------------------------------
# 回填逻辑
# ---------------------------------------------------------------------------

async def _backfill_check(
    db: AsyncSession,
    check: StockCheck,
    old_items: list[StockCheckItem],
    wh_map: dict[int, list[dict]],
) -> dict:
    """处理一张盘点单的老明细，返回统计。"""
    stats = {"single": 0, "multi_update": 0, "multi_insert": 0, "no_stock": 0, "guard_skip": 0}
    # 同 check 内 material_id 出现次数（安全护栏）
    mat_count: dict[int, int] = defaultdict(int)
    for item in old_items:
        mid = int(item.material_id)
        mat_count[mid] += 1

    for item in old_items:
        mid = int(item.material_id)
        whs = wh_map.get(mid, [])

        # 安全护栏：同 check 内同一 material_id 有多行老明细
        if mat_count[mid] > 1:
            stats["guard_skip"] += 1
            print(f"    ⚠ 跳过 id={item.id} material_id={mid}：同单内存在多行老明细")
            continue

        if not whs:
            # 无库存，保持 wh_id=NULL（未入库）
            stats["no_stock"] += 1
            continue

        if len(whs) == 1:
            # 单仓库：UPDATE 原行
            wh = whs[0]
            await db.execute(
                text("""
                    UPDATE scm_inventory_check_item
                    SET wh_id = :wh_id, wh_code = :wh_code, wh_name = :wh_name,
                        updated_at = NOW()
                    WHERE id = :item_id
                """),
                {"wh_id": wh["wh_id"], "wh_code": wh["wh_code"],
                 "wh_name": wh["wh_name"], "item_id": item.id},
            )
            stats["single"] += 1
        else:
            # 多仓库：UPDATE 原行（库存最大的仓库）+ INSERT 新行
            first = whs[0]
            await db.execute(
                text("""
                    UPDATE scm_inventory_check_item
                    SET wh_id = :wh_id, wh_code = :wh_code, wh_name = :wh_name,
                        updated_at = NOW()
                    WHERE id = :item_id
                """),
                {"wh_id": first["wh_id"], "wh_code": first["wh_code"],
                 "wh_name": first["wh_name"], "item_id": item.id},
            )
            stats["multi_update"] += 1

            for extra_wh in whs[1:]:
                await db.execute(
                    text("""
                        INSERT INTO scm_inventory_check_item
                            (check_id, line_no, level, material_id, material_code,
                             material_name, spec_model, unit, req_qty,
                             system_qty, system_qty_time,
                             actual_qty, diff_qty, is_checked,
                             wh_id, wh_code, wh_name,
                             created_at, updated_at, version)
                        VALUES
                            (:check_id, :line_no, :level, :material_id, :material_code,
                             :material_name, :spec_model, :unit, 0,
                             :system_qty, :system_qty_time,
                             NULL, 0, 0,
                             :wh_id, :wh_code, :wh_name,
                             NOW(), NOW(), 0)
                    """),
                    {
                        "check_id": check.id,
                        "line_no": item.line_no,
                        "level": item.level,
                        "material_id": item.material_id,
                        "material_code": item.material_code,
                        "material_name": item.material_name,
                        "spec_model": item.spec_model,
                        "unit": item.unit,
                        "system_qty": extra_wh["qty"],
                        "system_qty_time": extra_wh["updated_at"],
                        "wh_id": extra_wh["wh_id"],
                        "wh_code": extra_wh["wh_code"],
                        "wh_name": extra_wh["wh_name"],
                    },
                )
            stats["multi_insert"] += len(whs) - 1

    # 刷新头表汇总（total_materials/checked_materials/total_diff_qty）
    await db.execute(
        text("""
            WITH agg AS (
                SELECT
                    COUNT(*)                        AS total,
                    COALESCE(SUM(is_checked), 0)    AS checked,
                    COALESCE(SUM(diff_qty), 0)      AS diff
                FROM scm_inventory_check_item
                WHERE check_id = :check_id
            )
            UPDATE scm_inventory_check
            SET total_materials   = agg.total,
                checked_materials = agg.checked,
                total_diff_qty    = agg.diff,
                updated_at        = NOW()
            FROM agg
            WHERE id = :check_id
        """),
        {"check_id": check.id},
    )
    return stats


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    apply = "--apply" in sys.argv

    if not args:
        print("用法: python backfill_inventory_check_warehouse.py <订单号> [<订单号>...] [--apply]")
        print("  不带 --apply = 干跑（只打印不写库）")
        print("  --apply     = 提交写库")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        # 1. 查盘点单头
        checks = await _load_checks(db, args)
        if not checks:
            print(f"未找到匹配的盘点单（已排除 cancelled）: {args}")
            return

        # 打印找到的盘点单
        print(f"\n{'='*60}")
        print(f"订单号: {', '.join(args)}")
        print(f"{'='*60}")
        skipped_cancelled = 0
        for c in checks:
            print(f"  {c.check_no}  {c.status}  {c.check_date}  {c.order_no or '(手动)'}")
        # 被跳过的 cancelled 单
        all_result = await db.execute(
            select(StockCheck)
            .where(StockCheck.order_no.in_(args))
        )
        all_checks = list(all_result.scalars().all())
        cancelled = [c for c in all_checks if c.status == "cancelled"]
        if cancelled:
            print(f"\n  ⚠ 跳过已取消的盘点单 ({len(cancelled)} 张):")
            for c in cancelled:
                print(f"    {c.check_no}  {c.status}")
            skipped_cancelled = len(cancelled)

        # 2. 查老明细行
        check_ids = [c.id for c in checks]
        old_items = await _load_old_items(db, check_ids)
        if not old_items:
            print(f"\n无需要回填的老明细行（wh_id IS NULL 且 material_id NOT NULL）")
            return

        # 3. 查仓库信息
        material_ids = {int(it.material_id) for it in old_items if it.material_id is not None}
        wh_map = await _get_warehouse_map(db, material_ids)

        # 4. 按 check 分组回填
        items_by_check: dict[int, list[StockCheckItem]] = defaultdict(list)
        for it in old_items:
            items_by_check[it.check_id].append(it)

        total_stats = {"single": 0, "multi_update": 0, "multi_insert": 0, "no_stock": 0, "guard_skip": 0}

        print(f"\n{'='*60}")
        print("回填详情")
        print(f"{'='*60}")

        for check in checks:
            items = items_by_check.get(check.id, [])
            if not items:
                print(f"  {check.check_no}: 无老明细行，跳过")
                continue

            stats = await _backfill_check(db, check, items, wh_map)
            for k in total_stats:
                total_stats[k] += stats[k]

            new_count = stats["multi_insert"]
            old_count = len(items)
            print(
                f"  {check.check_no}: "
                f"原行={old_count}  "
                f"单仓更新={stats['single']}  "
                f"多仓拆分={stats['multi_update']}  "
                f"新增行={new_count}  "
                f"无库存跳过={stats['no_stock']}  "
                f"护栏跳过={stats['guard_skip']}"
            )

        # 汇总
        print(f"\n{'='*60}")
        print("汇总")
        print(f"{'='*60}")
        print(f"  处理盘点单: {len(checks)} 张（跳过 cancelled: {skipped_cancelled} 张）")
        print(f"  处理明细行: {len(old_items)} 条")
        print(f"  单仓更新: {total_stats['single']} 条")
        print(f"  多仓拆分: {total_stats['multi_update']} 条（原行更新）")
        print(f"  新增行:   {total_stats['multi_insert']} 条")
        print(f"  无库存跳过: {total_stats['no_stock']} 条")
        print(f"  安全护栏跳过: {total_stats['guard_skip']} 条")

        if apply:
            await db.commit()
            print(f"\n✅ 已提交写库")
        else:
            await db.rollback()
            print(f"\n🔒 干跑模式（未写库）。确认无误后加 --apply 执行：")
            print(f"   python backfill_inventory_check_warehouse.py {' '.join(args)} --apply")


if __name__ == "__main__":
    asyncio.run(main())
