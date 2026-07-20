"""基础数据与集成中心 — 物料模型"""

from sqlalchemy import Column, BigInteger, String, Integer, Numeric, Date, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Material(Base):
    __tablename__ = "scm_material"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    erp_material_id = Column(Integer, nullable=False, unique=True, comment="ERP物料ID")
    parent_id = Column(Integer, nullable=True, comment="父级物料ID(引用erp_material_id)")
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
    supplier_id = Column(Integer, nullable=True, comment="供应商ID")
    order_unit_price = Column(Numeric(15, 4), nullable=True, comment="订货单价")
    last_outbound_date = Column(Date, nullable=True, comment="最后出库日期")
    create_time = Column(DateTime, server_default=func.now(), nullable=True)
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
