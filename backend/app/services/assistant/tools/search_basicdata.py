"""Tool: 搜索基础数据（客户、供应商、物料）"""

from typing import Any, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.customer import Customer
from app.models.basicdata.supplier import Supplier
from app.models.basicdata.material import Material as MaterialMaster
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，匹配名称或编码",
        },
        "data_type": {
            "type": "string",
            "enum": ["customer", "supplier", "material"],
            "description": "基础数据类型: customer=客户, supplier=供应商, material=物料。不指定则查全部。",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_basicdata",
    description="搜索基础数据，包括客户、供应商、物料。支持按关键词和数据类型查询。返回完整的基础数据信息。",
    parameters=PARAMETERS,
    display_name="基础数据查询",
)
async def search_basicdata(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    data_type = params.get("data_type")
    keyword = params.get("keyword")
    limit = params.get("limit", 20)

    items = []
    total = 0

    # --- 客户 ---
    if not data_type or data_type == "customer":
        q = select(Customer)
        cq = select(func.count(Customer.id))
        if keyword:
            like = f"%{keyword}%"
            flt = Customer.customer_name.ilike(like) | Customer.customer_code.ilike(like) | Customer.customer_short.ilike(like)
            q = q.where(flt)
            cq = cq.where(flt)
        cnt = (await db.execute(cq)).scalar() or 0
        total += cnt
        if limit:
            q = q.limit(limit)
        rows = (await db.execute(q)).scalars().all()
        for r in rows:
            items.append({
                "type": "customer",
                "title": f"客户 {r.customer_name}",
                "subtitle": f"编码: {r.customer_code} | 等级: {r.customer_level or ''}",
                "url": "/basicdata/customers",
                "tags": [r.customer_level] if r.customer_level else [],
                # 完整字段
                "customer_code": r.customer_code,
                "customer_name": r.customer_name,
                "customer_short": r.customer_short,
                "customer_level": r.customer_level,
                "industry_type": r.industry_type,
                "credit_code": r.credit_code,
                "status": r.status,
            })

    # --- 供应商 ---
    if not data_type or data_type == "supplier":
        q = select(Supplier)
        cq = select(func.count(Supplier.id))
        if keyword:
            like = f"%{keyword}%"
            flt = Supplier.supplier_name.ilike(like) | Supplier.supplier_code.ilike(like) | Supplier.supplier_short.ilike(like)
            q = q.where(flt)
            cq = cq.where(flt)
        cnt = (await db.execute(cq)).scalar() or 0
        total += cnt
        if limit:
            q = q.limit(limit)
        rows = (await db.execute(q)).scalars().all()
        for r in rows:
            items.append({
                "type": "supplier",
                "title": f"供应商 {r.supplier_name}",
                "subtitle": f"编码: {r.supplier_code} | 类型: {r.supplier_type or ''}",
                "url": "/basicdata/suppliers",
                "tags": [r.supplier_type] if r.supplier_type else [],
                # 完整字段
                "supplier_code": r.supplier_code,
                "supplier_name": r.supplier_name,
                "supplier_short": r.supplier_short,
                "supplier_type": r.supplier_type,
                "contact_person": r.contact_person,
                "contact_phone": r.contact_phone,
                "payment_terms": r.payment_terms,
                "status": r.status,
            })

    # --- 物料 ---
    if not data_type or data_type == "material":
        try:
            q = select(MaterialMaster)
            cq = select(func.count(MaterialMaster.id))
            if keyword:
                like = f"%{keyword}%"
                flt = MaterialMaster.material_code.ilike(like) | MaterialMaster.material_name.ilike(like)
                q = q.where(flt)
                cq = cq.where(flt)
            cnt = (await db.execute(cq)).scalar() or 0
            total += cnt
            if limit:
                q = q.limit(limit)
            rows = (await db.execute(q)).scalars().all()
            for r in rows:
                items.append({
                    "type": "material_master",
                    "title": f"物料 {r.material_name}",
                    "subtitle": f"编码: {r.material_code} | 规格: {r.spec_model or ''}",
                    "url": "/basicdata/materials",
                    "tags": [r.material_type] if r.material_type else [],
                    # 完整字段
                    "material_code": r.material_code,
                    "material_name": r.material_name,
                    "spec_model": r.spec_model,
                    "material_type": r.material_type,
                    "unit_of_measure": r.unit_of_measure,
                    "brand": r.brand,
                    "is_purchase": r.is_purchase,
                    "is_produce": r.is_produce,
                    "status": r.status,
                })
        except Exception:
            pass

    return {"total": total, "items": items}
