"""add position role mapping

Revision ID: add_position_role_mapping
Revises: add_oa_position_id_to_position
Create Date: 2026-06-10 00:00:00.000000
"""
import hashlib
import json
from typing import Sequence, Union

from alembic import op


revision: str = "add_position_role_mapping"
down_revision: Union[str, Sequence[str], None] = "add_oa_position_id_to_position"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COMPANY_POSITION_NAMES = [
    "压铸师傅", "制程检验员", "组长", "模具师傅", "工程师", "实验室测量员", "业务员",
    "设备技术员", "抛丸工", "经理", "顾问", "总监", "技术员", "门卫", "厨师",
    "总经理助理", "专员", "维修技术员", "普工", "人事行政主管", "主任", "首件员",
    "喷枪手", "主管", "电子工程师", "仓管员", "多能工", "模具学徒工", "品质主管",
    "助理工程师", "结构工程师", "保洁", "采购员", "助理", "总经理", "主办会计",
    "AI经理", "后勤", "副总", "压铸工", "成本会计", "开发工程师",
]

COMMON = {
    "dashboard": ["read"],
    "basicdata.feedback": ["create", "read"],
    "announcements": ["read"],
    "topbar.share": ["read"],
    "topbar.feedback": ["read"],
    "topbar.ai_search": ["read"],
    "topbar.font_size": ["read"],
    "topbar.notifications": ["read"],
}

CATEGORY_BY_NAME = {
    "压铸师傅": "production_lead",
    "制程检验员": "quality",
    "组长": "production_lead",
    "模具师傅": "technician",
    "工程师": "engineer",
    "实验室测量员": "quality",
    "业务员": "sales",
    "设备技术员": "technician",
    "抛丸工": "operator",
    "经理": "manager",
    "顾问": "readonly",
    "总监": "director",
    "技术员": "technician",
    "门卫": "facility",
    "厨师": "facility",
    "总经理助理": "assistant",
    "专员": "assistant",
    "维修技术员": "technician",
    "普工": "operator",
    "人事行政主管": "hr_admin",
    "主任": "production_lead",
    "首件员": "quality",
    "喷枪手": "operator",
    "主管": "manager",
    "电子工程师": "engineer",
    "仓管员": "warehouse",
    "多能工": "operator",
    "模具学徒工": "operator",
    "品质主管": "quality_manager",
    "助理工程师": "engineer",
    "结构工程师": "engineer",
    "保洁": "facility",
    "采购员": "purchaser",
    "助理": "assistant",
    "总经理": "executive",
    "主办会计": "finance",
    "AI经理": "manager",
    "后勤": "facility",
    "副总": "director",
    "压铸工": "operator",
    "成本会计": "finance",
    "开发工程师": "engineer",
}

PRESETS = {
    "facility": COMMON,
    "employee": COMMON,
    "operator": {
        **COMMON,
        "production.overview": ["read"],
        "production.front_process": ["read", "update"],
        "production.smt": ["read", "update"],
        "production.lean": ["read", "update"],
        "production.assembly": ["read", "update"],
        "production.packaging": ["read", "update"],
        "production.exceptions": ["create", "read", "update"],
        "rules.work_instructions": ["read"],
    },
    "production_lead": {
        **COMMON,
        "orders.list": ["read"],
        "orders.run_orders": ["read", "update"],
        "materials.kit_analysis": ["read"],
        "production.overview": ["read", "update"],
        "production.front_process": ["read", "update", "import"],
        "production.smt": ["read", "update", "import"],
        "production.lean": ["read", "update", "import"],
        "production.assembly": ["read", "update", "import"],
        "production.packaging": ["read", "update", "import"],
        "production.exceptions": ["create", "read", "update"],
        "exceptions.pool": ["read", "update"],
        "exceptions.issue_log": ["create", "read", "update"],
        "exceptions.closure": ["read", "update"],
        "basicdata.data": ["read"],
    },
    "quality": {
        **COMMON,
        "production.overview": ["read"],
        "production.exceptions": ["read", "update"],
        "exceptions.pool": ["read"],
        "exceptions.issue_log": ["create", "read", "update"],
        "exceptions.quality": ["create", "read", "update", "import"],
        "exceptions.product_samples": ["read", "update"],
        "exceptions.closure": ["read", "update"],
        "rules.inspection": ["read"],
        "rules.node_standards": ["read"],
        "rules.order_standards": ["read"],
        "rules.work_instructions": ["read"],
        "basicdata.data": ["read"],
    },
    "quality_manager": {
        **COMMON,
        "orders.list": ["read"],
        "production.overview": ["read", "update"],
        "production.exceptions": ["read", "update"],
        "exceptions.pool": ["read", "update"],
        "exceptions.issue_log": ["read", "update"],
        "exceptions.change_log": ["read", "update"],
        "exceptions.quality": ["create", "read", "update", "delete", "import"],
        "exceptions.product_samples": ["create", "read", "update", "delete"],
        "exceptions.closure": ["read", "update"],
        "rules.inspection": ["read", "update"],
        "rules.node_standards": ["read", "update"],
        "basicdata.data": ["read"],
        "audit": ["read"],
    },
    "engineer": {
        **COMMON,
        "orders.list": ["read"],
        "materials.kit_analysis": ["read"],
        "production.overview": ["read", "update"],
        "production.exceptions": ["create", "read", "update"],
        "exceptions.pool": ["read", "update"],
        "exceptions.issue_log": ["create", "read", "update"],
        "exceptions.change_log": ["read", "update"],
        "exceptions.quality": ["read", "update"],
        "exceptions.product_samples": ["read", "update"],
        "exceptions.closure": ["read", "update"],
        "npi": ["read", "update"],
        "rules.inspection": ["read", "update"],
        "rules.node_standards": ["read", "update"],
        "rules.order_standards": ["read", "update"],
        "rules.work_instructions": ["read", "update"],
        "basicdata.data": ["read"],
    },
    "technician": {
        **COMMON,
        "production.overview": ["read"],
        "production.front_process": ["read", "update"],
        "production.smt": ["read", "update"],
        "production.lean": ["read", "update"],
        "production.assembly": ["read", "update"],
        "production.packaging": ["read", "update"],
        "production.exceptions": ["create", "read", "update"],
        "exceptions.issue_log": ["create", "read", "update"],
        "rules.work_instructions": ["read"],
        "basicdata.data": ["read"],
    },
    "sales": {
        **COMMON,
        "orders.list": ["read", "update"],
        "orders.run_orders": ["read", "update"],
        "orders.risk_pool": ["read"],
        "materials.purchase_plan": ["read"],
        "materials.kit_analysis": ["read"],
        "materials.supplier_risk": ["read"],
        "exceptions.pool": ["read"],
        "exceptions.issue_log": ["create", "read", "update"],
        "exceptions.change_log": ["read"],
        "exceptions.closure": ["read"],
        "meetings": ["read", "update"],
        "npi": ["read"],
        "basicdata.data": ["read"],
    },
    "purchaser": {
        **COMMON,
        "orders.list": ["read"],
        "orders.run_orders": ["read"],
        "orders.risk_pool": ["read"],
        "materials.purchase_plan": ["create", "read", "update", "import"],
        "materials.issues": ["create", "read", "update", "import"],
        "materials.long_lead": ["create", "read", "update", "import"],
        "materials.kit_analysis": ["create", "read", "update", "import"],
        "materials.supplier_risk": ["create", "read", "update", "import"],
        "materials.supplier_payment": ["create", "read", "update", "import"],
        "exceptions.pool": ["read"],
        "exceptions.issue_log": ["read"],
        "exceptions.change_log": ["read"],
        "exceptions.quality": ["read"],
        "basicdata.import": ["read"],
        "basicdata.data": ["read"],
        "audit": ["read"],
    },
    "warehouse": {
        **COMMON,
        "orders.list": ["read"],
        "materials.purchase_plan": ["read", "update", "import"],
        "materials.issues": ["read", "update", "import"],
        "materials.long_lead": ["read"],
        "materials.kit_analysis": ["read", "update", "import"],
        "production.overview": ["read"],
        "basicdata.data": ["read"],
    },
    "finance": {
        **COMMON,
        "orders.list": ["read"],
        "materials.purchase_plan": ["read"],
        "materials.supplier_risk": ["read"],
        "materials.supplier_payment": ["create", "read", "update", "import"],
        "basicdata.data": ["read"],
        "audit": ["read"],
    },
    "hr_admin": {
        **COMMON,
        "basicdata.data": ["read", "update"],
        "users": ["read", "update"],
        "audit": ["read"],
        "announcements": ["create", "read", "update"],
    },
    "assistant": {
        **COMMON,
        "orders.list": ["read"],
        "orders.run_orders": ["read"],
        "materials.purchase_plan": ["read"],
        "materials.kit_analysis": ["read"],
        "production.overview": ["read"],
        "exceptions.pool": ["read"],
        "exceptions.issue_log": ["create", "read", "update"],
        "meetings": ["read", "update"],
        "basicdata.data": ["read"],
    },
    "manager": {
        **COMMON,
        "orders.list": ["read", "update"],
        "orders.run_orders": ["read", "update"],
        "orders.risk_pool": ["read", "update"],
        "materials.purchase_plan": ["read", "update"],
        "materials.issues": ["read", "update"],
        "materials.long_lead": ["read", "update"],
        "materials.kit_analysis": ["read", "update"],
        "materials.supplier_risk": ["read", "update"],
        "materials.supplier_payment": ["read", "update"],
        "production.overview": ["read", "update"],
        "production.exceptions": ["read", "update"],
        "exceptions.pool": ["read", "update"],
        "exceptions.issue_log": ["read", "update"],
        "exceptions.change_log": ["read", "update"],
        "exceptions.quality": ["read", "update"],
        "exceptions.product_samples": ["read", "update"],
        "exceptions.closure": ["read", "update"],
        "meetings": ["create", "read", "update", "delete"],
        "npi": ["read", "update"],
        "rules.order_standards": ["read", "update"],
        "rules.work_instructions": ["read", "update"],
        "basicdata.import": ["read"],
        "basicdata.data": ["read"],
        "basicdata.feedback": ["read", "update"],
        "audit": ["read"],
    },
    "director": {
        **COMMON,
        "orders.list": ["read", "update"],
        "orders.run_orders": ["read", "update"],
        "orders.risk_pool": ["read", "update"],
        "materials.purchase_plan": ["read", "update"],
        "materials.issues": ["read", "update"],
        "materials.long_lead": ["read", "update"],
        "materials.kit_analysis": ["read", "update"],
        "materials.supplier_risk": ["read", "update"],
        "materials.supplier_payment": ["read", "update"],
        "production.overview": ["read", "update"],
        "production.exceptions": ["read", "update"],
        "exceptions.pool": ["read", "update"],
        "exceptions.issue_log": ["read", "update"],
        "exceptions.change_log": ["read", "update"],
        "exceptions.quality": ["read", "update"],
        "exceptions.product_samples": ["read", "update"],
        "exceptions.closure": ["read", "update"],
        "meetings": ["create", "read", "update", "delete"],
        "npi": ["read", "update"],
        "rules.risk_rules": ["read"],
        "rules.inspection": ["read"],
        "rules.node_standards": ["read"],
        "rules.order_standards": ["read"],
        "rules.work_instructions": ["read"],
        "rules.responsibility": ["read"],
        "rules.status_dict": ["read"],
        "basicdata.import": ["read"],
        "basicdata.data": ["read"],
        "basicdata.feedback": ["read", "update"],
        "audit": ["read"],
    },
    "executive": {
        **COMMON,
        "orders.list": ["read", "update"],
        "orders.run_orders": ["read", "update"],
        "orders.risk_pool": ["read", "update"],
        "materials.purchase_plan": ["read", "update"],
        "materials.issues": ["read", "update"],
        "materials.long_lead": ["read", "update"],
        "materials.kit_analysis": ["read", "update"],
        "materials.supplier_risk": ["read", "update"],
        "materials.supplier_payment": ["read", "update"],
        "production.overview": ["read", "update"],
        "production.exceptions": ["read", "update"],
        "exceptions.pool": ["read", "update"],
        "exceptions.issue_log": ["read", "update"],
        "exceptions.change_log": ["read", "update"],
        "exceptions.quality": ["read", "update"],
        "exceptions.product_samples": ["read", "update"],
        "exceptions.closure": ["read", "update"],
        "meetings": ["create", "read", "update", "delete"],
        "npi": ["read", "update"],
        "rules.risk_rules": ["read", "update"],
        "rules.inspection": ["read", "update"],
        "rules.node_standards": ["read", "update"],
        "rules.order_standards": ["read", "update"],
        "rules.work_instructions": ["read", "update"],
        "rules.responsibility": ["read", "update"],
        "rules.status_dict": ["read", "update"],
        "basicdata.import": ["read"],
        "basicdata.data": ["read"],
        "basicdata.feedback": ["read", "update"],
        "announcements": ["create", "read", "update"],
        "audit": ["read"],
        "settings": ["read"],
    },
    "readonly": {
        **COMMON,
        "orders.list": ["read"],
        "materials.purchase_plan": ["read"],
        "production.overview": ["read"],
        "exceptions.pool": ["read"],
        "rules.order_standards": ["read"],
        "rules.work_instructions": ["read"],
    },
}


def role_code(position_code: str, position_name: str) -> str:
    source = (position_name or position_code or "position").strip().lower()
    return "pos_" + hashlib.sha1(source.encode("utf-8")).hexdigest()[:24]


def permissions_for(name: str) -> str:
    category = CATEGORY_BY_NAME.get(name, "employee")
    return json.dumps(PRESETS.get(category, PRESETS["employee"]), ensure_ascii=False)


def upgrade() -> None:
    op.execute("ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS emp_code VARCHAR(20)")
    op.execute("ALTER TABLE scm_position ADD COLUMN IF NOT EXISTS role_id INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scm_position_role_id ON scm_position (role_id)")

    for index, name in enumerate(COMPANY_POSITION_NAMES, start=1):
        code = f"POS{index:03d}"
        role = role_code(code, name)
        role_name = f"岗位-{name}"
        perms = permissions_for(name).replace("'", "''")
        escaped_name = name.replace("'", "''")
        escaped_role_name = role_name.replace("'", "''")
        op.execute(
            f"""
            UPDATE scm_position
            SET status = 1
            WHERE position_code = '{code}'
               OR position_name = '{escaped_name}'
            """
        )
        op.execute(
            f"""
            INSERT INTO scm_position (position_code, position_name, status, data_source)
            SELECT '{code}', '{escaped_name}', 1, 'company_seed'
            WHERE NOT EXISTS (
                SELECT 1
                FROM scm_position
                WHERE position_code = '{code}'
                   OR position_name = '{escaped_name}'
            )
            """
        )
        op.execute(
            f"""
            INSERT INTO sys_role (role_code, role_name, permissions)
            VALUES ('{role}', '{escaped_role_name}', '{perms}'::jsonb)
            ON CONFLICT (role_code) DO UPDATE
            SET role_name = EXCLUDED.role_name,
                permissions = CASE
                    WHEN sys_role.permissions IS NULL OR sys_role.permissions = '{{}}'::jsonb
                    THEN EXCLUDED.permissions
                    ELSE sys_role.permissions
                END
            """
        )
        op.execute(
            f"""
            UPDATE scm_position
            SET role_id = (SELECT id FROM sys_role WHERE role_code = '{role}')
            WHERE position_code = '{code}'
               OR (position_name = '{escaped_name}' AND role_id IS NULL)
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_scm_position_role_id")
    op.execute("ALTER TABLE scm_position DROP COLUMN IF EXISTS role_id")
