"""基础数据与集成中心 — BOM明细模型"""

from sqlalchemy import Column, BigInteger, String, Integer, Numeric, Date, DateTime, Index
from sqlalchemy.sql import func

from app.core.database import Base


class BomDetail(Base):
    __tablename__ = "scm_bom_detail"
    __table_args__ = (
        Index("ix_scm_bom_detail_bom_id_line_no", "bom_id", "line_no"),
        Index("ix_scm_bom_detail_material_id", "material_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bom_id = Column(String(64), nullable=False, comment="BOM ID(外部系统)")
    line_no = Column(String(32), nullable=False, comment="行号")
    material_id = Column(Integer, nullable=True, comment="物料ID(引用scm_material.erp_material_id)")
    standard_qty = Column(Numeric(18, 6), nullable=True, default=0, comment="标准用量")
    aux_qty = Column(Numeric(18, 6), nullable=True, default=0, comment="辅助数量")
    material_type = Column(String(32), nullable=True, comment="物料类型")
    config_type = Column(String(32), nullable=True, comment="配置类型")
    lead_offset_days = Column(Integer, nullable=True, default=0, comment="前期偏移天数")
    back_flush = Column(Integer, nullable=False, default=0, comment="是否倒冲 0否1是")
    scrap_rate = Column(Numeric(10, 4), nullable=True, default=0, comment="损耗率")
    oper_sn = Column(String(32), nullable=True, comment="工序号(FOperSN)")
    process_id = Column(String(32), nullable=True, comment="工序ID")
    warehouse_id = Column(String(32), nullable=True, comment="仓库ID")
    location_id = Column(String(32), nullable=True, comment="库位ID")
    valid_date = Column(Date, nullable=True, comment="生效日期")
    invalid_date = Column(Date, nullable=True, comment="失效日期")
    unit_id = Column(String(32), nullable=True, comment="计量单位ID")
    customer_bom_code = Column(String(64), nullable=True, comment="客户BOM编码")
    aux_attr_id = Column(String(32), nullable=True, comment="辅助属性ID")
    material_size = Column(String(64), nullable=True, comment="物料尺寸")
    kit_flag = Column(Integer, nullable=False, default=0, comment="套件标识 0否1是")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
