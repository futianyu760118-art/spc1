"""审批中心 - 代码接入（builtin）Adapter 注册表。

接入一个新业务只需三件事：
1. 继承 ApprovalBizAdapter，实现 submit_payload / fetch_detail / on_transition；
2. 用 @approval_adapter 注册（biz_type / biz_name / 深链模板 / 条件字段选项）；
3. 在「审批配置」页为该 biz_type 配置审批链。
注册靠 import 副作用：消费方（approvals.py）import 业务 adapter 模块即完成注册。
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ApprovalBizAdapter:
    """代码接入协议基类。on_transition 每次流转都会被调用（含终态），业务用它同步自身状态列。"""

    biz_type: str = ""
    biz_name: str = ""
    deep_link_template: str = ""
    condition_field_options: list = None

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_payload(self, db: AsyncSession, entity_id: int) -> dict:
        """提交时的实例摘要：{no, title, summary, applicant, amount, extra:{条件字段: 值}}。"""
        raise NotImplementedError

    async def fetch_detail(self, db: AsyncSession, entity_id: int) -> dict:
        """详情页业务内容：{fields:[{label,value,emphasis?}], attachments?:[{name,key}]}。"""
        raise NotImplementedError

    async def on_transition(self, db: AsyncSession, entity_id: int, state: dict) -> None:
        """流转回调：state={status, level, snapshot, submitted_at, approved_by, approved_at, version}。"""
        raise NotImplementedError

    async def fetch_drafts(self, db: AsyncSession, username: str) -> list[dict]:
        """可选：业务侧草稿（未提交，无实例），供「我发起的」展示；默认无。"""
        return []


_adapters: dict[str, type[ApprovalBizAdapter]] = {}


def approval_adapter(cls: type[ApprovalBizAdapter]) -> type[ApprovalBizAdapter]:
    if not cls.biz_type or not cls.biz_name:
        raise ValueError(f"Adapter {cls.__name__} 缺少 biz_type/biz_name")
    if cls.biz_type in _adapters:
        raise ValueError(f"审批中心 Adapter 重复注册：{cls.biz_type}")
    _adapters[cls.biz_type] = cls
    return cls


def get_adapter_class(biz_type: str) -> Optional[type[ApprovalBizAdapter]]:
    return _adapters.get(biz_type)


def get_adapter_classes() -> list[type[ApprovalBizAdapter]]:
    return list(_adapters.values())


def adapter_instance(db: AsyncSession, biz_type: str) -> Optional[ApprovalBizAdapter]:
    cls = _adapters.get(biz_type)
    return cls(db) if cls else None
