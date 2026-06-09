"""基础数据与集成中心 — 组织模型"""

from sqlalchemy import Column, BigInteger, String, Integer
from sqlalchemy.sql import func

from app.core.database import Base


class Organization(Base):
    __tablename__ = "scm_organization"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    org_code = Column(String(20), nullable=False, unique=True, comment="组织编码")
    org_name = Column(String(50), nullable=False, comment="组织名称")
    oa_org_id = Column(String(64), nullable=True, comment="OA系统组织ID")
    org_type = Column(String(20), nullable=False, comment="组织类型")
    parent_id = Column(BigInteger, nullable=True, comment="父级组织ID")
    leader_id = Column(BigInteger, nullable=True, comment="负责人ID")
    status = Column(Integer, nullable=False, default=1, comment="状态")
    data_source = Column(String(32))
