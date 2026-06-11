"""Basic data position model."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, text
from sqlalchemy.sql import func

from app.core.database import Base


class Position(Base):
    __tablename__ = "scm_position"
    __table_args__ = (
        Index(
            "uq_scm_position_oa_position_id",
            "oa_position_id",
            unique=True,
            postgresql_where=text("oa_position_id IS NOT NULL"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    position_code = Column(String(64), nullable=True, unique=True, comment="岗位编码")
    oa_position_id = Column(String(64), nullable=True, comment="OA系统岗位ID")
    position_name = Column(String(100), nullable=False, comment="岗位名称")
    role_id = Column(Integer, nullable=True, comment="关联系统角色ID")
    status = Column(Integer, nullable=False, default=1, comment="状态")
    data_source = Column(String(32))
    create_time = Column(DateTime, server_default=func.now(), nullable=False)
