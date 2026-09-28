"""MRP 例外检测（纯函数，便于单测）。

供应单据 FIFO pegging → 改期/取消类例外；需求/供给拖期类由调用方（引擎）传入原始记录。
编码映射（金蝶）：6 过去需求 / 7 过去到货 / 11 整单提前 / 15 整单延后 / 20 整单取消 / 21 部分取消 / 50 无 BOM / 96 低于安全库存。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

_ZERO = Decimal("0")

EXC_PAST_DUE_DEMAND = 6
EXC_PAST_DUE_SUPPLY = 7
EXC_SUPPLY_LATE = 11
EXC_SUPPLY_EARLY = 15
EXC_SUPPLY_CANCEL = 20
EXC_SUPPLY_REDUCE = 21
EXC_NO_BOM = 50
EXC_BELOW_SAFETY = 96


@dataclass(frozen=True)
class SupplyInfo:
    date: Optional[date]
    qty: Decimal
    source_type: str
    doc_no: str
    line_no: str
    source_id: Optional[int]


@dataclass(frozen=True)
class DemandInfo:
    need_date: Optional[date]
    qty: Decimal
    order_no: str
    line_no: str


def make_exception_payload(
    material_id: int,
    material_code: str,
    material_name: str,
    *,
    code: int,
    type_: str,
    source_type: str,
    doc_no: Optional[str] = None,
    line_no: Optional[str] = None,
    source_id: Optional[int] = None,
    need_date: Optional[date] = None,
    doc_date: Optional[date] = None,
    adjust_days: Optional[int] = None,
    suggest_date: Optional[date] = None,
    suggest_qty: Optional[Decimal] = None,
    detail: str = "",
    pegging: Optional[list] = None,
) -> dict:
    return {
        "material_id": material_id,
        "material_code": material_code,
        "material_name": material_name,
        "exception_code": code,
        "exception_type": type_,
        "source_type": source_type,
        "source_doc_no": doc_no,
        "source_line_no": line_no,
        "source_id": source_id,
        "need_date": need_date,
        "doc_date": doc_date,
        "adjust_days": adjust_days,
        "suggest_date": suggest_date,
        "suggest_qty": suggest_qty,
        "detail": detail,
        "pegging": pegging or None,
        "status": "open",
    }


def detect_material_exceptions(
    *,
    material_id: int,
    material_code: str,
    material_name: str,
    supplies: list[SupplyInfo],
    demands: list[DemandInfo],
    grace_days: int,
    run_date: date,
) -> list[dict]:
    payloads: list[dict] = []

    for demand in demands:
        if demand.need_date is None or demand.need_date >= run_date:
            continue
        payloads.append(make_exception_payload(
            material_id, material_code, material_name,
            code=EXC_PAST_DUE_DEMAND, type_="past_due_demand",
            source_type="sale_order_line", doc_no=demand.order_no, line_no=demand.line_no,
            need_date=demand.need_date, doc_date=demand.need_date, suggest_qty=demand.qty,
            detail=f"需求日期 {demand.need_date} 已过去，请确认订单排期或关闭",
            pegging=[{"sale_order_no": demand.order_no, "line_no": demand.line_no, "qty": float(demand.qty)}],
        ))

    for supply in supplies:
        if supply.date is None or supply.date >= run_date:
            continue
        payloads.append(make_exception_payload(
            material_id, material_code, material_name,
            code=EXC_PAST_DUE_SUPPLY, type_="past_due_supply",
            source_type=supply.source_type, doc_no=supply.doc_no, line_no=supply.line_no,
            source_id=supply.source_id, doc_date=supply.date, suggest_qty=supply.qty,
            detail=f"单据日期 {supply.date} 已过去且未到货/完工，请催货或改期",
        ))

    remaining: list[list] = [
        [d.need_date, d.qty, d.order_no, d.line_no]
        for d in demands if d.qty and d.qty > 0
    ]
    remaining.sort(key=lambda r: (r[0] is None, r[0] or date.max))

    for supply in sorted(supplies, key=lambda s: (s.date is None, s.date or date.max)):
        left = supply.qty or _ZERO
        covered: list[list] = []
        for row in remaining:
            if left <= 0:
                break
            if row[1] <= 0:
                continue
            take = min(left, row[1])
            row[1] -= take
            left -= take
            covered.append([row[0], take, row[2], row[3]])
        if not covered:
            payloads.append(make_exception_payload(
                material_id, material_code, material_name,
                code=EXC_SUPPLY_CANCEL, type_="supply_excess",
                source_type=supply.source_type, doc_no=supply.doc_no, line_no=supply.line_no,
                source_id=supply.source_id, doc_date=supply.date, suggest_qty=supply.qty,
                detail="该在途供给无对应需求，建议取消",
            ))
            continue
        covered_dates = [c[0] for c in covered if c[0] is not None]
        if covered_dates and supply.date is not None:
            earliest, latest = min(covered_dates), max(covered_dates)
            if (supply.date - earliest).days > grace_days:
                payloads.append(make_exception_payload(
                    material_id, material_code, material_name,
                    code=EXC_SUPPLY_LATE, type_="supply_late",
                    source_type=supply.source_type, doc_no=supply.doc_no, line_no=supply.line_no,
                    source_id=supply.source_id, need_date=earliest, doc_date=supply.date,
                    adjust_days=(earliest - supply.date).days, suggest_date=earliest,
                    detail=f"供给晚于需求 { (supply.date - earliest).days } 天，建议提前",
                ))
            elif (latest - supply.date).days > grace_days:
                payloads.append(make_exception_payload(
                    material_id, material_code, material_name,
                    code=EXC_SUPPLY_EARLY, type_="supply_early",
                    source_type=supply.source_type, doc_no=supply.doc_no, line_no=supply.line_no,
                    source_id=supply.source_id, need_date=latest, doc_date=supply.date,
                    adjust_days=(latest - supply.date).days, suggest_date=latest,
                    detail=f"供给早于需求 { (latest - supply.date).days } 天，建议延后",
                ))
        if left > 0:
            payloads.append(make_exception_payload(
                material_id, material_code, material_name,
                code=EXC_SUPPLY_REDUCE, type_="supply_excess",
                source_type=supply.source_type, doc_no=supply.doc_no, line_no=supply.line_no,
                source_id=supply.source_id, doc_date=supply.date, suggest_qty=left,
                detail=f"供给超出需求 { left }，建议减量或取消",
            ))
    return payloads
