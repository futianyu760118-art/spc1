"""主数据与集成中心 — 人员主数据模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Employee(Base):
    __tablename__ = "scm_employee"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    emp_code = Column(String(20), nullable=False, unique=True, comment="员工工号")
    emp_name = Column(String(50), nullable=False, comment="员工姓名")
    org_id = Column(BigInteger, nullable=False, comment="所属组织ID")
    position = Column(String(50), nullable=True, comment="岗位名称")
    phone = Column(String(20), nullable=True, comment="手机号")
    email = Column(String(50), nullable=True, comment="邮箱")
    status = Column(Integer, nullable=False, default=1, comment="状态 (1-在职 0-离职)")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
