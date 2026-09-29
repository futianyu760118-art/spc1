"""备份管理请求模型"""

from pydantic import BaseModel, Field


class RestoreRequest(BaseModel):
    confirm_text: str = Field(default="", description="强确认文字，须为「确认恢复」")


class BackupConfigUpdate(BaseModel):
    enabled: bool
    frequency: str = Field(pattern="^(daily|weekly)$")
    schedule_time: str = Field(pattern="^([01]\\d|2[0-3]):[0-5]\\d$")
    weekday: int = Field(default=1, ge=1, le=7)
    retention_count: int = Field(default=7, ge=1, le=100)
