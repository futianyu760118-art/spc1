"""基础数据与集成中心 — SKU模型"""

from sqlalchemy import Column, BigInteger, String, DateTime, Numeric
from sqlalchemy.sql import func

from app.core.database import Base


class SKU(Base):
    __tablename__ = "scm_sku"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sku_code = Column(String(50), nullable=False, unique=True, comment="SKU编码")
    material_id = Column(BigInteger, nullable=False, comment="关联物料ID")
    sku_name = Column(String(100), nullable=False, comment="SKU名称")
    attr_json = Column(String, nullable=True, comment="属性JSON")
    barcode = Column(String(50), nullable=True, comment="条形码")
    gross_weight = Column(Numeric(10, 3), nullable=True, comment="毛重(KG)")
    net_weight = Column(Numeric(10, 3), nullable=True, comment="净重(KG)")
    volume = Column(Numeric(10, 3), nullable=True, comment="体积(CBM)")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
