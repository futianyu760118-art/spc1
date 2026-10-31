"""存储 key 构建（本地与 S3 后端共用）

路径规则: {namespace}/{YYYY}/{MM}/{uuid}{ext}
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

_SAFE_NS = re.compile(r"^[a-zA-Z0-9_\-]+$")
_SAFE_EXT = re.compile(r"^[a-z0-9]{1,8}$")


def build_storage_key(namespace: str, original_name: str) -> str:
    ns = namespace if _SAFE_NS.match(namespace or "") else "misc"
    now = datetime.now()
    ext = Path(original_name or "").suffix.lower().lstrip(".")
    # 纵深防御：扩展名落地前再清洗一次（上游已有 MIME->扩展名白名单校验）
    if not _SAFE_EXT.match(ext):
        ext = ""
    fname = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    return f"{ns}/{now:%Y}/{now:%m}/{fname}"
