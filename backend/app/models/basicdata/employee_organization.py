"""基础数据与集成中心 — 员工-组织关联模型"""

from sqlalchemy import Column, BigInteger, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class EmployeeOrganization(Base):
    __tablename__ = "scm_employee_organization"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    emp_code = Column(String(20), nullable=False, comment="员工工号")
    org_code = Column(String(20), nullable=False, comment="组织编码")
    is_primary = Column(Integer, nullable=False, default=0, comment="是否主部门 (1-是 0-否)")
    position = Column(String(50), nullable=True, comment="在该部门的岗位")
    status = Column(Integer, nullable=False, default=1, comment="状态")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("emp_code", "org_code", name="uq_emp_org_code"),
    )
