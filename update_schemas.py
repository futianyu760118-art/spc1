import re

file_path = r"E:\traexm\zt\zt\backend\app\schemas\production\schemas.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace ProductionSchedulePlanOut
old_out = """class ProductionSchedulePlanOut(BaseModel):
    id: int
    department: str
    plan_date: date
    order_no: Optional[str] = None
    product_code: Optional[str] = None
    model_code: Optional[str] = None
    quantity: Optional[float] = None
    owner: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: str
    status: str
    remark: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}"""

new_out = """class ProductionSchedulePlanOut(BaseModel):
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

    model_config = {"from_attributes": True}"""

content = content.replace(old_out, new_out)

# Replace ProductionSchedulePlanCreate
old_create = """class ProductionSchedulePlanCreate(BaseModel):
    department: str
    plan_date: date
    order_no: Optional[str] = None
    product_code: Optional[str] = None
    model_code: Optional[str] = None
    quantity: Optional[float] = None
    owner: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: str = "normal"
    status: str = "planned"
    remark: Optional[str] = None"""

new_create = """class ProductionSchedulePlanCreate(BaseModel):
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
    sync_batch_no: Optional[str] = None"""

content = content.replace(old_create, new_create)

# Replace ProductionSchedulePlanUpdate
old_update = """class ProductionSchedulePlanUpdate(BaseModel):
    department: Optional[str] = None
    plan_date: Optional[date] = None
    order_no: Optional[str] = None
    product_code: Optional[str] = None
    model_code: Optional[str] = None
    quantity: Optional[float] = None
    owner: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None"""

new_update = """class ProductionSchedulePlanUpdate(BaseModel):
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
    confirmed_at: Optional[datetime] = None"""

content = content.replace(old_update, new_update)

# Append new schemas
new_schemas = """

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
"""

if "SaleOrderLineChangeLogOut" not in content:
    content += new_schemas

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Schemas updated successfully.")
