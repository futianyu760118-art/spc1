"""add subcontract_order and subcontract_order_detail tables

Revision ID: add_subcontract_order_tables
Revises: add_scm_inventory_price_balance
Create Date: 2026-07-20

说明：
- 新增两张 ERP 同步表：委外订单 (subcontract_order) 和
  委外订单明细 (subcontract_order_detail)。
- 与 init_database.py 的 Base.metadata.create_all 并存，幂等：
  项目以 init_database.py 为运行时真相源；Alembic 仅手动执行。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_subcontract_order_tables"
down_revision: Union[str, Sequence[str], None] = "add_scm_inventory_price_balance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subcontract_order",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("erp_order_id", sa.Integer(), nullable=True, comment="委外订单ID (ERP FID)"),
        sa.Column("bill_no", sa.String(length=64), nullable=False, comment="单据编号"),
        sa.Column("bill_date", sa.Date(), nullable=True, comment="日期"),
        sa.Column("bill_type", sa.String(length=64), nullable=True, comment="类型"),
        sa.Column("settlement_method", sa.String(length=64), nullable=True, comment="结算方式"),
        sa.Column("settle_date", sa.Date(), nullable=True, comment="结算日期"),
        sa.Column("supplier_id", sa.Integer(), nullable=True, comment="供应商id"),
        sa.Column("department_id", sa.Integer(), nullable=True, comment="部门id"),
        sa.Column("salesman_id", sa.Integer(), nullable=True, comment="业务员id"),
        sa.Column("manager_id", sa.Integer(), nullable=True, comment="主管id"),
        sa.Column("auditor_id", sa.Integer(), nullable=True, comment="审核人id"),
        sa.Column("audit_date", sa.Date(), nullable=True, comment="审核日期"),
        sa.Column("creator_id", sa.Integer(), nullable=True, comment="制单人id"),
        sa.Column("remark", sa.Text(), nullable=True, comment="摘要"),
        sa.Column("voided_flag", sa.Integer(), nullable=True, comment="作废标志 0/1"),
        sa.Column("closed_flag", sa.Integer(), nullable=True, comment="关闭标志 0/1"),
        sa.Column("status", sa.String(length=32), nullable=True, comment="状态"),
        sa.Column("bill_type_id", sa.Integer(), nullable=True, comment="单据类型id"),
        sa.Column("rejected_flag", sa.Integer(), nullable=True, comment="拒单标识 0/1"),
        sa.Column("close_date", sa.Date(), nullable=True, comment="关闭日期"),
        sa.Column("plan_category", sa.Integer(), nullable=True, comment="计划类别"),
        sa.Column("closer_id", sa.Integer(), nullable=True, comment="关闭人id"),
        sa.Column("erp_updated_at", sa.DateTime(), nullable=True, comment="修改时间(增量同步用)"),
        sa.Column("data_source", sa.String(length=32), nullable=True, comment="数据来源"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_no", name="uq_subcontract_order_bill_no"),
    )
    op.create_index("ix_subcontract_order_erp_order_id", "subcontract_order", ["erp_order_id"])
    op.create_index("ix_subcontract_order_bill_no", "subcontract_order", ["bill_no"])

    op.create_table(
        "subcontract_order_detail",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("erp_order_id", sa.Integer(), nullable=False, comment="委外订单ID (ERP FID)"),
        sa.Column("detail_id", sa.Integer(), nullable=False, comment="明细标识 (ERP FEntryID)"),
        sa.Column("line_no", sa.Integer(), nullable=True, comment="行号"),
        sa.Column("unit_id", sa.Integer(), nullable=True, comment="单位id"),
        sa.Column("material_id", sa.Integer(), nullable=True, comment="物料id"),
        sa.Column("qty", sa.Numeric(precision=15, scale=2), nullable=True, comment="数量"),
        sa.Column("delivery_qty", sa.Numeric(precision=15, scale=2), nullable=True, comment="交货数量"),
        sa.Column("received_qty", sa.Numeric(precision=15, scale=2), nullable=True, comment="收货数量"),
        sa.Column("returned_qty", sa.Numeric(precision=15, scale=2), nullable=True, comment="退货数量"),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=True, comment="金额"),
        sa.Column("mrp_closed_flag", sa.Integer(), nullable=True, comment="MRP关闭标志 0/1"),
        sa.Column("sale_order_line_no", sa.Integer(), nullable=True, comment="销售订单行号"),
        sa.Column("sale_order_id", sa.Integer(), nullable=True, comment="销售订单id"),
        sa.Column("sale_order_no", sa.String(length=64), nullable=True, comment="销售订单编号"),
        sa.Column("data_source", sa.String(length=32), nullable=True, comment="数据来源"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("erp_order_id", "detail_id", name="uq_subcontract_order_detail_order_entry"),
    )
    op.create_index("ix_subcontract_order_detail_erp_order_id", "subcontract_order_detail", ["erp_order_id"])
    op.create_index("ix_subcontract_order_detail_material_id", "subcontract_order_detail", ["material_id"])
    op.create_index("ix_subcontract_order_detail_sale_order_id", "subcontract_order_detail", ["sale_order_id"])
    op.create_index("ix_subcontract_order_detail_sale_order_no", "subcontract_order_detail", ["sale_order_no"])


def downgrade() -> None:
    op.drop_index("ix_subcontract_order_detail_sale_order_no", table_name="subcontract_order_detail")
    op.drop_index("ix_subcontract_order_detail_sale_order_id", table_name="subcontract_order_detail")
    op.drop_index("ix_subcontract_order_detail_material_id", table_name="subcontract_order_detail")
    op.drop_index("ix_subcontract_order_detail_erp_order_id", table_name="subcontract_order_detail")
    op.drop_table("subcontract_order_detail")

    op.drop_index("ix_subcontract_order_bill_no", table_name="subcontract_order")
    op.drop_index("ix_subcontract_order_erp_order_id", table_name="subcontract_order")
    op.drop_table("subcontract_order")
