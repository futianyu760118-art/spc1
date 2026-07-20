"""基础主数据对外接口

为外部系统提供客户 / 供应商 / 物料 / 产品 主数据查询。
区别于内部 /api/v1/* 的复杂逻辑，对外只暴露精简字段集与常用筛选条件，
且字段集合独立于表结构变更。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.basicdata.customer import Customer
from app.models.basicdata.supplier import Supplier
from app.models.basicdata.material import Material
from app.models.basicdata.product import Product

from ..registry import register_external, ExternalCallContext


def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════
# 客户
# ═══════════════════════════════════════════

@register_external(
    "customers.list",
    "客户列表",
    method="GET",
    path="/customers/list",
    description="客户主数据列表查询，支持关键字、客户等级、行业、状态、增量同步",
    tags=["主数据"],
)
async def customers_list(ctx: ExternalCallContext) -> dict:
    """客户列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（客户编码 / 客户名称 / 简称 模糊匹配）
        customer_level: 客户等级，多选逗号分隔
        industry_type: 所属行业
        status: 状态，多选逗号分隔 (1-启用 0-禁用)
        updated_after: 增量同步，仅返回 update_time >= 此时间的记录 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    customer_level = params.get("customer_level")
    industry_type = params.get("industry_type")
    status = params.get("status")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(Customer)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Customer.customer_code.ilike(like_expr),
            Customer.customer_name.ilike(like_expr),
            Customer.customer_short.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if customer_level:
        levels = [s.strip() for s in customer_level.split(",") if s.strip()]
        if len(levels) == 1:
            query = query.where(Customer.customer_level == levels[0])
        elif levels:
            query = query.where(Customer.customer_level.in_(levels))
        count_query = select(func.count()).select_from(query.subquery())

    if industry_type:
        query = query.where(Customer.industry_type == industry_type)
        count_query = select(func.count()).select_from(query.subquery())

    if status is not None and status != "":
        statuses = [s.strip() for s in str(status).split(",") if s.strip() != ""]
        if len(statuses) == 1:
            query = query.where(Customer.status == int(statuses[0]))
        elif statuses:
            query = query.where(Customer.status.in_([int(s) for s in statuses]))
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Customer.update_time >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Customer.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "customer_code": r.customer_code,
        "customer_name": r.customer_name,
        "customer_short": r.customer_short,
        "customer_level": r.customer_level,
        "industry_type": r.industry_type,
        "credit_code": r.credit_code,
        "status": r.status,
        "update_time": r.update_time.isoformat() if r.update_time else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════
# 供应商
# ═══════════════════════════════════════════

@register_external(
    "suppliers.list",
    "供应商列表",
    method="GET",
    path="/suppliers/list",
    description="供应商主数据列表查询，支持关键字、类型、状态、增量同步（联系电话脱敏）",
    tags=["主数据"],
)
async def suppliers_list(ctx: ExternalCallContext) -> dict:
    """供应商列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（供应商编码 / 名称 / 简称 模糊匹配）
        supplier_type: 供应商类型精确匹配
        status: 状态，多选逗号分隔 (1-启用 0-禁用)
        updated_after: 增量同步 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    supplier_type = params.get("supplier_type")
    status = params.get("status")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(Supplier)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Supplier.supplier_code.ilike(like_expr),
            Supplier.supplier_name.ilike(like_expr),
            Supplier.supplier_short.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if supplier_type:
        query = query.where(Supplier.supplier_type == supplier_type)
        count_query = select(func.count()).select_from(query.subquery())

    if status is not None and status != "":
        statuses = [s.strip() for s in str(status).split(",") if s.strip() != ""]
        if len(statuses) == 1:
            query = query.where(Supplier.status == int(statuses[0]))
        elif statuses:
            query = query.where(Supplier.status.in_([int(s) for s in statuses]))
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Supplier.update_time >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Supplier.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    def _mask_phone(v):
        if not v or len(v) < 7:
            return v
        return v[:3] + "****" + v[-4:]

    items = [{
        "id": r.id,
        "supplier_code": r.supplier_code,
        "supplier_name": r.supplier_name,
        "supplier_short": r.supplier_short,
        "supplier_type": r.supplier_type,
        "contact_person": r.contact_person,
        "contact_phone": _mask_phone(r.contact_phone),
        "payment_terms": r.payment_terms,
        "status": r.status,
        "update_time": r.update_time.isoformat() if r.update_time else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════
# 物料
# ═══════════════════════════════════════════

@register_external(
    "materials.list",
    "物料列表",
    method="GET",
    path="/materials/list",
    description="物料主数据列表查询，支持关键字、物料分类、采购/生产属性、状态、增量同步",
    tags=["主数据"],
)
async def materials_list(ctx: ExternalCallContext) -> dict:
    """物料列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（物料编码 / 名称 / 规格型号 模糊匹配）
        material_type: 物料分类精确匹配
        is_purchase: 是否可采购 (0/1)
        is_produce: 是否可生产 (0/1)
        status: 状态，多选逗号分隔 (1-启用 0-禁用)
        updated_after: 增量同步 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    material_type = params.get("material_type")
    is_purchase = params.get("is_purchase")
    is_produce = params.get("is_produce")
    status = params.get("status")
    updated_after = _parse_dt(params.get("updated_after"))

    # 默认排除已删除物料；左连接供应商取名称（保留无供应商的物料）
    # 注：Material.supplier_id 存储的是 ERP 供应商内部ID，需关联 Supplier.erp_supply_id
    query = (
        select(Material, Supplier.supplier_name)
        .outerjoin(Supplier, Material.supplier_id == Supplier.erp_supply_id)
        .where(Material.is_deleted == 0)
    )
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Material.material_code.ilike(like_expr),
            Material.material_name.ilike(like_expr),
            Material.spec_model.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if material_type:
        query = query.where(Material.material_type == material_type)
        count_query = select(func.count()).select_from(query.subquery())

    if is_purchase is not None and is_purchase != "":
        query = query.where(Material.is_purchase == int(is_purchase))
        count_query = select(func.count()).select_from(query.subquery())

    if is_produce is not None and is_produce != "":
        query = query.where(Material.is_produce == int(is_produce))
        count_query = select(func.count()).select_from(query.subquery())

    if status is not None and status != "":
        statuses = [s.strip() for s in str(status).split(",") if s.strip() != ""]
        if len(statuses) == 1:
            query = query.where(Material.status == int(statuses[0]))
        elif statuses:
            query = query.where(Material.status.in_([int(s) for s in statuses]))
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Material.update_time >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Material.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    items = [{
        "id": m.id,
        "erp_material_id": m.erp_material_id,
        "material_code": m.material_code,
        "material_name": m.material_name,
        "spec_model": m.spec_model,
        "material_type": m.material_type,
        "unit_of_measure": m.unit_of_measure,
        "brand": m.brand,
        "is_purchase": m.is_purchase,
        "is_produce": m.is_produce,
        "status": m.status,
        "supplier_id": m.supplier_id,
        "supplier_name": supplier_name,
        "order_unit_price": float(m.order_unit_price) if m.order_unit_price is not None else None,
        "last_outbound_date": m.last_outbound_date.isoformat() if m.last_outbound_date else None,
        "update_time": m.update_time.isoformat() if m.update_time else None,
    } for m, supplier_name in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════
# 产品
# ═══════════════════════════════════════════

@register_external(
    "products.list",
    "产品列表",
    method="GET",
    path="/products/list",
    description="产品主数据列表查询，支持关键字、产品线、增量同步",
    tags=["主数据"],
)
async def products_list(ctx: ExternalCallContext) -> dict:
    """产品列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（产品编码模糊匹配）
        product_line: 产品线精确匹配
        updated_after: 增量同步 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    product_line = params.get("product_line")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(Product)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        query = query.where(Product.product_code.ilike(f"%{keyword}%"))
        count_query = select(func.count()).select_from(query.subquery())

    if product_line:
        query = query.where(Product.product_line == product_line)
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Product.update_time >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Product.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "product_code": r.product_code,
        "product_line": r.product_line,
        "tech_version": r.tech_version,
        "bom_version": r.bom_version,
        "default_warehouse": r.default_warehouse,
        "warranty_days": r.warranty_days,
        "upph": float(r.upph) if r.upph is not None else None,
        "update_time": r.update_time.isoformat() if r.update_time else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
