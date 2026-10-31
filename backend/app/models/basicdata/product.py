"""基础数据与集成中心 — 产品模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Numeric
from sqlalchemy.sql import func

from app.core.database import Base


class Product(Base):
    __tablename__ = "scm_product"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_code = Column(String(50), nullable=False, unique=True, comment="产品编码")
    product_line = Column(String(50), nullable=True, comment="产品线")
    tech_version = Column(String(20), nullable=True, comment="技术版本")
    bom_version = Column(String(20), nullable=True, comment="BOM版本号")
    default_warehouse = Column(String(50), nullable=True, comment="默认仓库")
    warranty_days = Column(Integer, nullable=True, comment="质保天数")
    upph = Column(Numeric(15, 2), nullable=True, default=0, comment="每小时产能UPPH")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
