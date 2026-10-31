"""物料齐套中心 — 付款申请模型（仅ERP同步）"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class PaymentApply(Base):
    __tablename__ = "payment_apply"
    __table_args__ = (
        UniqueConstraint("payment_apply_no", name="uq_payment_apply_no"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_apply_no = Column(String(64), nullable=False, index=True, comment="付款申请编号")
    doc_no = Column(String(64), index=True, comment="单据编号")
    doc_date = Column(Date, comment="单据日期")
    subsystem_id = Column(String(64), comment="子系统ID（ERP来源子系统标识）")
    paid_amount = Column(Numeric(15, 2), comment="已付款金额")
    data_source = Column(String(32), comment="数据来源（erp/manual）")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
