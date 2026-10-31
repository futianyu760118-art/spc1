"""品质异常 AI 分析报告 Schema — 同时用作 structured_output 目标与 API 响应体"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class QualityAnalysisHighFreqFinding(BaseModel):
    """高频异常发现"""
    defect_type: str           # 缺陷类型
    count: int                 # 出现次数
    proportion: str            # "32.5%"
    note: str                  # 该类型特征/共性描述


class QualityAnalysisActionItem(BaseModel):
    """行动项"""
    title: str                 # 行动项标题
    owner_suggestion: Optional[str] = None   # 建议责任人/部门
    priority: str              # "高" | "中" | "低"
    due_suggestion: Optional[str] = None     # 建议完成时限（自然语言）


class QualityAnalysisReportOut(BaseModel):
    """品质异常分析报告"""
    model_config = ConfigDict(from_attributes=True)

    summary: str                              # 整体概述
    high_freq_findings: List[QualityAnalysisHighFreqFinding]
    root_causes: List[str]                    # 根因清单
    strategies: List[str]                     # 解决策略清单
    action_items: List[QualityAnalysisActionItem]
    prevention: List[str]                      # 预防措施清单
    generated_at: Optional[datetime] = None
    provider: Optional[str] = None
    data_scope: Optional[dict] = None         # 本次分析的条件+命中总数