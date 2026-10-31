"""seed default writeback_sql_config for po_status (K3 ERP POOrder.FStatus)

Revision ID: 0108
Revises: 0107
Create Date: 2026-08-03

说明：种入首个落地场景的默认配置。幂等 INSERT,已存在则跳过。
对应 spec §5.7。后续场景(po_eta / po_arrival / po_inspection)通过前端配置面板或运维 SQL 插入。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0108"
down_revision: Union[str, Sequence[str], None] = "0107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM writeback_sql_config WHERE writeback_type = :t"),
        {"t": "po_status"},
    ).scalar()
    if exists:
        return

    op.execute(
        sa.text(
            """
            INSERT INTO writeback_sql_config
              (writeback_type, description, target_table, target_key_fields,
               update_sql_template, enqueue_trigger, max_retries, enabled, created_by)
            VALUES
              (:writeback_type, :description, :target_table, CAST(:target_key_fields AS JSONB),
               :update_sql_template, :enqueue_trigger, :max_retries, :enabled, :created_by)
            """
        ).params(
            {
                "writeback_type": "po_status",
                "description": "采购订单状态回写（K3 ERP POOrder.FStatus）",
                "target_table": "POOrder",
                "target_key_fields": '["FBillNo","FEntryID"]',
                "update_sql_template": (
                    "UPDATE POOrder SET "
                    "  FStatus = :payload__new_status, "
                    "  FModifyDate = :writeback_at "
                    "WHERE FBillNo = :target_keys__FBillNo "
                    "  AND FEntryID = :target_keys__FEntryID"
                ),
                "enqueue_trigger": "system:hook:po_status",
                "max_retries": 6,
                "enabled": True,
                "created_by": "system:init",
            },
        ),
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM writeback_sql_config WHERE writeback_type = 'po_status'")
    )