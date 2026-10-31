"""基础数据与集成中心 — 仓库模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Warehouse(Base):
    __tablename__ = "scm_warehouse"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wh_id = Column(Integer, nullable=True, unique=True, comment="仓库ID(外部系统)")
    parent_wh_id = Column(Integer, nullable=True, comment="父仓库ID")
    wh_code = Column(String(20), nullable=False, unique=True, comment="仓库编码")
    wh_name = Column(String(50), nullable=False, comment="仓库名称")
    wh_type = Column(String(20), nullable=True, comment="仓库类型")
    wh_attribute = Column(String(10), nullable=True, comment="仓库属性(10-良品,11-在检,12-不良)")
    plan_area = Column(String(50), nullable=True, comment="计划区域")
    phone = Column(String(30), nullable=True, comment="电话号码")
    address = Column(String(200), nullable=True, comment="仓库地址")
    is_workshop = Column(Integer, nullable=True, default=0, comment="是否为车间仓库")
    is_deleted = Column(Integer, nullable=True, default=0, comment="是否删除")
    manager_id = Column(BigInteger, nullable=True, comment="仓库管理员ID")
    is_enabled = Column(Integer, nullable=False, default=1, comment="是否启用")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
