"""主数据与集成中心 — 工序主数据模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Numeric
from sqlalchemy.sql import func

from app.core.database import Base


class Process(Base):
    __tablename__ = "scm_process"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    process_code = Column(String(20), nullable=False, unique=True, comment="工序编码")
    process_name = Column(String(50), nullable=False, comment="工序名称")
    process_group = Column(String(50), nullable=True, comment="工序分组")
    standard_hour = Column(Numeric(10, 4), nullable=True, comment="标准工时")
    work_center = Column(String(50), nullable=True, comment="工作中心")
    is_qc_point = Column(Integer, nullable=False, default=0, comment="是否为质检点")
    description = Column(String(200), nullable=True, comment="描述")
    data_source = Column(String(32))
