"""基础数据与集成中心 — 供应商模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Supplier(Base):
    __tablename__ = "scm_supplier"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    supplier_code = Column(String(50), nullable=False, unique=True, comment="供应商编码")
    supplier_name = Column(String(100), nullable=False, comment="供应商全称")
    supplier_short = Column(String(50), nullable=True, comment="供应商简称")
    supplier_type = Column(String(20), nullable=True, comment="供应商类型")
    contact_person = Column(String(50), nullable=True, comment="联系人")
    contact_phone = Column(String(20), nullable=True, comment="联系电话")
    fax = Column(String(50), nullable=True, comment="传真")
    address = Column(String(256), nullable=True, comment="地址")
    erp_supply_id = Column(Integer, nullable=True, unique=True, comment="ERP供应商内部ID")
    payment_terms = Column(String(50), nullable=True, comment="付款条款")
    status = Column(Integer, nullable=False, default=1, comment="状态 (1-启用 0-禁用)")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
