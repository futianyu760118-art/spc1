"""MRP 域 — 物料日桶平衡模型"""

from sqlalchemy import BigInteger, Column, Date, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class MrpBucket(Base):
    __tablename__ = "mrp_bucket"
    __table_args__ = (
        UniqueConstraint("run_id", "material_id", "bucket_date", name="uq_mrp_bucket_run_material_date"),
        Index("ix_mrp_bucket_run_material", "run_id", "material_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, comment="批次ID")
    material_id = Column(Integer, nullable=False, comment="物料ID(erp_material_id)")
    bucket_date = Column(Date, nullable=False, comment="桶日期")
    opening_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="期初物理可用")
    gross_demand_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="毛需求")
    supply_po_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="采购订单在途")
    supply_task_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="生产任务单在制")
    supply_subcontract_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="委外在途")
    supply_transfer_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="调拨在途")
    supply_requisition_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="采购申请剩余(P2 起)")
    substitute_in_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="替代占用进项(P3 起)")
    substitute_out_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="被替代占用(P3 起)")
    safety_stock_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="安全库存水位")
    closing_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="期末物理可用(含建议回填)")
    net_demand_qty = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="本桶缺口")
    pegging = Column(JSONB, nullable=True, comment="来源订单链 [{sale_order_no,line_no,qty}]")
