"""生产协同中心 — 前道管理手工数据模型

以生产任务单(喷塑车间/压铸车间)为主体，壳体/框/手杆/支架圆盘等
字段由人工填写。本表仅存放手工填写的数据，通过 task_id 与
production_task_order 关联；任务单基础信息在查询时 JOIN 带出，
保证任务单是唯一数据源（OA 同步不会触及本表）。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func

from app.core.database import Base


class FrontProcessRecord(Base):
    __tablename__ = "front_process_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=True, index=True, comment="关联 production_task_order.task_id")
    task_no = Column(String(64), nullable=True, index=True, comment="任务单号(冗余,便于展示/搜索)")
    # --- 手工填写字段 ---
    shell_status = Column(String(64), comment="壳体")
    frame_status = Column(String(64), comment="框")
    handle_status = Column(String(64), comment="手杆")
    bracket_status = Column(String(64), comment="支架圆盘")
    remark = Column(Text, comment="备注")
    # --- 状态(行着色用) ---
    status = Column(String(32), nullable=False, server_default="pending", default="pending")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_front_process_record_task_id", "task_id", unique=True),
    )
