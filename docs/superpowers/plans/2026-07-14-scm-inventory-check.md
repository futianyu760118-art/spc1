# 物料盘点 (`scm_inventory_check`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the existing `OrderInventoryCheck` JSONB-snapshot feature with a new material-centric inventory check (`scm_inventory_check` + `scm_inventory_check_item`) that records per-material actual counted quantity and a "is_checked" flag, BOM-expanded from a source order. No scm_inventory writeback (no stock adjustment).

**Architecture:** Two new tables (header + line items), one new service module that reuses `order_materials_service.get_order_product_materials` for BOM explosion and a new `material_id`-keyed stock snapshot helper, one new API router mounted at `/materials/stock-check`. Frontend: a new `OrderDelivery/StockCheck` page with inline-editable `actual_qty` + `is_checked` cells. The old `OrderInventoryCheck` is fully removed from both backend and frontend (old table and Alembic files kept for history).

**Tech Stack:** FastAPI + SQLAlchemy (async) + Pydantic v2 + Ant Design 5 + Zustand. Python 3.12, Node 20. Permission gates use `PermissionChecker("orders.stock_check", ...)`.

## Global Constraints

- All response envelopes must be `ResponseModel[T]` (`{code, message, data}`); code 0 is success — see `backend/app/schemas/common.py:9`.
- `get_db()` from `app/core/database.py` auto-commits on success and rolls back on exception; do **not** call `db.commit()` inside endpoints.
- New tables are auto-created by `init_database.py`'s `Base.metadata.create_all` on container start. **No Alembic migration needed** for new tables.
- The frontend axios interceptor (`frontend/src/services/api.ts`) treats `response.data.code !== 0` as a failure.
- `npm run build` (i.e. `tsc -b && vite build`) is the **only** typecheck (per AGENTS.md).
- Add comments only when explicitly requested.

---

## Task 1: New backend model — `StockCheck` + `StockCheckItem`

**Files:**
- Create: `backend/app/models/material/inventory_check.py`
- Modify: `backend/app/models/material/__init__.py`

**Step 1: Create the new model file**

Create `D:\wanghuazheng\project\SPC-v2\backend\app\models\material\inventory_check.py`:

```python
"""物料齐套中心 — 物料盘点单模型（盘点单头 + 物料行）"""

from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, DateTime, Date, Text,
    UniqueConstraint, Index, ForeignKey,
)
from sqlalchemy.sql import func

from app.core.database import Base


class StockCheck(Base):
    __tablename__ = "scm_inventory_check"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    check_no = Column(String(32), nullable=False, unique=True, comment="盘点单号 PDyyyyMMdd-NNN")
    order_no = Column(String(64), nullable=False, index=True, comment="触发起源订单号")
    title = Column(String(200), nullable=True, comment="盘点单标题")
    check_type = Column(String(16), nullable=False, default="order", comment="order/manual/cycle_count")
    status = Column(String(16), nullable=False, default="open", comment="open/in_progress/completed/cancelled")
    check_date = Column(Date, nullable=False, comment="盘点日期")
    total_materials = Column(Integer, nullable=False, default=0, comment="应盘物料数")
    checked_materials = Column(Integer, nullable=False, default=0, comment="已盘物料数")
    total_diff_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="总差异数")
    created_by = Column(String(100), nullable=True)
    checked_by = Column(String(100), nullable=True, comment="完工人")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    remark = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_scm_inventory_check_order_date", "order_no", "check_date"),
    )


class StockCheckItem(Base):
    __tablename__ = "scm_inventory_check_item"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    check_id = Column(BigInteger, ForeignKey("scm_inventory_check.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no = Column(String(32), nullable=True, comment="关联 SaleOrderLine 行号(跨行聚合行时为空)")
    material_id = Column(BigInteger, nullable=True, index=True, comment="物料ID")
    material_code = Column(String(50), nullable=True)
    material_name = Column(String(200), nullable=True)
    spec_model = Column(String(200), nullable=True)
    unit = Column(String(20), nullable=True)
    req_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="应盘数(BOM standard_qty × order_qty)")
    system_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="库存数(快照)")
    actual_qty = Column(Numeric(18, 4), nullable=True, comment="盘点数(用户录入)")
    diff_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="差异数=actual-system")
    is_checked = Column(Integer, nullable=False, default=0, comment="盘点标记 0否1是")
    checked_at = Column(DateTime, nullable=True)
    checked_by = Column(String(100), nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("check_id", "material_id", "line_no", name="uq_stock_check_item"),
    )
```

**Step 2: Register the new model in `material/__init__.py`**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\models\material\__init__.py`:

Add at the end (after the existing 9 imports):
```python
from app.models.material.inventory_check import StockCheck, StockCheckItem  # noqa: F401
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
python -c "from app.models.material.inventory_check import StockCheck, StockCheckItem; print(StockCheck.__tablename__, StockCheckItem.__tablename__)"
```
Expected output: `scm_inventory_check scm_inventory_check_item`

---

## Task 2: New Pydantic schemas

**Files:**
- Create: `backend/app/schemas/material/stock_check.py`

**Step 1: Create the schemas file**

Create `D:\wanghuazheng\project\SPC-v2\backend\app\schemas\material\stock_check.py`:

```python
"""物料盘点 (scm_inventory_check) Schemas"""

from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class StockCheckCreate(BaseModel):
    """从订单创建盘点单的入参"""
    order_no: str
    title: Optional[str] = None
    check_date: Optional[date] = None
    remark: Optional[str] = None


class StockCheckItemUpdate(BaseModel):
    """单行更新(单行 PUT 或批量 batch 的子项)"""
    id: Optional[int] = None
    actual_qty: Optional[Decimal] = None
    is_checked: Optional[int] = None
    remark: Optional[str] = None


class StockCheckItemBatchUpdate(BaseModel):
    check_id: int
    items: List[StockCheckItemUpdate]


class StockCheckItemOut(BaseModel):
    id: int
    check_id: int
    line_no: Optional[str] = None
    material_id: Optional[int] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    req_qty: Optional[Decimal] = None
    system_qty: Optional[Decimal] = None
    actual_qty: Optional[Decimal] = None
    diff_qty: Optional[Decimal] = None
    is_checked: Optional[int] = None
    checked_at: Optional[datetime] = None
    checked_by: Optional[str] = None
    remark: Optional[str] = None

    model_config = {"from_attributes": True}


class StockCheckOut(BaseModel):
    id: int
    check_no: str
    order_no: str
    title: Optional[str] = None
    check_type: Optional[str] = None
    status: Optional[str] = None
    check_date: Optional[date] = None
    total_materials: Optional[int] = None
    checked_materials: Optional[int] = None
    total_diff_qty: Optional[Decimal] = None
    created_by: Optional[str] = None
    checked_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    remark: Optional[str] = None
    items: List[StockCheckItemOut] = []

    model_config = {"from_attributes": True}


class StockCheckListOut(BaseModel):
    id: int
    check_no: str
    order_no: str
    title: Optional[str] = None
    status: Optional[str] = None
    check_date: Optional[date] = None
    total_materials: Optional[int] = None
    checked_materials: Optional[int] = None
    total_diff_qty: Optional[Decimal] = None
    created_by: Optional[str] = None
    checked_by: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
python -c "from app.schemas.material.stock_check import StockCheckCreate, StockCheckOut, StockCheckItemOut, StockCheckListOut; print('ok')"
```
Expected output: `ok`

---

## Task 3: New service module — `stock_check_service.py`

**Files:**
- Create: `backend/app/services/material/stock_check_service.py`

**Step 1: Create the service file**

Create `D:\wanghuazheng\project\SPC-v2\backend\app\services\material\stock_check_service.py`:

```python
"""物料盘点 (scm_inventory_check) 业务服务"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict

from sqlalchemy import select, func, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db  # noqa: F401  (re-exported for tests)
from app.models.basicdata.inventory import Inventory
from app.models.material.inventory_check import StockCheck, StockCheckItem
from app.models.order.sale_order import SaleOrder
from app.services.order.order_materials_service import get_order_product_materials


def _gen_check_no(seq: int) -> str:
    return f"PD{datetime.now().strftime('%Y%m%d')}-{seq:03d}"


async def _get_stock_by_material_id(
    db: AsyncSession,
    material_ids: List[int],
) -> Dict[int, Decimal]:
    """按 material_id 聚合 scm_inventory.qty_on_hand"""
    if not material_ids:
        return {}
    result = await db.execute(
        select(
            Inventory.material_id,
            func.coalesce(func.sum(Inventory.qty_on_hand), 0).label("total_qty"),
        )
        .where(Inventory.material_id.in_(material_ids))
        .group_by(Inventory.material_id)
    )
    return {row.material_id: Decimal(str(row.total_qty or 0)) for row in result}


async def _refresh_check_aggregates(db: AsyncSession, check_id: int) -> None:
    """刷新头表 total_materials / checked_materials / total_diff_qty"""
    items_agg = await db.execute(
        select(
            func.count(StockCheckItem.id).label("total"),
            func.coalesce(func.sum(StockCheckItem.is_checked), 0).label("checked"),
            func.coalesce(func.sum(StockCheckItem.diff_qty), 0).label("diff"),
        ).where(StockCheckItem.check_id == check_id)
    )
    row = items_agg.one()
    head = await db.execute(select(StockCheck).where(StockCheck.id == check_id))
    head_obj: Optional[StockCheck] = head.scalar_one_or_none()
    if head_obj:
        head_obj.total_materials = int(row.total or 0)
        head_obj.checked_materials = int(row.checked or 0)
        head_obj.total_diff_qty = Decimal(str(row.diff or 0))


async def _next_seq_for_today(db: AsyncSession) -> int:
    today_prefix = f"PD{datetime.now().strftime('%Y%m%d')}-"
    res = await db.execute(
        select(StockCheck.check_no).where(StockCheck.check_no.like(f"{today_prefix}%"))
    )
    existing = [r[0] for r in res.all()]
    max_seq = 0
    for no in existing:
        try:
            seq = int(no.split("-")[-1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError):
            pass
    return max_seq + 1


async def create_stock_check_from_order(
    db: AsyncSession,
    order_no: str,
    current_user: dict,
    *,
    title: Optional[str] = None,
    check_date: Optional[date] = None,
    remark: Optional[str] = None,
) -> StockCheck:
    """从订单创建盘点单: BOM 展开 + 聚合 system_qty + 写头/行"""
    order = (await db.execute(select(SaleOrder.id).where(SaleOrder.order_no == order_no))).scalar_one_or_none()
    if not order:
        raise ValueError(f"订单 {order_no} 不存在")

    line_materials = await get_order_product_materials(db, order_no=order_no)
    agg: Dict[int, Dict] = {}
    for lm in line_materials:
        for it in (lm.materials or []):
            if not it.material_id:
                continue
            mid = int(it.material_id)
            entry = agg.setdefault(mid, {
                "line_no": lm.line_no,
                "material_id": mid,
                "material_code": it.material_code,
                "material_name": it.material_name,
                "spec_model": it.spec_model,
                "unit": it.unit,
                "req_qty": Decimal("0"),
            })
            entry["req_qty"] += Decimal(str(it.req_qty or 0))

    if not agg:
        raise ValueError(f"订单 {order_no} 未展开出任何物料,无法创建盘点单")

    stock_map = await _get_stock_by_material_id(db, list(agg.keys()))

    seq = await _next_seq_for_today(db)
    check_no = _gen_check_no(seq)

    head = StockCheck(
        check_no=check_no,
        order_no=order_no,
        title=title or f"{order_no} 盘点 {datetime.now().strftime('%Y-%m-%d')}",
        check_type="order",
        status="in_progress",
        check_date=check_date or date.today(),
        created_by=current_user.get("username", ""),
        remark=remark,
    )
    db.add(head)
    await db.flush()

    item_rows: List[StockCheckItem] = []
    for mid, e in agg.items():
        sys_q = stock_map.get(mid, Decimal("0"))
        item_rows.append(StockCheckItem(
            check_id=head.id,
            line_no=None,  # 跨行聚合行
            material_id=mid,
            material_code=e["material_code"],
            material_name=e["material_name"],
            spec_model=e["spec_model"],
            unit=e["unit"],
            req_qty=e["req_qty"],
            system_qty=sys_q,
            actual_qty=None,
            diff_qty=Decimal("0"),
            is_checked=0,
        ))
    db.add_all(item_rows)
    await db.flush()

    await _refresh_check_aggregates(db, head.id)
    await db.flush()
    return head


async def update_stock_check_item(
    db: AsyncSession,
    item_id: int,
    *,
    actual_qty: Optional[Decimal] = None,
    is_checked: Optional[int] = None,
    remark: Optional[str] = None,
    current_user: Optional[dict] = None,
) -> StockCheckItem:
    item = (await db.execute(select(StockCheckItem).where(StockCheckItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise ValueError(f"盘点行 {item_id} 不存在")
    if actual_qty is not None:
        item.actual_qty = Decimal(str(actual_qty))
    if remark is not None:
        item.remark = remark
    if is_checked is not None:
        item.is_checked = int(is_checked)
        if int(is_checked) == 1:
            item.checked_at = datetime.utcnow()
            if current_user:
                item.checked_by = current_user.get("username", "")
        else:
            item.checked_at = None
            item.checked_by = None
    if item.actual_qty is not None and item.system_qty is not None:
        item.diff_qty = Decimal(str(item.actual_qty)) - Decimal(str(item.system_qty))
    await _refresh_check_aggregates(db, item.check_id)
    await db.flush()
    return item


async def batch_update_items(
    db: AsyncSession,
    check_id: int,
    items: List[dict],
    current_user: dict,
) -> int:
    n = 0
    for it in items:
        if it.get("id") is None:
            continue
        await update_stock_check_item(
            db,
            int(it["id"]),
            actual_qty=it.get("actual_qty"),
            is_checked=it.get("is_checked"),
            remark=it.get("remark"),
            current_user=current_user,
        )
        n += 1
    return n


async def complete_stock_check(db: AsyncSession, check_id: int, current_user: dict) -> StockCheck:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if head.status == "cancelled":
        raise ValueError("已取消的盘点单不能完结")
    total = (await db.execute(
        select(func.count(StockCheckItem.id)).where(StockCheckItem.check_id == check_id)
    )).scalar_one()
    checked = (await db.execute(
        select(func.count(StockCheckItem.id)).where(
            StockCheckItem.check_id == check_id, StockCheckItem.is_checked == 1
        )
    )).scalar_one()
    if int(total or 0) == 0:
        raise ValueError("盘点单无物料行,无法完结")
    if int(checked or 0) < int(total or 0):
        raise ValueError(f"还有 {int(total) - int(checked)} 行未盘点,无法完结")
    head.status = "completed"
    head.completed_at = datetime.utcnow()
    head.checked_by = current_user.get("username", "")
    await db.flush()
    return head


async def cancel_stock_check(db: AsyncSession, check_id: int, current_user: dict) -> StockCheck:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if head.status == "completed":
        raise ValueError("已完结的盘点单不能取消")
    head.status = "cancelled"
    await db.flush()
    return head


async def get_stock_check_with_items(db: AsyncSession, check_id: int) -> Optional[StockCheck]:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        return None
    items_res = await db.execute(
        select(StockCheckItem).where(StockCheckItem.check_id == check_id).order_by(StockCheckItem.id)
    )
    head.items = list(items_res.scalars().all())
    return head


async def list_recent_stock_checks(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 10,
) -> List[StockCheck]:
    res = await db.execute(
        select(StockCheck).order_by(desc(StockCheck.created_at))
        .offset((page - 1) * page_size).limit(page_size)
    )
    return list(res.scalars().all())


async def list_stock_checks_by_order(db: AsyncSession, order_no: str) -> List[StockCheck]:
    res = await db.execute(
        select(StockCheck).where(StockCheck.order_no == order_no).order_by(desc(StockCheck.created_at))
    )
    return list(res.scalars().all())
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
python -c "from app.services.material.stock_check_service import create_stock_check_from_order, update_stock_check_item, batch_update_items, complete_stock_check, cancel_stock_check, get_stock_check_with_items, list_recent_stock_checks, list_stock_checks_by_order; print('ok')"
```
Expected output: `ok`

---

## Task 4: New API router

**Files:**
- Create: `backend/app/api/v1/material/stock_check.py`

**Step 1: Create the router file**

Create `D:\wanghuazheng\project\SPC-v2\backend\app\api\v1\material\stock_check.py`:

```python
"""物料齐套中心 — 物料盘点 API (scm_inventory_check)"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.stock_check import (
    StockCheckCreate,
    StockCheckOut,
    StockCheckListOut,
    StockCheckItemOut,
    StockCheckItemUpdate,
    StockCheckItemBatchUpdate,
)
from app.models.material.inventory_check import StockCheck, StockCheckItem
from app.services.material.stock_check_service import (
    create_stock_check_from_order,
    update_stock_check_item,
    batch_update_items,
    complete_stock_check,
    cancel_stock_check,
    get_stock_check_with_items,
    list_recent_stock_checks,
    list_stock_checks_by_order,
)

router = APIRouter()


@router.post("/stock-check/from-order/{order_no}", response_model=ResponseModel[StockCheckOut])
async def create_from_order(
    order_no: str,
    body: Optional[StockCheckCreate] = None,
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    body = body or StockCheckCreate(order_no=order_no)
    try:
        head = await create_stock_check_from_order(
            db,
            order_no=order_no,
            current_user=current_user,
            title=body.title,
            check_date=body.check_date,
            remark=body.remark,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    head = await get_stock_check_with_items(db, head.id)
    return ResponseModel(data=StockCheckOut.model_validate(head))


@router.get("/stock-check/recent", response_model=ResponseModel[PageResult[StockCheckListOut]])
async def recent(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(StockCheck.id)))).scalar_one()
    rows = await list_recent_stock_checks(db, page=page, page_size=page_size)
    return ResponseModel(data=PageResult(
        total=int(total or 0),
        page=page,
        page_size=page_size,
        items=[StockCheckListOut.model_validate(r) for r in rows],
    ))


@router.get("/stock-check/by-order/{order_no}", response_model=ResponseModel[List[StockCheckListOut]])
async def list_by_order(
    order_no: str,
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_stock_checks_by_order(db, order_no)
    return ResponseModel(data=[StockCheckListOut.model_validate(r) for r in rows])


@router.get("/stock-check/{check_id}", response_model=ResponseModel[StockCheckOut])
async def get_detail(
    check_id: int,
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    head = await get_stock_check_with_items(db, check_id)
    if not head:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    return ResponseModel(data=StockCheckOut.model_validate(head))


@router.get("/stock-check/{check_id}/items", response_model=ResponseModel[PageResult[StockCheckItemOut]])
async def list_items(
    check_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = select(StockCheckItem).where(StockCheckItem.check_id == check_id).order_by(StockCheckItem.id)
    total = (await db.execute(
        select(func.count(StockCheckItem.id)).where(StockCheckItem.check_id == check_id)
    )).scalar_one()
    rows = (await db.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return ResponseModel(data=PageResult(
        total=int(total or 0),
        page=page,
        page_size=page_size,
        items=[StockCheckItemOut.model_validate(r) for r in rows],
    ))


@router.put("/stock-check/items/{item_id}", response_model=ResponseModel[StockCheckItemOut])
async def update_item(
    item_id: int,
    body: StockCheckItemUpdate,
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await update_stock_check_item(
            db,
            item_id,
            actual_qty=body.actual_qty,
            is_checked=body.is_checked,
            remark=body.remark,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    item = (await db.execute(select(StockCheckItem).where(StockCheckItem.id == item_id))).scalar_one()
    return ResponseModel(data=StockCheckItemOut.model_validate(item))


@router.post("/stock-check/items/batch", response_model=ResponseModel[dict])
async def batch_update(
    body: StockCheckItemBatchUpdate,
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        n = await batch_update_items(db, body.check_id, [it.model_dump() for it in body.items], current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResponseModel(data={"updated": n})


@router.post("/stock-check/{check_id}/complete", response_model=ResponseModel[StockCheckOut])
async def complete(
    check_id: int,
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await complete_stock_check(db, check_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    head = await get_stock_check_with_items(db, check_id)
    return ResponseModel(data=StockCheckOut.model_validate(head))


@router.post("/stock-check/{check_id}/cancel", response_model=ResponseModel[StockCheckOut])
async def cancel(
    check_id: int,
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await cancel_stock_check(db, check_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    head = await get_stock_check_with_items(db, check_id)
    return ResponseModel(data=StockCheckOut.model_validate(head))
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
python -c "from app.api.v1.material.stock_check import router; print(len(router.routes))"
```
Expected output: a positive integer (9 routes).

---

## Task 5: Wire up backend router + remove old code

**Files:**
- Modify: `backend/app/api/v1/material/__init__.py` (swap old for new router import)
- Modify: `backend/app/api/v1/__init__.py` (swap old for new include_router)
- Delete: `backend/app/api/v1/material/inventory_check.py`
- Modify: `backend/app/models/material/__init__.py` (already updated in Task 1; now remove old import)
- Delete: `backend/app/models/material/order_inventory_check.py`
- Modify: `backend/app/schemas/material/schemas.py` (remove the 4 obsolete Pydantic classes)
- Modify: `backend/app/core/permission_registry.py` (swap permission)
- Modify: `backend/init_database.py` (swap 4 role permissions)
- Modify: `backend/app/services/basicdata/position_role_service.py` (swap 6 position presets)

**Step 1: Update material router init**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\api\v1\material\__init__.py`:

Replace line 10 (the `inventory_check_router` import) with:
```python
from app.api.v1.material.stock_check import router as stock_check_router
```

**Step 2: Update top-level API mount**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\api\v1\__init__.py`:

Replace line 28:
```python
api_router.include_router(material.stock_check_router, prefix="/materials", tags=["物料齐套中心-物料盘点"])
```

**Step 3: Delete the old inventory_check API**

```bash
Remove-Item -LiteralPath "D:\wanghuazheng\project\SPC-v2\backend\app\api\v1\material\inventory_check.py"
```

**Step 4: Update model __init__ (remove old import; new one added in Task 1)**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\models\material\__init__.py`:

Delete line 9 (the `from app.models.material.order_inventory_check import OrderInventoryCheck` import).

**Step 5: Delete the old model file**

```bash
Remove-Item -LiteralPath "D:\wanghuazheng\project\SPC-v2\backend\app\models\material\order_inventory_check.py"
```

**Step 6: Remove obsolete Pydantic classes from schemas**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\schemas\material\schemas.py`:

Delete lines 418-471 (the entire `# ============ 订单物料盘点 ============` block including the 4 classes `InventoryCheckCreate`, `MaterialSnapshotItem`, `InventoryCheckOut`, `InventoryCheckListOut`).

**Step 7: Update permission registry**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\core\permission_registry.py`:

Replace line 146:
```python
declare_permission("orders.stock_check", "物料盘点", module="orders", parent_code="orders", route_path="/stock-check", sort_order=4)
```

(Old line was `declare_permission("orders.inventory_check", "订单物料盘点", module="orders", parent_code="orders", route_path="/inventory-check", sort_order=4)`.)

**Step 8: Update 4 role permission entries in init_database.py**

Edit `D:\wanghuazheng\project\SPC-v2\backend\init_database.py`:

In each of the 4 role blocks, find the line `"orders.inventory_check": [...]` and replace with `"orders.stock_check": [...]` (keep the action list unchanged). Lines to update: 537, 580, 616, 657.

**Step 9: Update 6 position presets in position_role_service.py**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\services\basicdata\position_role_service.py`:

In each of the 6 position preset dicts, find `"orders.inventory_check": ...` and replace with `"orders.stock_check": ...` (keep value unchanged). Lines to update: 52, 199, 218, 289, 325, 366.

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
python -c "from app.main import app; print(len(app.routes))"
```
Should complete without import errors. The new routes `/materials/stock-check/...` should be present.

```bash
Select-String -Path "D:\wanghuazheng\project\SPC-v2\backend" -Pattern "orders\.inventory_check|OrderInventoryCheck|scm_order_inventory_check" -Recurse | Select-Object -First 5
```
Should return **zero matches** (excluding the two historical Alembic files at `backend/alembic/versions/0100_*.py` and `0101_*.py`).

---

## Task 6: Frontend API client — replace inventoryCheck with stockCheck

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: Replace the 5 inventory check methods with 9 stock check methods**

Edit `D:\wanghuazheng\project\SPC-v2\frontend\src\services\api.ts`:

Delete lines 206-216 (the 5 `// 订单物料盘点` methods).

In the same location, insert:
```typescript
  // 物料盘点
  createStockCheckFromOrder: (orderNo: string, data?: { title?: string; check_date?: string; remark?: string }) =>
    api.post(`/materials/stock-check/from-order/${orderNo}`, data || {}),
  getRecentStockChecks: (params: Record<string, any> = {}) =>
    api.get('/materials/stock-check/recent', { params }),
  getStockChecksByOrder: (orderNo: string) =>
    api.get(`/materials/stock-check/by-order/${orderNo}`),
  getStockCheck: (checkId: number) =>
    api.get(`/materials/stock-check/${checkId}`),
  getStockCheckItems: (checkId: number, params: Record<string, any> = {}) =>
    api.get(`/materials/stock-check/${checkId}/items`, { params }),
  updateStockCheckItem: (itemId: number, data: { actual_qty?: number; is_checked?: number; remark?: string }) =>
    api.put(`/materials/stock-check/items/${itemId}`, data),
  batchUpdateStockCheckItems: (checkId: number, items: Array<{ id: number; actual_qty?: number; is_checked?: number; remark?: string }>) =>
    api.post('/materials/stock-check/items/batch', { check_id: checkId, items }),
  completeStockCheck: (checkId: number) =>
    api.post(`/materials/stock-check/${checkId}/complete`),
  cancelStockCheck: (checkId: number) =>
    api.post(`/materials/stock-check/${checkId}/cancel`),
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npx tsc --noEmit -p tsconfig.json 2>&1 | Select-String "stockCheck|InventoryCheck" | Select-Object -First 10
```
(TS may report errors in the new page file we haven't created yet — that's expected for now. Old `InventoryCheck` references in `api.ts` should be gone.)

---

## Task 7: Frontend page — `OrderDelivery/StockCheck/index.tsx`

**Files:**
- Create: `frontend/src/pages/OrderDelivery/StockCheck/index.tsx`
- Delete: `frontend/src/pages/OrderDelivery/InventoryCheck/` (entire directory after new page is wired)

**Step 1: Create the new page directory**

```bash
New-Item -ItemType Directory -Path "D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\StockCheck" -Force | Out-Null
```

**Step 2: Create the page file**

Create `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\StockCheck\index.tsx`:

```tsx
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Table, Input, Button, Space, Tag, message, Modal, Card, Row, Col,
  InputNumber, Checkbox, Tooltip, Empty, Spin,
} from 'antd'
import { SearchOutlined, ReloadOutlined, CheckCircleOutlined, StopOutlined, ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons'
import { materialApi } from '@/services/api'
import { formatDateTime } from '@/utils'

interface StockCheckItem {
  id: number
  check_id: number
  line_no?: string | null
  material_id?: number | null
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  req_qty?: number | null
  system_qty?: number | null
  actual_qty?: number | null
  diff_qty?: number | null
  is_checked?: number | null
  checked_at?: string | null
  checked_by?: string | null
  remark?: string | null
}

interface StockCheck {
  id: number
  check_no: string
  order_no: string
  title?: string | null
  status?: string | null
  check_date?: string | null
  total_materials?: number | null
  checked_materials?: number | null
  total_diff_qty?: number | null
  created_by?: string | null
  checked_by?: string | null
  created_at?: string | null
  completed_at?: string | null
  remark?: string | null
  items?: StockCheckItem[]
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待盘点', color: 'default' },
  in_progress: { label: '进行中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  cancelled: { label: '已取消', color: 'error' },
}

export default function StockCheckPage() {
  const [params, setParams] = useSearchParams()
  const [orderNo, setOrderNo] = useState<string>(params.get('orderNo') || '')
  const [searchText, setSearchText] = useState<string>('')

  const [activeCheck, setActiveCheck] = useState<StockCheck | null>(null)
  const [items, setItems] = useState<StockCheckItem[]>([])
  const [recent, setRecent] = useState<StockCheck[]>([])
  const [recentTotal, setRecentTotal] = useState(0)
  const [recentPage, setRecentPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [savingAll, setSavingAll] = useState(false)

  const loadRecent = useCallback(async (p = 1) => {
    try {
      const res: any = await materialApi.getRecentStockChecks({ page: p, page_size: 20 })
      setRecent(res.data?.items || [])
      setRecentTotal(res.data?.total || 0)
      setRecentPage(p)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载最近盘点失败')
    }
  }, [])

  const loadCheck = useCallback(async (checkId: number) => {
    setLoading(true)
    try {
      const res: any = await materialApi.getStockCheck(checkId)
      const c: StockCheck = res.data
      setActiveCheck(c)
      setItems(c.items || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载盘点单失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleCreate = useCallback(async (no: string) => {
    setLoading(true)
    try {
      const res: any = await materialApi.createStockCheckFromOrder(no, {})
      const c: StockCheck = res.data
      message.success(`已创建盘点单 ${c.check_no}`)
      setActiveCheck(c)
      setItems(c.items || [])
      await loadRecent(1)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '创建盘点单失败')
    } finally {
      setLoading(false)
    }
  }, [loadRecent])

  const handleSearch = useCallback(() => {
    if (searchText.trim()) {
      setParams({ orderNo: searchText.trim() })
      setOrderNo(searchText.trim())
    } else {
      setParams({})
      setOrderNo('')
      setActiveCheck(null)
      setItems([])
    }
  }, [searchText, setParams])

  useEffect(() => {
    if (orderNo && !activeCheck) {
      // Try to load the most recent check for this order
      materialApi.getStockChecksByOrder(orderNo).then((res: any) => {
        const list: StockCheck[] = res.data || []
        if (list.length > 0) {
          loadCheck(list[0].id)
        }
      }).catch(() => {})
    }
  }, [orderNo, activeCheck, loadCheck])

  useEffect(() => {
    if (!activeCheck) {
      loadRecent(recentPage)
    }
  }, [activeCheck, recentPage, loadRecent])

  const saveItem = useCallback(async (item: StockCheckItem) => {
    try {
      const res: any = await materialApi.updateStockCheckItem(item.id, {
        actual_qty: item.actual_qty ?? undefined,
        is_checked: item.is_checked ?? 0,
        remark: item.remark ?? undefined,
      })
      const updated: StockCheckItem = res.data
      setItems(prev => prev.map(p => p.id === updated.id ? { ...p, ...updated } : p))
      // refresh head aggregates
      const headRes: any = await materialApi.getStockCheck(updated.check_id)
      setActiveCheck(prev => prev ? { ...prev, ...headRes.data } : headRes.data)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '保存失败')
    }
  }, [])

  const saveAll = useCallback(async () => {
    if (!activeCheck) return
    setSavingAll(true)
    try {
      await materialApi.batchUpdateStockCheckItems(
        activeCheck.id,
        items.map(it => ({
          id: it.id,
          actual_qty: it.actual_qty ?? undefined,
          is_checked: it.is_checked ?? 0,
          remark: it.remark ?? undefined,
        })),
      )
      message.success('已批量保存')
      await loadCheck(activeCheck.id)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '批量保存失败')
    } finally {
      setSavingAll(false)
    }
  }, [activeCheck, items, loadCheck])

  const handleComplete = useCallback(async () => {
    if (!activeCheck) return
    Modal.confirm({
      title: '标记完成',
      content: '完结后所有行将不可再修改,确认继续?',
      onOk: async () => {
        try {
          const res: any = await materialApi.completeStockCheck(activeCheck.id)
          setActiveCheck(res.data)
          setItems(res.data.items || [])
          message.success('已完结')
        } catch (e: any) {
          message.error(e?.response?.data?.detail || e.message || '完结失败')
        }
      },
    })
  }, [activeCheck])

  const handleCancel = useCallback(async () => {
    if (!activeCheck) return
    Modal.confirm({
      title: '取消盘点单',
      content: '确认取消该盘点单?',
      okType: 'danger',
      onOk: async () => {
        try {
          const res: any = await materialApi.cancelStockCheck(activeCheck.id)
          setActiveCheck(res.data)
          message.success('已取消')
        } catch (e: any) {
          message.error(e?.response?.data?.detail || e.message || '取消失败')
        }
      },
    })
  }, [activeCheck])

  const goBack = useCallback(() => {
    setActiveCheck(null)
    setItems([])
  }, [])

  const updateItem = useCallback((id: number, patch: Partial<StockCheckItem>) => {
    setItems(prev => prev.map(p => p.id === id ? { ...p, ...patch } : p))
  }, [])

  const columns = useMemo(() => [
    { title: '物料编码', dataIndex: 'material_code', width: 140, fixed: 'left' as const },
    { title: '物料名称', dataIndex: 'material_name', width: 200, ellipsis: true },
    { title: '规格', dataIndex: 'spec_model', width: 140, ellipsis: true },
    { title: '单位', dataIndex: 'unit', width: 60 },
    { title: '应盘数', dataIndex: 'req_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '库存数', dataIndex: 'system_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '盘点数', dataIndex: 'actual_qty', width: 120, align: 'right' as const,
      render: (_: any, r: StockCheckItem) => (
        <InputNumber
          size="small"
          min={0}
          step={0.01}
          style={{ width: 100 }}
          disabled={activeCheck?.status === 'completed' || activeCheck?.status === 'cancelled'}
          value={r.actual_qty != null ? Number(r.actual_qty) : null}
          onChange={(v) => updateItem(r.id, { actual_qty: v == null ? null : Number(v) })}
        />
      ) },
    { title: '差异', dataIndex: 'diff_qty', width: 90, align: 'right' as const,
      render: (v: any) => {
        if (v == null) return '-'
        const n = Number(v)
        const color = n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#64748b'
        return <span style={{ color, fontWeight: 500 }}>{n.toFixed(2)}</span>
      } },
    { title: '已盘', dataIndex: 'is_checked', width: 70, align: 'center' as const,
      render: (_: any, r: StockCheckItem) => (
        <Checkbox
          disabled={activeCheck?.status === 'completed' || activeCheck?.status === 'cancelled'}
          checked={r.is_checked === 1}
          onChange={(e) => updateItem(r.id, { is_checked: e.target.checked ? 1 : 0 })}
        />
      ) },
    { title: '标记时间', dataIndex: 'checked_at', width: 140,
      render: (v: any) => v ? formatDateTime(v) : '-' },
    { title: '标记人', dataIndex: 'checked_by', width: 100 },
    { title: '备注', dataIndex: 'remark', width: 160, ellipsis: true },
    { title: '操作', key: 'op', width: 80, fixed: 'right' as const,
      render: (_: any, r: StockCheckItem) => (
        <Button type="link" size="small" icon={<SaveOutlined />}
          disabled={activeCheck?.status === 'completed' || activeCheck?.status === 'cancelled'}
          onClick={() => saveItem(r)}>保存</Button>
      ) },
  ], [activeCheck?.status, saveItem, updateItem])

  // ===== 顶部搜索栏 =====
  const renderSearch = () => (
    <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
      <Space>
        <Input
          placeholder="输入订单号 (如 HJ2024-001)"
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          onPressEnter={handleSearch}
          allowClear
          style={{ width: 280 }}
          prefix={<SearchOutlined />}
        />
        <Button type="primary" onClick={handleSearch}>搜索订单</Button>
        <Button onClick={() => { setSearchText(''); setOrderNo(''); setActiveCheck(null); setItems([]); setParams({}) }}>清空</Button>
        {orderNo && !activeCheck && (
          <Button type="primary" ghost onClick={() => handleCreate(orderNo)} loading={loading}>
            为 {orderNo} 创建盘点单
          </Button>
        )}
      </Space>
    </div>
  )

  // ===== 主视图 =====
  return (
    <div>
      {renderSearch()}
      {!activeCheck ? (
        <div className="card-modern" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>最近盘点单</h3>
          <Table
            rowKey="id"
            dataSource={recent}
            pagination={{
              current: recentPage,
              pageSize: 20,
              total: recentTotal,
              onChange: (p) => loadRecent(p),
              showSizeChanger: false,
            }}
            columns={[
              { title: '盘点单号', dataIndex: 'check_no', width: 180 },
              { title: '订单号', dataIndex: 'order_no', width: 180 },
              { title: '标题', dataIndex: 'title', ellipsis: true },
              { title: '状态', dataIndex: 'status', width: 100,
                render: (v) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag> },
              { title: '盘点日期', dataIndex: 'check_date', width: 120 },
              { title: '应盘', dataIndex: 'total_materials', width: 70, align: 'right' as const },
              { title: '已盘', dataIndex: 'checked_materials', width: 70, align: 'right' as const },
              { title: '总差异', dataIndex: 'total_diff_qty', width: 100, align: 'right' as const,
                render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
              { title: '创建人', dataIndex: 'created_by', width: 100 },
              { title: '创建时间', dataIndex: 'created_at', width: 160,
                render: (v: any) => v ? formatDateTime(v) : '-' },
              { title: '操作', key: 'op', width: 100, fixed: 'right' as const,
                render: (_: any, r: StockCheck) => (
                  <Button type="link" size="small" onClick={() => loadCheck(r.id)}>详情</Button>
                ) },
            ]}
            scroll={{ x: 1400 }}
          />
        </div>
      ) : (
        <div>
          <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
            <Space style={{ marginBottom: 12 }}>
              <Button icon={<ArrowLeftOutlined />} onClick={goBack}>返回</Button>
              <h2 style={{ margin: 0 }}>{activeCheck.check_no}</h2>
              <Tag color={STATUS_MAP[activeCheck.status || '']?.color || 'default'}>
                {STATUS_MAP[activeCheck.status || '']?.label || activeCheck.status}
              </Tag>
              <span style={{ color: '#64748b' }}>订单: {activeCheck.order_no}</span>
              <span style={{ color: '#64748b' }}>创建: {activeCheck.created_by} / {formatDateTime(activeCheck.created_at)}</span>
            </Space>
            <Row gutter={12}>
              <Col span={4}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>应盘</div>
                <div style={{ fontSize: 22, fontWeight: 600 }}>{activeCheck.total_materials || 0}</div>
              </Card></Col>
              <Col span={4}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>已盘</div>
                <div style={{ fontSize: 22, fontWeight: 600, color: '#16a34a' }}>{activeCheck.checked_materials || 0}</div>
              </Card></Col>
              <Col span={4}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>未盘</div>
                <div style={{ fontSize: 22, fontWeight: 600, color: '#dc2626' }}>
                  {(activeCheck.total_materials || 0) - (activeCheck.checked_materials || 0)}
                </div>
              </Card></Col>
              <Col span={6}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>总差异 (实盘-库存)</div>
                <div style={{ fontSize: 22, fontWeight: 600 }}>
                  {activeCheck.total_diff_qty != null ? Number(activeCheck.total_diff_qty).toFixed(2) : '0.00'}
                </div>
              </Card></Col>
              <Col span={6} style={{ textAlign: 'right' }}>
                <Space>
                  <Button icon={<SaveOutlined />} onClick={saveAll} loading={savingAll}
                    disabled={activeCheck.status === 'completed' || activeCheck.status === 'cancelled'}>
                    保存全部
                  </Button>
                  <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleComplete}
                    disabled={activeCheck.status === 'completed' || activeCheck.status === 'cancelled'}>
                    标记完成
                  </Button>
                  <Button danger icon={<StopOutlined />} onClick={handleCancel}
                    disabled={activeCheck.status === 'completed' || activeCheck.status === 'cancelled'}>
                    取消
                  </Button>
                </Space>
              </Col>
            </Row>
          </div>
          <div className="card-modern" style={{ padding: 4 }}>
            <Spin spinning={loading}>
              <Table
                rowKey="id"
                dataSource={items}
                columns={columns}
                pagination={{ pageSize: 50, showSizeChanger: true, showTotal: t => `共 ${t} 项` }}
                scroll={{ x: 1600, y: 600 }}
                size="small"
              />
            </Spin>
          </div>
        </div>
      )}
    </div>
  )
}
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npx tsc --noEmit -p tsconfig.json 2>&1 | Select-String "StockCheck" | Select-Object -First 10
```
Should report 0 errors in the new file.

---

## Task 8: Wire frontend route, menu, and OrderList button

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/layouts/MainLayout.tsx`
- Modify: `frontend/src/pages/OrderDelivery/OrderList/index.tsx`
- Delete: `frontend/src/pages/OrderDelivery/InventoryCheck/` (the old directory)

**Step 1: Update App.tsx**

Edit `D:\wanghuazheng\project\SPC-v2\frontend\src\App.tsx`:

Delete line 18:
```tsx
import InventoryCheck from './pages/OrderDelivery/InventoryCheck/index'
```

Add an import (after the `import OrderDetail` line on line 17, or wherever appropriate):
```tsx
import StockCheck from './pages/OrderDelivery/StockCheck/index'
```

Replace line 179:
```tsx
                            <Route path="stock-check" element={<StockCheck />} />
```

**Step 2: Update MainLayout.tsx**

Edit `D:\wanghuazheng\project\SPC-v2\frontend\src\layouts\MainLayout.tsx`:

Delete line 83 (`'orders.inventory_check': <CheckOutlined />`).

Add (in the same `PERMISSION_ICON_MAP` block):
```tsx
  'orders.stock_check': <AuditOutlined />,
```

Delete line 179 (the menu item with `key: '/inventory-check'`).

Add (in the same `children` array, after the risk pool item):
```tsx
      { key: '/stock-check', icon: <AuditOutlined />, label: '物料盘点', permission: 'orders.stock_check' },
```

Delete line 378 (`'/inventory-check': 'order-delivery'`) in the `pathToGroupKey` dict.

Add (in the same dict):
```tsx
  '/stock-check': 'order-delivery',
```

Delete line 449 (`'/inventory-check': 'orders.inventory_check'`) in the `pathToPermission` dict.

Add (in the same dict):
```tsx
  '/stock-check': 'orders.stock_check',
```

**Step 3: Update OrderList navigate URL**

Edit `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\OrderList\index.tsx`:

Replace line 1785:
```tsx
              onClick={() => navigate(`/stock-check?orderNo=${r.order_no}`)}
```

**Step 4: Delete the old InventoryCheck directory**

```bash
Remove-Item -LiteralPath "D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\InventoryCheck" -Recurse -Force
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npm run build
```
Expected: TypeScript compiles, vite build succeeds. Check stdout for any reference to `InventoryCheck`, `inventory-check`, `orders.inventory_check` — should be zero (the only remaining `InventoryCheck` reference, if any, would be in a chunk filename generated by Vite, not a real reference).

```bash
Select-String -Path "D:\wanghuazheng\project\SPC-v2\frontend\src" -Pattern "InventoryCheck|inventory-check|orders\.inventory_check" -Recurse | Select-Object -First 5
```
Expected: zero matches.

---

## Task 9: Run init_database.py and verify

**Step 1: Run init_database.py to create new tables**

```bash
cd D:\wanghuazheng\project\SPC-v2\backend
python init_database.py
```

Expected: completion without errors. The new tables `scm_inventory_check` and `scm_inventory_check_item` should be created (idempotent on re-run).

**Step 2: Verify via DB query (if psql / PG client available)**

```sql
\d scm_inventory_check
\d scm_inventory_check_item
SELECT code, name FROM sys_permission WHERE code = 'orders.stock_check';
```
Expected: Both `\d` commands list the new tables; the permission row should show the new code. There should be **no** rows for `orders.inventory_check`.

**Step 3: Smoke-test the API**

Start uvicorn:
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
uvicorn app.main:app --reload --port 8000
```

Then in another terminal, with a valid admin JWT:
```bash
# Get the permission tree (confirm orders.stock_check is present, orders.inventory_check is absent)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/permissions/tree | jq '.data[] | select(.code=="orders.stock_check")'
# Should return: {"code": "orders.stock_check", "name": "物料盘点", ...}

# Create a stock check from an order
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/materials/stock-check/from-order/HJ2024-001
# Should return: { "code": 0, "data": { "check_no": "PD2026...", "items": [...] } }
```

---

## Task 10: Final cross-repo grep for stale references

**Step 1: Confirm no stale references remain**

```bash
# Backend
Select-String -Path "D:\wanghuazheng\project\SPC-v2\backend" -Pattern "OrderInventoryCheck|orders\.inventory_check|scm_order_inventory_check" -Recurse `
  | Where-Object { $_.Path -notlike "*\alembic\versions\0100_*" -and $_.Path -notlike "*\alembic\versions\0101_*" } `
  | Select-Object -First 5
# Expected: zero matches

# Frontend
Select-String -Path "D:\wanghuazheng\project\SPC-v2\frontend\src" -Pattern "InventoryCheck|inventory-check|orders\.inventory_check" -Recurse `
  | Select-Object -First 5
# Expected: zero matches
```

**Step 2: Confirm new references are in place**

```bash
# Backend
Select-String -Path "D:\wanghuazheng\project\SPC-v2\backend" -Pattern "scm_inventory_check|orders\.stock_check|StockCheck" -Recurse `
  | Select-Object -First 10
# Expected: model, schemas, service, api, permission_registry, init_database, position_role_service

# Frontend
Select-String -Path "D:\wanghuazheng\project\SPC-v2\frontend\src" -Pattern "stock-check|stockCheck|StockCheck" -Recurse `
  | Select-Object -First 10
# Expected: api.ts, App.tsx, MainLayout.tsx, pages/OrderDelivery/StockCheck/index.tsx, OrderList/index.tsx
```

---

## Done criteria

- [ ] `python init_database.py` runs cleanly, both new tables created
- [ ] `npm run build` (i.e. `tsc -b && vite build`) succeeds
- [ ] `GET /api/v1/permissions/tree` shows `orders.stock_check` and not `orders.inventory_check`
- [ ] Admin can navigate to "物料盘点" in the order-delivery menu
- [ ] Clicking "盘点" in OrderList opens `/stock-check?orderNo=...`
- [ ] Creating a stock check from a real order returns BOM-expanded items with `system_qty` populated
- [ ] Editing `actual_qty` and `is_checked` in the table saves successfully and updates head aggregates
- [ ] "标记完成" requires all rows checked
- [ ] `grep` finds zero stale `OrderInventoryCheck` / `inventory-check` references in non-historical files
