"""基础数据与集成中心 — 物料模型"""

from sqlalchemy import Column, BigInteger, String, Integer
from sqlalchemy.sql import func

from app.core.database import Base


class Material(Base):
    __tablename__ = "scm_material"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    material_id = Column(String(50), nullable=False, unique=True, comment="物料ID(外部系统)")
    parent_id = Column(String(50), nullable=True, comment="父级物料ID(引用material_id)")
    material_code = Column(String(50), nullable=False, unique=True, comment="物料编码")
    material_name = Column(String(100), nullable=False, comment="物料名称")
    spec_model = Column(String(200), nullable=True, comment="规格型号")
    material_type = Column(String(50), nullable=False, comment="物料分类")
    unit_of_measure = Column(String(10), nullable=False, comment="基本计量单位")
    brand = Column(String(50), nullable=True, comment="品牌/厂商")
    is_purchase = Column(Integer, nullable=False, default=0, comment="是否可采购")
    is_produce = Column(Integer, nullable=False, default=0, comment="是否可生产")
    status = Column(Integer, nullable=False, default=1, comment="状态")
    erp_sync_flag = Column(Integer, nullable=False, default=0, comment="ERP同步标识")
    is_deleted = Column(Integer, nullable=False, default=0, comment="是否删除 0否1是")
    data_source = Column(String(32))
