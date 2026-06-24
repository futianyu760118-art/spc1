"""物料齐套中心 — Schema定义"""

from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel


# ============ 采购订单 / 采购到料计划（合并模型） ============

class PurchaseOrderOut(BaseModel):
    id: int
    po_no: str
    detail_id: int = 1
    material_code: str
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_account: Optional[str] = None
    material_type_name: Optional[str] = None
    material_property: Optional[int] = None
    material_name: Optional[str] = None
    po_qty: Optional[float] = None
    po_price: Optional[float] = None
    po_date: Optional[date] = None
    po_status: str
    eta: Optional[date] = None
    original_eta: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    owner: Optional[str] = None
    remark: Optional[str] = None
    data_source: Optional[str] = None
    # CSV采购到料计划扩展字段
    order_no: Optional[str] = None
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    received_qty: Optional[float] = None
    arrival_hour_note: Optional[str] = None
    inspection_date: Optional[date] = None
    is_closed: int = 0
    is_stagnant: bool = False
    stagnant_qty: Optional[float] = None
    # 缺料差异：po_qty - received_qty，正数表示缺料
    shortage_qty: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PurchaseOrderCreate(BaseModel):
    po_no: str
    detail_id: Optional[int] = None
    material_code: str
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_account: Optional[str] = None
    material_type_name: Optional[str] = None
    material_property: Optional[int] = None
    material_name: Optional[str] = None
    po_qty: Optional[float] = None
    po_price: Optional[float] = None
    po_date: Optional[date] = None
    po_status: str = "placed"
    eta: Optional[date] = None
    original_eta: Optional[date] = None
    owner: Optional[str] = None
    data_source: Optional[str] = None
    order_no: Optional[str] = None
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    received_qty: Optional[float] = None
    arrival_hour_note: Optional[str] = None
    inspection_date: Optional[date] = None


class PurchaseOrderUpdate(BaseModel):
    detail_id: Optional[int] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_account: Optional[str] = None
    material_property: Optional[int] = None
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    order_no: Optional[str] = None
    po_qty: Optional[float] = None
    po_price: Optional[float] = None
    eta: Optional[date] = None
    original_eta: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    owner: Optional[str] = None
    remark: Optional[str] = None
    received_qty: Optional[float] = None
    arrival_hour_note: Optional[str] = None
    inspection_date: Optional[date] = None
    is_closed: Optional[int] = None


class PurchaseOrderBatchUpdate(BaseModel):
    """批量更新采购到料计划（交货时间 + 责任人）"""
    ids: List[int]
    eta: Optional[date] = None
    owner: Optional[str] = None
    supplier_account: Optional[str] = None
    actual_arrival_date: Optional[date] = None
    inspection_date: Optional[date] = None
    is_closed: Optional[int] = None
    clear_fields: Optional[List[str]] = None


class POStatusUpdate(BaseModel):
    po_status: str
    remark: Optional[str] = None


class POTimelineItem(BaseModel):
    timestamp: Optional[datetime] = None
    action: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    operator: Optional[str] = None


class ETAUpdateRequest(BaseModel):
    new_eta: date
    update_reason: Optional[str] = None
    remark: Optional[str] = None


class ETAUpdateOut(BaseModel):
    id: int
    po_no: str
    old_eta: Optional[date] = None
    new_eta: date
    updater: Optional[str] = None
    update_reason: Optional[str] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============ 问题物料 ============

class MaterialIssueOut(BaseModel):
    id: int
    year: Optional[int] = None
    week_no: Optional[int] = None
    department: Optional[str] = None
    category: Optional[str] = None
    issue_date: Optional[date] = None
    reporter: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[date] = None
    responsible_dept: Optional[str] = None
    responsible_person: Optional[str] = None
    audit_score: Optional[int] = None
    is_project: Optional[bool] = None
    follow_up_record: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MaterialIssueCreate(BaseModel):
    year: Optional[int] = None
    week_no: Optional[int] = None
    department: Optional[str] = None
    category: Optional[str] = None
    issue_date: Optional[date] = None
    reporter: Optional[str] = None
    description: str
    deadline: Optional[date] = None
    responsible_dept: Optional[str] = None
    responsible_person: Optional[str] = None
    audit_score: Optional[int] = None
    is_project: Optional[bool] = False
    follow_up_record: Optional[str] = None
    status: str = "open"


class MaterialIssueUpdate(BaseModel):
    department: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[date] = None
    responsible_dept: Optional[str] = None
    responsible_person: Optional[str] = None
    audit_score: Optional[int] = None
    is_project: Optional[bool] = None
    follow_up_record: Optional[str] = None
    status: Optional[str] = None


# ============ 长交期物料池（注解表 + 派生视图） ============

class LongLeadMaterialOut(BaseModel):
    """注解表输出（仅 improvement_plan / status）"""
    id: int
    material_code: Optional[str] = None
    supplier_name: Optional[str] = None
    improvement_plan: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LongLeadMaterialUpdate(BaseModel):
    """注解表更新（仅允许修改改善对策和状态）"""
    improvement_plan: Optional[str] = None
    status: Optional[str] = None


class EnsureAnnotationRequest(BaseModel):
    """按 material_code + supplier_name 确保注解记录存在"""
    material_code: str
    supplier_name: Optional[str] = None


class LongLeadDerivedItem(BaseModel):
    """长交期物料池 — 派生视图项（PO聚合 + 注解表JOIN）"""
    id: Optional[int] = None
    material_code: str
    material_name: Optional[str] = None
    supplier_name: Optional[str] = None
    avg_lead_time_days: Optional[float] = None
    max_lead_time_days: Optional[int] = None
    po_count: int = 0
    latest_eta: Optional[date] = None
    improvement_plan: Optional[str] = None
    status: str = 'active'
    risk_level: str = 'normal'


# ============ 齐套分析 ============

class KitAnalysisMaterialItem(BaseModel):
    material_code: str
    material_name: Optional[str] = None
    material_property: Optional[int] = None
    material_property_label: Optional[str] = None
    material_type: Optional[str] = None
    unit_name: Optional[str] = None
    supplier_name: Optional[str] = None
    order_qty: Optional[float] = None
    shortage_qty: Optional[float] = None
    req_date: Optional[date] = None
    po_no: Optional[str] = None
    po_count: int = 0
    received_qty: Optional[float] = None
    eta: Optional[date] = None
    first_eta: Optional[date] = None
    latest_eta: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    inspection_date: Optional[date] = None
    status: str
    status_label: Optional[str] = None
    is_stagnant: bool = False
    stagnant_qty: Optional[float] = None
    is_closed: int = 0
    bill_type: Optional[int] = None
    bill_type_label: Optional[str] = None


class KitAnalysisItem(BaseModel):
    order_no: str
    total_materials: int
    received_materials: int
    partial_received_materials: int = 0
    not_ordered_materials: int = 0
    overdue_materials: int = 0
    stagnant_materials: int = 0
    kit_rate: float
    risk_level: str
    promised_date: Optional[date] = None


# ============ 供应商风险分析 ============

class SupplierRiskOrderItem(BaseModel):
    po_no: Optional[str] = None
    material_code: str
    material_name: Optional[str] = None
    order_no: Optional[str] = None
    eta: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    inspection_date: Optional[date] = None
    po_status: Optional[str] = None
    po_qty: Optional[float] = None
    received_qty: Optional[float] = None


class SupplierRiskItem(BaseModel):
    supplier_name: str
    total_orders: int
    delayed_count: int
    issue_count: int
    avg_delay_days: float
    risk_level: str
    orders: List[SupplierRiskOrderItem] = []


# ============ 采购计划统计 ============

class PurchasePlanStats(BaseModel):
    total: int
    pending: int
    partial_received: int
    fully_received: int
    overdue: int
    stagnant: int
    closed: int = 0


# ============ 供应商付款排程（基于 purchase_invoice 聚合） ============

class InvoiceDetail(BaseModel):
    invoice_no: str = ''
    line_no: str = ''
    invoice_date: Optional[str] = None
    payment_term: str = ''
    settlement_method: str = ''
    invoice_amount: float = 0.0
    remain_payable: float = 0.0


class SupplierPaymentOut(BaseModel):
    supplier_code: str
    supplier_name: Optional[str] = None
    invoice_date: Optional[str] = None
    schedule_month: Optional[str] = None
    payment_term: Optional[str] = None
    payment_method: Optional[str] = None
    total_payable: Optional[float] = None
    monthly_due: Optional[float] = None
    monthly_bill: Optional[float] = None
    payment_month: Optional[str] = None
    invoices: List[InvoiceDetail] = []

    model_config = {"from_attributes": True}


class SupplierPaymentSummary(BaseModel):
    total_payable: float
    total_monthly_due: float
    supplier_count: int
    overdue_amount: float = 0.0
    not_due_amount: float = 0.0


# ============ 供应商即时沟通消息 ============

class SupplierMessageCreate(BaseModel):
    supplier_name: str
    supplier_account: Optional[str] = None
    content: str
    po_no: Optional[str] = None


class SupplierMessageOut(BaseModel):
    id: int
    supplier_name: str
    supplier_account: Optional[str] = None
    sender_id: int
    sender_name: str
    content: str
    po_no: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============ MRP计划订单 ============

class MrpPlanOrderOut(BaseModel):
    """MRP计划订单 — 销售订单ID + 物料ID 联合主键"""
    sale_order_id: int
    material_id: str
    sale_order_no: Optional[str] = None
    material_code: str
    material_name: Optional[str] = None
    material_property: Optional[int] = None
    material_type: Optional[str] = None
    unit_id: Optional[str] = None
    unit_name: Optional[str] = None
    base_plan_qty: Optional[float] = None
    mrp_run_time: Optional[datetime] = None
    need_date: Optional[date] = None
    is_closed: int = 0
    close_type: Optional[int] = None
    bill_type: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
