"""Schemas for shared business document ledgers."""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class BusinessDocumentVersionOut(BaseModel):
    id: int
    document_id: int
    version_no: str
    content: Optional[str] = None
    attachments: Optional[list[dict[str, Any]]] = None
    status: str
    effective_date: Optional[date] = None
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BusinessDocumentOut(BaseModel):
    id: int
    doc_type: str
    code: str
    title: str
    applicable_product: Optional[str] = None
    applicable_order: Optional[str] = None
    applicable_process: Optional[str] = None
    current_version: Optional[str] = None
    status: str
    is_deleted: int = 0
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    custom_fields: Optional[dict[str, Any]] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BusinessDocumentCreate(BaseModel):
    code: str
    title: str
    applicable_product: Optional[str] = None
    applicable_order: Optional[str] = None
    applicable_process: Optional[str] = None
    version_no: str = "V1.0"
    content: Optional[str] = None
    attachments: Optional[list[dict[str, Any]]] = None
    custom_fields: Optional[dict[str, Any]] = None
    effective_date: Optional[date] = None


class BusinessDocumentUpdate(BaseModel):
    title: Optional[str] = None
    applicable_product: Optional[str] = None
    applicable_order: Optional[str] = None
    applicable_process: Optional[str] = None
    custom_fields: Optional[dict[str, Any]] = None


class BusinessDocumentVersionCreate(BaseModel):
    version_no: str
    content: Optional[str] = None
    attachments: Optional[list[dict[str, Any]]] = None
    effective_date: Optional[date] = None


class BusinessDocumentFieldConfigOut(BaseModel):
    id: int
    doc_type: str
    field_key: str
    label: str
    widget: str
    required: bool
    show_in_list: bool
    options: Optional[list[str]] = None
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BusinessDocumentFieldConfigCreate(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    widget: str = Field(min_length=1, max_length=16)
    required: bool = False
    show_in_list: bool = True
    options: Optional[list[str]] = None
    sort_order: int = 0


class BusinessDocumentFieldConfigUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    required: Optional[bool] = None
    show_in_list: Optional[bool] = None
    options: Optional[list[str]] = None
    sort_order: Optional[int] = None
