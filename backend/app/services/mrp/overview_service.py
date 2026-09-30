"""MRP 总览聚合（只读）。口径＝最新成功批次。"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.mrp.run import MrpRun
from app.models.mrp.suggestion import MrpSuggestion
from app.models.mrp.exception import MrpException
from app.models.basicdata.supplier import Supplier


async def build_overview(db: AsyncSession) -> dict:
    run = (await db.execute(
        select(MrpRun).where(MrpRun.status == "success").order_by(MrpRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    if run is None:
        return {"last_run": None, "pending_suggestions": 0, "gap_materials": 0,
                "pending_exceptions": 0, "related_orders": 0, "top_gaps": []}

    pending_rows = (await db.execute(
        select(MrpSuggestion).where(MrpSuggestion.run_id == run.id, MrpSuggestion.status == "pending")
    )).scalars().all()
    pending_exceptions = (await db.execute(
        select(func.count()).select_from(MrpException)
        .where(MrpException.run_id == run.id, MrpException.status == "open")
    )).scalar() or 0

    related_orders: set[str] = set()
    for sug in pending_rows:
        for item in (sug.pegging or []):
            no = item.get("sale_order_no")
            if no:
                related_orders.add(no)

    top_gaps = sorted(pending_rows, key=lambda s: float(s.suggest_qty or 0), reverse=True)[:10]
    supplier_ids = {s.suggested_supplier_id for s in top_gaps if s.suggested_supplier_id}
    supplier_names: dict[int, str] = {}
    if supplier_ids:
        rows = (await db.execute(select(Supplier.id, Supplier.supplier_name).where(Supplier.id.in_(supplier_ids)))).all()
        supplier_names = {int(i): n for i, n in rows}

    stats = run.stats or {}
    return {
        "last_run": {
            "id": run.id, "run_no": run.run_no, "status": run.status, "run_type": run.run_type,
            "duration_sec": stats.get("duration_sec"),
            "suggestions": stats.get("suggestions"), "exceptions": stats.get("exceptions"),
            "created_at": run.created_at.isoformat() if run.created_at else None,
        },
        "pending_suggestions": len(pending_rows),
        "gap_materials": len({s.material_id for s in pending_rows}),
        "pending_exceptions": int(pending_exceptions),
        "related_orders": len(related_orders),
        "top_gaps": [
            {"id": s.id, "material_code": s.material_code, "material_name": s.material_name,
             "bill_type": s.bill_type, "suggest_qty": float(s.suggest_qty or 0),
             "need_date": s.need_date.isoformat() if s.need_date else None,
             "action_date": s.action_date.isoformat() if s.action_date else None,
             "source": s.source, "status": s.status,
             "supplier_name": supplier_names.get(s.suggested_supplier_id or 0)}
            for s in top_gaps
        ],
    }
