"""Tool: 搜索物料需求 / 问题物料 / 长交期物料"""

from typing import Any, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.material_demand import MaterialDemand
from app.models.material.material_issue import MaterialIssue
from app.models.material.long_lead_material import LongLeadMaterial
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，匹配物料编码或物料名称",
        },
        "order_no": {
            "type": "string",
            "description": "关联的订单号",
        },
        "shortage_only": {
            "type": "boolean",
            "description": "是否只查欠料物料",
        },
        "category": {
            "type": "string",
            "enum": ["demand", "issue", "long_lead"],
            "description": "物料类别: demand=物料需求, issue=问题物料, long_lead=长交期物料。不指定则查全部。",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_materials",
    description="搜索物料相关数据，包括物料需求（欠料情况）、问题物料、长交期物料。支持按关键词、订单号、是否欠料、物料类别等条件查询。返回完整的物料信息。",
    parameters=PARAMETERS,
    display_name="物料查询",
)
async def search_materials(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    category = params.get("category")
    limit = params.get("limit", 20)
    keyword = params.get("keyword")
    order_no = params.get("order_no")
    shortage_only = params.get("shortage_only", False)

    items = []
    total = 0

    # --- 物料需求 ---
    if not category or category == "demand":
        q = select(MaterialDemand)
        cq = select(func.count(MaterialDemand.id))
        filters = []
        if keyword:
            like = f"%{keyword}%"
            filters.append(MaterialDemand.material_code.ilike(like) | MaterialDemand.material_name.ilike(like))
        if order_no:
            filters.append(MaterialDemand.order_no.ilike(f"%{order_no}%"))
        if shortage_only:
            filters.append(MaterialDemand.shortage_flag == True)
        for f in filters:
            q = q.where(f)
            cq = cq.where(f)
        cnt = (await db.execute(cq)).scalar() or 0
        total += cnt
        q = q.order_by(MaterialDemand.shortage_qty.desc().nullslast())
        if limit:
            q = q.limit(limit)
        rows = (await db.execute(q)).scalars().all()
        for r in rows:
            items.append({
                "type": "material_demand",
                "title": f"物料需求 {r.material_code}",
                "subtitle": f"{r.material_name or ''} | 订单 {r.order_no}",
                "url": f"/purchase-plan",
                "tags": ["欠料"] if r.shortage_flag else [],
                # 完整字段
                "material_code": r.material_code,
                "material_name": r.material_name,
                "order_no": r.order_no,
                "line_no": r.line_no,
                "req_qty": float(r.req_qty) if r.req_qty else None,
                "req_date": str(r.req_date) if r.req_date else None,
                "allocated_qty": float(r.allocated_qty) if r.allocated_qty else None,
                "shortage_qty": float(r.shortage_qty) if r.shortage_qty else None,
                "shortage_flag": r.shortage_flag,
                "data_source": r.data_source,
            })

    # --- 问题物料 ---
    if not category or category == "issue":
        q = select(MaterialIssue)
        cq = select(func.count(MaterialIssue.id))
        filters = []
        if keyword:
            filters.append(MaterialIssue.description.ilike(f"%{keyword}%"))
        for f in filters:
            q = q.where(f)
            cq = cq.where(f)
        cnt = (await db.execute(cq)).scalar() or 0
        total += cnt
        q = q.order_by(MaterialIssue.created_at.desc())
        if limit:
            q = q.limit(limit)
        rows = (await db.execute(q)).scalars().all()
        for r in rows:
            items.append({
                "type": "material_issue",
                "title": f"问题物料 #{r.id}",
                "subtitle": r.description[:80] if r.description else "",
                "url": f"/material-issues",
                "tags": [t for t in [r.status, r.category] if t],
                # 完整字段
                "year": r.year,
                "week_no": r.week_no,
                "department": r.department,
                "category": r.category,
                "issue_date": str(r.issue_date) if r.issue_date else None,
                "reporter": r.reporter,
                "description": r.description,
                "deadline": str(r.deadline) if r.deadline else None,
                "responsible_dept": r.responsible_dept,
                "responsible_person": r.responsible_person,
                "audit_score": r.audit_score,
                "is_project": r.is_project,
                "follow_up_record": r.follow_up_record,
                "status": r.status,
            })

    # --- 长交期物料 ---
    if not category or category == "long_lead":
        q = select(LongLeadMaterial)
        cq = select(func.count(LongLeadMaterial.id))
        filters = []
        if keyword:
            like = f"%{keyword}%"
            filters.append(LongLeadMaterial.material_code.ilike(like) | LongLeadMaterial.supplier_name.ilike(like))
        for f in filters:
            q = q.where(f)
            cq = cq.where(f)
        cnt = (await db.execute(cq)).scalar() or 0
        total += cnt
        q = q.order_by(LongLeadMaterial.created_at.desc())
        if limit:
            q = q.limit(limit)
        rows = (await db.execute(q)).scalars().all()
        for r in rows:
            items.append({
                "type": "long_lead_material",
                "title": f"长交期物料 {r.material_code}",
                "subtitle": f"供应商: {r.supplier_name or ''}",
                "url": f"/long-lead-materials",
                "tags": [r.status] if r.status else [],
                # 完整字段
                "material_code": r.material_code,
                "supplier_name": r.supplier_name,
                "improvement_plan": r.improvement_plan,
                "status": r.status,
            })

    return {"total": total, "items": items[:limit]}
