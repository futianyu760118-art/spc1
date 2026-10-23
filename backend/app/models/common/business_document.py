"""Shared business document and version ledger."""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class BusinessDocument(Base):
    __tablename__ = "business_document"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_type = Column(String(32), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    title = Column(String(256), nullable=False)
    applicable_product = Column(String(128), nullable=True)
    applicable_order = Column(String(128), nullable=True)
    applicable_process = Column(String(128), nullable=True)
    current_version = Column(String(32), nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    custom_fields = Column(JSONB, nullable=True, server_default=text("'{}'::jsonb"))
    is_deleted = Column(Integer, nullable=False, default=0, server_default=text("0"), index=True, comment="是否删除 0否1是")  # server_default 对齐 migrate 路径的 DEFAULT 0，否则新库 seed 插入未带列值会 NOT NULL 失败
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    versions = relationship("BusinessDocumentVersion", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "uq_business_document_type_code", "doc_type", "code",
            unique=True, postgresql_where=text("is_deleted = 0"),
        ),
    )


class BusinessDocumentVersion(Base):
    __tablename__ = "business_document_version"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("business_document.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no = Column(String(32), nullable=False)
    content = Column(Text, nullable=True)
    attachments = Column(JSONB, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    effective_date = Column(Date, nullable=True)
    published_at = Column(DateTime, nullable=True)
    published_by = Column(String(64), nullable=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    document = relationship("BusinessDocument", back_populates="versions")

    __table_args__ = (
        Index("uq_business_document_version", "document_id", "version_no", unique=True),
    )


class BusinessDocumentFieldConfig(Base):
    __tablename__ = "business_document_field_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_type = Column(String(32), nullable=False, index=True)
    field_key = Column(String(64), nullable=False)
    label = Column(String(64), nullable=False)
    widget = Column(String(16), nullable=False)
    required = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    show_in_list = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    options = Column(JSONB, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_business_document_field_config_key", "doc_type", "field_key", unique=True),
        Index("uq_business_document_field_config_label", "doc_type", "label", unique=True),
    )
