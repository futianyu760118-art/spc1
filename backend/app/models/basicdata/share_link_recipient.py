"""基础数据与集成中心 — 页面分享链接收件人模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from app.core.database import Base


class ShareLinkRecipient(Base):
    __tablename__ = "share_link_recipient"

    id = Column(Integer, primary_key=True, autoincrement=True)
    share_link_id = Column(
        Integer,
        ForeignKey("share_link.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的分享链接ID",
    )
    recipient_type = Column(String(16), nullable=False, comment="收件人类型: user / group")
    recipient_id = Column(String(64), nullable=False, comment="收件人标识")
    recipient_name = Column(String(128), nullable=True, comment="收件人姓名")
    delivered = Column(Boolean, nullable=False, default=False, comment="是否已送达")
    delivered_at = Column(DateTime(timezone=True), nullable=True, comment="送达时间")
    wecom_msg_id = Column(String(256), nullable=True, comment="企微消息ID")
    error_msg = Column(String(512), nullable=True, comment="发送失败原因")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_share_link_recipient_link_type", "share_link_id", "recipient_type"),
    )
