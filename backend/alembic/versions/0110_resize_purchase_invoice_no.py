"""resize purchase_invoice.invoice_no to VARCHAR(256)

Revision ID: 0110
Revises: 0109
Create Date: 2026-08-03

说明：K3 ERP 的 ICPurchase.FBillNo 可能存储多张发票号拼接（中文逗号分隔），
原 VARCHAR(64) 不够，扩到 VARCHAR(256)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0110"
down_revision: Union[str, Sequence[str], None] = "0109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "purchase_invoice",
        "invoice_no",
        type_=sa.String(length=256),
        existing_comment="发票号码",
    )


def downgrade() -> None:
    op.alter_column(
        "purchase_invoice",
        "invoice_no",
        type_=sa.String(length=64),
        existing_comment="发票号码",
    )
