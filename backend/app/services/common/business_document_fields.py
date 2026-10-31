"""共享台账自定义字段的校验与字段 key 生成。"""

import math
from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

WIDGETS = {"text", "textarea", "number", "date", "select", "boolean"}


def generate_field_key() -> str:
    return f"field_{uuid4().hex[:8]}"


def normalize_options(widget: str, options: list[str] | None) -> list[str] | None:
    if widget != "select":
        return None
    cleaned: list[str] = []
    for item in options or []:
        if item is None:
            continue
        value = str(item).strip()
        if value and value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        raise HTTPException(status_code=400, detail="下拉字段至少需要一个选项")
    return cleaned


def validate_custom_fields(
    configs,
    values: dict[str, Any] | None,
    current_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if values is not None and not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="自定义字段格式错误")
    if current_values is not None and not isinstance(current_values, dict):
        raise HTTPException(status_code=400, detail="自定义字段格式错误")

    configs = list(configs)
    known_keys = {config.field_key for config in configs}
    unknown_keys = set(values or {}) - known_keys
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"未知字段：{', '.join(sorted(unknown_keys))}",
        )

    merged = dict(current_values or {})
    merged.update(values or {})

    result: dict[str, Any] = {}
    for config in configs:
        value = _normalize_value(config, merged.get(config.field_key))
        if config.required and value is None:
            raise HTTPException(status_code=400, detail=f"字段「{config.label}」为必填")
        if value is not None:
            result[config.field_key] = value
    return result


def _normalize_value(config, raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == "":
        return None

    widget = config.widget
    if widget in ("text", "textarea"):
        if not isinstance(raw, str):
            raise HTTPException(status_code=400, detail=f"字段「{config.label}」必须为文本")
        return raw.strip() or None

    if widget == "number":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise HTTPException(status_code=400, detail=f"字段「{config.label}」必须为数字")
        if isinstance(raw, float) and not math.isfinite(raw):
            raise HTTPException(status_code=400, detail=f"字段「{config.label}」必须为有限数字")
        return raw

    if widget == "date":
        if not isinstance(raw, str):
            raise HTTPException(status_code=400, detail=f"字段「{config.label}」必须为日期")
        value = raw.strip()
        message = f"字段「{config.label}」日期格式应为 YYYY-MM-DD"
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=400, detail=message) from None
        if parsed.isoformat() != value:
            raise HTTPException(status_code=400, detail=message)
        return parsed.isoformat()

    if widget == "boolean":
        if not isinstance(raw, bool):
            raise HTTPException(status_code=400, detail=f"字段「{config.label}」必须为布尔值")
        return raw

    if widget == "select":
        if not isinstance(raw, str):
            raise HTTPException(status_code=400, detail=f"字段「{config.label}」必须为选项值")
        value = raw.strip()
        if value not in (config.options or []):
            raise HTTPException(
                status_code=400,
                detail=f"字段「{config.label}」的值不在可选项中",
            )
        return value

    raise HTTPException(status_code=400, detail=f"不支持的字段类型：{widget}")
