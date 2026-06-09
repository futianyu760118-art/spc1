"""工具辅助函数"""

from typing import Any, Dict
from decimal import Decimal
from datetime import date, datetime
from sqlalchemy.inspection import inspect


def model_to_dict(instance: Any, exclude_fields: set = None) -> Dict[str, Any]:
    """
    将 SQLAlchemy 模型实例转换为字典，自动获取所有字段
    
    Args:
        instance: SQLAlchemy 模型实例
        exclude_fields: 要排除的字段集合（如 'id', 'created_at' 等）
    
    Returns:
        包含所有字段的字典
    """
    if exclude_fields is None:
        exclude_fields = set()
    
    result = {}
    mapper = inspect(instance.__class__)
    
    for column in mapper.columns:
        col_name = column.name
        
        # 跳过排除的字段
        if col_name in exclude_fields:
            continue
        
        value = getattr(instance, col_name, None)
        
        # 类型转换
        if value is not None:
            if isinstance(value, Decimal):
                result[col_name] = float(value)
            elif isinstance(value, (date, datetime)):
                result[col_name] = str(value)
            else:
                result[col_name] = value
        else:
            result[col_name] = None
    
    return result


def create_search_result_item(
    instance: Any,
    item_type: str,
    title: str,
    subtitle: str,
    url: str,
    tags: list = None,
    exclude_fields: set = None
) -> Dict[str, Any]:
    """
    创建搜索结果项，包含类型、标题、副标题、URL、标签和所有模型字段
    
    Args:
        instance: SQLAlchemy 模型实例
        item_type: 项目类型（如 'order', 'material' 等）
        title: 标题
        subtitle: 副标题
        url: 跳转 URL
        tags: 标签列表
        exclude_fields: 要排除的字段集合
    
    Returns:
        完整的搜索结果项字典
    """
    if tags is None:
        tags = []
    
    # 基本信息
    item = {
        "type": item_type,
        "title": title,
        "subtitle": subtitle,
        "url": url,
        "tags": tags,
    }
    
    # 添加所有模型字段
    item.update(model_to_dict(instance, exclude_fields))
    
    return item
