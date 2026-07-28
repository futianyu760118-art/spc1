"""基础数据与集成中心 — 库位模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Location(Base):
    __tablename__ = "scm_location"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    location_id = Column(Integer, nullable=False, unique=True, comment="库位ID(外部系统)")
    location_group_id = Column(Integer, nullable=True, comment="库位分组ID")
    location_code = Column(String(50), nullable=True, comment="库位编码")
    location_name = Column(String(100), nullable=True, comment="库位名称")
    location_full_name = Column(String(200), nullable=True, comment="库位全称")
    depth = Column(Integer, nullable=True, default=0, comment="层级深度")
    detail_flag = Column(Integer, nullable=True, default=0, comment="明细标识")
    parent_id = Column(Integer, nullable=True, comment="父库位ID")
    is_deleted = Column(Integer, nullable=True, default=0, comment="是否删除")
    system_type = Column(Integer, nullable=True, default=0, comment="系统类型")
    data_source = Column(String(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)