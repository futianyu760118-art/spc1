"""MRP 参数装载与解析（含回退链）。"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.material import Material
from app.models.material.purchase_order import PurchaseOrder
from app.models.mrp.parameter import MrpParameter
from app.models.mrp.scheme import MrpScheme

DEFAULT_LEAD_TIME_DAYS = 7
DERIVED_MIN_SAMPLES = 3
DERIVED_LOOKBACK_DAYS = 180

_ZERO = Decimal("0")


@dataclass(frozen=True)
class ResolvedParam:
    material_id: int
    purchase_lead_time_days: int
    purchase_variable_lead_time_days: Optional[int]
    purchase_variable_lead_time_batch: Optional[Decimal]
    inspection_lead_time_days: int
    produce_lead_time_days: int
    subcontract_lead_time_days: int
    safety_stock: Decimal
    max_stock: Optional[Decimal]
    moq: Optional[Decimal]
    batch_policy: str
    batch_qty: Optional[Decimal]
    default_supplier_id: Optional[int]
    lead_time_source: str  # configured / derived / default


def total_lead_time(param: ResolvedParam, bill_type: int, order_qty: Decimal) -> int:
    """按建议类型计算总提前期(天)。
    11010 外购 = 固定 + ceil(建议量/变动批量)×变动 + 检验
    11011 自制 = produce_lead_time_days
    11012 委外 = subcontract_lead_time_days
    """
    if bill_type == 11010:
        days = param.purchase_lead_time_days + param.inspection_lead_time_days
        if param.purchase_variable_lead_time_days and param.purchase_variable_lead_time_batch:
            multiples = (order_qty / param.purchase_variable_lead_time_batch).to_integral_value(rounding="ROUND_CEILING")
            days += int(multiples) * param.purchase_variable_lead_time_days
        return days
    if bill_type == 11011:
        return param.produce_lead_time_days
    return param.subcontract_lead_time_days


async def ensure_default_scheme(db: AsyncSession) -> MrpScheme:
    """取默认方案，不存在则创建（幂等）。"""
    scheme = (
        await db.execute(
            select(MrpScheme).where(MrpScheme.scheme_code == "default").limit(1)
        )
    ).scalar_one_or_none()
    if scheme is None:
        scheme = MrpScheme(
            scheme_code="default",
            scheme_name="默认计划方案",
            is_default=True,
            is_active=True,
        )
        db.add(scheme)
        await db.flush()
    return scheme


async def load_historical_purchase_lead_times(db: AsyncSession) -> dict[int, int]:
    """按物料编码聚合近 N 天已完成 PO 的实际提前期均值（天），样本 >= 3 才采纳。"""
    since = date.today() - timedelta(days=DERIVED_LOOKBACK_DAYS)
    rows = (
        await db.execute(
            select(
                PurchaseOrder.material_code,
                func.avg(PurchaseOrder.actual_arrival_date - PurchaseOrder.po_date),
                func.count(),
            )
            .where(
                PurchaseOrder.actual_arrival_date.isnot(None),
                PurchaseOrder.po_date.isnot(None),
                PurchaseOrder.po_date >= since,
                PurchaseOrder.actual_arrival_date >= PurchaseOrder.po_date,
            )
            .group_by(PurchaseOrder.material_code)
        )
    ).all()
    derived: dict[str, int] = {}
    for code, avg_days, sample_count in rows:
        if code and sample_count and sample_count >= DERIVED_MIN_SAMPLES and avg_days is not None:
            derived[code] = max(0, int(round(float(avg_days))))
    if not derived:
        return {}
    material_rows = (
        await db.execute(
            select(Material.material_code, Material.erp_material_id).where(
                Material.material_code.in_(list(derived.keys()))
            )
        )
    ).all()
    return {
        int(erp_id): derived[code]
        for code, erp_id in material_rows
        if code in derived and erp_id is not None
    }


def resolve_param(row: Optional[MrpParameter], material_id: int, derived_lt: Optional[int]) -> ResolvedParam:
    """单物料参数解析：配置行 → 历史推导 → 全局默认。"""
    if row is not None:
        return ResolvedParam(
            material_id=material_id,
            purchase_lead_time_days=row.purchase_lead_time_days if row.purchase_lead_time_days is not None else (derived_lt if derived_lt is not None else DEFAULT_LEAD_TIME_DAYS),
            purchase_variable_lead_time_days=row.purchase_variable_lead_time_days,
            purchase_variable_lead_time_batch=Decimal(str(row.purchase_variable_lead_time_batch)) if row.purchase_variable_lead_time_batch is not None else None,
            inspection_lead_time_days=row.inspection_lead_time_days or 0,
            produce_lead_time_days=row.produce_lead_time_days if row.produce_lead_time_days is not None else DEFAULT_LEAD_TIME_DAYS,
            subcontract_lead_time_days=row.subcontract_lead_time_days if row.subcontract_lead_time_days is not None else DEFAULT_LEAD_TIME_DAYS,
            safety_stock=Decimal(str(row.safety_stock)) if row.safety_stock is not None else _ZERO,
            max_stock=Decimal(str(row.max_stock)) if row.max_stock is not None else None,
            moq=Decimal(str(row.moq)) if row.moq is not None else None,
            batch_policy=row.batch_policy or "lot_for_lot",
            batch_qty=Decimal(str(row.batch_qty)) if row.batch_qty is not None else None,
            default_supplier_id=row.default_supplier_id,
            lead_time_source="configured",
        )
    if derived_lt is not None:
        return ResolvedParam(
            material_id=material_id,
            purchase_lead_time_days=derived_lt,
            purchase_variable_lead_time_days=None,
            purchase_variable_lead_time_batch=None,
            inspection_lead_time_days=0,
            produce_lead_time_days=DEFAULT_LEAD_TIME_DAYS,
            subcontract_lead_time_days=DEFAULT_LEAD_TIME_DAYS,
            safety_stock=_ZERO,
            max_stock=None,
            moq=None,
            batch_policy="lot_for_lot",
            batch_qty=None,
            default_supplier_id=None,
            lead_time_source="derived",
        )
    return ResolvedParam(
        material_id=material_id,
        purchase_lead_time_days=DEFAULT_LEAD_TIME_DAYS,
        purchase_variable_lead_time_days=None,
        purchase_variable_lead_time_batch=None,
        inspection_lead_time_days=0,
        produce_lead_time_days=DEFAULT_LEAD_TIME_DAYS,
        subcontract_lead_time_days=DEFAULT_LEAD_TIME_DAYS,
        safety_stock=_ZERO,
        max_stock=None,
        moq=None,
        batch_policy="lot_for_lot",
        batch_qty=None,
        default_supplier_id=None,
        lead_time_source="default",
    )


async def load_parameters(db: AsyncSession) -> tuple[dict[int, ResolvedParam], dict]:
    """装载全部物料参数（含回退），返回 (params_by_material_id, 统计)。"""
    rows = (await db.execute(select(MrpParameter))).scalars().all()
    by_material = {r.material_id: r for r in rows}
    derived = await load_historical_purchase_lead_times(db)

    all_material_ids = (
        await db.execute(select(Material.erp_material_id).where(Material.erp_material_id.isnot(None)))
    ).scalars().all()

    params: dict[int, ResolvedParam] = {}
    stats = {"total": 0, "configured": 0, "derived": 0, "default": 0}
    for erp_id in all_material_ids:
        mid = int(erp_id)
        resolved = resolve_param(by_material.get(mid), mid, derived.get(mid))
        params[mid] = resolved
        stats["total"] += 1
        stats[resolved.lead_time_source] += 1
    return params, stats


def scheme_snapshot(scheme: MrpScheme, param_stats: dict) -> dict:
    """方案 + 参数解析统计快照（写入 mrp_run.scheme_snapshot）。"""
    return {
        "scheme": {
            "scheme_code": scheme.scheme_code,
            "scheme_name": scheme.scheme_name,
            "horizon_days": scheme.horizon_days,
            "consider_inventory": scheme.consider_inventory,
            "consider_po": scheme.consider_po,
            "consider_task": scheme.consider_task,
            "consider_subcontract": scheme.consider_subcontract,
            "consider_transfer": scheme.consider_transfer,
            "consider_requisition": scheme.consider_requisition,
            "consider_safety_stock": scheme.consider_safety_stock,
            "supply_priority": scheme.supply_priority,
            "exception_grace_days": scheme.exception_grace_days,
            "compare_window_days": scheme.compare_window_days,
            "compare_qty_threshold_pct": (
                float(scheme.compare_qty_threshold_pct)
                if scheme.compare_qty_threshold_pct is not None
                else 5.0
            ),
        },
        "param_stats": param_stats,
    }
