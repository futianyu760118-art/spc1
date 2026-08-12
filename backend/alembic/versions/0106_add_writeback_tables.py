"""add writeback tables: writeback_sql_config / writeback_queue / writeback_log

Revision ID: 0106
Revises: 0105
Create Date: 2026-08-03

说明：中台数据回写（Write-Back）功能的 3 张新表，对应 spec:
  docs/superpowers/specs/2026-08-03-spc-writeback-design.md
- writeback_sql_config: 回写场景的 SQL 配置（类比 sync_sql_config，但存 UPDATE）
- writeback_queue: 持久化任务队列，partial unique 索引去重
- writeback_log: 每次执行的日志（含 SQL、影响行数、耗时、错误）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0106"
down_revision: Union[str, Sequence[str], None] = "0105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "writeback_sql_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("writeback_type", sa.String(length=64), nullable=False, unique=True,
                  comment="回写场景标识(po_status/po_eta/po_arrival...)"),
        sa.Column("description", sa.String(length=256), nullable=True,
                  comment="业务说明"),
        sa.Column("target_table", sa.String(length=128), nullable=False,
                  comment="ERP 目标表,如 POOrder"),
        sa.Column("target_key_fields", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, comment="WHERE 字段列表,如 [\"FBillNo\",\"FEntryID\"]"),
        sa.Column("update_sql_template", sa.Text(), nullable=False,
                  comment="UPDATE 模板,使用 :payload__xxx / :target_keys__xxx / :writeback_at 占位符"),
        sa.Column("field_mapping_json", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, comment="SPC字段→ERP字段映射(可选)"),
        sa.Column("enqueue_trigger", sa.String(length=128), nullable=True,
                  comment="入队触发点标识,用于自动注册"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="6",
                  comment="最大重试次数"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true(),
                  comment="是否启用该回写场景"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_writeback_sql_config_enabled", "writeback_sql_config", ["enabled"])

    op.create_table(
        "writeback_queue",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("writeback_type", sa.String(length=64), nullable=False,
                  comment="关联 writeback_sql_config.writeback_type"),
        sa.Column("business_table", sa.String(length=128), nullable=False,
                  comment="SPC 业务表名,如 purchase_order"),
        sa.Column("business_pk", sa.String(length=64), nullable=False,
                  comment="SPC 主键值(字符串以兼容 UUID/雪花ID)"),
        sa.Column("target_keys", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, comment="WHERE 字段值快照 {\"FBillNo\":\"PO001\",\"FEntryID\":1}"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, comment="待写入字段快照"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending",
                  comment="pending/processing/done/failed/dead"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0",
                  comment="已重试次数"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True,
                  comment="下次可执行时间(用于指数退避)"),
        sa.Column("last_error", sa.Text(), nullable=True,
                  comment="最近一次错误信息"),
        sa.Column("enqueued_by", sa.String(length=64), nullable=False,
                  comment="入队来源:system:hook / manual:user01 / manual:batch"),
        sa.Column("enqueued_by_user", sa.String(length=64), nullable=True,
                  comment="手动入队时的操作人"),
        sa.Column("enqueued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("picked_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_writeback_queue_type", "writeback_queue", ["writeback_type"])
    op.create_index("ix_writeback_queue_status", "writeback_queue", ["status"])
    op.create_index("ix_writeback_queue_next_retry_at", "writeback_queue", ["next_retry_at"])

    op.create_table(
        "writeback_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), nullable=False, unique=True,
                  comment="UUID 任务ID"),
        sa.Column("queue_id", sa.BigInteger(), nullable=True,
                  comment="关联 writeback_queue.id(队列行清理后仍可追溯)"),
        sa.Column("writeback_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False,
                  comment="success/failed"),
        sa.Column("sql_executed", sa.Text(), nullable=True,
                  comment="实际执行的 SQL(参数已绑定)"),
        sa.Column("rows_affected", sa.Integer(), nullable=True,
                  comment="ERP 端影响行数(应为1,0表示WHERE没匹配)"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True,
                  comment="异常堆栈/数据库错误码"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_writeback_log_type", "writeback_log", ["writeback_type"])
    op.create_index("ix_writeback_log_status", "writeback_log", ["status"])
    op.create_index("ix_writeback_log_queue_id", "writeback_log", ["queue_id"])

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_writeback_queue_active "
        "ON writeback_queue (writeback_type, business_pk) "
        "WHERE status IN ('pending', 'processing')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_writeback_queue_pending_retry "
        "ON writeback_queue (next_retry_at) "
        "WHERE status IN ('pending', 'failed')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_writeback_queue_pending_retry")
    op.execute("DROP INDEX IF EXISTS uq_writeback_queue_active")

    op.drop_index("ix_writeback_log_queue_id", table_name="writeback_log")
    op.drop_index("ix_writeback_log_status", table_name="writeback_log")
    op.drop_index("ix_writeback_log_type", table_name="writeback_log")
    op.drop_table("writeback_log")

    op.drop_index("ix_writeback_queue_next_retry_at", table_name="writeback_queue")
    op.drop_index("ix_writeback_queue_status", table_name="writeback_queue")
    op.drop_index("ix_writeback_queue_type", table_name="writeback_queue")
    op.drop_table("writeback_queue")

    op.drop_index("ix_writeback_sql_config_enabled", table_name="writeback_sql_config")
    op.drop_table("writeback_sql_config")