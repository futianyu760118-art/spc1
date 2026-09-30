"""物料齐套中心 — 采购申请单 Schema"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RequisitionLineIn(BaseModel):
    material_code: str
    req_qty: float = Field(gt=0)
    need_date: Optional[date] = None
    supplier_id: Optional[int] = None
    remark: Optional[str] = None


class RequisitionCreateRequest(BaseModel):
    department: Optional[str] = None
    remark: Optional[str] = None
    lines: list[RequisitionLineIn] = Field(min_length=1)


class RequisitionUpdateRequest(BaseModel):
    department: Optional[str] = None
    remark: Optional[str] = None
    lines: Optional[list[RequisitionLineIn]] = None


class RequisitionLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_no: int
    material_id: Optional[int] = None
    material_code: str
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    req_qty: float
    need_date: Optional[date] = None
    supplier_id: Optional[int] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    unit_price: Optional[float] = None
    source_suggestion_id: Optional[int] = None
    converted_qty: float = 0
    converted_po_no: Optional[str] = None
    status: str
    remark: Optional[str] = None


class RequisitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    req_no: str
    status: str
    applicant: Optional[str] = None
    department: Optional[str] = None
    source: str
    run_id: Optional[int] = None
    remark: Optional[str] = None
    submitted_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    version: int
    created_at: datetime
    line_count: int = 0
    total_amount: float = 0


class RequisitionDetailOut(RequisitionOut):
    lines: list[RequisitionLineOut] = []
    line_count: int = 0
    total_qty: float = 0
    approval_logs: list[dict] = []


class ConvertToPoItem(BaseModel):
    line_id: int
    qty: float = Field(gt=0)


class ConvertToPoRequest(BaseModel):
    items: list[ConvertToPoItem] = Field(min_length=1)
