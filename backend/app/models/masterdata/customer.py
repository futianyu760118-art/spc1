"""主数据与集成中心 — 客户主数据模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Customer(Base):
    __tablename__ = "scm_customer"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    customer_code = Column(String(50), nullable=False, unique=True, comment="客户编码")
    customer_name = Column(String(100), nullable=False, comment="客户全称")
    customer_short = Column(String(50), nullable=True, comment="客户简称")
    customer_level = Column(String(20), nullable=True, comment="客户等级")
    industry_type = Column(String(50), nullable=True, comment="所属行业")
    credit_code = Column(String(18), nullable=True, comment="统一社会信用代码")
    status = Column(Integer, nullable=False, default=1, comment="状态 (1-启用 0-禁用)")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
