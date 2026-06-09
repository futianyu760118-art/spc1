"""Schemas for shared business document ledgers."""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel


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
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BusinessDocumentCreate(BaseModel):
    code: str
    title: str
    applicable_product: Optional[str] = None
    applicable_order: Optional[str] = None
    applicable_process: Optional[str] = None
    status: str = "draft"
    version_no: str = "V1.0"
    content: Optional[str] = None
    attachments: Optional[list[dict[str, Any]]] = None
    effective_date: Optional[date] = None


class BusinessDocumentUpdate(BaseModel):
    title: Optional[str] = None
    applicable_product: Optional[str] = None
    applicable_order: Optional[str] = None
    applicable_process: Optional[str] = None
    status: Optional[str] = None


class BusinessDocumentVersionCreate(BaseModel):
    version_no: str
    content: Optional[str] = None
    attachments: Optional[list[dict[str, Any]]] = None
    status: str = "published"
    effective_date: Optional[date] = None
