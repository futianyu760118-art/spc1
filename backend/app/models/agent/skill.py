"""智能体技能库：共享技能定义与智能体绑定（技能不授予能力，只提供方法与上下文）。"""

from sqlalchemy import Boolean, BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class AgentSkill(Base):
    """技能索引：磁盘文件夹为准，本表只做检索、启停与绑定。"""

    __tablename__ = "agent_skill"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    skill_key = Column(String(128), nullable=True, unique=True, comment="文件夹名（slug），磁盘主键")
    name = Column(String(64), nullable=False, unique=True, comment="frontmatter name（展示名）")
    description = Column(Text, nullable=False, comment="给 LLM 判断何时加载的说明")
    instructions = Column(Text, nullable=False, comment="SKILL.md 正文缓存（运行时仍读磁盘）")
    executor_name = Column(String(64), nullable=True, comment="frontmatter executor；空=纯指令技能")
    source = Column(String(16), nullable=False, default="builtin", server_default="builtin", comment="builtin|imported")
    content_hash = Column(String(64), nullable=True, comment="SKILL.md 内容哈希")
    file_count = Column(Integer, nullable=False, default=0, server_default="0", comment="技能文件夹文件数")
    has_scripts = Column(Boolean, nullable=False, default=False, server_default="false", comment="是否含 scripts/ 脚本")
    status = Column(String(16), nullable=False, default="active", server_default="active", comment="active|disabled")
    created_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_skill_status", "status"),
        Index("ix_agent_skill_source", "source"),
    )


class AgentSkillBinding(Base):
    """智能体 → 技能绑定（多对多）。"""

    __tablename__ = "agent_skill_binding"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id = Column(
        BigInteger, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, comment="智能体",
    )
    skill_id = Column(
        BigInteger, ForeignKey("agent_skill.id", ondelete="CASCADE"), nullable=False, comment="技能",
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill_binding_agent_skill"),
        Index("ix_agent_skill_binding_skill_id", "skill_id"),
    )
