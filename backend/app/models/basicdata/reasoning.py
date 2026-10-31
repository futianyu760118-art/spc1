"""基础数据与集成中心 — 执行面推理任务审计模型（AEOS reason_control_platform 接入）

一次推理调用 = 一条任务记录，覆盖任务、只读工具调用、LLM 调用与证据审计
（任务书§四.8）。写入本表是推理能力对数据库的唯一写操作——业务表零写入。
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class ReasoningTask(Base):
    """推理任务审计记录"""

    __tablename__ = "reasoning_task"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(String(64), nullable=False, unique=True, index=True,
                     comment="任务 ID（调用方可指定，缺省服务端生成；取消接口按此寻址）")
    task_type = Column(String(64), nullable=False, comment="任务类型，如 order_delivery_analysis")
    prompt = Column(Text, nullable=False, comment="分析问题原文")
    context_json = Column(JSONB, nullable=True, comment="调用方上下文（businessObjectRef 等）")
    constraints_json = Column(JSONB, nullable=True, comment="约束（read_only / require_evidence）")
    status = Column(String(16), nullable=False, default="running",
                    comment="running/succeeded/failed/cancelled/timeout")
    error_code = Column(Integer, nullable=True, comment="失败信封码 400/404/490/503/504/500")
    error_message = Column(Text, nullable=True, comment="失败原因")
    result_json = Column(JSONB, nullable=True, comment="结构化结论（summary/conclusions/warnings 等）")
    evidence_json = Column(JSONB, nullable=True, comment="证据清单（evidence_refs 的源数据快照）")
    tool_calls_json = Column(JSONB, nullable=True, comment="只读取数工具调用审计")
    dropped_conclusion_count = Column(Integer, nullable=False, default=0,
                                      comment="因无有效证据引用被拒绝的结论数")
    llm_called = Column(Integer, nullable=False, default=0,
                        comment="是否实际调用中台大模型 0/1（验收证明：非直查 REST 伪装）")
    llm_provider = Column(String(32), nullable=True, comment="LLM provider 名")
    llm_model = Column(String(64), nullable=True, comment="模型名")
    llm_latency_ms = Column(Integer, nullable=True, comment="LLM 调用耗时(ms)")
    data_as_of = Column(DateTime, nullable=True, comment="证据数据业务时点")
    data_confidence = Column(String(16), nullable=True, comment="数据置信度 high/medium/low")
    api_key_id = Column(Integer, nullable=True, index=True, comment="调用方 API Key ID")
    api_key_name = Column(String(128), nullable=True, comment="调用方 Key 名称快照")
    app_key = Column(String(64), nullable=True, comment="调用方 AppKey")
    request_id = Column(String(128), nullable=True, comment="调用方请求 ID（回显）")
    duration_ms = Column(Numeric(10, 2), nullable=True, comment="任务总耗时(ms)")
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True, comment="任务结束时间")
