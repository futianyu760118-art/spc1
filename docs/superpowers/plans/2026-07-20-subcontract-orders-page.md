# 委外订单页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在「物料齐套中心」下新增「委外订单」页面：头表 + 行内展开明细，完整 CRUD（手动 + ERP 同步共存），独立权限 `materials.subcontract_orders`。

**Architecture:** 后端在现有 `subcontract_order` + `subcontract_order_detail` 两表之上加读/CRUD/CSV API；ERP 同步 service 已存在，复用 `data_source='erp'` guard（不重写 ERP 行）。前端新增 1 个 Ant Design Table 页面，头表 + expandable 嵌套明细。

**Tech Stack:** FastAPI + async SQLAlchemy + Pydantic v2 / React + TypeScript + Ant Design 5 + Zustand。

**Spec:** `docs/superpowers/specs/2026-07-20-subcontract-orders-page-design.md`

## Global Constraints

- Python 3.12 / Node 20
- 响应必须包 `{code, message, data}`（ResponseModel / PageResult）；axios 拦截器把 `code !== 0` 当失败
- 权限检查用 `PermissionChecker("materials.subcontract_orders", "<action>")`
- 所有路由挂在 `/api/v1` 下；本模块子前缀 `/materials/subcontract-orders`
- ERP 同步行（`data_source='erp'`）禁止被本模块 CRUD 覆盖/删除（spec §4.2）
- 新增/修改列必须同时改 `init_database.py` 的 `migrate_columns`（本次不新增列）
- 前端无 lint/test，`npm run build`（= `tsc -b && vite build`）是唯一 typecheck
- 不写注释（除非用户后续要求）；不修改 .env / 不打印密钥

---

## Task 1: 后端 Pydantic Schemas

**File:** `backend/app/schemas/material/schemas.py`

在文件末尾追加（参考现有 `PurchaseOrderOut` 风格）：

```python
# ============ 委外订单 ============

class SubcontractOrderDetailOut(BaseModel):
    id: int
    erp_order_id: Optional[int] = None
    detail_id: Optional[int] = None
    line_no: Optional[int] = None
    material_id: Optional[int] = None
    qty: Optional[float] = None
    delivery_qty: Optional[float] = None
    received_qty: Optional[float] = None
    returned_qty: Optional[float] = None
    amount: Optional[float] = None
    mrp_closed_flag: Optional[int] = None
    sale_order_line_no: Optional[int] = None
    sale_order_id: Optional[int] = None
    sale_order_no: Optional[str] = None
    data_source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class SubcontractOrderOut(BaseModel):
    id: int
    erp_order_id: Optional[int] = None
    bill_no: str
    bill_date: Optional[date] = None
    bill_type: Optional[str] = None
    settlement_method: Optional[str] = None
    settle_date: Optional[date] = None
    supplier_id: Optional[int] = None
    department_id: Optional[int] = None
    salesman_id: Optional[int] = None
    manager_id: Optional[int] = None
    auditor_id: Optional[int] = None
    audit_date: Optional[date] = None
    creator_id: Optional[int] = None
    remark: Optional[str] = None
    voided_flag: Optional[int] = None
    closed_flag: Optional[int] = None
    status: Optional[str] = None
    bill_type_id: Optional[int] = None
    rejected_flag: Optional[int] = None
    close_date: Optional[date] = None
    plan_category: Optional[int] = None
    closer_id: Optional[int] = None
    data_source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    detail_count: int = 0
    total_qty: Optional[float] = None
    details: Optional[List[SubcontractOrderDetailOut]] = None
    model_config = {"from_attributes": True}


class SubcontractOrderDetailCreate(BaseModel):
    material_id: Optional[int] = None
    qty: Optional[float] = None
    delivery_qty: Optional[float] = None
    sale_order_no: Optional[str] = None
    sale_order_id: Optional[int] = None


class SubcontractOrderCreate(BaseModel):
    bill_no: str
    bill_date: Optional[date] = None
    bill_type: Optional[str] = None
    supplier_id: Optional[int] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    details: List[SubcontractOrderDetailCreate] = []


class SubcontractOrderUpdate(BaseModel):
    bill_date: Optional[date] = None
    bill_type: Optional[str] = None
    supplier_id: Optional[int] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class SubcontractOrderBatchUpdate(BaseModel):
    ids: List[int]
    status: Optional[str] = None
    remark: Optional[str] = None


class SubcontractOrderDetailUpdate(BaseModel):
    material_id: Optional[int] = None
    qty: Optional[float] = None
    delivery_qty: Optional[float] = None
    sale_order_no: Optional[str] = None
    sale_order_id: Optional[int] = None
```

**Verify:** `python -c "from app.schemas.material.schemas import SubcontractOrderOut, SubcontractOrderCreate"` 在 `backend/` 下应无报错。

**Commit:** `feat(material): add subcontract order schemas`

---

## Task 2: 后端 API — 列表 + 详情 + 明细

**File:** `backend/app/api/v1/material/subcontract_orders.py`（新建）

完整代码：

```python
"""物料齐套中心 — 委外订单 API"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.material.subcontract_order import SubcontractOrder
from app.models.material.subcontract_order_detail import SubcontractOrderDetail
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import (
    SubcontractOrderOut, SubcontractOrderDetailOut,
    SubcontractOrderCreate, SubcontractOrderUpdate,
    SubcontractOrderBatchUpdate,
    SubcontractOrderDetailCreate, SubcontractOrderDetailUpdate,
)

router = APIRouter()

ERP_SOURCE = "erp"
ERP_PROTECTED_FIELDS = {
    "bill_no", "bill_date", "bill_type", "supplier_id", "erp_order_id",
    "voided_flag", "closed_flag", "audit_date", "auditor_id", "settle_date",
}


def _head_to_out(head, details=None) -> SubcontractOrderOut:
    out = SubcontractOrderOut.model_validate(head)
    out.details = details
    return out


@router.get("", response_model=ResponseModel[PageResult[SubcontractOrderOut]])
async def list_subcontract_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="模糊匹配 bill_no"),
    include_voided: bool = Query(False, description="是否包含 voided_flag=1 的单"),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = []
    if not include_voided:
        base.append((SubcontractOrder.voided_flag != 1) | SubcontractOrder.voided_flag.is_(None))
    if keyword:
        base.append(SubcontractOrder.bill_no.ilike(f"%{keyword}%"))

    total = (await db.execute(select(func.count(SubcontractOrder.id)).where(*base))).scalar() or 0

    detail_subq = (
        select(
            SubcontractOrderDetail.erp_order_id.label("oid"),
            func.count(SubcontractOrderDetail.id).label("cnt"),
            func.sum(SubcontractOrderDetail.qty).label("qty"),
        )
        .group_by(SubcontractOrderDetail.erp_order_id)
        .subquery()
    )

    query = (
        select(SubcontractOrder, func.coalesce(detail_subq.c.cnt, 0), func.coalesce(detail_subq.c.qty, 0))
        .outerjoin(detail_subq, detail_subq.c.oid == SubcontractOrder.erp_order_id)
        .where(*base)
        .order_by(SubcontractOrder.bill_date.desc().nullslast(), SubcontractOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()
    items = []
    for head, cnt, qty in rows:
        out = SubcontractOrderOut.model_validate(head)
        out.detail_count = int(cnt or 0)
        out.total_qty = float(qty) if qty is not None else None
        items.append(out)
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.get("/{order_id}", response_model=ResponseModel[SubcontractOrderOut])
async def get_subcontract_order(
    order_id: int,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    details = (
        await db.execute(
            select(SubcontractOrderDetail)
            .where(SubcontractOrderDetail.erp_order_id == head.erp_order_id)
            .order_by(SubcontractOrderDetail.line_no.asc().nullslast(), SubcontractOrderDetail.id.asc())
        )
    ).scalars().all()
    return ResponseModel(data=_head_to_out(head, [SubcontractOrderDetailOut.model_validate(d) for d in details]))


@router.get("/{order_id}/details", response_model=ResponseModel[PageResult[SubcontractOrderDetailOut]])
async def list_subcontract_order_details(
    order_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    base = [SubcontractOrderDetail.erp_order_id == head.erp_order_id]
    total = (await db.execute(select(func.count(SubcontractOrderDetail.id)).where(*base))).scalar() or 0
    rows = (
        await db.execute(
            select(SubcontractOrderDetail)
            .where(*base)
            .order_by(SubcontractOrderDetail.line_no.asc().nullslast(), SubcontractOrderDetail.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = [SubcontractOrderDetailOut.model_validate(r) for r in rows]
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))
```

**Verify:** 文件能 `python -c "from app.api.v1.material.subcontract_orders import router"`（在 `backend/` 下）。

**Commit:** `feat(material): add subcontract order list/detail api`

---

## Task 3: 后端 API — CRUD + 明细操作

在同一文件 `backend/app/api/v1/material/subcontract_orders.py` 追加：

```python
@router.post("", response_model=ResponseModel[SubcontractOrderOut])
async def create_subcontract_order(
    data: SubcontractOrderCreate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "create")),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.bill_no == data.bill_no))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"bill_no={data.bill_no} 已存在")

    head = SubcontractOrder(
        **data.model_dump(exclude={"details"}),
        data_source="manual",
    )
    db.add(head)
    await db.flush()
    head.erp_order_id = head.id  # 让两表始终能 JOIN

    created_details = []
    if data.details:
        for idx, d in enumerate(data.details, start=1):
            det = SubcontractOrderDetail(
                erp_order_id=head.erp_order_id,
                detail_id=idx,
                line_no=idx,
                data_source="manual",
                **d.model_dump(exclude_unset=True),
            )
            db.add(det)
            created_details.append(det)
        await db.flush()

    await log_audit(db, "subcontract_order", head.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(head)
    return ResponseModel(data=_head_to_out(head, [SubcontractOrderDetailOut.model_validate(d) for d in created_details]))


@router.put("/{order_id}", response_model=ResponseModel[SubcontractOrderOut])
async def update_subcontract_order(
    order_id: int,
    data: SubcontractOrderUpdate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")

    update_data = data.model_dump(exclude_unset=True)
    if head.data_source == ERP_SOURCE:
        blocked = ERP_PROTECTED_FIELDS & update_data.keys()
        if blocked:
            raise HTTPException(
                status_code=400,
                detail=f"ERP 同步行不可修改字段: {','.join(sorted(blocked))}",
            )

    await log_audit(db, "subcontract_order", head.id, "update", old_obj=head, update_data=update_data, operator=current_user["username"])
    for k, v in update_data.items():
        setattr(head, k, v)
    await db.commit()
    await db.refresh(head)
    return ResponseModel(data=_head_to_out(head))


@router.put("/batch", response_model=ResponseModel[dict])
async def batch_update_subcontract_orders(
    data: SubcontractOrderBatchUpdate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    if not data.ids:
        raise HTTPException(status_code=400, detail="请选择要更新的记录")
    if data.status is None and data.remark is None:
        raise HTTPException(status_code=400, detail="请至少填写一个更新字段")
    update_fields = {k: v for k, v in {"status": data.status, "remark": data.remark}.items() if v is not None}
    result = await db.execute(
        select(SubcontractOrder).where(SubcontractOrder.id.in_(data.ids))
    )
    heads = result.scalars().all()
    for h in heads:
        for k, v in update_fields.items():
            setattr(h, k, v)
    await log_audit(
        db, "subcontract_order", 0, "batch_update",
        field_name="batch_status_remark",
        new_value=f"ids={data.ids}, {update_fields}",
        operator=current_user["username"],
    )
    await db.commit()
    return ResponseModel(data={"updated": len(heads)})


@router.delete("/{order_id}", response_model=ResponseModel[dict])
async def delete_subcontract_order(
    order_id: int,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "delete")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    if head.data_source == ERP_SOURCE:
        raise HTTPException(status_code=409, detail="ERP 同步行不可删除（请在 ERP 系统作废）")

    await db.execute(
        delete(SubcontractOrderDetail).where(SubcontractOrderDetail.erp_order_id == head.erp_order_id)
    )
    await log_audit(db, "subcontract_order", head.id, "delete", old_obj=head, operator=current_user["username"])
    await db.delete(head)
    await db.commit()
    return ResponseModel(data={"deleted": order_id})


@router.post("/{order_id}/details", response_model=ResponseModel[SubcontractOrderDetailOut])
async def add_subcontract_order_detail(
    order_id: int,
    data: SubcontractOrderDetailCreate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    max_detail = (await db.execute(
        select(func.max(SubcontractOrderDetail.detail_id))
        .where(SubcontractOrderDetail.erp_order_id == head.erp_order_id)
    )).scalar() or 0
    det = SubcontractOrderDetail(
        erp_order_id=head.erp_order_id,
        detail_id=max_detail + 1,
        line_no=max_detail + 1,
        data_source="manual",
        **data.model_dump(exclude_unset=True),
    )
    db.add(det)
    await log_audit(db, "subcontract_order_detail", det.id, "create", new_value=str(data.model_dump()), operator=current_user["username"])
    await db.commit()
    await db.refresh(det)
    return ResponseModel(data=SubcontractOrderDetailOut.model_validate(det))


@router.put("/{order_id}/details/{detail_id}", response_model=ResponseModel[SubcontractOrderDetailOut])
async def update_subcontract_order_detail(
    order_id: int,
    detail_id: int,
    data: SubcontractOrderDetailUpdate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    det = (await db.execute(
        select(SubcontractOrderDetail).where(
            SubcontractOrderDetail.erp_order_id == head.erp_order_id,
            SubcontractOrderDetail.id == detail_id,
        )
    )).scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="明细不存在")
    if det.data_source == ERP_SOURCE:
        raise HTTPException(status_code=400, detail="ERP 同步明细不可修改")
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "subcontract_order_detail", det.id, "update", old_obj=det, update_data=update_data, operator=current_user["username"])
    for k, v in update_data.items():
        setattr(det, k, v)
    await db.commit()
    await db.refresh(det)
    return ResponseModel(data=SubcontractOrderDetailOut.model_validate(det))


@router.delete("/{order_id}/details/{detail_id}", response_model=ResponseModel[dict])
async def delete_subcontract_order_detail(
    order_id: int,
    detail_id: int,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    det = (await db.execute(
        select(SubcontractOrderDetail).where(
            SubcontractOrderDetail.erp_order_id == head.erp_order_id,
            SubcontractOrderDetail.id == detail_id,
        )
    )).scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="明细不存在")
    if det.data_source == ERP_SOURCE:
        raise HTTPException(status_code=400, detail="ERP 同步明细不可删除")
    await log_audit(db, "subcontract_order_detail", det.id, "delete", old_obj=det, operator=current_user["username"])
    await db.delete(det)
    await db.commit()
    return ResponseModel(data={"deleted": detail_id})
```

**Verify:** `python -c "from app.api.v1.material.subcontract_orders import router; print(len(router.routes))"` 应输出 `10`。

**Commit:** `feat(material): add subcontract order crud endpoints`

---

## Task 4: 后端 CSV 导入 + 导出

**File:** `backend/app/services/material/import_material_csv.py` 在文件末尾追加：

```python
from app.models.material.subcontract_order import SubcontractOrder
from app.models.material.subcontract_order_detail import SubcontractOrderDetail


async def import_subcontract_order_csv(filepath: str, db: AsyncSession) -> dict:
    """导入委外订单 CSV。
    CSV 列头（第1行）：bill_no, bill_date, bill_type, supplier_id, status, remark,
                       material_id, qty, sale_order_no
    同 bill_no 多行 → 头只建一次，后续行作为明细累加。
    幂等：
      - 存在且 data_source='erp' → 跳过整行
      - 存在且 data_source in (manual/excel) → 更新头非空字段 + 追加新明细
      - 不存在 → 新建（data_source='excel'）
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 2:
        return {"created": 0, "updated": 0, "skipped": 0, "details_added": 0}

    created = updated = skipped = details_added = 0
    head_cache: dict[str, SubcontractOrder] = {}

    for row_idx, row in enumerate(rows[1:], start=2):
        if len(row) < 1:
            skipped += 1
            continue
        bill_no = (row[0] or '').strip()
        if not bill_no:
            skipped += 1
            continue

        bill_date = _parse_date(row[1] if len(row) > 1 else '')
        bill_type = (row[2] or '').strip() if len(row) > 2 else None
        supplier_id = _parse_int(row[3] if len(row) > 3 else '')
        status = (row[4] or '').strip() if len(row) > 4 else None
        remark = (row[5] or '').strip() if len(row) > 5 else None
        material_id = _parse_int(row[6] if len(row) > 6 else '')
        qty = _parse_float(row[7] if len(row) > 7 else '')
        sale_order_no = (row[8] or '').strip() if len(row) > 8 else None

        head = head_cache.get(bill_no)
        if head is None:
            result = await db.execute(
                select(SubcontractOrder).where(SubcontractOrder.bill_no == bill_no)
            )
            head = result.scalar_one_or_none()
            if head is not None:
                if head.data_source == "erp":
                    skipped += 1
                    head_cache[bill_no] = head
                    continue

        if head is None:
            head = SubcontractOrder(
                bill_no=bill_no,
                bill_date=bill_date,
                bill_type=bill_type,
                supplier_id=supplier_id,
                status=status or "open",
                remark=remark,
                data_source="excel",
            )
            db.add(head)
            await db.flush()
            head.erp_order_id = head.id
            created += 1
        else:
            if bill_type and not head.bill_type:
                head.bill_type = bill_type
            if supplier_id is not None and head.supplier_id is None:
                head.supplier_id = supplier_id
            if status and not head.status:
                head.status = status
            if remark and not head.remark:
                head.remark = remark
            if bill_date and not head.bill_date:
                head.bill_date = bill_date
            updated += 1

        head_cache[bill_no] = head

        if material_id is not None or qty is not None or sale_order_no:
            max_detail = (await db.execute(
                select(func.max(SubcontractOrderDetail.detail_id))
                .where(SubcontractOrderDetail.erp_order_id == head.erp_order_id)
            )).scalar() or 0
            det = SubcontractOrderDetail(
                erp_order_id=head.erp_order_id,
                detail_id=max_detail + 1,
                line_no=max_detail + 1,
                material_id=material_id,
                qty=qty,
                sale_order_no=sale_order_no or None,
                data_source="excel",
            )
            db.add(det)
            details_added += 1

    await db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "details_added": details_added}
```

**File:** `backend/app/api/v1/material/subcontract_orders.py` 在 Task 2/3 代码后追加 import + 导入/导出 endpoint：

在文件顶部 import 段加：
```python
import os
import tempfile
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
from app.services.material.import_material_csv import import_subcontract_order_csv
from app.services.common.export_service import GenericExportService, ExportColumn
```

在文件末尾追加：
```python
SUBCONTRACT_EXPORT_COLUMNS = [
    ExportColumn('bill_no', '单据编号', 20),
    ExportColumn('bill_date', '日期', 12),
    ExportColumn('bill_type', '类型', 14),
    ExportColumn('supplier_id', '供应商ID', 12),
    ExportColumn('status', '状态', 14),
    ExportColumn('detail_count', '明细数', 8),
    ExportColumn('total_qty', '总数量', 12),
    ExportColumn('remark', '摘要', 30),
    ExportColumn('data_source', '数据来源', 10),
]


@router.post("/import", response_model=ResponseModel[dict])
async def import_subcontract_orders(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "import")),
    db: AsyncSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or '')[1] or '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = await import_subcontract_order_csv(tmp_path, db)
    finally:
        os.unlink(tmp_path)
    await log_audit(db, "subcontract_order", 0, "import", field_name="csv", new_value=file.filename, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)


@router.get("/export")
async def export_subcontract_orders(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    keyword: Optional[str] = Query(None),
    include_voided: bool = Query(False),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = []
    if not include_voided:
        base.append((SubcontractOrder.voided_flag != 1) | SubcontractOrder.voided_flag.is_(None))
    if keyword:
        base.append(SubcontractOrder.bill_no.ilike(f"%{keyword}%"))

    detail_subq = (
        select(
            SubcontractOrderDetail.erp_order_id.label("oid"),
            func.count(SubcontractOrderDetail.id).label("cnt"),
            func.sum(SubcontractOrderDetail.qty).label("qty"),
        )
        .group_by(SubcontractOrderDetail.erp_order_id)
        .subquery()
    )
    query = (
        select(SubcontractOrder, func.coalesce(detail_subq.c.cnt, 0), func.coalesce(detail_subq.c.qty, 0))
        .outerjoin(detail_subq, detail_subq.c.oid == SubcontractOrder.erp_order_id)
        .where(*base)
        .order_by(SubcontractOrder.bill_date.desc().nullslast())
    )
    rows = (await db.execute(query)).all()
    export_rows = []
    for head, cnt, qty in rows:
        export_rows.append({
            'bill_no': head.bill_no,
            'bill_date': str(head.bill_date) if head.bill_date else '',
            'bill_type': head.bill_type or '',
            'supplier_id': head.supplier_id or '',
            'status': head.status or '',
            'detail_count': int(cnt or 0),
            'total_qty': float(qty) if qty is not None else '',
            'remark': head.remark or '',
            'data_source': head.data_source or '',
        })
    svc = GenericExportService(SUBCONTRACT_EXPORT_COLUMNS, export_rows, sheet_name='委外订单')
    if format == 'csv':
        return StreamingResponse(svc.to_csv(), media_type='text/csv; charset=utf-8',
                                 headers={'Content-Disposition': 'attachment; filename=subcontract_orders.csv'})
    return StreamingResponse(svc.to_xlsx(),
                             media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             headers={'Content-Disposition': 'attachment; filename=subcontract_orders.xlsx'})
```

> 注意：`/import` 和 `/export` 路径与 `/{order_id}` 路由冲突。FastAPI 按声明顺序匹配，因此 `/import`、`/export` 必须放在 `/{order_id}` 之前。**实际放置顺序：列表 GET "" → /import → /export → /batch → /{order_id} 系列**。重排时把 Task 3 的 `put /batch` 也移到 `/{order_id}` PUT 之前。

**Verify:**
- `python -c "from app.api.v1.material.subcontract_orders import router; print(len(router.routes))"` 应输出 `12`
- 准备测试 CSV（`backend/test_subcontract_import.csv`）：
  ```
  bill_no,bill_date,bill_type,supplier_id,status,remark,material_id,qty,sale_order_no
  WW001,2026-07-20,委外加工,1001,open,测试,5001,100,SO-X001
  WW001,2026-07-20,委外加工,1001,open,测试,5002,200,SO-X001
  WW002,2026-07-20,委外加工,1002,open,,5003,50,
  ```
- 运行临时脚本验证（可选，不放进 plan）：手工 `python -c "import asyncio; from app.core.database import AsyncSessionLocal; from app.services.material.import_material_csv import import_subcontract_order_csv; asyncio.run(import_subcontract_order_csv('test_subcontract_import.csv', AsyncSessionLocal()))"` 应返回 created=2, details_added=3

**Commit:** `feat(material): add subcontract order csv import/export`

---

## Task 5: 后端 Router 挂载 + 权限注册

**5.1** File: `backend/app/api/v1/material/__init__.py` 在末尾追加：
```python
from app.api.v1.material.subcontract_orders import router as subcontract_orders_router
```

**5.2** File: `backend/app/api/v1/__init__.py` 在 L28（stock_check 后）追加：
```python
api_router.include_router(material.subcontract_orders_router, prefix="/materials/subcontract-orders", tags=["物料齐套中心-委外订单"])
```

**5.3** File: `backend/app/core/permission_registry.py` 在 L194 (`materials.stock_check` 之后) 追加：
```python
declare_permission("materials.subcontract_orders", "委外订单", module="materials", parent_code="materials", route_path="/subcontract-orders", sort_order=8)
```

**5.4** File: `backend/app/core/security.py` 在 L107 (`/supplier-payment` 之后) 追加：
```python
    "/subcontract-orders": "materials.subcontract_orders",
```

**5.5** File: `backend/init_database.py` 的 `seed_roles()` 里给 5 个角色的 `permissions` dict 加上：

- admin (L598 附近)：在 `"materials.supplier_payment"` 后加 `"materials.subcontract_orders": ["create", "read", "update", "delete", "import"],`
- planner (L657 附近)：在 `"materials.supplier_payment": ["read"],` 后加 `"materials.subcontract_orders": ["read"],`
- purchaser (L700 附近)：在 `"materials.supplier_payment": ...` 后加 `"materials.subcontract_orders": ["create", "read", "update", "import"],`
- manager (L736 附近)：加 `"materials.subcontract_orders": ["read", "update"],`
- purchase_manager (L777 附近)：加 `"materials.subcontract_orders": ["create", "read", "update", "delete", "import"],`

**Verify:**
- `cd backend && python init_database.py`（应输出 `Seeding system roles...` 和 `System roles seeded/updated successfully`，无报错）
- 启动 uvicorn：`uvicorn app.main:app --port 8000`，启动日志里应能看到 `materials.subcontract_orders` 注册
- `curl -s http://localhost:8000/api/v1/permissions/tree`（带 admin token）应能在 materials 节点下看到委外订单

**Commit:** `feat(material): wire subcontract order router and permission`

---

## Task 6: 后端冒烟测试

无新文件，仅命令。需先准备 admin token：

```bash
# 1. 登录拿 token
$resp = Invoke-WebRequest -Uri http://localhost:8000/api/v1/basicdata/auth/login -Method Post `
  -Body @{ login_type='employee'; username='admin'; password='admin123' } -ContentType 'application/x-www-form-urlencoded'
$token = ($resp.Content | ConvertFrom-Json).data.access_token
$h = @{ Authorization = "Bearer $token" }

# 2. 创建一张手动单
Invoke-WebRequest -Uri http://localhost:8000/api/v1/materials/subcontract-orders -Method Post `
  -Headers $h -ContentType 'application/json' `
  -Body '{"bill_no":"WW-TEST-001","bill_type":"委外加工","status":"open","details":[{"material_id":5001,"qty":100,"sale_order_no":"SO-X"}]}'

# 3. 列表
Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/materials/subcontract-orders?page=1' -Headers $h

# 4. 详情（应包含 details 数组）
Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/materials/subcontract-orders/1' -Headers $h

# 5. 更新
Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/materials/subcontract-orders/1' -Method Put `
  -Headers $h -ContentType 'application/json' -Body '{"remark":"测试备注"}'

# 6. 删除
Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/materials/subcontract-orders/1' -Method Delete -Headers $h
```

**预期：** 每个请求 `code:0`，第 5 步 data.remark = "测试备注"，第 6 步 data.deleted = 1。无 commit（只是验证）。

---

## Task 7: 前端 API service

**File:** `frontend/src/services/api.ts` 在 L224 附近（`materialApi` 内 stock-check 之后）追加：

```ts
  // 委外订单
  listSubcontractOrders: (params: Record<string, any>) =>
    api.get('/materials/subcontract-orders', { params }),
  getSubcontractOrder: (id: number) =>
    api.get(`/materials/subcontract-orders/${id}`),
  getSubcontractOrderDetails: (id: number, params: Record<string, any> = {}) =>
    api.get(`/materials/subcontract-orders/${id}/details`, { params }),
  createSubcontractOrder: (data: Record<string, any>) =>
    api.post('/materials/subcontract-orders', data),
  updateSubcontractOrder: (id: number, data: Record<string, any>) =>
    api.put(`/materials/subcontract-orders/${id}`, data),
  batchUpdateSubcontractOrders: (data: { ids: number[]; status?: string; remark?: string }) =>
    api.put('/materials/subcontract-orders/batch', data),
  deleteSubcontractOrder: (id: number) =>
    api.delete(`/materials/subcontract-orders/${id}`),
  importSubcontractOrders: (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return api.post('/materials/subcontract-orders/import', fd)
  },
  exportSubcontractOrders: (params: Record<string, any>) =>
    api.get('/materials/subcontract-orders/export', { params, responseType: 'blob' }),
  addSubcontractOrderDetail: (id: number, data: Record<string, any>) =>
    api.post(`/materials/subcontract-orders/${id}/details`, data),
  updateSubcontractOrderDetail: (id: number, detailId: number, data: Record<string, any>) =>
    api.put(`/materials/subcontract-orders/${id}/details/${detailId}`, data),
  deleteSubcontractOrderDetail: (id: number, detailId: number) =>
    api.delete(`/materials/subcontract-orders/${id}/details/${detailId}`),
```

**Verify:** `cd frontend && npx tsc --noEmit`（或者等 Task 9 完成再一起 `npm run build`）。

**Commit:** `feat(frontend): add subcontract order api`

---

## Task 8: 前端菜单 + 路由 + 路径映射

**8.1** File: `frontend/src/layouts/MainLayout.tsx`

L19 `ContainerOutlined,` 后追加（或紧贴其下）：
```tsx
  ProfileOutlined,
```

L193（`/stock-check` 菜单项之后，children 数组末尾）追加：
```tsx
      { key: '/subcontract-orders', icon: <ProfileOutlined />, label: '委外订单', permission: 'materials.subcontract_orders' },
```

L384（`pathToGroupKey` 里 `/supplier-payment` 后）追加：
```tsx
  '/subcontract-orders': 'material-center',
```

L455（`pathToPermission` 里 `/supplier-payment` 后）追加：
```tsx
  '/subcontract-orders': 'materials.subcontract_orders',
```

**8.2** File: `frontend/src/App.tsx`

L18 `import StockCheck ...` 下加：
```tsx
import SubcontractOrders from './pages/MaterialCenter/SubcontractOrders/index'
```

L179 (`<Route path="stock-check" ... />` 下) 加：
```tsx
                            <Route path="subcontract-orders" element={<SubcontractOrders/>}/>
```

**Verify:** `npm run build` 应能通过（页面在 Task 9 之前会有 TS 报错，跳过；本步完成后下一并验证）。

**Commit:** `feat(frontend): wire subcontract order menu and route`

---

## Task 9: 前端页面

**File:** `frontend/src/pages/MaterialCenter/SubcontractOrders/index.tsx`（新建）

最小可用页面（头表 + expandable 明细 + 工具栏：搜索 / 新增 / 编辑 / 删除 / 导入 / 导出）。完整代码：

```tsx
import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Input, Button, Space, message, Modal, Form, DatePicker, InputNumber,
  Upload, Tooltip, Popconfirm, Card, Row, Col, Statistic,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
  UploadOutlined, DownloadOutlined, ExpandOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { materialApi } from '../../../services/api'
import { formatDate } from '../../../utils'

interface DetailRow {
  id: number
  detail_id?: number
  line_no?: number
  material_id?: number
  qty?: number | null
  delivery_qty?: number | null
  received_qty?: number | null
  sale_order_no?: string | null
  data_source?: string | null
}

interface HeadRow {
  id: number
  bill_no: string
  bill_date?: string | null
  bill_type?: string | null
  supplier_id?: number | null
  status?: string | null
  remark?: string | null
  data_source?: string | null
  voided_flag?: number | null
  closed_flag?: number | null
  detail_count?: number
  total_qty?: number | null
}

const STATUS_COLOR: Record<string, string> = {
  open: 'processing',
  closed: 'default',
  voided: 'error',
  audited: 'success',
}

export default function SubcontractOrders() {
  const [data, setData] = useState<HeadRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [includeVoided, setIncludeVoided] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<HeadRow | null>(null)
  const [detailOpen, setDetailOpen] = useState<HeadRow | null>(null)
  const [details, setDetails] = useState<DetailRow[]>([])
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailForm] = Form.useForm()
  const [headForm] = Form.useForm()

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.listSubcontractOrders({
        page, page_size: pageSize,
        keyword: keyword || undefined,
        include_voided: includeVoided,
      })
      const d = res?.data
      setData(d?.items || [])
      setTotal(d?.total || 0)
    } catch (e: any) {
      message.error(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword, includeVoided])

  useEffect(() => { fetchData() }, [fetchData])

  const openDetails = async (row: HeadRow) => {
    setDetailOpen(row)
    setDetailsLoading(true)
    try {
      const res: any = await materialApi.getSubcontractOrderDetails(row.id, { page: 1, page_size: 500 })
      setDetails(res?.data?.items || [])
    } finally {
      setDetailsLoading(false)
    }
  }

  const openCreate = () => {
    setEditing(null)
    headForm.resetFields()
    setEditOpen(true)
  }
  const openEdit = (row: HeadRow) => {
    setEditing(row)
    headForm.setFieldsValue({
      bill_no: row.bill_no,
      bill_date: row.bill_date ? dayjs(row.bill_date) : undefined,
      bill_type: row.bill_type,
      supplier_id: row.supplier_id,
      status: row.status,
      remark: row.remark,
    })
    setEditOpen(true)
  }

  const submitHead = async () => {
    const v = await headForm.validateFields()
    const payload: any = { ...v }
    if (payload.bill_date) payload.bill_date = dayjs(payload.bill_date).format('YYYY-MM-DD')
    try {
      if (editing) {
        await materialApi.updateSubcontractOrder(editing.id, payload)
        message.success('已更新')
      } else {
        await materialApi.createSubcontractOrder(payload)
        message.success('已创建')
      }
      setEditOpen(false)
      fetchData()
    } catch (e: any) {
      message.error(e?.message || '保存失败')
    }
  }

  const remove = async (id: number) => {
    try {
      await materialApi.deleteSubcontractOrder(id)
      message.success('已删除')
      fetchData()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败')
    }
  }

  const onImport = async (file: File) => {
    try {
      const res: any = await materialApi.importSubcontractOrders(file)
      message.success(`导入完成: ${JSON.stringify(res?.data)}`)
      fetchData()
    } catch (e: any) {
      message.error(e?.message || '导入失败')
    }
    return false
  }

  const onExport = async () => {
    try {
      const res: any = await materialApi.exportSubcontractOrders({
        keyword: keyword || undefined,
        include_voided: includeVoided,
        format: 'xlsx',
      })
      const url = window.URL.createObjectURL(new Blob([res]))
      const a = document.createElement('a')
      a.href = url
      a.download = 'subcontract_orders.xlsx'
      a.click()
      window.URL.revokeObjectURL(url)
    } catch (e: any) {
      message.error(e?.message || '导出失败')
    }
  }

  const addDetail = async () => {
    if (!detailOpen) return
    const v = await detailForm.validateFields()
    try {
      await materialApi.addSubcontractOrderDetail(detailOpen.id, v)
      message.success('已添加明细')
      detailForm.resetFields()
      openDetails(detailOpen)
    } catch (e: any) {
      message.error(e?.message || '添加失败')
    }
  }

  const removeDetail = async (detailId: number) => {
    if (!detailOpen) return
    try {
      await materialApi.deleteSubcontractOrderDetail(detailOpen.id, detailId)
      message.success('已删除')
      openDetails(detailOpen)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败')
    }
  }

  const columns = [
    { title: '单据编号', dataIndex: 'bill_no', width: 180, fixed: 'left' as const },
    { title: '日期', dataIndex: 'bill_date', width: 110, render: (v: string) => formatDate(v) },
    { title: '类型', dataIndex: 'bill_type', width: 120 },
    { title: '供应商ID', dataIndex: 'supplier_id', width: 90 },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => v ? <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag> : null,
    },
    { title: '明细数', dataIndex: 'detail_count', width: 80, align: 'right' as const },
    { title: '总数量', dataIndex: 'total_qty', width: 100, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    {
      title: '来源', dataIndex: 'data_source', width: 90,
      render: (v: string) => v === 'erp' ? <Tag color="blue">ERP</Tag> : (v ? <Tag>{v}</Tag> : null),
    },
    { title: '摘要', dataIndex: 'remark', ellipsis: true },
    {
      title: '操作', key: 'op', width: 200, fixed: 'right' as const,
      render: (_: any, r: HeadRow) => (
        <Space>
          <Button size="small" onClick={() => openDetails(r)}>明细</Button>
          <Button size="small" icon={<EditOutlined />} disabled={r.data_source === 'erp'}
            onClick={() => openEdit(r)} />
          <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)}
            disabled={r.data_source === 'erp'}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.data_source === 'erp'} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const detailColumns = [
    { title: '行号', dataIndex: 'line_no', width: 60 },
    { title: '物料ID', dataIndex: 'material_id', width: 90 },
    { title: '数量', dataIndex: 'qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '交货数', dataIndex: 'delivery_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '已收', dataIndex: 'received_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '销售订单号', dataIndex: 'sale_order_no', width: 140 },
    {
      title: '操作', key: 'op', width: 80,
      render: (_: any, r: DetailRow) => (
        <Popconfirm title="删除该明细？" onConfirm={() => removeDetail(r.id)}
          disabled={r.data_source === 'erp'}>
          <Button size="small" danger icon={<DeleteOutlined />} disabled={r.data_source === 'erp'} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="p-4">
      <Card size="small" className="mb-3">
        <Row gutter={16}>
          <Col span={6}><Statistic title="总数" value={total} /></Col>
          <Col span={6}><Statistic title="当前页" value={data.length} /></Col>
        </Row>
      </Card>

      <Space className="mb-3" wrap>
        <Input
          placeholder="搜索 bill_no"
          prefix={<SearchOutlined />}
          value={keyword}
          onChange={(e) => { setKeyword(e.target.value); setPage(1) }}
          style={{ width: 240 }}
          allowClear
        />
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增</Button>
        <Upload beforeUpload={onImport} showUploadList={false} accept=".csv">
          <Button icon={<UploadOutlined />}>导入 CSV</Button>
        </Upload>
        <Button icon={<DownloadOutlined />} onClick={onExport}>导出</Button>
      </Space>

      <Table<HeadRow>
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        scroll={{ x: 1400 }}
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) => setSelectedIds(keys as number[]),
        }}
        pagination={{
          current: page, pageSize, total,
          showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        expandable={{
          expandRowByClick: false,
          expandIcon: () => <ExpandOutlined />,
          rowExpandable: (r) => (r.detail_count ?? 0) > 0,
          expandedRowRender: (r) => <SubcontractDetailInline headId={r.id} />,
        }}
      />

      <Modal
        title={editing ? `编辑 ${editing.bill_no}` : '新建委外订单'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={submitHead}
        width={640}
        destroyOnClose
      >
        <Form form={headForm} layout="vertical">
          <Form.Item name="bill_no" label="单据编号" rules={[{ required: true }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="bill_date" label="日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="bill_type" label="类型"><Input /></Form.Item>
          <Form.Item name="supplier_id" label="供应商ID"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="status" label="状态"><Input placeholder="open / closed / voided" /></Form.Item>
          <Form.Item name="remark" label="摘要"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title={detailOpen ? `明细 - ${detailOpen.bill_no}` : ''}
        open={!!detailOpen}
        onCancel={() => setDetailOpen(null)}
        footer={null}
        width={900}
        destroyOnClose
      >
        <Space className="mb-2" wrap>
          <InputNumber placeholder="物料ID" onChange={(v) => detailForm.setFieldValue('material_id', v)} />
          <InputNumber placeholder="数量" onChange={(v) => detailForm.setFieldValue('qty', v)} />
          <Input placeholder="销售订单号" onChange={(e) => detailForm.setFieldValue('sale_order_no', e.target.value)} />
          <Button icon={<PlusOutlined />} onClick={addDetail}>加明细</Button>
        </Space>
        <Table<DetailRow>
          rowKey="id"
          size="small"
          loading={detailsLoading}
          dataSource={details}
          columns={detailColumns}
          pagination={false}
          scroll={{ y: 360 }}
        />
      </Modal>
    </div>
  )
}

function SubcontractDetailInline({ headId }: { headId: number }) {
  const [items, setItems] = useState<DetailRow[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    materialApi.getSubcontractOrderDetails(headId, { page: 1, page_size: 500 })
      .then((res: any) => { if (!cancelled) setItems(res?.data?.items || []) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headId])

  const columns = [
    { title: '行号', dataIndex: 'line_no', width: 60 },
    { title: '物料ID', dataIndex: 'material_id', width: 90 },
    { title: '数量', dataIndex: 'qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '交货数', dataIndex: 'delivery_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '已收', dataIndex: 'received_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '销售订单号', dataIndex: 'sale_order_no', width: 140 },
  ]

  return (
    <Table<DetailRow>
      rowKey="id"
      size="small"
      loading={loading}
      dataSource={items}
      columns={columns}
      pagination={false}
    />
  )
}
```

**Verify:**
- `cd frontend && npm run build` 必须 0 错误
- 启动 `npm run dev`，登录 admin/purchaser，进入「物料齐套中心 → 委外订单」
- 测试：搜索、新增、编辑、删除、展开明细、导入 CSV、导出 xlsx

**Commit:** `feat(frontend): add subcontract orders page`

---

## Task 10: 端到端验证

无需写代码。按 spec §7 验证清单逐项跑一遍：

| 项 | 命令 / 操作 | 期望 |
|---|---|---|
| 后端启动 | `uvicorn app.main:app --reload --port 8000` | 无错误，看到 router 注册 |
| 前端构建 | `cd frontend && npm run build` | 0 错误 |
| 列表 API | `curl -H "Authorization: Bearer <admin>" http://localhost:8000/api/v1/materials/subcontract-orders` | `code:0, data:{items:[], total:0}` |
| 手动新增 | 前端点新增 | 成功，`data_source=manual`，展开能看到明细 |
| ERP guard | 把一行手动改成 `data_source='erp'` 后调 PUT 改 bill_type | 400 + "ERP 同步行不可修改字段" |
| 删除 guard | DELETE 一条 erp 行 | 409 |
| 权限 | purchaser01 能新增；planner01 只能看 | 符合 |
| 菜单 | purchaser01 登录后侧边栏有「委外订单」 | 符合 |
| ERP 同步 | `POST /api/v1/basicdata/sync/subcontract_orders` | 现有 sync service 不报错（占位 SQL 返回 0 行即可） |

全部通过后提交最终修复（如有）。

---

## 关键文件清单

**新增**
- `backend/app/api/v1/material/subcontract_orders.py`
- `frontend/src/pages/MaterialCenter/SubcontractOrders/index.tsx`

**修改**
- `backend/app/schemas/material/schemas.py`
- `backend/app/services/material/import_material_csv.py`
- `backend/app/api/v1/material/__init__.py`
- `backend/app/api/v1/__init__.py`
- `backend/app/core/permission_registry.py`
- `backend/app/core/security.py`
- `backend/init_database.py`
- `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/App.tsx`
- `frontend/src/services/api.ts`

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| `erp_order_id` 手动回填可能与 ERP FID 数值碰撞 | ERP FID 一般是 8 位以上大整数；本系统 id 从 1 起步，短期安全。长期可改为负值或加 head_id 列（v2） |
| `/import` `/export` 与 `/{order_id}` 路由顺序冲突 | Task 4 明确要求 `/import`、`/export`、`/batch` 在 `/{order_id}` 之前声明 |
| ERP 同步行被前端误改 | 后端两层防护：update 拒绝改 ERP 字段；delete 拒绝删 erp 行；前端按钮置灰 |
| 明细大批量展开性能 | 默认 page_size=500，超过时前端可加分页（v2） |
