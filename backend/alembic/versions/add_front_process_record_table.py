"""add front_process_record table

前道管理手工数据表：以喷塑/压铸车间生产任务单为主体，
壳体/框/手杆/支架圆盘/备注 等手工字段存于此表，通过 task_id
关联 production_task_order。OA 同步只更新任务单映射字段，不会触及本表。

Revision ID: add_front_process_record
Revises: add_scm_material_3cols
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_front_process_record"
down_revision: Union[str, None] = "add_scm_material_3cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等：init_database.py 的 create_all 可能已建过该表，重复执行不报错
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("front_process_record"):
        return

    op.create_table(
        "front_process_record",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), nullable=True, comment="关联 production_task_order.task_id"),
        sa.Column("task_no", sa.String(length=64), nullable=True, comment="任务单号(冗余,便于展示/搜索)"),
        sa.Column("shell_status", sa.String(length=64), nullable=True, comment="壳体"),
        sa.Column("frame_status", sa.String(length=64), nullable=True, comment="框"),
        sa.Column("handle_status", sa.String(length=64), nullable=True, comment="手杆"),
        sa.Column("bracket_status", sa.String(length=64), nullable=True, comment="支架圆盘"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_front_process_record_task_id", "front_process_record", ["task_id"])
    op.create_index("ix_front_process_record_task_no", "front_process_record", ["task_no"])
    op.create_index(
        "uq_front_process_record_task_id", "front_process_record", ["task_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_front_process_record_task_id", table_name="front_process_record")
    op.drop_index("ix_front_process_record_task_no", table_name="front_process_record")
    op.drop_index("ix_front_process_record_task_id", table_name="front_process_record")
    op.drop_table("front_process_record")
