"""MRP 域请求/响应模型"""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_no: str
    run_type: str
    triggered_by: Optional[str] = None
    status: str
    horizon_days: int
    stats: Optional[dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class RunTriggerRequest(BaseModel):
    scope: Literal["all", "sale_order_no", "material_codes"] = "all"
    sale_order_no: Optional[str] = None
    material_codes: Optional[list[str]] = None

    @model_validator(mode="after")
    def _validate_scope_payload(self):
        if self.scope == "sale_order_no" and not self.sale_order_no:
            raise ValueError("scope=sale_order_no 时 sale_order_no 必填")
        if self.scope == "material_codes" and not self.material_codes:
            raise ValueError("scope=material_codes 时 material_codes 不能为空")
        return self


class RunTriggerOut(BaseModel):
    run_id: int
    run_no: str
    status: str


class BucketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bucket_date: date
    opening_qty: float
    gross_demand_qty: float
    supply_po_qty: float
    supply_task_qty: float
    supply_subcontract_qty: float
    supply_transfer_qty: float
    supply_requisition_qty: float
    substitute_in_qty: float
    substitute_out_qty: float
    safety_stock_qty: float
    closing_qty: float
    net_demand_qty: float
    pegging: Optional[list] = None


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    material_id: int
    material_code: str
    material_name: Optional[str] = None
    bill_type: int
    suggest_qty: float
    need_date: date
    action_date: Optional[date] = None
    suggested_supplier_id: Optional[int] = None
    source: str
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    pegging: Optional[list] = None
    compare_status: Optional[str] = None
    k3_qty: Optional[float] = None
    k3_need_date: Optional[date] = None
    converted_target_type: Optional[str] = None
    converted_target_id: Optional[int] = None
    is_substitute: bool = False
    substitute_for_material_id: Optional[int] = None


class BatchReviewRequest(BaseModel):
    suggestion_ids: list[int] = Field(min_length=1)
    action: Literal["approve", "reject"]
    comment: str = ""


class SuggestionConvertRequest(BaseModel):
    suggestion_ids: list[int] = Field(min_length=1)


class SchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_code: str
    scheme_name: str
    horizon_days: int
    consider_inventory: bool
    consider_po: bool
    consider_task: bool
    consider_subcontract: bool
    consider_transfer: bool
    consider_requisition: bool
    consider_safety_stock: bool
    supply_priority: str
    exception_enabled: bool
    exception_grace_days: int
    supply_valid_months: int
    compare_window_days: int
    compare_qty_threshold_pct: float
    is_default: bool
    is_active: bool
    remark: Optional[str] = None


class SchemeUpdateRequest(BaseModel):
    scheme_name: Optional[str] = None
    horizon_days: Optional[int] = Field(default=None, ge=1, le=365)
    consider_inventory: Optional[bool] = None
    consider_po: Optional[bool] = None
    consider_task: Optional[bool] = None
    consider_subcontract: Optional[bool] = None
    consider_transfer: Optional[bool] = None
    consider_requisition: Optional[bool] = None
    consider_safety_stock: Optional[bool] = None
    supply_priority: Optional[Literal["by_date", "by_type"]] = None
    exception_enabled: Optional[bool] = None
    exception_grace_days: Optional[int] = Field(default=None, ge=0, le=90)
    supply_valid_months: Optional[int] = Field(default=None, ge=1, le=60)
    compare_window_days: Optional[int] = Field(default=None, ge=0, le=30)
    compare_qty_threshold_pct: Optional[float] = Field(default=None, ge=0, le=100)
    remark: Optional[str] = None


class ParameterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    purchase_lead_time_days: Optional[int] = None
    purchase_variable_lead_time_days: Optional[int] = None
    purchase_variable_lead_time_batch: Optional[float] = None
    inspection_lead_time_days: Optional[int] = None
    produce_lead_time_days: Optional[int] = None
    subcontract_lead_time_days: Optional[int] = None
    safety_stock: float
    max_stock: Optional[float] = None
    moq: Optional[float] = None
    batch_policy: str
    batch_qty: Optional[float] = None
    default_supplier_id: Optional[int] = None
    data_source: str
    remark: Optional[str] = None


class ParameterUpsertRequest(BaseModel):
    material_id: Optional[int] = None
    material_code: Optional[str] = None
    purchase_lead_time_days: Optional[int] = Field(default=None, ge=0)
    purchase_variable_lead_time_days: Optional[int] = Field(default=None, ge=0)
    purchase_variable_lead_time_batch: Optional[float] = Field(default=None, gt=0)
    inspection_lead_time_days: Optional[int] = Field(default=None, ge=0)
    produce_lead_time_days: Optional[int] = Field(default=None, ge=0)
    subcontract_lead_time_days: Optional[int] = Field(default=None, ge=0)
    safety_stock: float = Field(default=0, ge=0)
    max_stock: Optional[float] = Field(default=None, ge=0)
    moq: Optional[float] = Field(default=None, ge=0)
    batch_policy: Literal["lot_for_lot", "multiple", "fixed"] = "lot_for_lot"
    batch_qty: Optional[float] = Field(default=None, gt=0)
    default_supplier_id: Optional[int] = None
    remark: Optional[str] = None


class MrpExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    material_id: int
    material_code: str
    material_name: Optional[str] = None
    exception_code: int
    exception_type: str
    source_type: str
    source_doc_no: Optional[str] = None
    source_line_no: Optional[str] = None
    source_id: Optional[int] = None
    need_date: Optional[date] = None
    doc_date: Optional[date] = None
    adjust_days: Optional[int] = None
    suggest_date: Optional[date] = None
    suggest_qty: Optional[float] = None
    detail: Optional[str] = None
    pegging: Optional[list] = None
    status: str
    handled_by: Optional[str] = None
    handled_at: Optional[datetime] = None
    handle_action: Optional[str] = None
    created_at: datetime


class BatchHandleRequest(BaseModel):
    exception_ids: list[int] = Field(min_length=1)
    action: Literal["ignore", "reschedule", "cancel_reduce", "notify"]
    comment: str = ""


class SubstituteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    main_material_id: int
    substitute_material_id: int
    main_material_code: Optional[str] = None
    main_material_name: Optional[str] = None
    substitute_material_code: Optional[str] = None
    substitute_material_name: Optional[str] = None
    priority: int
    policy: str
    ratio: Optional[float] = None
    substitute_mode: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    enabled: bool
    remark: Optional[str] = None


class SubstituteUpsertRequest(BaseModel):
    main_material_id: Optional[int] = None
    main_material_code: Optional[str] = None
    substitute_material_id: Optional[int] = None
    substitute_material_code: Optional[str] = None
    priority: int = Field(default=1, ge=1)
    policy: Literal["priority", "ratio"] = "priority"
    ratio: Optional[float] = Field(default=None, gt=0, le=100)
    substitute_mode: Literal["offset", "replace"] = "offset"
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    enabled: bool = True
    remark: Optional[str] = None
