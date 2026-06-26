"""基础数据与集成中心 — Schema定义"""

from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


# ── Auth ──
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    role_code: Optional[str] = None
    role_name: Optional[str] = None
    permissions: Optional[dict] = None
    supplier_name: Optional[str] = None
    supplier_code: Optional[str] = None
    is_active: bool = True
    font_size_scale: Optional[str] = None
    ui_preferences: Optional[dict] = None
    is_default_password: bool = True
    login_version: int = 0

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str
    password: str


# ── AuditLog ──
class AuditLogOut(BaseModel):
    id: int
    table_name: str
    record_id: int
    action: str
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    operator: Optional[str] = None
    operated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Customer ──
class CustomerBase(BaseModel):
    customer_code: str
    customer_name: str
    customer_short: Optional[str] = None
    customer_level: Optional[str] = None
    industry_type: Optional[str] = None
    credit_code: Optional[str] = None
    status: int = 1


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_short: Optional[str] = None
    customer_level: Optional[str] = None
    industry_type: Optional[str] = None
    credit_code: Optional[str] = None
    status: Optional[int] = None


class CustomerOut(CustomerBase):
    id: int
    create_time: datetime
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Supplier ──
class SupplierBase(BaseModel):
    supplier_code: str
    supplier_name: str
    supplier_short: Optional[str] = None
    supplier_type: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    payment_terms: Optional[str] = None
    status: int = 1


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    supplier_name: Optional[str] = None
    supplier_short: Optional[str] = None
    supplier_type: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    payment_terms: Optional[str] = None
    status: Optional[int] = None


class SupplierOut(SupplierBase):
    id: int
    create_time: datetime
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Material ──
class MaterialBase(BaseModel):
    material_id: str
    parent_id: Optional[str] = None
    material_code: str
    material_name: str
    spec_model: Optional[str] = None
    material_type: str
    unit_of_measure: str
    brand: Optional[str] = None
    is_purchase: int = 0
    is_produce: int = 0
    status: int = 1
    erp_sync_flag: int = 0
    is_deleted: int = 0


class MaterialCreate(MaterialBase):
    pass


class MaterialUpdate(BaseModel):
    material_id: Optional[str] = None
    parent_id: Optional[str] = None
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    material_type: Optional[str] = None
    unit_of_measure: Optional[str] = None
    brand: Optional[str] = None
    is_purchase: Optional[int] = None
    is_produce: Optional[int] = None
    status: Optional[int] = None
    erp_sync_flag: Optional[int] = None
    is_deleted: Optional[int] = None


class MaterialOut(MaterialBase):
    id: int

    model_config = {"from_attributes": True}


class MaterialTreeNode(BaseModel):
    id: int
    material_id: str
    parent_id: Optional[str] = None
    material_code: str
    material_name: str
    spec_model: Optional[str] = None
    material_type: str
    unit_of_measure: str
    brand: Optional[str] = None
    is_purchase: int = 0
    is_produce: int = 0
    status: int = 1
    children: List["MaterialTreeNode"] = []

    model_config = {"from_attributes": True}


# ── SKU ──
class SKUBase(BaseModel):
    sku_code: str
    material_id: int
    sku_name: str
    attr_json: Optional[str] = None
    barcode: Optional[str] = None
    gross_weight: Optional[Decimal] = None
    net_weight: Optional[Decimal] = None
    volume: Optional[Decimal] = None


class SKUCreate(SKUBase):
    pass


class SKUUpdate(BaseModel):
    material_id: Optional[int] = None
    sku_name: Optional[str] = None
    attr_json: Optional[str] = None
    barcode: Optional[str] = None
    gross_weight: Optional[Decimal] = None
    net_weight: Optional[Decimal] = None
    volume: Optional[Decimal] = None


class SKUOut(SKUBase):
    id: int
    create_time: datetime

    model_config = {"from_attributes": True}


# ── Product ──
class ProductBase(BaseModel):
    product_code: str
    product_line: Optional[str] = None
    tech_version: Optional[str] = None
    bom_version: Optional[str] = None
    default_warehouse: Optional[str] = None
    warranty_days: Optional[int] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    product_line: Optional[str] = None
    tech_version: Optional[str] = None
    bom_version: Optional[str] = None
    default_warehouse: Optional[str] = None
    warranty_days: Optional[int] = None


class ProductOut(ProductBase):
    id: int
    create_time: datetime
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Warehouse ──
class WarehouseBase(BaseModel):
    wh_code: str
    wh_name: str
    wh_type: str
    address: Optional[str] = None
    manager_id: Optional[int] = None
    is_enabled: int = 1


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    wh_name: Optional[str] = None
    wh_type: Optional[str] = None
    address: Optional[str] = None
    manager_id: Optional[int] = None
    is_enabled: Optional[int] = None


class WarehouseOut(WarehouseBase):
    id: int
    create_time: datetime

    model_config = {"from_attributes": True}


# ── Process ──
class ProcessBase(BaseModel):
    process_code: str
    process_name: str
    process_group: Optional[str] = None
    standard_hour: Optional[Decimal] = None
    work_center: Optional[str] = None
    is_qc_point: int = 0
    description: Optional[str] = None


class ProcessCreate(ProcessBase):
    pass


class ProcessUpdate(BaseModel):
    process_name: Optional[str] = None
    process_group: Optional[str] = None
    standard_hour: Optional[Decimal] = None
    work_center: Optional[str] = None
    is_qc_point: Optional[int] = None
    description: Optional[str] = None


class ProcessOut(ProcessBase):
    id: int

    model_config = {"from_attributes": True}


# ── Organization ──
class OrganizationBase(BaseModel):
    org_code: str
    org_name: str
    org_type: str
    parent_id: Optional[int] = None
    leader_id: Optional[int] = None
    oa_org_id: Optional[str] = None
    status: int = 1
    data_source: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    org_name: Optional[str] = None
    org_type: Optional[str] = None
    parent_id: Optional[int] = None
    leader_id: Optional[int] = None
    oa_org_id: Optional[str] = None
    status: Optional[int] = None
    data_source: Optional[str] = None


class OrganizationOut(OrganizationBase):
    id: int

    model_config = {"from_attributes": True}


class OrganizationTreeNode(BaseModel):
    id: int
    org_code: str
    org_name: str
    org_type: str
    parent_id: Optional[int] = None
    leader_id: Optional[int] = None
    leader_name: Optional[str] = None
    oa_org_id: Optional[str] = None
    status: int = 1
    data_source: Optional[str] = None
    children: List["OrganizationTreeNode"] = []

    model_config = {"from_attributes": True}


class OrganizationWithLeaderOut(OrganizationOut):
    leader_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Employee ──
class PositionBase(BaseModel):
    position_code: Optional[str] = None
    oa_position_id: Optional[str] = None
    position_name: str
    status: int = 1
    data_source: Optional[str] = None


class PositionOut(PositionBase):
    id: int
    create_time: datetime

    model_config = {"from_attributes": True}


class EmployeeBase(BaseModel):
    emp_code: str
    emp_name: str
    org_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_oa_user_id: Optional[str] = None
    position: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: int = 1


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    emp_name: Optional[str] = None
    org_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_oa_user_id: Optional[str] = None
    position: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[int] = None


class EmployeeOut(EmployeeBase):
    id: int
    create_time: datetime
    position_name: Optional[str] = None
    manager_name: Optional[str] = None

    model_config = {"from_attributes": True}
