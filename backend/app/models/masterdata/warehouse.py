"""主数据与集成中心 — 仓库主数据模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Warehouse(Base):
    __tablename__ = "scm_warehouse"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wh_code = Column(String(20), nullable=False, unique=True, comment="仓库编码")
    wh_name = Column(String(50), nullable=False, comment="仓库名称")
    wh_type = Column(String(20), nullable=False, comment="仓库类型")
    address = Column(String(200), nullable=True, comment="仓库地址")
    manager_id = Column(BigInteger, nullable=True, comment="仓库管理员ID")
    is_enabled = Column(Integer, nullable=False, default=1, comment="是否启用")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
