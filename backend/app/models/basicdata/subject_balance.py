"""基础数据与集成中心 — 科目余额模型"""

from sqlalchemy import Column, BigInteger, String, Integer, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class SubjectBalance(Base):
    __tablename__ = "scm_subject_balance"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    subject_category = Column(String(64), nullable=True, comment="科目类别名称")
    subject_id = Column(Integer, nullable=False, comment="科目ID(外部系统)")
    subject_name = Column(String(200), nullable=True, comment="科目名称")
    subject_code = Column(String(64), nullable=True, index=True, comment="科目编码")
    item_code = Column(String(64), nullable=False, server_default="", comment="核算项目代码(空值统一为'')")
    item_name = Column(String(200), nullable=True, comment="核算项目名称")
    parent_subject_id = Column(Integer, nullable=True, comment="科目父ID")
    fiscal_year = Column(Integer, nullable=False, comment="年份")
    fiscal_month = Column(Integer, nullable=False, comment="月份(1-12)")
    credit_amount_month = Column(Numeric(20, 4), nullable=False, server_default="0", comment="本月贷方发生")
    credit_amount_year = Column(Numeric(20, 4), nullable=False, server_default="0", comment="年度贷方累计额")
    data_source = Column(String(32))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'subject_id', 'item_code', 'fiscal_year', 'fiscal_month',
            name='uq_subject_balance_key',
        ),
    )
