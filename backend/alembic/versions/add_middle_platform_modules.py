"""add middle platform modules

Revision ID: add_middle_platform_modules
Revises: add_order_amount
Create Date: 2026-06-02 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "add_middle_platform_modules"
down_revision: Union[str, None] = "add_order_amount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_schedule_plan",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("department", sa.String(length=32), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=True),
        sa.Column("product_code", sa.String(length=64), nullable=True),
        sa.Column("model_code", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Numeric(15, 2), nullable=True),
        sa.Column("owner", sa.String(length=64), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_production_schedule_plan_department", "production_schedule_plan", ["department"])
    op.create_index("ix_production_schedule_plan_plan_date", "production_schedule_plan", ["plan_date"])
    op.create_index("ix_production_schedule_plan_status", "production_schedule_plan", ["status"])
    op.create_index("ix_production_schedule_dept_date", "production_schedule_plan", ["department", "plan_date"])
    op.create_index("ix_production_schedule_order_product", "production_schedule_plan", ["order_no", "product_code"])

    op.create_table(
        "business_document",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("applicable_product", sa.String(length=128), nullable=True),
        sa.Column("applicable_order", sa.String(length=128), nullable=True),
        sa.Column("applicable_process", sa.String(length=128), nullable=True),
        sa.Column("current_version", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_type", "code", name="uq_business_document_type_code"),
    )
    op.create_index("ix_business_document_doc_type", "business_document", ["doc_type"])
    op.create_index("ix_business_document_status", "business_document", ["status"])

    op.create_table(
        "business_document_version",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("published_by", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["business_document.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_no", name="uq_business_document_version"),
    )
    op.create_index("ix_business_document_version_document_id", "business_document_version", ["document_id"])
    op.create_index("ix_business_document_version_status", "business_document_version", ["status"])


def downgrade() -> None:
    op.drop_index("ix_business_document_version_status", table_name="business_document_version")
    op.drop_index("ix_business_document_version_document_id", table_name="business_document_version")
    op.drop_table("business_document_version")

    op.drop_index("ix_business_document_status", table_name="business_document")
    op.drop_index("ix_business_document_doc_type", table_name="business_document")
    op.drop_table("business_document")

    op.drop_index("ix_production_schedule_plan_status", table_name="production_schedule_plan")
    op.drop_index("ix_production_schedule_order_product", table_name="production_schedule_plan")
    op.drop_index("ix_production_schedule_dept_date", table_name="production_schedule_plan")
    op.drop_index("ix_production_schedule_plan_plan_date", table_name="production_schedule_plan")
    op.drop_index("ix_production_schedule_plan_department", table_name="production_schedule_plan")
    op.drop_table("production_schedule_plan")
