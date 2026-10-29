"""订单写操作注册表 — 唯一源 agents/shared/order-write-operations.json。

adapter（JS）与 write_service / 助手工具（Python）共同消费该声明：
新增「字段写入类」操作只需在注册表加一项，无需改代码；
「特殊语义」操作（备注/状态联动）在 write_service 以 custom handler 实现。
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re

_PACKAGE_COPY = Path(__file__).with_name("write_operations.json")
_REPO_SOURCE = Path(__file__).resolve().parents[4] / "agents" / "shared" / "order-write-operations.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_registry() -> dict:
    for path in (_PACKAGE_COPY, _REPO_SOURCE):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise RuntimeError(f"订单写操作注册表缺失：{_PACKAGE_COPY} 与 {_REPO_SOURCE} 均不存在")


REGISTRY = _load_registry()
OPERATION_MAP: Dict[str, dict] = {op["name"]: op for op in REGISTRY["operations"]}
OPERATION_NAMES = frozenset(OPERATION_MAP)
ASSISTANT_OPERATIONS: List[dict] = [
    op for op in REGISTRY["operations"] if "assistant" in op["audiences"]
]
ASSISTANT_OPERATION_NAMES = [op["name"] for op in ASSISTANT_OPERATIONS]
DEFAULT_ASSISTANT_OPERATION = ASSISTANT_OPERATION_NAMES[0] if len(ASSISTANT_OPERATION_NAMES) == 1 else ""
ASSISTANT_FIELDS: List[dict] = [f for op in ASSISTANT_OPERATIONS for f in op.get("fields", [])]
ASSISTANT_FIELD_WIRES = tuple(dict.fromkeys(f["wire"] for f in ASSISTANT_FIELDS))


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize_changes(operation: str, changes: Any) -> Tuple[Optional[dict], Optional[str]]:
    """按注册表归一化 changes。

    返回 (normalized, error)：error 非 None 时 normalized 为 None。
    错误消息与 adapter 校验及 HTTP 契约保持一致。
    """
    if not isinstance(changes, dict):
        return None, "changes 必须是对象"
    spec = OPERATION_MAP[operation]
    key = spec["changesKey"]
    if set(changes) != {key}:
        return None, f"{operation} 只允许 changes.{key}"
    value = changes[key]
    value_spec = spec["value"]
    kind = value_spec["type"]
    if kind == "string_or_null":
        if value is not None and not isinstance(value, str):
            return None, f"changes.{key} 必须是字符串或 null"
        if isinstance(value, str) and len(value) > value_spec["maxLength"]:
            return None, f"changes.{key} 不能超过 {value_spec['maxLength']} 字符"
        if isinstance(value, str):
            return {key: value.strip() or None}, None
        return {key: None}, None
    if kind == "enum":
        if value not in value_spec["values"]:
            return None, f"changes.{key} 必须是 {' 或 '.join(value_spec['values'])}"
        return {key: value}, None
    if kind == "date":
        if not isinstance(value, str) or not DATE_RE.match(value):
            return None, f"changes.{key} 必须是 YYYY-MM-DD"
        parsed = _parse_iso_date(value)
        if parsed is None:
            return None, f"changes.{key} 不是有效日期"
        return {key: parsed.isoformat()}, None
    # date_map
    if not isinstance(value, dict) or not value:
        return None, f"changes.{key} 至少一个字段"
    allowed = {field["wire"] for field in spec["fields"]}
    normalized: dict = {}
    for field, item in value.items():
        if field not in allowed:
            return None, f"字段不在白名单：{field}"
        if item is None:
            normalized[field] = None
            continue
        if not isinstance(item, str) or not DATE_RE.match(item):
            return None, f"字段 {field} 必须是 YYYY-MM-DD 或 null"
        parsed = _parse_iso_date(item)
        if parsed is None:
            return None, f"字段 {field} 不是有效日期"
        normalized[field] = parsed.isoformat()
    return {key: normalized}, None
