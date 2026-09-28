"""物料齐套中心 — 采购申请单模型（含明细与审批日志）"""

from sqlalchemy import (Column, Date, DateTime, Index, Integer, JSON, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.sql import func

from app.core.database import Base


class PurchaseRequisition(Base):
    __tablename__ = "purchase_requisition"

    id = Column(Integer, primary_key=True, autoincrement=True)
    req_no = Column(String(32), nullable=False, unique=True, comment="申请单号 PR-YYYYMMDD-NNN")
    status = Column(String(16), nullable=False, default="draft", server_default="draft", comment="draft/approving/approved/rejected/closed")
    applicant = Column(String(64), nullable=True, comment="申请人")
    department = Column(String(64), nullable=True)
    source = Column(String(16), nullable=False, default="manual", server_default="manual", comment="mrp/manual/excel")
    run_id = Column(Integer, nullable=True, comment="MRP 批次ID(来源=mrp 时)")
    remark = Column(Text, nullable=True)
    # 审批引擎约定列（照 supplier_claim，类型/default 以该文件为准）
    approval_status = Column(String(16), default="draft")
    approval_level = Column(Integer, default=1)
    approval_snapshot = Column(JSON)
    submitted_at = Column(DateTime)
    approved_by = Column(String(64))
    approved_at = Column(DateTime)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class PurchaseRequisitionLine(Base):
    __tablename__ = "purchase_requisition_line"
    __table_args__ = (
        UniqueConstraint("req_id", "line_no", name="uq_purchase_requisition_line_req_line"),
        Index("ix_purchase_requisition_line_req", "req_id"),
        Index("ix_purchase_requisition_line_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    req_id = Column(Integer, nullable=False)
    line_no = Column(Integer, nullable=False)
    material_id = Column(Integer, nullable=True, comment="物料ID(erp_material_id)")
    material_code = Column(String(64), nullable=False)
    material_name = Column(String(256), nullable=True)
    spec_model = Column(String(256), nullable=True)
    unit = Column(String(32), nullable=True)
    req_qty = Column(Numeric(18, 4), nullable=False, comment="申请数量")
    need_date = Column(Date, nullable=True, comment="到货日期")
    supplier_id = Column(Integer, nullable=True, comment="建议供应商ID(scm_supplier.id)")
    supplier_code = Column(String(64), nullable=True)
    supplier_name = Column(String(256), nullable=True)
    unit_price = Column(Numeric(15, 4), nullable=True, comment="参考单价(scm_material.order_unit_price)")
    source_suggestion_id = Column(Integer, nullable=True, comment="mrp_suggestion.id")
    converted_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="已转订单数量")
    converted_po_no = Column(String(64), nullable=True)
    converted_po_detail_id = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="open", server_default="open", comment="open/partially_converted/closed")
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class PurchaseRequisitionApprovalLog(Base):
    __tablename__ = "purchase_requisition_approval_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    req_id = Column(Integer, nullable=False, index=True)
    approval_level = Column(Integer, nullable=True)
    approver = Column(String(64), nullable=True)
    action = Column(String(16), nullable=True, comment="submit/approve/reject/recall")
    comment = Column(Text, nullable=True)
    operated_at = Column(DateTime, server_default=func.now(), nullable=False)
