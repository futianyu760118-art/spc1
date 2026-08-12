"""回写服务共用辅助函数"""
from datetime import datetime
from typing import Tuple, Optional


# SPC 状态字符串 → K3 ERP FStatus 整数映射
# K3: 0=未审核, 1=已审核, 2=部分收料, 3=已关闭
SPC_TO_K3_FSTATUS = {
    "placed": 0,
    "accepted": 1,
    "partial_received": 2,
    "received": 3,
    "fully_received": 3,
}

K3_FSTATUS_TO_SPC = {v: k for k, v in SPC_TO_K3_FSTATUS.items()}


def spc_status_to_k3(status: str) -> Optional[int]:
    """将 SPC 状态字符串转换为 K3 FStatus 整数。未知状态返回 None。"""
    return SPC_TO_K3_FSTATUS.get(status)


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
