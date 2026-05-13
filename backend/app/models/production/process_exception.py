"""生产协同中心 — 工序异常模型"""

from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ProcessException(Base):
    __tablename__ = "process_exception"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exception_no = Column(String(64), nullable=False, unique=True)
    process_type = Column(String(16), index=True)
    order_no = Column(String(64), index=True)
    model_code = Column(String(128))
    exception_type = Column(String(32))
    severity = Column(String(16))
    description = Column(Text)
    responsible_dept = Column(String(64))
    responsible_person = Column(String(64))
    status = Column(String(32), nullable=False, default='open')
    resolved_at = Column(Date)
    remark = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
