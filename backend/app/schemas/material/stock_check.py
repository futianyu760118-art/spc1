"""物料盘点 (scm_inventory_check) Schemas"""

from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class StockCheckCreate(BaseModel):
    """从订单创建盘点单的入参(order_no 已存在 URL path 中,body 可省略)"""
    order_no: Optional[str] = None
    title: Optional[str] = None
    check_date: Optional[date] = None
    remark: Optional[str] = None


class StockCheckFromMaterialsCreate(BaseModel):
    """手动盘点: 用户从物料库选定的物料 ID 列表"""
    material_ids: List[int]
    title: Optional[str] = None
    check_date: Optional[date] = None
    remark: Optional[str] = None


class MaterialCandidateOut(BaseModel):
    """手动盘点选物料弹窗中的候选项,含即时库存"""
    erp_material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    system_qty: Optional[Decimal] = None

    model_config = {"from_attributes": True}


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
    order_no: Optional[str] = None
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
    order_no: Optional[str] = None
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

    model_config = {"from_attributes": True}


class MaterialHistoryItem(BaseModel):
    check_no: str
    order_no: str
    customer: Optional[str] = None
    status: str
    check_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    actual_qty: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}


class MaterialOrderUsageOut(BaseModel):
    """物料反查: 哪些未结订单在使用该物料,各需多少"""
    order_no: str
    line_no: str
    customer: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    order_qty: Optional[Decimal] = None
    bom_no: Optional[str] = None
    standard_qty: Optional[Decimal] = None
    req_qty: Optional[Decimal] = None
    promised_date: Optional[date] = None
    status: Optional[str] = None
    order_nature: Optional[str] = None

    model_config = {"from_attributes": True}
