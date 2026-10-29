"""供应商索赔测试套件全局设施。

关键约束：app.core.database 在「导入时」就按 settings.DATABASE_URL 创建全局引擎池，
因此必须在任何 app 业务模块导入之前完成环境变量覆盖（指向独立测试库 spc_test）
并清空 get_settings 的 lru_cache。pytest 先导入 conftest 再导入测试模块，
故本文件顶部的覆盖代码天然先于所有测试模块的 app 导入执行。
"""

import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse

from app.core.config import get_settings  # config 模块无副作用，不建引擎

TEST_DB_NAME = os.environ.get("SPC_TEST_DB", "spc_test")
TEST_PASSWORD = "test1234"

# 基线配置（来自 backend/.env.local），只用于推导测试库地址
_base = get_settings()


def _swap_db(url: str, db_name: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{db_name}"))


os.environ["DATABASE_URL"] = _swap_db(_base.DATABASE_URL, TEST_DB_NAME)
os.environ["DATABASE_URL_SYNC"] = _swap_db(_base.DATABASE_URL_SYNC, TEST_DB_NAME)
# Redis 指向不可达地址：通知推送等 Redis 调用走降级分支。测试用户 id 与开发库重叠，
# 不隔离会把 spc_test 的 notif:{user_id} 事件推给正在使用的开发环境
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
get_settings.cache_clear()

# ---------------------------------------------------------------- 环境就绪，以下才能导入 app 模块

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

ROLES = ["admin", "quality", "purchase_manager", "manager", "finance", "general_manager", "viewer"]
# permissions 为空 dict 时 PermissionChecker 视作「角色配置异常」（not row[0]），故每个角色至少给一项
BASE_PERMS = {"dashboard": ["read"]}
# general_manager 无代码内权限加成，直接在角色行种入权限 JSON，模拟「角色管理」运行时授予路径
ROLE_PERMS = {
    code: dict(BASE_PERMS) for code in ROLES
}
ROLE_PERMS["general_manager"].update({
    "quality.supplier_claim": ["read"],
    "approval.pending": ["read"],
})
ROLE_PERMS["admin"].update({"orders.list": ["read"], "topbar.notifications": ["read"]})
ROLE_PERMS["manager"].update({"orders.list": ["read"], "topbar.notifications": ["read"]})
USERS = {
    "admin": "admin",
    "qa_quality": "quality",
    "qa_quality2": "quality",
    "qa_pm": "purchase_manager",
    "qa_mgr": "manager",
    "qa_fin": "finance",
    "qa_gm": "general_manager",
    "qa_viewer": "viewer",
}

DEFAULT_CHAIN = [
    {"seq": 1, "label": "索赔部门意见", "role": "purchase_manager"},
    {"seq": 2, "label": "上级部门意见", "role": "manager",
     "condition": {"field": "claim_amount", "op": ">=", "value": 1000}},
    {"seq": 3, "label": "总经理意见", "role": "general_manager",
     "condition": {"field": "claim_amount", "op": ">=", "value": 5000}},
    {"seq": 4, "label": "财务结算", "role": "finance"},
]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _test_db():
    """创建独立测试库 + 全量表 + 最小种子（角色/用户/默认审批链），整个测试会话复用。"""
    import asyncio

    import app.models  # noqa: F401 — 将全部模型注册到 Base.metadata
    from app.core.database import Base, engine
    from app.core.security import get_password_hash

    # 1) 经 sync 引擎连 postgres 库建测试库（与 init_database.create_database 同模式）
    sync_engine = create_engine(_swap_db(_base.DATABASE_URL_SYNC, "postgres"))
    with sync_engine.connect() as conn:
        conn.execute(text("COMMIT"))
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": TEST_DB_NAME}
        ).fetchone()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        conn.execute(text("COMMIT"))
    sync_engine.dispose()

    # 2) 只建本套件所需的最小表集合——全量 create_all 会被遗留模型的
    #    order_material_po_binding 非法外键（po_no 无唯一约束）卡死，且与本功能无关
    from app.models.basicdata.announcement import Notification
    from app.models.basicdata.ai_agent import AiAgentConfig, AssistantRun
    from app.models.basicdata.audit_log import AuditLog
    from app.models.basicdata.backup import BackupConfig, BackupRecord
    from app.models.basicdata.bom import Bom
    from app.models.basicdata.bom_detail import BomDetail
    from app.models.basicdata.data_supply import DataSupplyApiKey, DataSupplyCallLog
    from app.models.basicdata.file_asset import FileAsset
    from app.models.basicdata.feedback import Feedback
    from app.models.basicdata.inventory import Inventory
    from app.models.basicdata.location import Location
    from app.models.basicdata.material import Material
    from app.models.basicdata.permission import SysPermission
    from app.models.basicdata.sync_sql_config import SyncSqlConfig
    from app.models.basicdata.user import SysRole, SysUser
    from app.models.basicdata.supplier import Supplier
    from app.models.basicdata.user_org_scope import UserOrgScope
    from app.models.basicdata.employee import Employee
    from app.models.basicdata.organization import Organization
    from app.models.agent import (
        Agent, AgentCallLog, AgentConversation, AgentMessage,
        AgentTeamMember, GatewayDispatchLog,
    )
    from app.models.basicdata.reasoning import ReasoningTask
    from app.models.exception.quality_issue import QualityIssue
    from app.models.material.inventory_check import StockCheck, StockCheckItem
    from app.models.material.kitting import KittingResult, KittingShortage
    from app.models.material.purchase_order import PurchaseOrder
    from app.models.material.purchase_requisition import (
        PurchaseRequisition,
        PurchaseRequisitionApprovalLog,
        PurchaseRequisitionLine,
    )
    from app.models.purchase.price_change import (
        PurchasePriceChange,
        PurchasePriceChangeAiAnalysis,
        PurchasePriceChangeApprovalLog,
        PurchasePriceChangeItem,
    )
    from app.models.order.sale_order import SaleOrder, SaleOrderLine
    from app.models.order.write_idempotency import OrderWriteIdempotency
    from app.models.production.base_condition import ProductionBaseCondition
    from app.models.production.capacity_slot import CapacitySlot
    from app.models.production.order_schedule_snapshot import ProductionOrderScheduleSnapshot
    from app.models.production.process_progress import ProcessProgress
    from app.models.production.production_daily_report import ProductionDailyReport
    from app.models.production.production_task_order import ProductionTaskOrder
    from app.models.quality.supplier_claim import SupplierClaim, SupplierClaimApprovalLog
    from app.models.common.approval_business import ApprovalBusiness
    from app.models.common.approval_center import ApprovalInstance, ApprovalRecord, ApprovalTask
    from app.models.common.completeness_rule import CompletenessRule
    tables = [
        SysRole.__table__, SysUser.__table__, UserOrgScope.__table__,
        SysPermission.__table__,
        BackupRecord.__table__, BackupConfig.__table__,
        SupplierClaim.__table__, SupplierClaimApprovalLog.__table__,
        Notification.__table__, FileAsset.__table__,
        Feedback.__table__,
        DataSupplyApiKey.__table__, DataSupplyCallLog.__table__,
        QualityIssue.__table__, SaleOrder.__table__, SaleOrderLine.__table__,
        OrderWriteIdempotency.__table__,
        Bom.__table__, BomDetail.__table__, Supplier.__table__,
        ProductionTaskOrder.__table__, ProcessProgress.__table__,
        ProductionOrderScheduleSnapshot.__table__, ProductionDailyReport.__table__,
        CapacitySlot.__table__, ProductionBaseCondition.__table__,
        ApprovalBusiness.__table__, SyncSqlConfig.__table__, AuditLog.__table__,
        ApprovalInstance.__table__, ApprovalTask.__table__, ApprovalRecord.__table__,
        Material.__table__, PurchaseOrder.__table__,
        PurchaseRequisition.__table__, PurchaseRequisitionLine.__table__,
        PurchaseRequisitionApprovalLog.__table__,
        PurchasePriceChange.__table__, PurchasePriceChangeItem.__table__,
        PurchasePriceChangeApprovalLog.__table__, PurchasePriceChangeAiAnalysis.__table__,
        Inventory.__table__, Location.__table__,
        StockCheck.__table__, StockCheckItem.__table__,
        ReasoningTask.__table__, KittingResult.__table__, KittingShortage.__table__,
        AiAgentConfig.__table__, AssistantRun.__table__,
        CompletenessRule.__table__,
        Organization.__table__, Employee.__table__,
        Agent.__table__, AgentCallLog.__table__, AgentConversation.__table__,
        AgentMessage.__table__, AgentTeamMember.__table__, GatewayDispatchLog.__table__,
    ]
    async with engine.begin() as conn:
        # 旧结构测试库（agent 表仍含 user_id 或单值 capability_code 列）：agent 域表整体重建——
        # create_all 只建缺失表、不改既有列，与 init_database 的 legacy 判断同模式
        legacy_agent = (await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'agent' AND column_name IN ('user_id', 'capability_code')"
        ))).first()
        if legacy_agent:
            await conn.execute(text(
                "DROP TABLE IF EXISTS agent_team_member, agent_hierarchy_log, agent_config_log, "
                "agent_call_log, agent_conversation, agent_message, gateway_dispatch_log, agent CASCADE"
            ))
        await conn.run_sync(Base.metadata.create_all, tables=tables)
        # 既有测试库补列：create_all 只建缺失表不加列（同 init_database 的 migrate_columns 模式）
        await conn.execute(text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS ai_result JSONB"))
        await conn.execute(text("ALTER TABLE supplier_claim ADD COLUMN IF NOT EXISTS clause_snapshot JSONB"))
        await conn.execute(text("ALTER TABLE notification ADD COLUMN IF NOT EXISTS ref_no VARCHAR(64)"))
        await conn.execute(text("ALTER TABLE assistant_run ADD COLUMN IF NOT EXISTS agent_id BIGINT"))
        await conn.execute(text("ALTER TABLE assistant_run ADD COLUMN IF NOT EXISTS task_id BIGINT"))
        await conn.execute(text("ALTER TABLE assistant_run ADD COLUMN IF NOT EXISTS conversation_id BIGINT"))
        await conn.execute(text(
            "ALTER TABLE assistant_run ADD COLUMN IF NOT EXISTS trigger VARCHAR(16) NOT NULL DEFAULT 'chat'"
        ))
        await conn.execute(text(
            "ALTER TABLE purchase_price_change_item ADD COLUMN IF NOT EXISTS unit_id INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE purchase_price_change_item "
            "ALTER COLUMN price_change_pct TYPE NUMERIC(10,2)"
        ))
        await conn.execute(text(
            "ALTER TABLE purchase_price_change "
            "ALTER COLUMN self_check_evidence TYPE JSONB USING self_check_evidence::jsonb"
        ))
        # approval_config 模型在 purchase 域（故意不导入），直接 DDL 建表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS approval_config (
                id SERIAL PRIMARY KEY,
                biz_type VARCHAR(64) NOT NULL UNIQUE,
                biz_name VARCHAR(128),
                nodes JSONB NOT NULL DEFAULT '[]'::jsonb,
                is_active BOOLEAN DEFAULT TRUE,
                updated_by VARCHAR(64),
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL
            )
        """))

    # 3) 幂等种子（upsert，重复运行不产生重复行）
    async with engine.begin() as conn:
        for code in ROLES:
            await conn.execute(text("""
                INSERT INTO sys_role (role_code, role_name, permissions)
                VALUES (:code, :code, CAST(:perms AS jsonb))
                ON CONFLICT (role_code) DO UPDATE SET role_name = EXCLUDED.role_name,
                                                     permissions = EXCLUDED.permissions
            """), {"code": code, "perms": json.dumps(ROLE_PERMS.get(code, {}))})
        rows = ",".join(f"('{u}', '{r}')" for u, r in USERS.items())
        user_rows_sql = f"""
            INSERT INTO sys_user (username, hashed_password, is_active, role_id, login_version,
                                  is_default_password, channel_sessions, font_size_scale, created_at)
            SELECT u.username, :pwd, TRUE, r.id, 1, TRUE, '{{}}'::jsonb, '1.0', NOW()
            FROM (VALUES {rows}) AS u(username, role_code)
            JOIN sys_role r ON r.role_code = u.role_code
            ON CONFLICT (username) DO UPDATE SET hashed_password = EXCLUDED.hashed_password,
                                            is_active = TRUE, role_id = EXCLUDED.role_id
        """
        await conn.execute(text(user_rows_sql), {"pwd": get_password_hash(TEST_PASSWORD)})
        await conn.execute(text("""
            INSERT INTO approval_config (biz_type, biz_name, nodes, is_active, updated_by)
            VALUES ('supplier_claim', '供应商索赔单', CAST(:nodes AS jsonb), TRUE, 'pytest')
            ON CONFLICT (biz_type) DO NOTHING
        """), {"nodes": json.dumps(DEFAULT_CHAIN)})
        # 生产协同对外接口空表时的 data_as_of 回退源（固定旧值使断言稳定）
        await conn.execute(text("""
            INSERT INTO sync_sql_config
                (sync_type, description, sql_text, sync_interval, sync_strategy,
                 sync_priority, sync_enabled, is_active, last_sync_time)
            VALUES ('production_daily_reports', 'pytest 时效回退种子', 'SELECT 1', '1h', 'full',
                    5, TRUE, TRUE, :t)
            ON CONFLICT (sync_type) DO UPDATE SET last_sync_time = EXCLUDED.last_sync_time
        """), {"t": datetime(2026, 8, 6, 15, 44, 3)})
        # 工序表全空时回退的 CSV 导入时间（audit_log，先删旧种子保证幂等）
        # 取相对当前时间 3 小时前：新时效口径下仍为 high 且 stale=false，断言不随运行日期漂移
        process_import_at = (datetime.now() - timedelta(hours=3)).replace(microsecond=0)
        await conn.execute(text(
            "DELETE FROM audit_log WHERE table_name = 'process_progress' AND operator = 'pytest'"
        ))
        await conn.execute(text("""
            INSERT INTO audit_log
                (table_name, record_id, action, field_name, new_value, operator, operated_at)
            VALUES ('process_progress', 0, 'import', 'assembly_csv', 'pytest.csv', 'pytest', :t)
        """), {"t": process_import_at})
    yield
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def client(_test_db):
    """每个测试独立的 ASGI 客户端；前置清空业务表，保证用例互不影响可重复运行。"""
    from app.core.database import engine
    from app.main import app

    async with engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE supplier_claim, supplier_claim_approval_log, notification, file_asset, feedback, "
            "purchase_requisition, purchase_requisition_line, purchase_requisition_approval_log, "
            "purchase_price_change, purchase_price_change_item, purchase_price_change_approval_log, "
            "purchase_price_change_ai_analysis, "
            "purchase_order, approval_instance, approval_task, approval_record, "
            "backup_record, scm_inventory, scm_location, scm_inventory_check, scm_inventory_check_item, "
            "ai_agent_config, assistant_run, completeness_rule, "
            "agent_message, agent_conversation, agent_call_log, "
            "agent_team_member, agent, gateway_dispatch_log, "
            "scm_employee, scm_organization RESTART IDENTITY CASCADE"
        ))
        # 审批配置恢复默认链与启用态（配置/停用类用例会改，不能污染后续用例）
        await conn.execute(text("""
            UPDATE approval_config SET nodes = CAST(:nodes AS jsonb), is_active = TRUE
            WHERE biz_type = 'supplier_claim'
        """), {"nodes": json.dumps(DEFAULT_CHAIN)})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        try:
            yield c
        finally:
            from app.services.notification.assistant_notify import flush_notifications
            await flush_notifications()


@pytest_asyncio.fixture(loop_scope="session")
async def db(_test_db):
    """直查数据库用的会话（通知/引用计数等落库断言）。"""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session


# 质量对外接口测试用 HMAC Key（假凭证，rate_limit=0 绕过 Redis）
EXTERNAL_QUALITY_KEY = {"app_key": "ak_pytest_quality", "app_secret": "sk_pytest_quality"}
EXTERNAL_ORDERS_KEY = {"app_key": "ak_pytest_orders", "app_secret": "sk_pytest_orders"}
EXTERNAL_PRODUCTION_KEY = {"app_key": "ak_pytest_production", "app_secret": "sk_pytest_production"}
EXTERNAL_REASONING_KEY = {"app_key": "ak_pytest_reasoning", "app_secret": "sk_pytest_reasoning"}
EXTERNAL_AGENT_KEY = {"app_key": "ak_pytest_agent", "app_secret": "sk_pytest_agent"}
EXTERNAL_ORDER_AGENT_KEY = {"app_key": "ak_pytest_order_agent", "app_secret": "sk_pytest_order_agent"}

PRODUCTION_ENDPOINT_CODES = [
    "production.work_orders.list",
    "production.operations.list",
    "production.order_links.list",
    "production.reports.list",
    "production.capacity.list",
]


@pytest_asyncio.fixture(loop_scope="session")
async def external_keys(_test_db):
    """清空质量/生产/数据供给表并种入四把 HMAC Key：quality / orders（未授权对照）/ production / reasoning。"""
    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE quality_issue, sale_order, sale_order_line, order_write_idempotency, "
            "scm_bom, scm_bom_detail, "
            "scm_material, scm_supplier, production_task_order, process_progress, "
            "production_order_schedule_snapshot, production_daily_report, "
            "production_capacity_slot, production_base_condition, "
            "data_supply_api_key, data_supply_call_log, "
            "reasoning_task, kitting_result, kitting_shortage RESTART IDENTITY CASCADE"
        ))
        await conn.execute(text("""
            INSERT INTO data_supply_api_key
                (key_name, api_key, is_active, allowed_endpoints_json, rate_limit,
                 app_key, app_secret, ip_whitelist_json, created_by)
            VALUES
                ('pytest-quality', 'ak_pytest_quality', TRUE,
                 '["quality_issues.list", "quality_trace.list"]', 0, :qak, :qas, NULL, 'pytest'),
                ('pytest-orders', 'ak_pytest_orders', TRUE,
                 '["orders.list", "order_details.list", "boms.tree", "materials.list", "suppliers.list"]',
                 0, :oak, :oas, NULL, 'pytest'),
                ('pytest-production', 'ak_pytest_production', TRUE,
                 CAST(:pcodes AS jsonb), 0, :pak, :pas, NULL, 'pytest'),
                ('pytest-reasoning', 'ak_pytest_reasoning', TRUE,
                 '["reasoning.analyze", "reasoning.cancel", "reasoning.task"]',
                 0, :rak, :ras, NULL, 'pytest'),
                ('pytest-agent', 'ak_pytest_agent', TRUE,
                 '["agent.config"]', 0, :gak, :gas, NULL, 'pytest'),
                ('pytest-order-write', 'ak_pytest_order_agent', TRUE,
                 '["orders.write"]', 0, :oak2, :oas2, NULL, 'pytest')
        """), {
            "qak": EXTERNAL_QUALITY_KEY["app_key"], "qas": EXTERNAL_QUALITY_KEY["app_secret"],
            "oak": EXTERNAL_ORDERS_KEY["app_key"], "oas": EXTERNAL_ORDERS_KEY["app_secret"],
            "pak": EXTERNAL_PRODUCTION_KEY["app_key"], "pas": EXTERNAL_PRODUCTION_KEY["app_secret"],
            "rak": EXTERNAL_REASONING_KEY["app_key"], "ras": EXTERNAL_REASONING_KEY["app_secret"],
            "gak": EXTERNAL_AGENT_KEY["app_key"], "gas": EXTERNAL_AGENT_KEY["app_secret"],
            "oak2": EXTERNAL_ORDER_AGENT_KEY["app_key"], "oas2": EXTERNAL_ORDER_AGENT_KEY["app_secret"],
            "pcodes": json.dumps(PRODUCTION_ENDPOINT_CODES),
        })
    yield {
        "quality": EXTERNAL_QUALITY_KEY,
        "orders": EXTERNAL_ORDERS_KEY,
        "production": EXTERNAL_PRODUCTION_KEY,
        "reasoning": EXTERNAL_REASONING_KEY,
        "agent": EXTERNAL_AGENT_KEY,
        "order_agent": EXTERNAL_ORDER_AGENT_KEY,
    }


@pytest_asyncio.fixture(loop_scope="session")
async def ext_client(external_keys):
    """质量对外接口用例专用 ASGI 客户端（先清表种 Key，再进入用例）。"""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, username: str, password: str = TEST_PASSWORD) -> dict:
    r = await client.post("/api/v1/basicdata/auth/login",
                          data={"username": username, "password": password, "login_type": "employee"})
    body = r.json()
    assert body.get("code") == 0, f"login {username} failed: {body}"
    return {"Authorization": f"Bearer {body['data']['access_token']}"}


# ----------------------------- 智能体目录/团队测试辅助 -----------------------------

async def insert_catalog_agent(
    db, *, agent_no: str, name: str, capabilities,
    scope_type: str = "all", scope_role_ids=None, status: str = "active",
) -> int:
    """向 agent 目录插入一行（capabilities 为能力码列表），返回 id。"""
    from app.models.agent.agent import Agent

    agent = Agent(
        agent_no=agent_no, display_name=name, capability_codes=list(capabilities),
        scope_type=scope_type, scope_role_ids=scope_role_ids, status=status,
    )
    db.add(agent)
    await db.flush()
    return int(agent.id)


async def check_team_member(db, *, user_id: int, agent_id: int) -> None:
    """勾选团队成员（幂等：已勾选则跳过）。"""
    from sqlalchemy import select

    from app.models.agent.team import AgentTeamMember

    exists = (await db.execute(
        select(AgentTeamMember.id).where(
            AgentTeamMember.user_id == int(user_id),
            AgentTeamMember.agent_id == int(agent_id),
        )
    )).scalars().first()
    if exists:
        return
    db.add(AgentTeamMember(
        user_id=int(user_id), agent_id=int(agent_id), created_by_user_id=int(user_id),
    ))
    await db.flush()


async def get_user_id_by_username(username: str) -> int:
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.basicdata.user import SysUser

    async with AsyncSessionLocal() as session:
        return int((await session.execute(
            select(SysUser.id).where(SysUser.username == username)
        )).scalar_one())


async def seed_query_agent_for_user(username: str) -> int:
    """为用户准备 query.orders 团队成员（幂等），返回 user id（网关路由用例辅助）。"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.agent.agent import Agent

    user_id = await get_user_id_by_username(username)
    async with AsyncSessionLocal() as session:
        agent = (await session.execute(
            select(Agent).where(Agent.agent_no == "AG-TEST-QUERY-ORDERS")
        )).scalars().first()
        agent_id = int(agent.id) if agent else await insert_catalog_agent(
            session, agent_no="AG-TEST-QUERY-ORDERS", name="订单查询员",
            capabilities=["query.orders"],
        )
        await check_team_member(session, user_id=user_id, agent_id=agent_id)
        await session.commit()
    return user_id
