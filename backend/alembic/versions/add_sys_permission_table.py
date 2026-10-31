"""add sys_permission table and seed data

Revision ID: add_sys_permission_table
Revises: merge_heads_before_perm
Create Date: 2026-06-23 00:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_sys_permission_table"
down_revision: Union[str, Sequence[str], None] = "merge_heads_before_perm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 所有当前系统权限的 seed 数据
# 格式: (code, name, module, parent_code, actions, route_path, sort_order)
PERMISSION_SEEDS = [
    # 供应链驾驶舱
    ("dashboard", "供应链驾驶舱", "dashboard", None, ["read"], "/dashboard", 1),

    # 顶栏功能
    ("topbar", "顶栏功能", "topbar", None, ["read"], None, 2),
    ("topbar.share", "页面分享", "topbar", "topbar", ["read"], None, 1),
    ("topbar.feedback", "问题反馈", "topbar", "topbar", ["read"], None, 2),
    ("topbar.ai_search", "AI 全局搜索", "topbar", "topbar", ["read"], None, 3),
    ("topbar.font_size", "字号设置", "topbar", "topbar", ["read"], None, 4),
    ("topbar.notifications", "通知铃铛", "topbar", "topbar", ["read"], None, 5),

    # 订单交付中心
    ("orders", "订单交付中心", "orders", None, ["create", "read", "update", "delete"], None, 3),
    ("orders.list", "订单总控台", "orders", "orders", ["create", "read", "update", "delete"], "/orders", 1),
    ("orders.run_orders", "跑单管理", "orders", "orders", ["create", "read", "update", "delete"], "/run-orders", 2),
    ("orders.risk_pool", "订单风险池", "orders", "orders", ["create", "read", "update", "delete"], "/order-risk-pool", 3),

    # 物料齐套中心
    ("materials", "物料齐套中心", "materials", None, ["create", "read", "update", "delete"], None, 4),
    ("materials.purchase_plan", "采购到料计划", "materials", "materials", ["create", "read", "update", "delete"], "/purchase-plan", 1),
    ("materials.issues", "问题物料池", "materials", "materials", ["create", "read", "update", "delete"], "/material-issues", 2),
    ("materials.long_lead", "长交期物料池", "materials", "materials", ["create", "read", "update", "delete"], "/long-lead-materials", 3),
    ("materials.kit_analysis", "齐套分析", "materials", "materials", ["create", "read", "update", "delete"], "/kit-analysis", 4),
    ("materials.supplier_risk", "供应商风险分析", "materials", "materials", ["create", "read", "update", "delete"], "/supplier-risk", 5),
    ("materials.supplier_payment", "供应商付款排程", "materials", "materials", ["create", "read", "update", "delete"], "/supplier-payment", 6),

    # 生产协同中心
    ("production", "生产协同中心", "production", None, ["create", "read", "update", "delete"], None, 5),
    ("production.overview", "生产总览", "production", "production", ["create", "read", "update", "delete"], "/production-overview", 1),
    ("production.schedule_plans", "计划排产", "production", "production", ["create", "read", "update", "delete"], "/schedule-plans", 2),
    ("production.product_process_capacities", "产品工序产能", "production", "production", ["create", "read", "update", "delete"], "/product-process-capacities", 3),
    ("production.front_process", "前道管理", "production", "production", ["create", "read", "update", "delete"], "/front-process", 4),
    ("production.smt", "贴片管理", "production", "production", ["create", "read", "update", "delete"], "/smt", 5),
    ("production.lean", "精益管理", "production", "production", ["create", "read", "update", "delete"], "/lean", 6),
    ("production.assembly", "组装管理", "production", "production", ["create", "read", "update", "delete"], "/assembly", 7),
    ("production.packaging", "包装管理", "production", "production", ["create", "read", "update", "delete"], "/packaging", 8),
    ("production.exceptions", "工序异常池", "production", "production", ["create", "read", "update", "delete"], "/process-exceptions", 9),

    # 异常与质量中心
    ("exceptions", "异常与质量中心", "exceptions", None, ["create", "read", "update", "delete"], None, 6),
    ("exceptions.pool", "异常总池", "exceptions", "exceptions", ["create", "read", "update", "delete"], "/issues", 1),
    ("exceptions.issue_log", "问题日志", "exceptions", "exceptions", ["create", "read", "update", "delete"], "/issue-log", 2),
    ("exceptions.change_log", "变更日志", "exceptions", "exceptions", ["create", "read", "update", "delete"], "/change-log", 3),
    ("exceptions.quality", "品质异常", "exceptions", "exceptions", ["create", "read", "update", "delete"], "/quality-issues", 4),
    ("exceptions.product_samples", "产品封样", "exceptions", "exceptions", ["create", "read", "update", "delete"], "/product-samples", 5),
    ("exceptions.closure", "闭环跟踪", "exceptions", "exceptions", ["create", "read", "update", "delete"], "/closure-tracking", 6),

    # 会议与任务中心
    ("meetings", "会议与任务中心", "meetings", None, ["create", "read", "update", "delete"], "/meetings", 7),

    # 新品/NPI项目中心
    ("npi", "新品/NPI项目中心", "npi", None, ["create", "read", "update", "delete"], "/npi", 8),

    # 规则配置中心
    ("rules", "规则配置中心", "rules", None, ["create", "read", "update", "delete"], None, 9),
    ("rules.risk_rules", "预警规则", "rules", "rules", ["create", "read", "update", "delete"], "/risk-rules", 1),
    ("rules.inspection", "点检规则", "rules", "rules", ["create", "read", "update", "delete"], "/inspection-rules", 2),
    ("rules.node_standards", "节点标准", "rules", "rules", ["create", "read", "update", "delete"], "/node-standards", 3),
    ("rules.order_standards", "订单标准", "rules", "rules", ["create", "read", "update", "delete"], "/order-standards", 4),
    ("rules.work_instructions", "作业指导书", "rules", "rules", ["create", "read", "update", "delete"], "/work-instructions", 5),
    ("rules.responsibility", "责任归属", "rules", "rules", ["create", "read", "update", "delete"], "/responsibility-map", 6),
    ("rules.status_dict", "状态字典", "rules", "rules", ["create", "read", "update", "delete"], "/status-dict", 7),

    # 基础数据与集成中心
    ("basicdata", "基础数据与集成中心", "basicdata", None, ["create", "read", "update", "delete"], None, 10),
    ("basicdata.import", "数据集成", "basicdata", "basicdata", ["create", "read", "update", "delete", "import"], "/import", 1),
    ("basicdata.data", "基础数据管理", "basicdata", "basicdata", ["create", "read", "update", "delete"], None, 2),
    ("basicdata.feedback", "问题反馈", "basicdata", "basicdata", ["create", "read", "update", "delete"], "/basicdata/feedback", 3),
    ("basicdata.files", "文件管理", "basicdata", "basicdata", ["create", "read", "update", "delete"], "/basicdata/files", 4),
    ("announcements", "公告管理", "basicdata", "basicdata", ["create", "read", "update", "delete"], "/announcements", 5),
    ("users", "用户管理", "basicdata", "basicdata", ["create", "read", "update", "delete"], "/users", 6),
    ("roles", "角色管理", "basicdata", "basicdata", ["create", "read", "update", "delete"], "/roles", 7),
    ("audit", "审计日志", "basicdata", "basicdata", ["read"], "/audit", 8),
    ("settings", "同步SQL配置", "basicdata", "basicdata", ["create", "read", "update", "delete"], "/sync-config", 9),
]


def upgrade() -> None:
    op.create_table(
        "sys_permission",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("parent_code", sa.String(128), nullable=True),
        sa.Column("actions", postgresql.JSONB(), nullable=False),
        sa.Column("route_path", sa.String(128), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    # Seed 权限数据
    op.execute("ALTER TABLE sys_permission ALTER COLUMN actions SET DEFAULT '[\"create\",\"read\",\"update\",\"delete\"]'::jsonb")

    for code, name, module, parent_code, actions, route_path, sort_order in PERMISSION_SEEDS:
        actions_json = json.dumps(actions, ensure_ascii=False)
        route_path_sql = f"'{route_path}'" if route_path else "NULL"
        parent_code_sql = f"'{parent_code}'" if parent_code else "NULL"
        op.execute(
            f"INSERT INTO sys_permission (code, name, module, parent_code, actions, route_path, sort_order, is_active) "
            f"VALUES ('{code}', '{name}', '{module}', {parent_code_sql}, '{actions_json}'::jsonb, {route_path_sql}, {sort_order}, true)"
        )


def downgrade() -> None:
    op.drop_table("sys_permission")
