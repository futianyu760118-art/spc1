"""审批中心 - 待审批提供者注册表。

新业务流程接入统一「待我审批」列表时，只需在 approval_providers.py 里注册一个
provider（biz_type + 名称 + 归一化取数函数），审批中心 API 自动聚合，无需改本模块。
"""

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

# 取数签名：(db, username, role_code) -> 归一化待审批条目列表（各 biz 内部自行按节点权限过滤）
PendingFetcher = Callable[[AsyncSession, str, str], Awaitable[list[dict]]]


@dataclass(frozen=True)
class ApprovalPendingProvider:
    biz_type: str
    biz_name: str
    fetch: PendingFetcher


_providers: dict[str, ApprovalPendingProvider] = {}


def register_pending_provider(provider: ApprovalPendingProvider) -> None:
    _providers[provider.biz_type] = provider


def get_pending_providers() -> list[ApprovalPendingProvider]:
    return list(_providers.values())


def is_registered(biz_type: str) -> bool:
    return biz_type in _providers
