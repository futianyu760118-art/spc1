"""数据供给 — 数据类型注册表

每种可对外暴露的数据类型在此手动注册，定义：
- 对外暴露的字段（独立于数据库表结构，内部表结构变更不影响外部接口）
- 可筛选字段
- 需脱敏字段
- 对应的 SQLAlchemy 模型（用于查询）
- 可选的业务 Service 获取函数（优先于直接查表）
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Any


@dataclass
class DataTypeDefinition:
    """数据类型定义"""
    data_type: str                           # 数据类型标识（如 customers）
    data_name: str                           # 中文名（如 客户）
    description: str                         # 描述
    model_name: str                          # 对应的 SQLAlchemy 模型类名
    exposed_fields: list[str]                # 对外暴露的字段列表（独立于表结构）
    filter_fields: list[str] = field(default_factory=list)  # 允许筛选的字段
    mask_fields: list[str] = field(default_factory=list)    # 需要脱敏的字段
    search_fields: list[str] = field(default_factory=list)  # 关键字搜索字段（默认取 exposed_fields 前两个）
    service_fn: Optional[Callable] = None    # 可选：业务 Service 获取函数，优先于直接查表

    def __post_init__(self):
        if not self.search_fields and len(self.exposed_fields) >= 2:
            self.search_fields = self.exposed_fields[:2]


# ═══════════════════════════════════════════
# 注册表
# ═══════════════════════════════════════════

DATA_TYPE_REGISTRY: dict[str, DataTypeDefinition] = {}


def register_data_type(definition: DataTypeDefinition):
    """注册一个数据类型"""
    DATA_TYPE_REGISTRY[definition.data_type] = definition


def get_data_type_definition(data_type: str) -> Optional[DataTypeDefinition]:
    """获取数据类型定义"""
    return DATA_TYPE_REGISTRY.get(data_type)


# ═══════════════════════════════════════════
# 注册所有数据类型
# ═══════════════════════════════════════════

# ── 基础数据 ──

register_data_type(DataTypeDefinition(
    data_type="customers",
    data_name="客户",
    description="客户主数据",
    model_name="Customer",
    exposed_fields=[
        "id", "customer_code", "customer_name", "customer_short",
        "customer_level", "industry_type", "credit_code", "status",
    ],
    filter_fields=["customer_level", "industry_type", "status"],
    mask_fields=["credit_code"],
    search_fields=["customer_code", "customer_name"],
))

register_data_type(DataTypeDefinition(
    data_type="suppliers",
    data_name="供应商",
    description="供应商主数据",
    model_name="Supplier",
    exposed_fields=[
        "id", "supplier_code", "supplier_name", "supplier_short",
        "supplier_type", "contact_person", "contact_phone", "fax",
        "address", "erp_supply_id", "payment_terms", "status",
    ],
    filter_fields=["supplier_type", "status"],
    mask_fields=["contact_phone", "fax"],
    search_fields=["supplier_code", "supplier_name"],
))

register_data_type(DataTypeDefinition(
    data_type="materials",
    data_name="物料",
    description="物料主数据",
    model_name="Material",
    exposed_fields=[
        "id", "erp_material_id", "material_code", "material_name", "spec_model",
        "material_type", "unit_of_measure", "brand", "is_purchase", "is_produce", "status",
    ],
    filter_fields=["material_type", "is_purchase", "is_produce", "status"],
    search_fields=["material_code", "material_name"],
))

register_data_type(DataTypeDefinition(
    data_type="products",
    data_name="产品",
    description="产品主数据",
    model_name="Product",
    exposed_fields=[
        "id", "product_code", "product_line", "tech_version",
        "bom_version", "default_warehouse", "warranty_days", "upph",
    ],
    filter_fields=["product_line"],
    search_fields=["product_code"],
))

register_data_type(DataTypeDefinition(
    data_type="boms",
    data_name="BOM",
    description="BOM物料清单",
    model_name="Bom",
    exposed_fields=[
        "id", "bom_id", "bom_no", "material_id", "parent_material_id",
        "bom_version", "bom_type", "bill_type_id", "base_qty", "aux_attr_qty",
        "unit_id", "aux_attr_id", "supply_mode", "customer_material_id",
        "audit_status", "use_status", "disabled_status", "void_flag",
        "is_audited", "audit_date", "entry_date",
    ],
    filter_fields=["bom_type", "audit_status", "use_status", "disabled_status", "void_flag"],
    search_fields=["bom_no", "material_id"],
))

register_data_type(DataTypeDefinition(
    data_type="bom_details",
    data_name="BOM明细",
    description="BOM明细行数据",
    model_name="BomDetail",
    exposed_fields=[
        "id", "bom_id", "line_no", "material_id", "standard_qty", "aux_qty",
        "material_type", "config_type", "lead_offset_days", "back_flush",
        "scrap_rate", "oper_sn", "process_id", "warehouse_id", "location_id",
        "valid_date", "invalid_date", "unit_id", "customer_bom_code",
        "aux_attr_id", "material_size", "kit_flag",
    ],
    filter_fields=["bom_id", "material_id", "material_type", "config_type", "kit_flag"],
    search_fields=["bom_id", "line_no", "material_id"],
))

register_data_type(DataTypeDefinition(
    data_type="warehouses",
    data_name="仓库",
    description="仓库主数据",
    model_name="Warehouse",
    exposed_fields=[
        "id", "wh_code", "wh_name", "wh_type", "address", "is_enabled",
    ],
    filter_fields=["wh_type", "is_enabled"],
    search_fields=["wh_code", "wh_name"],
))

register_data_type(DataTypeDefinition(
    data_type="processes",
    data_name="工序",
    description="工序主数据",
    model_name="Process",
    exposed_fields=[
        "id", "process_code", "process_name", "process_group",
        "standard_hour", "work_center", "is_qc_point", "description",
    ],
    filter_fields=["process_group", "work_center", "is_qc_point"],
    search_fields=["process_code", "process_name"],
))

register_data_type(DataTypeDefinition(
    data_type="organizations",
    data_name="组织",
    description="组织架构",
    model_name="Organization",
    exposed_fields=[
        "id", "org_code", "org_name", "oa_org_id", "org_type", "parent_id", "leader_id", "status",
    ],
    filter_fields=["org_type", "status"],
    search_fields=["org_code", "org_name"],
))

register_data_type(DataTypeDefinition(
    data_type="positions",
    data_name="岗位",
    description="岗位主数据",
    model_name="Position",
    exposed_fields=[
        "id", "position_code", "oa_position_id", "position_name", "status",
    ],
    filter_fields=["status"],
    search_fields=["position_code", "position_name"],
))

register_data_type(DataTypeDefinition(
    data_type="employees",
    data_name="人员",
    description="员工主数据",
    model_name="Employee",
    exposed_fields=[
        "id", "emp_code", "emp_name", "org_id", "position_id", "position", "phone", "email", "status",
    ],
    filter_fields=["org_id", "position_id", "status"],
    mask_fields=["phone", "email"],
    search_fields=["emp_code", "emp_name"],
))

# ── 订单/采购 ──

register_data_type(DataTypeDefinition(
    data_type="orders",
    data_name="销售订单",
    description="销售订单及订单行",
    model_name="SaleOrderLine",
    exposed_fields=[
        "id", "order_no", "line_no", "customer", "customer_code",
        "product_code", "product_name", "order_qty", "order_amount",
        "completed_qty", "promised_date", "planned_start_date",
        "status", "risk_level", "owner",
    ],
    filter_fields=["status", "risk_level", "customer_code"],
    search_fields=["order_no", "product_name"],
))

register_data_type(DataTypeDefinition(
    data_type="purchase_orders",
    data_name="采购订单",
    description="采购订单",
    model_name="PurchaseOrder",
    exposed_fields=[
        "id", "po_no", "material_code", "supplier_code", "supplier_name",
        "material_name", "po_qty", "po_price", "po_date", "po_status",
        "eta", "actual_arrival_date", "owner", "order_no",
    ],
    filter_fields=["po_status", "supplier_code"],
    search_fields=["po_no", "material_name"],
))

# ── 生产 ──

register_data_type(DataTypeDefinition(
    data_type="schedule_plans",
    data_name="生产排产计划",
    description="生产排产计划",
    model_name="SchedulePlan",
    exposed_fields=[
        "id", "plan_date", "product_code", "quantity", "plan_type",
        "status", "scheduled_by", "scheduled_at", "updated_at",
    ],
    filter_fields=["plan_type", "status", "plan_date"],
    search_fields=["product_code"],
))

register_data_type(DataTypeDefinition(
    data_type="work_orders",
    data_name="工单",
    description="生产工单",
    model_name="WorkOrder",
    exposed_fields=[
        "id", "order_code", "product_code", "quantity",
        "status", "scheduled_at", "actual_start_time", "actual_end_time",
        "created_at", "updated_at",
    ],
    filter_fields=["status"],
    search_fields=["order_code", "product_code"],
))

register_data_type(DataTypeDefinition(
    data_type="process_exceptions",
    data_name="工序异常",
    description="生产工序异常记录",
    model_name="ProcessException",
    exposed_fields=[
        "id", "work_order_id", "process_id", "exception_type",
        "exception_desc", "occurred_at", "status", "created_at", "updated_at",
    ],
    filter_fields=["exception_type", "status"],
    search_fields=["exception_desc"],
))

register_data_type(DataTypeDefinition(
    data_type="process_progress",
    data_name="工序进度",
    description="生产工序进度",
    model_name="ProcessProgress",
    exposed_fields=[
        "id", "work_order_id", "process_id", "status",
        "actual_start_time", "actual_end_time", "completed_percentage",
        "created_at", "updated_at",
    ],
    filter_fields=["status", "work_order_id"],
    search_fields=["work_order_id"],
))

register_data_type(DataTypeDefinition(
    data_type="production_task_orders",
    data_name="生产任务单",
    description="OA 生产任务单（车间作业级）",
    model_name="ProductionTaskOrder",
    exposed_fields=[
        "id", "task_id", "task_no", "workshop",
        "material_code", "material_name",
        "planned_start_date", "planned_end_date",
        "actual_start_date", "actual_end_date",
        "task_qty", "repair_qty", "actual_qty",
        "task_type", "sale_order_no",
        "start_flag", "is_closed", "audit_status", "mrp_flag",
        "audit_user_id", "request_user_id", "supplier_id",
        "erp_updated_at", "updated_at",
    ],
    filter_fields=["workshop", "task_type", "is_closed", "audit_status", "mrp_flag", "sale_order_no"],
    search_fields=["task_no", "material_name"],
))
