"""AEOS Hub 出站共享低层：配置开关 / 鉴权头 / 带私有 CA 的 httpx 客户端工厂。

供 hub_reporter（观测上报）与 hub_client（能力调用）复用。
契约：《AEOS-Hub-能力调用-中台对接执行单-含令牌-20261022》X-AEOS-Contract-Version: 4.0。
"""

import logging
import os
from typing import Dict
from urllib.parse import quote

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

HUB_CONTRACT_VERSION = "4.0"


def is_hub_enabled() -> bool:
    """AEOS_HUB_BASE / AEOS_SYSTEM_ID / AEOS_SYSTEM_TOKEN 三项任一缺失即整体停用。"""
    settings = get_settings()
    return bool(settings.AEOS_HUB_BASE and settings.AEOS_SYSTEM_ID and settings.AEOS_SYSTEM_TOKEN)


def hub_auth_headers() -> Dict[str, str]:
    """Hub 系统鉴权头：x-aeos-system-id（非 ASCII 必须 URL 编码）+ x-aeos-system-token + 契约版本。"""
    settings = get_settings()
    return {
        "x-aeos-system-id": quote(settings.AEOS_SYSTEM_ID, safe=""),
        "x-aeos-system-token": settings.AEOS_SYSTEM_TOKEN,
        "X-AEOS-Contract-Version": HUB_CONTRACT_VERSION,
    }


def hub_http_client(timeout: float) -> httpx.AsyncClient:
    """新建带超时的 httpx 客户端；Hub 私有 CA 时只信任该 CA，避免影响其它 HTTPS 出站。"""
    settings = get_settings()
    ca_cert = settings.AEOS_HUB_CA_CERT or os.environ.get("REQUESTS_CA_BUNDLE", "")
    return httpx.AsyncClient(timeout=timeout, verify=ca_cert or True)
