"""基础数据与集成中心 — 基础数据CRUD API"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.schemas.common import ResponseModel
from app.schemas.basicdata.schemas import (
    CustomerCreate, CustomerUpdate, CustomerOut,
    SupplierCreate, SupplierUpdate, SupplierOut,
    MaterialCreate, MaterialUpdate, MaterialOut, MaterialTreeNode,
    SKUCreate, SKUUpdate, SKUOut,
    ProductCreate, ProductUpdate, ProductOut,
    WarehouseCreate, WarehouseUpdate, WarehouseOut,
    ProcessCreate, ProcessUpdate, ProcessOut,
    OrganizationCreate, OrganizationUpdate, OrganizationOut, OrganizationTreeNode, OrganizationWithLeaderOut,
    EmployeeCreate, EmployeeUpdate, EmployeeOut,
)
from app.models.basicdata import (
    Customer, Supplier, Material, SKU, Product,
    Warehouse, Process, Organization, Employee,
)
router = APIRouter()


def _apply_sort(query, model, sort_by: Optional[str], sort_order: Optional[str], sortable: dict):
    """通用排序辅助函数"""
    order_clauses = []
    if sort_by and sort_by in sortable:
        col = sortable[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [model.id.desc()]
    return query.order_by(*order_clauses)



# ── Customer ──
@router.get("/customers", response_model=ResponseModel[dict])
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索编码/名称"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    customer_level: Optional[str] = Query(None, description="客户等级筛选，逗号分隔"),
    status: Optional[str] = Query(None, description="状态筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))
):
    """查询客户列表（分页+排序+筛选）"""
    SORTABLE = {
        'customer_code': Customer.customer_code,
        'customer_name': Customer.customer_name,
        'customer_short': Customer.customer_short,
        'customer_level': Customer.customer_level,
        'status': Customer.status,
    }
    query = select(Customer)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Customer.customer_code.ilike(like), Customer.customer_name.ilike(like)))
    if customer_level:
        levels = [l.strip() for l in customer_level.split(",") if l.strip()]
        if levels:
            query = query.where(Customer.customer_level.in_(levels))
    if status:
        statuses = [int(s.strip()) for s in status.split(",") if s.strip().isdigit()]
        if statuses:
            query = query.where(Customer.status.in_(statuses))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Customer, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [CustomerOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/customers/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    """查询单个客户"""
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="客户不存在")
    return item


@router.post("/customers", response_model=CustomerOut)
async def create_customer(customer: CustomerCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """创建客户"""
    # 检查编码唯一性
    result = await db.execute(select(Customer).filter(Customer.customer_code == customer.customer_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="客户编码已存在")
    
    db_item = Customer(**customer.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "customer", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/customers/{customer_id}", response_model=CustomerOut)
async def update_customer(customer_id: int, customer: CustomerUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新客户"""
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="客户不存在")
    
    update_data = customer.model_dump(exclude_unset=True)
    await log_audit(db, "customer", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """删除客户"""
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="客户不存在")
    
    await log_audit(db, "customer", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


# ── Supplier ──
@router.get("/suppliers", response_model=ResponseModel[dict])
async def list_suppliers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索编码/名称"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    supplier_type: Optional[str] = Query(None, description="供应商类型筛选，逗号分隔"),
    status: Optional[str] = Query(None, description="状态筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))
):
    """查询供应商列表（分页+排序+筛选）"""
    SORTABLE = {
        'supplier_code': Supplier.supplier_code,
        'supplier_name': Supplier.supplier_name,
        'supplier_type': Supplier.supplier_type,
        'contact_person': Supplier.contact_person,
        'status': Supplier.status,
    }
    query = select(Supplier)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Supplier.supplier_code.ilike(like), Supplier.supplier_name.ilike(like)))
    if supplier_type:
        types = [t.strip() for t in supplier_type.split(",") if t.strip()]
        if types:
            query = query.where(Supplier.supplier_type.in_(types))
    if status:
        statuses = [int(s.strip()) for s in status.split(",") if s.strip().isdigit()]
        if statuses:
            query = query.where(Supplier.status.in_(statuses))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Supplier, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [SupplierOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
async def get_supplier(supplier_id: int, db: AsyncSession = Depends(get_db)):
    """查询单个供应商"""
    result = await db.execute(select(Supplier).filter(Supplier.id == supplier_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return item


@router.post("/suppliers", response_model=SupplierOut)
async def create_supplier(supplier: SupplierCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """创建供应商"""
    result = await db.execute(select(Supplier).filter(Supplier.supplier_code == supplier.supplier_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="供应商编码已存在")
    
    db_item = Supplier(**supplier.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "supplier", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
async def update_supplier(supplier_id: int, supplier: SupplierUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """更新供应商"""
    result = await db.execute(select(Supplier).filter(Supplier.id == supplier_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    update_data = supplier.model_dump(exclude_unset=True)
    await log_audit(db, "supplier", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """删除供应商"""
    result = await db.execute(select(Supplier).filter(Supplier.id == supplier_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    await log_audit(db, "supplier", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


# ── Material ──
@router.get("/materials/tree", response_model=ResponseModel[List[MaterialTreeNode]])
async def get_material_tree(db: AsyncSession = Depends(get_db)):
    """查询物料树形结构"""
    result = await db.execute(
        select(Material)
        .filter(Material.is_deleted == 0)
        .order_by(Material.parent_id.nullsfirst(), Material.id)
    )
    all_items = result.scalars().all()

    node_map: dict[str, MaterialTreeNode] = {}
    roots: List[MaterialTreeNode] = []
    for item in all_items:
        node = MaterialTreeNode(
            id=item.id, material_id=item.material_id, parent_id=item.parent_id,
            material_code=item.material_code, material_name=item.material_name,
            spec_model=item.spec_model, material_type=item.material_type,
            unit_of_measure=item.unit_of_measure, brand=item.brand,
            is_purchase=item.is_purchase, is_produce=item.is_produce,
            status=item.status, children=[],
        )
        node_map[item.material_id] = node
        if item.parent_id is None:
            roots.append(node)
        else:
            parent = node_map.get(item.parent_id)
            if parent:
                parent.children.append(node)
            else:
                roots.append(node)
    return ResponseModel(data=roots)


@router.get("/materials", response_model=ResponseModel[dict])
async def list_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    parent_id: Optional[str] = Query(None, description="父级物料ID筛选, 'root'表示根级"),
    keyword: Optional[str] = Query(None, description="搜索编码/名称"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    material_type: Optional[str] = Query(None, description="物料分类筛选，逗号分隔"),
    status: Optional[str] = Query(None, description="状态筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))
):
    """查询物料列表（分页+排序+筛选, 默认排除已删除）"""
    SORTABLE = {
        'material_code': Material.material_code,
        'material_name': Material.material_name,
        'spec_model': Material.spec_model,
        'material_type': Material.material_type,
        'unit_of_measure': Material.unit_of_measure,
        'status': Material.status,
    }
    query = select(Material).filter(Material.is_deleted == 0)
    if parent_id is not None:
        if parent_id == 'root':
            query = query.filter(Material.parent_id.is_(None))
        else:
            query = query.filter(Material.parent_id == parent_id)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Material.material_code.ilike(like), Material.material_name.ilike(like)))
    if material_type:
        types = [t.strip() for t in material_type.split(",") if t.strip()]
        if types:
            query = query.where(Material.material_type.in_(types))
    if status:
        statuses = [int(s.strip()) for s in status.split(",") if s.strip().isdigit()]
        if statuses:
            query = query.where(Material.status.in_(statuses))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Material, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [MaterialOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/materials/{material_id}", response_model=MaterialOut)
async def get_material(material_id: str, db: AsyncSession = Depends(get_db)):
    """查询单个物料"""
    result = await db.execute(
        select(Material).filter(Material.material_id == material_id, Material.is_deleted == 0)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="物料不存在")
    return item


@router.post("/materials", response_model=MaterialOut)
async def create_material(material: MaterialCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建物料"""
    result = await db.execute(select(Material).filter(Material.material_id == material.material_id))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="物料ID已存在")
    
    db_item = Material(**material.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "material", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/materials/{material_id}", response_model=MaterialOut)
async def update_material(material_id: str, material: MaterialUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新物料"""
    result = await db.execute(select(Material).filter(Material.material_id == material_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="物料不存在")
    
    update_data = material.model_dump(exclude_unset=True)
    await log_audit(db, "material", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/materials/{material_id}")
async def delete_material(material_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """逻辑删除物料"""
    result = await db.execute(
        select(Material).filter(Material.material_id == material_id, Material.is_deleted == 0)
    )
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="物料不存在")
    
    await log_audit(db, "material", db_item.id, "delete", operator=current_user["username"])
    db_item.is_deleted = 1
    await db.commit()
    return {"message": "删除成功"}


# ── SKU ──
@router.get("/skus", response_model=ResponseModel[dict])
async def list_skus(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索编码/名称"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """查询SKU列表（分页+排序+筛选）"""
    SORTABLE = {
        'sku_code': SKU.sku_code,
        'sku_name': SKU.sku_name,
        'material_id': SKU.material_id,
        'barcode': SKU.barcode,
    }
    query = select(SKU)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(SKU.sku_code.ilike(like), SKU.sku_name.ilike(like)))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, SKU, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [SKUOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/skus/{sku_id}", response_model=SKUOut)
async def get_sku(sku_id: int, db: AsyncSession = Depends(get_db)):
    """查询单个SKU"""
    result = await db.execute(select(SKU).filter(SKU.id == sku_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="SKU不存在")
    return item


@router.post("/skus", response_model=SKUOut)
async def create_sku(sku: SKUCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建SKU"""
    result = await db.execute(select(SKU).filter(SKU.sku_code == sku.sku_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="SKU编码已存在")
    
    db_item = SKU(**sku.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "sku", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/skus/{sku_id}", response_model=SKUOut)
async def update_sku(sku_id: int, sku: SKUUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新SKU"""
    result = await db.execute(select(SKU).filter(SKU.id == sku_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="SKU不存在")
    
    update_data = sku.model_dump(exclude_unset=True)
    await log_audit(db, "sku", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/skus/{sku_id}")
async def delete_sku(sku_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """删除SKU"""
    result = await db.execute(select(SKU).filter(SKU.id == sku_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="SKU不存在")
    
    await log_audit(db, "sku", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


# ── Product ──
@router.get("/products", response_model=ResponseModel[dict])
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索编码"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """查询产品列表（分页+排序+筛选）"""
    SORTABLE = {
        'product_code': Product.product_code,
        'product_line': Product.product_line,
        'tech_version': Product.tech_version,
        'bom_version': Product.bom_version,
    }
    query = select(Product)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(Product.product_code.ilike(like))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Product, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [ProductOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """查询单个产品"""
    result = await db.execute(select(Product).filter(Product.id == product_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="产品不存在")
    return item


@router.post("/products", response_model=ProductOut)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建产品"""
    result = await db.execute(select(Product).filter(Product.product_code == product.product_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="产品编码已存在")
    
    db_item = Product(**product.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "product", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/products/{product_id}", response_model=ProductOut)
async def update_product(product_id: int, product: ProductUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新产品"""
    result = await db.execute(select(Product).filter(Product.id == product_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="产品不存在")
    
    update_data = product.model_dump(exclude_unset=True)
    await log_audit(db, "product", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """删除产品"""
    result = await db.execute(select(Product).filter(Product.id == product_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="产品不存在")
    
    await log_audit(db, "product", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


# ── Warehouse ──
@router.get("/warehouses", response_model=ResponseModel[dict])
async def list_warehouses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索编码/名称"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    wh_type: Optional[str] = Query(None, description="仓库类型筛选，逗号分隔"),
    is_enabled: Optional[str] = Query(None, description="启用状态筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db)
):
    """查询仓库列表（分页+排序+筛选）"""
    SORTABLE = {
        'wh_code': Warehouse.wh_code,
        'wh_name': Warehouse.wh_name,
        'wh_type': Warehouse.wh_type,
        'is_enabled': Warehouse.is_enabled,
    }
    query = select(Warehouse)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Warehouse.wh_code.ilike(like), Warehouse.wh_name.ilike(like)))
    if wh_type:
        types = [t.strip() for t in wh_type.split(",") if t.strip()]
        if types:
            query = query.where(Warehouse.wh_type.in_(types))
    if is_enabled:
        statuses = [int(s.strip()) for s in is_enabled.split(",") if s.strip().isdigit()]
        if statuses:
            query = query.where(Warehouse.is_enabled.in_(statuses))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Warehouse, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [WarehouseOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def get_warehouse(warehouse_id: int, db: AsyncSession = Depends(get_db)):
    """查询单个仓库"""
    result = await db.execute(select(Warehouse).filter(Warehouse.id == warehouse_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="仓库不存在")
    return item


@router.post("/warehouses", response_model=WarehouseOut)
async def create_warehouse(warehouse: WarehouseCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建仓库"""
    result = await db.execute(select(Warehouse).filter(Warehouse.wh_code == warehouse.wh_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="仓库编码已存在")
    
    db_item = Warehouse(**warehouse.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "warehouse", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def update_warehouse(warehouse_id: int, warehouse: WarehouseUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新仓库"""
    result = await db.execute(select(Warehouse).filter(Warehouse.id == warehouse_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    update_data = warehouse.model_dump(exclude_unset=True)
    await log_audit(db, "warehouse", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/warehouses/{warehouse_id}")
async def delete_warehouse(warehouse_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """删除仓库"""
    result = await db.execute(select(Warehouse).filter(Warehouse.id == warehouse_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    await log_audit(db, "warehouse", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


# ── Process ──
@router.get("/processes", response_model=ResponseModel[dict])
async def list_processes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索编码/名称"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    process_group: Optional[str] = Query(None, description="工序分组筛选，逗号分隔"),
    is_qc_point: Optional[str] = Query(None, description="质检点筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db)
):
    """查询工序列表（分页+排序+筛选）"""
    SORTABLE = {
        'process_code': Process.process_code,
        'process_name': Process.process_name,
        'process_group': Process.process_group,
        'work_center': Process.work_center,
        'is_qc_point': Process.is_qc_point,
    }
    query = select(Process)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Process.process_code.ilike(like), Process.process_name.ilike(like)))
    if process_group:
        groups = [g.strip() for g in process_group.split(",") if g.strip()]
        if groups:
            query = query.where(Process.process_group.in_(groups))
    if is_qc_point:
        vals = [int(v.strip()) for v in is_qc_point.split(",") if v.strip().isdigit()]
        if vals:
            query = query.where(Process.is_qc_point.in_(vals))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Process, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [ProcessOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/processes/{process_id}", response_model=ProcessOut)
async def get_process(process_id: int, db: AsyncSession = Depends(get_db)):
    """查询单个工序"""
    result = await db.execute(select(Process).filter(Process.id == process_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工序不存在")
    return item


@router.post("/processes", response_model=ProcessOut)
async def create_process(process: ProcessCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建工序"""
    result = await db.execute(select(Process).filter(Process.process_code == process.process_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="工序编码已存在")
    
    db_item = Process(**process.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "process", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/processes/{process_id}", response_model=ProcessOut)
async def update_process(process_id: int, process: ProcessUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新工序"""
    result = await db.execute(select(Process).filter(Process.id == process_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="工序不存在")
    
    update_data = process.model_dump(exclude_unset=True)
    await log_audit(db, "process", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/processes/{process_id}")
async def delete_process(process_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """删除工序"""
    result = await db.execute(select(Process).filter(Process.id == process_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="工序不存在")
    
    await log_audit(db, "process", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


# ── Organization ──
@router.get("/organizations/tree", response_model=ResponseModel[List[OrganizationTreeNode]])
async def get_organization_tree(db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """查询组织树形结构（含负责人姓名）"""
    result = await db.execute(
        select(
            Organization,
            Employee.emp_name.label('leader_name')
        )
        .outerjoin(Employee, Organization.leader_id == Employee.id)
        .order_by(Organization.parent_id.nullsfirst(), Organization.id)
    )
    all_items = result.all()

    node_map: dict[str, OrganizationTreeNode] = {}
    roots: List[OrganizationTreeNode] = []
    
    # 第一遍：创建所有节点
    # 如果有 oa_org_id 则用 oa_org_id 作为key，否则用 id（转为字符串）
    for org, leader_name in all_items:
        node = OrganizationTreeNode(
            id=org.id,
            org_code=org.org_code,
            org_name=org.org_name,
            org_type=org.org_type,
            parent_id=org.parent_id,
            leader_id=org.leader_id,
            leader_name=leader_name,
            oa_org_id=org.oa_org_id,
            status=org.status,
            data_source=org.data_source,
            children=[],
        )
        # 使用 oa_org_id 或 id（转为字符串）作为key
        node_key = org.oa_org_id if org.oa_org_id else str(org.id)
        node_map[node_key] = node
    
    # 第二遍：构建树结构，parent_id 引用的是 oa_org_id
    for org, leader_name in all_items:
        # 获取当前节点的key
        node_key = org.oa_org_id if org.oa_org_id else str(org.id)
        node = node_map.get(node_key)
        if not node:
            continue
        
        if org.parent_id is None or org.parent_id == 0:
            roots.append(node)
        else:
            # parent_id 引用的是 oa_org_id
            parent = node_map.get(str(org.parent_id))
            if parent:
                parent.children.append(node)
            else:
                roots.append(node)
    return ResponseModel(data=roots)


@router.get("/organizations", response_model=ResponseModel[dict])
async def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索编码/名称"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    org_type: Optional[str] = Query(None, description="组织类型筛选，逗号分隔"),
    status: Optional[str] = Query(None, description="状态筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))
):
    """查询组织列表（分页+排序+筛选，含负责人姓名）"""
    SORTABLE = {
        'org_code': Organization.org_code,
        'org_name': Organization.org_name,
        'org_type': Organization.org_type,
        'parent_id': Organization.parent_id,
        'status': Organization.status,
    }
    query = select(Organization, Employee.emp_name.label('leader_name')).outerjoin(Employee, Organization.leader_id == Employee.id)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Organization.org_code.ilike(like), Organization.org_name.ilike(like)))
    if org_type:
        types = [t.strip() for t in org_type.split(",") if t.strip()]
        if types:
            query = query.where(Organization.org_type.in_(types))
    if status:
        statuses = [int(s.strip()) for s in status.split(",") if s.strip().isdigit()]
        if statuses:
            query = query.where(Organization.status.in_(statuses))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Organization, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = []
    for org, leader_name in result.all():
        org_out = OrganizationWithLeaderOut.model_validate(org)
        org_out.leader_name = leader_name
        items.append(org_out)
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/organizations/{org_id}", response_model=OrganizationWithLeaderOut)
async def get_organization(org_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """查询单个组织（含负责人姓名）"""
    result = await db.execute(
        select(Organization, Employee.emp_name.label('leader_name'))
        .outerjoin(Employee, Organization.leader_id == Employee.id)
        .filter(Organization.id == org_id)
    )
    item = result.first()
    if not item:
        raise HTTPException(status_code=404, detail="组织不存在")
    org, leader_name = item
    org_out = OrganizationWithLeaderOut.model_validate(org)
    org_out.leader_name = leader_name
    return org_out


@router.post("/organizations", response_model=OrganizationOut)
async def create_organization(org: OrganizationCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建组织"""
    result = await db.execute(select(Organization).filter(Organization.org_code == org.org_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="组织编码已存在")
    
    db_item = Organization(**org.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "organization", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/organizations/{org_id}", response_model=OrganizationOut)
async def update_organization(org_id: int, org: OrganizationUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新组织"""
    result = await db.execute(select(Organization).filter(Organization.id == org_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    update_data = org.model_dump(exclude_unset=True)
    await log_audit(db, "organization", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/organizations/{org_id}")
async def delete_organization(org_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """删除组织"""
    result = await db.execute(select(Organization).filter(Organization.id == org_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    await log_audit(db, "organization", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


# ── Employee ──
@router.get("/employees", response_model=ResponseModel[dict])
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索工号/姓名"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="状态筛选，逗号分隔"),
    org_id: Optional[int] = Query(None, description="所属组织ID筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))
):
    """查询人员列表（分页+排序+筛选）"""
    SORTABLE = {
        'emp_code': Employee.emp_code,
        'emp_name': Employee.emp_name,
        'org_id': Employee.org_id,
        'position': Employee.position,
        'phone': Employee.phone,
        'status': Employee.status,
    }
    query = select(Employee)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Employee.emp_code.ilike(like), Employee.emp_name.ilike(like)))
    if status:
        statuses = [int(s.strip()) for s in status.split(",") if s.strip().isdigit()]
        if statuses:
            query = query.where(Employee.status.in_(statuses))
    if org_id is not None:
        query = query.where(Employee.org_id == org_id)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = _apply_sort(query, Employee, sort_by, sort_order, SORTABLE)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [EmployeeOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))):
    """查询单个人员"""
    result = await db.execute(select(Employee).filter(Employee.id == employee_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="人员不存在")
    return item


@router.post("/employees", response_model=EmployeeOut)
async def create_employee(employee: EmployeeCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建人员"""
    result = await db.execute(select(Employee).filter(Employee.emp_code == employee.emp_code))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="员工工号已存在")
    
    db_item = Employee(**employee.model_dump())
    db.add(db_item)
    await db.flush()
    await log_audit(db, "employee", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/employees/{employee_id}", response_model=EmployeeOut)
async def update_employee(employee_id: int, employee: EmployeeUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新人员"""
    result = await db.execute(select(Employee).filter(Employee.id == employee_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="人员不存在")
    
    update_data = employee.model_dump(exclude_unset=True)
    await log_audit(db, "employee", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """删除人员"""
    result = await db.execute(select(Employee).filter(Employee.id == employee_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="人员不存在")
    
    await log_audit(db, "employee", db_item.id, "delete", operator=current_user["username"])
    await db.delete(db_item)
    await db.commit()
    return {"message": "删除成功"}


@router.get("/organizations/{org_identifier}/employees", response_model=ResponseModel[dict])
async def get_organization_employees(
    org_identifier: str,
    keyword: Optional[str] = Query(None, description="搜索工号/姓名"),
    status: Optional[str] = Query(None, description="状态筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data", "read"))
):
    """查询指定组织下的全部员工列表（支持通过 id 或 oa_org_id 查询，不分页）"""
    SORTABLE = {
        'emp_code': Employee.emp_code,
        'emp_name': Employee.emp_name,
        'position': Employee.position,
        'status': Employee.status,
    }
    
    # 前端传 oa_org_id；为兼容历史调用，找不到时再兜底按内部 id 查询。
    org_result = await db.execute(select(Organization).where(Organization.oa_org_id == org_identifier))
    org = org_result.scalar_one_or_none()

    if not org:
        if org_identifier.isdigit():
            org_result = await db.execute(select(Organization).where(Organization.id == int(org_identifier)))
            org = org_result.scalar_one_or_none()
    
    if not org:
        return ResponseModel(data={"items": [], "total": 0})
    
    # 员工表 org_id 存的是组织表 oa_org_id；手工组织没有 oa_org_id 时兜底使用内部 id。
    employee_org_id = int(org.oa_org_id) if org.oa_org_id and str(org.oa_org_id).isdigit() else org.id
    query = select(Employee).where(Employee.org_id == employee_org_id)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Employee.emp_code.ilike(like), Employee.emp_name.ilike(like)))
    if status:
        statuses = [int(s.strip()) for s in status.split(",") if s.strip().isdigit()]
        if statuses:
            query = query.where(Employee.status.in_(statuses))

    query = _apply_sort(query, Employee, None, None, SORTABLE)
    result = await db.execute(query)
    items = [EmployeeOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": len(items)})
