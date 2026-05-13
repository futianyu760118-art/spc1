"""订单交付中心 — ETA更新模型"""

from sqlalchemy import Column, Integer, String, Date, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class ETAUpdate(Base):
    __tablename__ = "eta_update"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_no = Column(String(64), nullable=False, index=True)
    old_eta = Column(Date)
    new_eta = Column(Date, nullable=False)
    updater = Column(String(64))
    update_reason = Column(String(256))
    remark = Column(String(512))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
