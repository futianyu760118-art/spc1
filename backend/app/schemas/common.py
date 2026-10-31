"""通用响应模型"""

from typing import Optional, List, Generic, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: Optional[T] = None


class PageResult(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: List[T]
    stats: Optional[dict] = None
