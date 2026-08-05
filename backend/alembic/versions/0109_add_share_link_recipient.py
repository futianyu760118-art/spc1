"""add share_link_recipient table

Revision ID: 0109
Revises: 0108
Create Date: 2026-08-03

说明：新增 share_link_recipient 表,记录 share_link 的接收人(企微用户/部门/外部)及投递状态。
- share_link_id: 关联 share_link.id,on delete CASCADE
- recipient_type / recipient_id / recipient_name: 接收人标识
- delivered / delivered_at / wecom_msg_id / error_msg: 企微投递回执
- created_at: 创建时间,服务器默认 CURRENT_TIMESTAMP
对应 spec §WecomShare 投递。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0109"
down_revision: Union[str, Sequence[str], None] = "0108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "share_link_recipient",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("share_link_id", sa.Integer, sa.ForeignKey("share_link.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_type", sa.String(length=16), nullable=False),
        sa.Column("recipient_id", sa.String(length=64), nullable=False),
        sa.Column("recipient_name", sa.String(length=128), nullable=True),
        sa.Column("delivered", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wecom_msg_id", sa.String(length=256), nullable=True),
        sa.Column("error_msg", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_share_link_recipient_link_type", "share_link_recipient", ["share_link_id", "recipient_type"])
    op.create_index("ix_share_link_recipient_share_link_id", "share_link_recipient", ["share_link_id"])


def downgrade() -> None:
    op.drop_index("ix_share_link_recipient_link_type", table_name="share_link_recipient")
    op.drop_index("ix_share_link_recipient_share_link_id", table_name="share_link_recipient")
    op.drop_table("share_link_recipient")