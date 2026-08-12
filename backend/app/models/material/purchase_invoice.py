"""物料齐套中心 — 采购开票模型（仅ERP同步）"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoice"
    __table_args__ = (
        UniqueConstraint("invoice_no", "line_no", name="uq_purchase_invoice_no_line"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    line_no = Column(String(32), nullable=False, comment="发票行号")
    invoice_no = Column(String(256), nullable=False, index=True, comment="发票号码")
    invoice_date = Column(Date, comment="开票日期")
    supplier_id = Column(String(64), comment="供应商ID（ERP内部ID）")
    supplier_code = Column(String(64), index=True, comment="供应商编号")
    supplier_name = Column(String(256), index=True, comment="供应商名称")
    payment_term = Column(String(64), comment="账期")
    settlement_method = Column(String(64), comment="结算方式")
    invoice_amount = Column(Numeric(15, 2), comment="开票金额")
    remain_payable = Column(Numeric(15, 2), comment="剩余应付金额")
    payment_apply_amount = Column(Numeric(15, 2), comment="付款申请金额")
    paid_amount = Column(Numeric(15, 2), comment="已付款金额")
    payment_order_id = Column(Integer, nullable=True, comment="付款单ID")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
