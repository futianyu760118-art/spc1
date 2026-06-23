"""生产协同中心 — Schema定义"""

from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel


# ============ 工序进度（统一模型） ============

class ProcessProgressOut(BaseModel):
    id: int
    process_type: str
    seq_no: Optional[int] = None
    plan_date: Optional[date] = None
    order_no: Optional[str] = None
    product_code: Optional[str] = None
    line_no: Optional[str] = None
    model_code: Optional[str] = None
    color_spec: Optional[str] = None
    qty: Optional[float] = None
    planned_qty: Optional[float] = None
    kit_qty: Optional[float] = None
    online_date: Optional[date] = None
    daily_plan_qty: Optional[float] = None
    daily_complete_qty: Optional[float] = None
    completion_rate: Optional[str] = None
    work_hours: Optional[float] = None
    remark: Optional[str] = None
    # 前道
    customer_code: Optional[str] = None
    sale_order_no: Optional[str] = None
    order_date: Optional[str] = None
    by_style: Optional[int] = None
    shell_status: Optional[str] = None
    frame_status: Optional[str] = None
    handle_status: Optional[str] = None
    bracket_status: Optional[str] = None
    product_name: Optional[str] = None
    delivery_date: Optional[date] = None
    # 贴片
    material_long_code: Optional[str] = None
    material_name: Optional[str] = None
    material_confirm: Optional[str] = None
    unit_price: Optional[float] = None
    daily_amount: Optional[float] = None
    complete_time: Optional[str] = None
    hour_capacity: Optional[float] = None
    demand_time: Optional[str] = None
    total_plan_complete: Optional[float] = None
    # 精益
    next_process: Optional[str] = None
    # 组装/包装
    assembly_group: Optional[str] = None
    warehouse_in_qty: Optional[float] = None
    # 状态
    status: str
    data_source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProcessProgressCreate(BaseModel):
    process_type: str
    seq_no: Optional[int] = None
    plan_date: Optional[date] = None
    order_no: Optional[str] = None
    product_code: Optional[str] = None
    line_no: Optional[str] = None
    model_code: Optional[str] = None
    color_spec: Optional[str] = None
    qty: Optional[float] = None
    planned_qty: Optional[float] = None
    kit_qty: Optional[float] = None
    online_date: Optional[date] = None
    daily_plan_qty: Optional[float] = None
    daily_complete_qty: Optional[float] = None
    completion_rate: Optional[str] = None
    work_hours: Optional[float] = None
    remark: Optional[str] = None
    customer_code: Optional[str] = None
    sale_order_no: Optional[str] = None
    order_date: Optional[str] = None
    by_style: Optional[int] = None
    shell_status: Optional[str] = None
    frame_status: Optional[str] = None
    handle_status: Optional[str] = None
    bracket_status: Optional[str] = None
    product_name: Optional[str] = None
    delivery_date: Optional[date] = None
    material_long_code: Optional[str] = None
    material_name: Optional[str] = None
    material_confirm: Optional[str] = None
    unit_price: Optional[float] = None
    daily_amount: Optional[float] = None
    complete_time: Optional[str] = None
    hour_capacity: Optional[float] = None
    demand_time: Optional[str] = None
    total_plan_complete: Optional[float] = None
    next_process: Optional[str] = None
    assembly_group: Optional[str] = None
    warehouse_in_qty: Optional[float] = None
    status: str = 'pending'


class ProcessProgressUpdate(BaseModel):
    plan_date: Optional[date] = None
    order_no: Optional[str] = None
    product_code: Optional[str] = None
    line_no: Optional[str] = None
    model_code: Optional[str] = None
    color_spec: Optional[str] = None
    qty: Optional[float] = None
    planned_qty: Optional[float] = None
    kit_qty: Optional[float] = None
    online_date: Optional[date] = None
    daily_plan_qty: Optional[float] = None
    daily_complete_qty: Optional[float] = None
    completion_rate: Optional[str] = None
    work_hours: Optional[float] = None
    remark: Optional[str] = None
    customer_code: Optional[str] = None
    sale_order_no: Optional[str] = None
    order_date: Optional[str] = None
    by_style: Optional[int] = None
    shell_status: Optional[str] = None
    frame_status: Optional[str] = None
    handle_status: Optional[str] = None
    bracket_status: Optional[str] = None
    product_name: Optional[str] = None
    delivery_date: Optional[date] = None
    material_long_code: Optional[str] = None
    material_name: Optional[str] = None
    material_confirm: Optional[str] = None
    unit_price: Optional[float] = None
    daily_amount: Optional[float] = None
    complete_time: Optional[str] = None
    hour_capacity: Optional[float] = None
    demand_time: Optional[str] = None
    total_plan_complete: Optional[float] = None
    next_process: Optional[str] = None
    assembly_group: Optional[str] = None
    warehouse_in_qty: Optional[float] = None
    status: Optional[str] = None


# ============ Production schedule plans ============

class ProductionSchedulePlanOut(BaseModel):
    id: int
    department: str
    plan_date: date
    order_no: Optional[str] = None
    line_no: Optional[str] = None
    product_code: Optional[str] = None
    model_code: Optional[str] = None
    quantity: Optional[float] = None
    owner: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: str
    status: str
    upph: Optional[float] = None
    daily_work_hours: Optional[float] = None
    remark: Optional[str] = None
    
    plan_version: int = 1
    is_active: bool = True
    source_promised_date: Optional[date] = None
    source_order_qty: Optional[float] = None
    source_product_code: Optional[str] = None
    source_product_model: Optional[str] = None
    source_upph: Optional[float] = None
    source_process_type: Optional[str] = None
    needs_reschedule: bool = False
    reschedule_reason: Optional[str] = None
    previous_plan_id: Optional[int] = None
    sync_batch_no: Optional[str] = None
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None

    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductionSchedulePlanCreate(BaseModel):
    department: str
    plan_date: date
    order_no: Optional[str] = None
    line_no: Optional[str] = None
    product_code: Optional[str] = None
    model_code: Optional[str] = None
    quantity: Optional[float] = None
    owner: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: str = "normal"
    status: str = "planned"
    upph: Optional[float] = None
    daily_work_hours: Optional[float] = None
    remark: Optional[str] = None
    
    plan_version: int = 1
    is_active: bool = True
    source_promised_date: Optional[date] = None
    source_order_qty: Optional[float] = None
    source_product_code: Optional[str] = None
    source_product_model: Optional[str] = None
    source_upph: Optional[float] = None
    source_process_type: Optional[str] = None
    needs_reschedule: bool = False
    reschedule_reason: Optional[str] = None
    previous_plan_id: Optional[int] = None
    sync_batch_no: Optional[str] = None


class ProductionSchedulePlanUpdate(BaseModel):
    department: Optional[str] = None
    plan_date: Optional[date] = None
    order_no: Optional[str] = None
    line_no: Optional[str] = None
    product_code: Optional[str] = None
    model_code: Optional[str] = None
    quantity: Optional[float] = None
    owner: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    upph: Optional[float] = None
    daily_work_hours: Optional[float] = None
    remark: Optional[str] = None
    
    is_active: Optional[bool] = None
    needs_reschedule: Optional[bool] = None
    reschedule_reason: Optional[str] = None
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None


# ============ 一键排产相关 ============

class OrderForSchedulingOut(BaseModel):
    order_no: str
    line_no: str
    customer: Optional[str] = None
    product_code: Optional[str] = None
    product_model: Optional[str] = None
    order_qty: Optional[float] = None
    promised_date: Optional[date] = None
    risk_level: Optional[str] = None
    status: Optional[str] = None
    upph: Optional[float] = None
    has_schedule: bool = False


class AutoScheduleRequest(BaseModel):
    order_no: str
    line_no: str
    department: str = "生产"
    plan_date: Optional[date] = None
    upph: Optional[float] = None
    daily_work_hours: Optional[float] = None
    owner: Optional[str] = None


class AutoScheduleResponse(BaseModel):
    success: bool
    message: str
    schedule_plan: Optional[ProductionSchedulePlanOut] = None
    calculation_result: Optional[dict] = None


# ============ 工序异常 ============

class ProcessExceptionOut(BaseModel):
    id: int
    exception_no: str
    process_type: Optional[str] = None
    order_no: Optional[str] = None
    model_code: Optional[str] = None
    exception_type: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    responsible_dept: Optional[str] = None
    responsible_person: Optional[str] = None
    status: str
    resolved_at: Optional[date] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProcessExceptionCreate(BaseModel):
    process_type: Optional[str] = None
    order_no: Optional[str] = None
    model_code: Optional[str] = None
    exception_type: str
    severity: Optional[str] = None
    description: str
    responsible_dept: Optional[str] = None
    responsible_person: Optional[str] = None
    status: str = 'open'
    remark: Optional[str] = None


class ProcessExceptionUpdate(BaseModel):
    process_type: Optional[str] = None
    order_no: Optional[str] = None
    model_code: Optional[str] = None
    exception_type: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    responsible_dept: Optional[str] = None
    responsible_person: Optional[str] = None
    status: Optional[str] = None
    resolved_at: Optional[date] = None
    remark: Optional[str] = None


# ============ 生产总览聚合 ============

class ProcessTypeStatItem(BaseModel):
    process_type: str
    total: int
    completed: int
    in_progress: int
    overdue: int
    abnormal: int


class ProductProcessItem(BaseModel):
    product_code: Optional[str] = None
    model_code: Optional[str] = None
    color_spec: Optional[str] = None
    qty: Optional[float] = None
    front_process_status: Optional[str] = None
    smt_status: Optional[str] = None
    lean_status: Optional[str] = None
    assembly_status: Optional[str] = None
    packaging_status: Optional[str] = None
    current_process: Optional[str] = None
    block_reason: Optional[str] = None


class OrderProcessItem(BaseModel):
    order_no: str
    products: List[ProductProcessItem] = []
    current_process: Optional[str] = None
    block_reason: Optional[str] = None


class ProductionOverviewData(BaseModel):
    process_stats: List[ProcessTypeStatItem]
    orders: List[OrderProcessItem]
    total_orders: int
    blocked_orders: int


# ============ 变更追踪与产能 ============

class SaleOrderLineChangeLogOut(BaseModel):
    id: int
    order_no: str
    line_no: str
    change_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    is_processed: int
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductProcessCapacityOut(BaseModel):
    id: int
    product_code: str
    process_type: str
    upph: float
    source: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductProcessCapacityCreate(BaseModel):
    product_code: str
    process_type: str
    upph: float
    source: Optional[str] = None


class ProductProcessCapacityUpdate(BaseModel):
    product_code: Optional[str] = None
    process_type: Optional[str] = None
    upph: Optional[float] = None
    source: Optional[str] = None
