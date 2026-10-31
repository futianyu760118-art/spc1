"""MRP 与 K3 ICMrpResult（mrp_plan_order）影子对比。

读写分离：运算引擎走 build_comparison（回写建议 compare 字段），
GET 总览走 read_comparison（纯查询不落库）；两者共用纯函数 classify_comparison。
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.mrp_plan_order import MrpPlanOrder
from app.models.mrp.scheme import MrpScheme
from app.models.mrp.suggestion import MrpSuggestion
from app.models.order.sale_order import SaleOrder


def _qty_diff_within(sug_qty: Decimal, k3_qty: Decimal, threshold_pct: Decimal) -> bool:
    base = k3_qty if k3_qty > 0 else sug_qty
    if base <= 0:
        return sug_qty == k3_qty
    return abs(sug_qty - k3_qty) / base * Decimal("100") <= threshold_pct


async def _load_k3_materials(db: AsyncSession) -> dict[int, dict]:
    """K3 对比基线：仅取未关单/未删单销售订单下的结果行（与 SPC 需求口径对齐；
    已交付订单的 K3 历史行会滞留在同步表中，混入会把 k3_only 放大数倍），
    按（销售订单+物料）取最新运算行（表本身按该键 upsert），再按物料聚合：
    数量求和、需求日取最早。"""
    rows = (
        await db.execute(
            select(
                MrpPlanOrder.sale_order_id,
                MrpPlanOrder.material_id,
                MrpPlanOrder.need_date,
                MrpPlanOrder.base_plan_qty,
                MrpPlanOrder.mrp_run_time,
            )
            .join(SaleOrder, SaleOrder.erp_id == MrpPlanOrder.sale_order_id)
            .where(
                SaleOrder.is_closed == 0,
                SaleOrder.is_deleted == 0,
                MrpPlanOrder.material_id.op("~")("^[0-9]+$"),
                MrpPlanOrder.need_date.isnot(None),
            )
            .order_by(MrpPlanOrder.mrp_run_time.desc())
        )
    ).all()
    deduped: dict[tuple, tuple[int, date, Decimal]] = {}
    for sale_order_id, material_id, need_date, qty, _run_time in rows:
        try:
            mid = int(material_id)
        except (TypeError, ValueError):
            continue
        key = (sale_order_id, mid)
        if key in deduped:
            continue
        deduped[key] = (mid, need_date, Decimal(str(qty or 0)))
    aggregated: dict[int, dict] = {}
    for mid, need_date, qty in deduped.values():
        group = aggregated.setdefault(
            mid, {"qty": Decimal("0"), "need_date": need_date, "orders": 0}
        )
        group["qty"] += qty
        group["orders"] += 1
        if need_date < group["need_date"]:
            group["need_date"] = need_date
    return aggregated


def classify_comparison(
    suggestions: list[dict],
    k3_groups: dict[int, dict],
    window_days: int,
    threshold_pct: Decimal,
) -> tuple[dict, list[dict], list[dict]]:
    """纯函数：逐条建议对照 K3 物料组判定状态。

    suggestions 元素：{"id", "material_id", "suggest_qty", "need_date"}；
    返回 (counts, rows, k3_only)：counts 为 match/diff_qty/diff_date/spc_only 计数，
    rows 为每建议 {"suggestion_id", "status", "k3_qty", "k3_need_date"}，
    k3_only 为未被任何建议使用的 K3 物料组。
    """
    counts = {"match": 0, "diff_qty": 0, "diff_date": 0, "spc_only": 0}
    rows: list[dict] = []
    used_materials: set[int] = set()

    for sug in suggestions:
        sug_qty = Decimal(str(sug.get("suggest_qty") or 0))
        group = k3_groups.get(sug["material_id"])
        if group is None:
            counts["spc_only"] += 1
            rows.append(
                {"suggestion_id": sug["id"], "status": "spc_only", "k3_qty": None, "k3_need_date": None}
            )
            continue
        used_materials.add(sug["material_id"])
        qty_ok = _qty_diff_within(sug_qty, group["qty"], threshold_pct)
        date_ok = abs((group["need_date"] - sug["need_date"]).days) <= window_days
        if qty_ok and date_ok:
            status = "match"
        elif not qty_ok:
            status = "diff_qty"
        else:
            status = "diff_date"
        counts[status] += 1
        rows.append(
            {
                "suggestion_id": sug["id"],
                "status": status,
                "k3_qty": group["qty"],
                "k3_need_date": group["need_date"],
            }
        )

    k3_only = [
        {
            "material_id": mid,
            "need_date": group["need_date"],
            "qty": group["qty"],
            "orders": group["orders"],
        }
        for mid, group in k3_groups.items()
        if mid not in used_materials
    ]
    return counts, rows, k3_only


def _scheme_compare_config(scheme: MrpScheme) -> tuple[int, Decimal]:
    window_days = int(scheme.compare_window_days) if scheme.compare_window_days is not None else 3
    threshold = (
        Decimal(str(scheme.compare_qty_threshold_pct))
        if scheme.compare_qty_threshold_pct is not None
        else Decimal("5")
    )
    return window_days, threshold


async def _load_suggestions(db: AsyncSession, run_id: int) -> list[MrpSuggestion]:
    return (
        await db.execute(
            select(MrpSuggestion)
            .where(MrpSuggestion.run_id == run_id, MrpSuggestion.status != "rejected")
            .order_by(MrpSuggestion.material_code, MrpSuggestion.need_date)
        )
    ).scalars().all()


def _build_summary(run_id: int, total: int, counts: dict, k3_only_count: int) -> dict:
    match = counts["match"]
    return {
        "run_id": run_id,
        "total_suggestions": total,
        "match": match,
        "diff_qty": counts["diff_qty"],
        "diff_date": counts["diff_date"],
        "spc_only": counts["spc_only"],
        "k3_only": k3_only_count,
        "match_rate": round(match / total * 100, 2) if total else 0.0,
    }


async def _classify_run(
    db: AsyncSession, run_id: int, scheme: MrpScheme
) -> tuple[list[MrpSuggestion], dict, list[dict], list[dict]]:
    window_days, threshold = _scheme_compare_config(scheme)
    suggestions = await _load_suggestions(db, run_id)
    k3_groups = await _load_k3_materials(db)
    counts, rows, k3_only = classify_comparison(
        [
            {
                "id": sug.id,
                "material_id": sug.material_id,
                "suggest_qty": sug.suggest_qty,
                "need_date": sug.need_date,
            }
            for sug in suggestions
        ],
        k3_groups,
        window_days,
        threshold,
    )
    return suggestions, counts, rows, k3_only


async def build_comparison(db: AsyncSession, run_id: int, scheme: MrpScheme) -> dict:
    """对比并回写建议的 compare 字段；返回总览 + k3_only 清单。"""
    suggestions, counts, rows, k3_only = await _classify_run(db, run_id, scheme)

    for row in rows:
        await db.execute(
            update(MrpSuggestion)
            .where(MrpSuggestion.id == row["suggestion_id"])
            .values(
                compare_status=row["status"],
                k3_qty=row["k3_qty"],
                k3_need_date=row["k3_need_date"],
            )
        )

    return {
        "summary": _build_summary(run_id, len(suggestions), counts, len(k3_only)),
        "k3_only": k3_only,
    }


async def read_comparison(db: AsyncSession, run_id: int, scheme: MrpScheme) -> dict:
    """只读对比总览：不落库，返回 summary / k3_only / 建议行（含实时对比结果）。"""
    suggestions, counts, rows, k3_only = await _classify_run(db, run_id, scheme)
    row_by_id = {row["suggestion_id"]: row for row in rows}

    items = []
    for sug in suggestions:
        row = row_by_id[sug.id]
        items.append(
            {
                "id": sug.id,
                "material_id": sug.material_id,
                "material_code": sug.material_code,
                "material_name": sug.material_name,
                "bill_type": sug.bill_type,
                "suggest_qty": float(sug.suggest_qty or 0),
                "need_date": sug.need_date.isoformat() if sug.need_date else None,
                "compare_status": row["status"],
                "k3_qty": float(row["k3_qty"]) if row["k3_qty"] is not None else None,
                "k3_need_date": row["k3_need_date"].isoformat() if row["k3_need_date"] else None,
            }
        )

    return {
        "summary": _build_summary(run_id, len(suggestions), counts, len(k3_only)),
        "k3_only": k3_only,
        "items": items,
    }
