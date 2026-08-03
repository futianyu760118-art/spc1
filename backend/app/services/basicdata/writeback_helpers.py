"""回写服务共用辅助函数"""
from datetime import datetime
from typing import Tuple


def render_sql(template: str, target_keys: dict, payload: dict) -> Tuple[str, dict]:
    """渲染 SQL 模板,返回 (rendered_template, params).

    占位符约定:
      :target_keys__XXX  ->  target_keys[XXX]  (用于 WHERE)
      :payload__XXX      ->  payload[XXX]      (用于 SET)
      :writeback_at      ->  当前时间戳 ISO 格式 (系统自动注入)
    """
    params = {}
    for k, v in target_keys.items():
        params[f"target_keys__{k}"] = v
    for k, v in payload.items():
        params[f"payload__{k}"] = v
    params["writeback_at"] = datetime.utcnow().isoformat()
    return template, params
