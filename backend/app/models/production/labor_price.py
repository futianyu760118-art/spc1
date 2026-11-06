"""工程工价主表/明细（OA 工价镜像 + 系统手工新增）。"""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class LaborPriceMain(Base):
    __tablename__ = "labor_price_main"

    id = Column(Integer, primary_key=True, autoincrement=True)
    oa_main_id = Column(String(64), nullable=True, index=True, comment="OA 主表 ID")
    bom_code = Column(String(64), nullable=True, index=True, comment="BOM 编码")
    product_code = Column(String(64), nullable=True, index=True, comment="产品编码")
    product_name = Column(String(256), nullable=True, comment="产品名称")
    workshop_id = Column(String(64), nullable=True, comment="车间 ID")
    workshop_name = Column(String(255), nullable=True, comment="车间名称")
    status = Column(String(32), nullable=False, default="pending", index=True, comment="draft/pending/approved/rejected/inactive")
    source = Column(String(32), nullable=False, default="manual", comment="oa/manual")
    effective_date = Column(Date, nullable=True, comment="生效日期")
    version = Column(Integer, nullable=False, default=1, comment="版本号")
    request_id = Column(String(64), nullable=True, comment="OA 变更单号")
    reason = Column(Text, nullable=True, comment="调价/新增原因")
    remark = Column(Text, nullable=True, comment="备注")
    applicant = Column(String(64), nullable=True, comment="申请人")
    approver = Column(String(64), nullable=True, comment="审批人")
    approved_at = Column(DateTime, nullable=True, comment="审批时间")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    details = relationship(
        "LaborPriceDetail",
        back_populates="main",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_labor_price_main_bom_status", "bom_code", "status"),
    )


class LaborPriceDetail(Base):
    __tablename__ = "labor_price_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    main_id = Column(Integer, ForeignKey("labor_price_main.id", ondelete="CASCADE"), nullable=False, index=True)
    oa_detail_id = Column(String(64), nullable=True, index=True, comment="OA 明细 ID")
    gx = Column(Integer, nullable=True, comment="OA 工序编码")
    process_type = Column(String(32), nullable=False, comment="工序名称")
    original_price = Column(Numeric(15, 4), nullable=True, comment="提交时原单价")
    price = Column(Numeric(15, 4), nullable=False, default=0, comment="工序单价")
    pph = Column(Numeric(15, 2), nullable=True, comment="OA PPH")
    bottleneck_hours = Column(Numeric(15, 2), nullable=True, comment="瓶颈工时")
    standard_capacity = Column(Numeric(15, 2), nullable=True, comment="标准产能")
    manpower = Column(Integer, nullable=True, comment="人数")
    remark = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    main = relationship("LaborPriceMain", back_populates="details")

    __table_args__ = (
        Index("ix_labor_price_detail_main_process", "main_id", "process_type"),
    )
