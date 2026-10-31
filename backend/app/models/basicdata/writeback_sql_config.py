from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class WritebackSqlConfig(Base):
    __tablename__ = "writeback_sql_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    writeback_type = Column(String(64), nullable=False, unique=True)
    description = Column(String(256))
    target_table = Column(String(128), nullable=False)
    target_key_fields = Column(JSONB, nullable=False)
    update_sql_template = Column(Text, nullable=False)
    field_mapping_json = Column(JSONB)
    enqueue_trigger = Column(String(128))
    max_retries = Column(Integer, nullable=False, default=6)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(64))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
