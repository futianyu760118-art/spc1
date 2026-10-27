"""从泛微 OA 同步返工单（品质异常流程 formtable_main_23）.

只读：直接连 OA 库读取已审批归档（sfsp=1 且 currentnodetype=3）的记录，
写入本地 production_rework_order 快照，供日期调整页选单插入。
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.production.rework_order import ProductionReworkOrder

FETCH_SQL = """
SELECT
    a.id AS form_id,
    a.requestId AS request_id,
    a.lcbh AS flow_no,
    a.sqrq AS apply_date,
    a.lclx AS flow_type,
    a.ddh AS order_no,
    a.cpbhlh AS product_code,
    a.cpmclm AS product_name,
    a.scrwdh AS production_task_no,
    a.pls AS batch_qty,
    a.cys AS sample_qty,
    a.bls AS defect_qty,
    a.rggss AS rework_hours,
    a.gsdj AS hour_price,
    a.gsfy AS hour_cost,
    a.zjfy AS total_cost,
    a.sffg AS is_rework,
    a.sfsp AS approve_flag,
    a.zxqk AS execute_status,
    a.bt AS title,
    b.currentnodetype AS flow_status
FROM [FWsv].[ecology].dbo.formtable_main_23 a
JOIN [FWsv].[ecology].dbo.workflow_requestbase b ON a.requestId = b.requestId
WHERE a.sfsp = 1 AND b.currentnodetype = 3
ORDER BY a.id DESC
"""


def _parse_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: Any) -> Optional[date]:
    raw = _parse_text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _fetch_oa_rows() -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.ERP_DB_URL:
        raise RuntimeError("ERP_DB_URL 未配置，无法读取 OA 返工单")
    url = settings.ERP_DB_URL
    for param in ["TrustServerCertificate=yes", "Encrypt=no"]:
        key = param.split("=")[0]
        if key not in url:
            url += f"&{param}" if "?" in url else f"?{param}"
    engine = create_engine(
        url,
        connect_args={"login_timeout": 10, "timeout": 60, "charset": "utf-8"},
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(FETCH_SQL)).mappings().all()]
    finally:
        engine.dispose()


def _build_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(row.get("request_id")),
        "form_id": _parse_int(row.get("form_id")),
        "flow_no": _parse_text(row.get("flow_no")),
        "apply_date": _parse_date(row.get("apply_date")),
        "flow_type": _parse_int(row.get("flow_type")),
        "order_no": _parse_text(row.get("order_no")),
        "product_code": _parse_text(row.get("product_code")),
        "product_name": _parse_text(row.get("product_name")),
        "production_task_no": _parse_text(row.get("production_task_no")),
        "batch_qty": _parse_int(row.get("batch_qty")),
        "sample_qty": _parse_int(row.get("sample_qty")),
        "defect_qty": _parse_int(row.get("defect_qty")),
        "rework_hours": _parse_decimal(row.get("rework_hours")),
        "hour_price": _parse_decimal(row.get("hour_price")),
        "hour_cost": _parse_decimal(row.get("hour_cost")),
        "total_cost": _parse_decimal(row.get("total_cost")),
        "is_rework": _parse_int(row.get("is_rework")),
        "approve_flag": _parse_int(row.get("approve_flag")),
        "execute_status": _parse_text(row.get("execute_status")),
        "flow_status": _parse_int(row.get("flow_status")),
        "title": _parse_text(row.get("title")),
    }


async def sync_rework_orders(db: AsyncSession) -> dict[str, Any]:
    """全量拉取已审批归档返工单并 upsert（按 requestId 幂等）."""
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, _fetch_oa_rows)

    stats = {"fetched": len(rows), "created": 0, "updated": 0, "skipped": 0}
    if not rows:
        return stats

    request_ids = [str(row["request_id"]) for row in rows if row.get("request_id") is not None]
    existing_map: dict[str, ProductionReworkOrder] = {}
    for start in range(0, len(request_ids), 500):
        chunk = request_ids[start:start + 500]
        existing = (
            await db.execute(
                select(ProductionReworkOrder).where(
                    ProductionReworkOrder.request_id.in_(chunk)
                )
            )
        ).scalars().all()
        existing_map.update({item.request_id: item for item in existing})

    now = datetime.now()
    for row in rows:
        if row.get("request_id") is None:
            stats["skipped"] += 1
            continue
        values = _build_values(row)
        record = existing_map.get(values["request_id"])
        if record is None:
            record = ProductionReworkOrder(**values, synced_at=now)
            db.add(record)
            stats["created"] += 1
        else:
            for field, value in values.items():
                setattr(record, field, value)
            record.synced_at = now
            db.add(record)
            stats["updated"] += 1

    await db.flush()
    return stats
