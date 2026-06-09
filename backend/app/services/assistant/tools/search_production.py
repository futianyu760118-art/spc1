"""Tool: 搜索生产工序进度 + 工序异常"""

from typing import Any, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.production.process_progress import ProcessProgress
from app.models.production.process_exception import ProcessException
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，匹配订单号、产品编码、物料名称",
        },
        "order_no": {
            "type": "string",
            "description": "订单号",
        },
        "process_type": {
            "type": "string",
            "enum": ["front_process", "smt", "lean", "assembly", "packaging"],
            "description": "工序类型: front_process=前道, smt=贴片, lean=精益, assembly=组装, packaging=包装",
        },
        "status": {
            "type": "string",
            "description": "状态筛选",
        },
        "include_exceptions": {
            "type": "boolean",
            "description": "是否同时搜索工序异常记录，默认true",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_production",
    description="搜索生产工序进度（前道、贴片、精益、组装、包装）和工序异常。支持按订单号、工序类型、状态等条件查询。返回完整的工序进度和异常信息。",
    parameters=PARAMETERS,
    display_name="生产进度查询",
)
async def search_production(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    keyword = params.get("keyword")
    order_no = params.get("order_no")
    process_type = params.get("process_type")
    status = params.get("status")
    include_exceptions = params.get("include_exceptions", True)
    limit = params.get("limit", 20)

    items = []
    total = 0

    # --- 工序进度 ---
    q = select(ProcessProgress)
    cq = select(func.count(ProcessProgress.id))
    filters = []
    if keyword:
        like = f"%{keyword}%"
        filters.append(
            ProcessProgress.order_no.ilike(like)
            | ProcessProgress.product_code.ilike(like)
            | ProcessProgress.material_name.ilike(like)
            | ProcessProgress.product_name.ilike(like)
        )
    if order_no:
        filters.append(ProcessProgress.order_no.ilike(f"%{order_no}%"))
    if process_type:
        filters.append(ProcessProgress.process_type == process_type)
    if status:
        filters.append(ProcessProgress.status == status)
    for f in filters:
        q = q.where(f)
        cq = cq.where(f)
    cnt = (await db.execute(cq)).scalar() or 0
    total += cnt
    q = q.order_by(ProcessProgress.plan_date.asc().nullslast())
    if limit:
        q = q.limit(limit)
    rows = (await db.execute(q)).scalars().all()

    process_type_map = {
        "front_process": "前道",
        "smt": "贴片",
        "lean": "精益",
        "assembly": "组装",
        "packaging": "包装",
    }
    for r in rows:
        pt_label = process_type_map.get(r.process_type, r.process_type or "")
        items.append({
            "type": "production",
            "title": f"[{pt_label}] 订单 {r.order_no or ''}",
            "subtitle": f"{r.product_name or r.product_code or ''} | 计划日期 {r.plan_date or ''}",
            "url": f"/{r.process_type}" if r.process_type else "/production-overview",
            "tags": [t for t in [r.status, pt_label] if t],
            # 完整字段
            "order_no": r.order_no,
            "process_type": r.process_type,
            "seq_no": r.seq_no,
            "plan_date": str(r.plan_date) if r.plan_date else None,
            "product_code": r.product_code,
            "product_name": r.product_name,
            "line_no": r.line_no,
            "model_code": r.model_code,
            "color_spec": r.color_spec,
            "qty": float(r.qty) if r.qty else None,
            "planned_qty": float(r.planned_qty) if r.planned_qty else None,
            "kit_qty": float(r.kit_qty) if r.kit_qty else None,
            "online_date": str(r.online_date) if r.online_date else None,
            "daily_plan_qty": float(r.daily_plan_qty) if r.daily_plan_qty else None,
            "daily_complete_qty": float(r.daily_complete_qty) if r.daily_complete_qty else None,
            "completion_rate": r.completion_rate,
            "work_hours": float(r.work_hours) if r.work_hours else None,
            "remark": r.remark,
            "status": r.status,
            # 前道特有
            "customer_code": r.customer_code,
            "sale_order_no": r.sale_order_no,
            "delivery_date": str(r.delivery_date) if r.delivery_date else None,
            "shell_status": r.shell_status,
            "frame_status": r.frame_status,
            "handle_status": r.handle_status,
            "bracket_status": r.bracket_status,
            # 贴片特有
            "material_long_code": r.material_long_code,
            "material_name": r.material_name,
            "material_confirm": r.material_confirm,
            # 组装/包装特有
            "assembly_group": r.assembly_group,
            "warehouse_in_qty": float(r.warehouse_in_qty) if r.warehouse_in_qty else None,
        })

    # --- 工序异常 ---
    if include_exceptions:
        q2 = select(ProcessException)
        cq2 = select(func.count(ProcessException.id))
        filters2 = []
        if keyword:
            like = f"%{keyword}%"
            filters2.append(
                ProcessException.order_no.ilike(like)
                | ProcessException.description.ilike(like)
                | ProcessException.exception_no.ilike(like)
            )
        if order_no:
            filters2.append(ProcessException.order_no.ilike(f"%{order_no}%"))
        if process_type:
            filters2.append(ProcessException.process_type == process_type)
        if status:
            filters2.append(ProcessException.status == status)
        for f in filters2:
            q2 = q2.where(f)
            cq2 = cq2.where(f)
        cnt2 = (await db.execute(cq2)).scalar() or 0
        total += cnt2
        q2 = q2.order_by(ProcessException.created_at.desc())
        if limit:
            q2 = q2.limit(limit)
        rows2 = (await db.execute(q2)).scalars().all()
        for r in rows2:
            items.append({
                "type": "process_exception",
                "title": f"工序异常 {r.exception_no}",
                "subtitle": r.description[:80] if r.description else "",
                "url": "/process-exceptions",
                "tags": [t for t in [r.severity, r.status] if t],
                # 完整字段
                "exception_no": r.exception_no,
                "process_type": r.process_type,
                "order_no": r.order_no,
                "model_code": r.model_code,
                "exception_type": r.exception_type,
                "severity": r.severity,
                "description": r.description,
                "responsible_dept": r.responsible_dept,
                "responsible_person": r.responsible_person,
                "status": r.status,
                "resolved_at": str(r.resolved_at) if r.resolved_at else None,
                "remark": r.remark,
                "created_at": str(r.created_at) if r.created_at else None,
            })

    return {"total": total, "items": items[:limit]}
