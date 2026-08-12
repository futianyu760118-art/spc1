"""回写相关 Pydantic schema"""
from typing import Optional
from pydantic import BaseModel, Field


class EnqueueWritebackRequest(BaseModel):
    writeback_type: str = Field(..., max_length=64)
    business_table: str = Field(default="purchase_order", max_length=128)
    business_pk: str = Field(..., max_length=64)
    target_keys: dict
    payload: dict
    reason: Optional[str] = None


class EnqueueWritebackResponse(BaseModel):
    queue_id: int
    deduplicated: bool


class BatchEnqueueRequest(BaseModel):
    writeback_type: str = Field(..., max_length=64)
    filters: dict
    reason: Optional[str] = None


class BatchEnqueueResponse(BaseModel):
    enqueued: int
    skipped: int
    errors: list[str] = []


class RetryQueueRequest(BaseModel):
    queue_id: int


class AbandonQueueRequest(BaseModel):
    queue_id: int
    reason: Optional[str] = None


class WritebackConfigUpsert(BaseModel):
    writeback_type: str = Field(..., max_length=64)
    description: Optional[str] = None
    target_table: str = Field(..., max_length=128)
    target_key_fields: list[str]
    update_sql_template: str
    field_mapping_json: Optional[dict] = None
    enqueue_trigger: Optional[str] = None
    max_retries: int = 6
    enabled: bool = True
