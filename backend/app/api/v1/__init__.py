from fastapi import APIRouter

from app.api.v1 import dashboard, order, material, production, exception, meeting, npi, rules, masterdata, common, assistant

api_router = APIRouter()

# 供应链驾驶舱
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["供应链驾驶舱"])

# 订单交付中心
api_router.include_router(order.order_router, prefix="/orders", tags=["订单交付中心"])
api_router.include_router(order.eta_router, prefix="/orders/eta", tags=["ETA管理"])
api_router.include_router(order.run_order_router, prefix="/run-orders", tags=["跑单管理"])

# 物料齐套中心（具体子路由必须注册在 po_router 之前，否则 /{po_no} 通配会抢占子路径）
api_router.include_router(material.purchase_plan_router, prefix="/materials/purchase-plan", tags=["物料齐套中心-采购到料计划"])
api_router.include_router(material.issues_router, prefix="/materials/issues", tags=["物料齐套中心-问题物料"])
api_router.include_router(material.long_lead_router, prefix="/materials/long-lead", tags=["物料齐套中心-长交期物料"])
api_router.include_router(material.kit_analysis_router, prefix="/materials/kit-analysis", tags=["物料齐套中心-齐套分析"])
api_router.include_router(material.supplier_risk_router, prefix="/materials/supplier-risk", tags=["物料齐套中心-供应商风险"])
api_router.include_router(material.supplier_payment_router, prefix="/materials/supplier-payment", tags=["物料齐套中心-供应商付款排程"])
api_router.include_router(material.po_router, prefix="/materials", tags=["物料齐套中心-ERP采购订单"])

# 生产协同中心
api_router.include_router(production.router, prefix="/production", tags=["生产协同中心"])

# 异常与质量中心
api_router.include_router(exception.issues_router, prefix="/exceptions", tags=["异常与质量中心"])
api_router.include_router(exception.risk_router, prefix="/exceptions/risk", tags=["风险扫描"])
api_router.include_router(exception.pool_router, prefix="/exceptions/pool", tags=["异常总池"])
api_router.include_router(exception.issue_log_router, prefix="/exceptions/issue-log", tags=["问题日志"])
api_router.include_router(exception.change_log_router, prefix="/exceptions/change-log", tags=["变更日志"])
api_router.include_router(exception.quality_router, prefix="/exceptions/quality", tags=["品质异常"])

# 会议与任务中心（占位）
api_router.include_router(meeting.router, prefix="/meetings", tags=["会议与任务中心"])

# 新品/NPI项目中心（占位）
api_router.include_router(npi.router, prefix="/npi", tags=["新品/NPI项目中心"])

# 规则配置中心
api_router.include_router(rules.rules_router, prefix="/rules", tags=["规则配置中心"])
api_router.include_router(rules.inspections_router, prefix="/rules/inspections", tags=["点检规则配置"])
api_router.include_router(rules.node_standards_router, prefix="/rules/node-standards", tags=["节点标准配置"])
api_router.include_router(rules.responsibilities_router, prefix="/rules/responsibilities", tags=["责任归属配置"])
api_router.include_router(rules.status_dict_router, prefix="/rules/status-dict", tags=["状态字典配置"])

# 主数据与集成中心
api_router.include_router(masterdata.auth_router, prefix="/masterdata/auth", tags=["认证"])
api_router.include_router(masterdata.users_router, prefix="/masterdata/users", tags=["用户管理"])
api_router.include_router(masterdata.audit_router, prefix="/masterdata/audit", tags=["审计日志"])
api_router.include_router(masterdata.import_export_router, prefix="/masterdata/import-export", tags=["导入导出"])
api_router.include_router(masterdata.sync_router, prefix="/masterdata/sync", tags=["ERP同步"])
api_router.include_router(masterdata.masterdata_router, prefix="/masterdata", tags=["主数据管理"])
api_router.include_router(masterdata.sync_sql_router, prefix="/masterdata/sync-sql", tags=["同步SQL配置"])
api_router.include_router(masterdata.feedback_router, prefix="/masterdata/feedback", tags=["问题反馈"])

# 通用文件服务
api_router.include_router(common.files_router, prefix="/files", tags=["文件"])

# 智能助手
api_router.include_router(assistant.assistant_router, prefix="/assistant", tags=["智能助手"])
