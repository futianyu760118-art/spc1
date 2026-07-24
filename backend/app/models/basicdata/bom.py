"""基础数据与集成中心 — BOM模型"""

from sqlalchemy import Column, BigInteger, String, Integer, Numeric, Date, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Bom(Base):
    __tablename__ = "scm_bom"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bom_id = Column(String(64), nullable=False, unique=True, comment="BOM ID(外部系统)")
    bom_no = Column(String(64), nullable=False, comment="BOM编号")
    material_id = Column(String(50), nullable=True, comment="物料ID")
    parent_material_id = Column(String(50), nullable=True, comment="上级物料ID")
    bom_version = Column(String(20), nullable=True, comment="BOM版本号")
    bom_type = Column(String(32), nullable=True, comment="BOM类型")
    bill_type_id = Column(String(32), nullable=True, comment="单据类型ID")
    base_qty = Column(Numeric(18, 6), nullable=True, default=0, comment="基础用量")
    aux_attr_qty = Column(Numeric(18, 6), nullable=True, default=0, comment="辅助属性数量")
    unit_id = Column(String(32), nullable=True, comment="计量单位ID")
    aux_attr_id = Column(String(32), nullable=True, comment="辅助属性ID")
    supply_mode = Column(String(32), nullable=True, comment="供应模式")
    customer_material_id = Column(String(64), nullable=True, comment="客户物料ID")
    audit_status = Column(String(32), nullable=True, comment="审核状态")
    use_status = Column(String(32), nullable=True, comment="使用状态")
    disabled_status = Column(Integer, nullable=False, default=0, comment="禁用状态 0否1是")
    void_flag = Column(Integer, nullable=False, default=0, comment="作废标识 0否1是")
    is_audited = Column(Integer, nullable=False, default=0, comment="是否审核 0否1是")
    audit_date = Column(Date, nullable=True, comment="审核日期")
    entry_date = Column(Date, nullable=True, comment="录入日期")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
