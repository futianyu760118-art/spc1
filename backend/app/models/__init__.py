# 订单交付中心
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.order.eta_update import ETAUpdate

# 物料齐套中心
from app.models.material.material_demand import MaterialDemand
from app.models.material.purchase_order import PurchaseOrder
from app.models.material.binding import OrderMaterialPoBinding
from app.models.material.receipt_batch import ReceiptBatch
from app.models.material.material_issue import MaterialIssue
from app.models.material.long_lead_material import LongLeadMaterial
from app.models.material.purchase_invoice import PurchaseInvoice
from app.models.material.payment_apply import PaymentApply
from app.models.material.subcontract_order import SubcontractOrder
from app.models.material.subcontract_order_detail import SubcontractOrderDetail
from app.models.material.supplier_message import SupplierMessage
from app.models.material.kitting import KittingResult, KittingRun, KittingShortage  # noqa: F401
from app.models.material.transfer_order import TransferOrder  # noqa: F401
from app.models.material.purchase_requisition import PurchaseRequisition, PurchaseRequisitionLine, PurchaseRequisitionApprovalLog  # noqa: F401

# MRP 域（2026-09-24）
from app.models.mrp import MrpBucket, MrpParameter, MrpRun, MrpScheme, MrpSubstitute, MrpSuggestion  # noqa: F401

# 生产协同中心
from app.models.production.process_progress import ProcessProgress
from app.models.production.process_exception import ProcessException
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.models.production.base_condition import ProductionBaseCondition  # noqa: F401
from app.models.production.production_daily_report import ProductionDailyReport  # noqa: F401
from app.models.production.labor_price_audit import ProductionLaborPriceAudit  # noqa: F401
from app.models.production.workshop_daily_report import (  # noqa: F401
    WorkshopDailyReport,
    WorkshopDailyReportLeave,
    WorkshopDailyReportWork,
    WorkshopDailyReportTask,
)
from app.models.production.production_report import ProductionReport  # noqa: F401
from app.models.production.rework_order import ProductionReworkOrder  # noqa: F401

# 异常与质量中心
from app.models.exception.risk_issue import RiskIssue
from app.models.exception.quality_issue import QualityIssue

from app.models.common.business_document import BusinessDocument, BusinessDocumentVersion
from app.models.common.approval_business import ApprovalBusiness  # noqa: F401
from app.models.common.completeness_rule import CompletenessRule  # noqa: F401

# 规则配置中心
from app.models.rules.risk_rule import RiskRule
from app.models.rules.node_standard import NodeStandard

# 品质管理
from app.models.quality.supplier_claim import SupplierClaim, SupplierClaimApprovalLog  # noqa: F401

# 基础数据与集成中心
from app.models.basicdata.user import SysUser, SysRole
from app.models.basicdata.user_org_scope import UserOrgScope  # noqa: F401
from app.models.basicdata.audit_log import AuditLog
from app.models.basicdata.sync_sql_config import SyncSqlConfig  # noqa: F401
from app.models.basicdata.sync_log import SyncLog  # noqa: F401
from app.models.basicdata.position import Position  # noqa: F401
from app.models.basicdata.file_asset import FileAsset  # noqa: F401
from app.models.basicdata.feedback import Feedback  # noqa: F401
from app.models.basicdata.permission import SysPermission  # noqa: F401
from app.models.basicdata.announcement import Announcement, Notification  # noqa: F401
from app.models.basicdata.data_supply import DataSupplyApiKey, DataSupplyCallLog  # noqa: F401
from app.models.basicdata.reasoning import ReasoningTask  # noqa: F401
from app.models.basicdata.share_link import ShareLink  # noqa: F401
from app.models.basicdata.share_link_recipient import ShareLinkRecipient  # noqa: F401
from app.models.basicdata.backup import BackupConfig, BackupRecord  # noqa: F401
from app.models.basicdata.ai_agent import AiAgentConfig, AssistantRun  # noqa: F401
from app.models.purchase.price_change import (  # noqa: F401
    ApprovalConfig,
    PriceChangeRuleConfig,
    PurchasePriceChange,
    PurchasePriceChangeAiAnalysis,
    PurchasePriceChangeApprovalLog,
    PurchasePriceChangeItem,
)

# 以下模块此前未在本文件注册：init_database.create_all / alembic env 经 import app.models
# 只能看到已注册的表，漏注册 = 新库建不出表。注册只 import，符号用到处再引。
import app.models.basicdata.bom  # noqa: F401
import app.models.basicdata.bom_detail  # noqa: F401
import app.models.basicdata.customer  # noqa: F401
import app.models.basicdata.employee  # noqa: F401
import app.models.basicdata.employee_organization  # noqa: F401
import app.models.basicdata.inventory  # noqa: F401
import app.models.basicdata.location  # noqa: F401
import app.models.basicdata.material  # noqa: F401
import app.models.basicdata.organization  # noqa: F401
import app.models.basicdata.product  # noqa: F401
import app.models.basicdata.sku  # noqa: F401
import app.models.basicdata.subject_balance  # noqa: F401
import app.models.basicdata.supplier  # noqa: F401
import app.models.basicdata.warehouse  # noqa: F401
import app.models.basicdata.writeback_log  # noqa: F401
import app.models.basicdata.writeback_queue  # noqa: F401
import app.models.basicdata.writeback_sql_config  # noqa: F401
import app.models.common.approval_center  # noqa: F401
import app.models.material.inventory_check  # noqa: F401
import app.models.material.mrp_plan_order  # noqa: F401
import app.models.material.stock_check_writeback  # noqa: F401
import app.models.material.supplier_payment  # noqa: F401
import app.models.meeting.meeting  # noqa: F401
import app.models.npi.npi_project  # noqa: F401
import app.models.order.run_order  # noqa: F401
import app.models.production.capacity_slot  # noqa: F401
import app.models.production.front_process_record  # noqa: F401
import app.models.production.order_schedule_snapshot  # noqa: F401
import app.models.production.production_task_order  # noqa: F401
import app.models.production.product_process_capacity  # noqa: F401
import app.models.production.sale_order_line_change_log  # noqa: F401
import app.models.production.schedule_operation_log  # noqa: F401
import app.models.production.upph_formula_config  # noqa: F401
import app.models.production.work_order  # noqa: F401

__all__ = [
    # 订单交付中心
    "SaleOrder",
    "SaleOrderLine",
    # 物料齐套中心
    "MaterialDemand",
    "PurchaseOrder",
    "OrderMaterialPoBinding",
    "ReceiptBatch",
    "ETAUpdate",
    "MaterialIssue",
    "LongLeadMaterial",
    "PurchaseInvoice",
    "PaymentApply",
    "SubcontractOrder",
    "SubcontractOrderDetail",
    "SupplierMessage",
    # 生产协同中心
    "ProcessProgress",
    "ProcessException",
    "ProductionSchedulePlan",
    # 异常与质量中心
    "RiskIssue",
    "QualityIssue",
    "BusinessDocument",
    "BusinessDocumentVersion",
    "ApprovalBusiness",
    "CompletenessRule",
    # 规则配置中心
    "RiskRule",
    "NodeStandard",
    # 基础数据与集成中心
    "SysUser",
    "SysRole",
    "AuditLog",
    "SyncSqlConfig",
    "SyncLog",
    "Position",
    "FileAsset",
    "Feedback",
    "Announcement",
    "Notification",
    "SysPermission",
    "DataSupplyApiKey",
    "DataSupplyCallLog",
    "ReasoningTask",
    "ShareLink",
    "ShareLinkRecipient",
    # 品质管理
    "SupplierClaim",
    "SupplierClaimApprovalLog",
    "BackupConfig",
    "BackupRecord",
    "AiAgentConfig",
    "AssistantRun",
    "ApprovalConfig",
    "PriceChangeRuleConfig",
    "PurchasePriceChange",
    "PurchasePriceChangeAiAnalysis",
    "PurchasePriceChangeApprovalLog",
    "PurchasePriceChangeItem",
]
