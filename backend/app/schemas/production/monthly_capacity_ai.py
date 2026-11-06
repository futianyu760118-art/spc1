"""月度产能 AI 排产 — 结构化输出 Schema"""

from typing import List

from pydantic import BaseModel, Field, field_validator


class AiScheduleOrderKey(BaseModel):
    """AI 返回的单条订单行排产顺序键"""

    order_no: str
    line_no: str

    @field_validator("order_no", "line_no", mode="before")
    @classmethod
    def _normalize_text(cls, value):
        return str(value).strip()


class AiSchedulePlanOut(BaseModel):
    """AI 排产顺序方案：仅决定订单行先后，容量分摊仍由确定性算法完成"""

    summary: str = ""
    order_sequence: List[AiScheduleOrderKey] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _normalize_summary(cls, value):
        return "" if value is None else str(value)

    @field_validator("order_sequence", "risks", mode="before")
    @classmethod
    def _normalize_list(cls, value):
        return value or []
