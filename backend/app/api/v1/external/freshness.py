"""对外接口数据时效公共组件

统一口径（2026-09-29 AEOS 生产协同时效交接 + 2026-09-28 时效契约设计）：
- data_as_of = 源表全表最大修改时间 与 相关同步类型最近成功时间的较晚者；
  多同步类型共担同一数据集时取 min（薄弱环节），再与源表时间取 max；
- 全部来源皆空 → ExternalSourceUnavailable（信封级结构化错误，code=503）；
- confidence/stale 复用 6h/24h 阈值（kitting_calc_service.freshness_of）：
  超过 24h 有效期一律 low + stale=true，历史快照类数据同样不再豁免；
- 时间统一输出带时区 ISO 8601：DB 无时区时间按进程本地时区解释（部署 TZ=Asia/Shanghai），
  不得用响应时间冒充 data_as_of，缺失时间不得填 now；
- generated_at（本次响应生成时间）与 data_as_of（数据快照时间）分别保留；
- warnings 承载数据过期、字段缺失、部分结果等结构化提示。
"""

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.material.kitting_calc_service import (
    STALE_HOURS,
    freshness_of,
    load_source_as_of,
    min_as_of,
)


class ExternalSourceUnavailable(Exception):
    """对外接口数据源不可用：算不出 data_as_of，由 log_external_call 转 code=503 信封错误"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def local_tzinfo():
    """业务本地时区（DB 无时区时间戳的解释口径；部署 compose 固定 TZ=Asia/Shanghai）。"""
    return datetime.now().astimezone().tzinfo


def iso_aware(value: datetime) -> str:
    """datetime → 带时区 ISO 8601；无时区值按进程本地时区解释，不允许输出无时区字符串。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_tzinfo())
    return value.isoformat()


async def table_max_as_of(db: AsyncSession, *columns) -> Optional[datetime]:
    """源表全表 max(时间列)（忽略 NULL，多列取最大）；空表/无值返回 None。"""
    latest = None
    for column in columns:
        value = (await db.execute(select(func.max(column)))).scalar()
        if value is not None and (latest is None or value > latest):
            latest = value
    return latest


async def source_as_of(
    db: AsyncSession, *, columns: Iterable = (), sync_types: Iterable[str] = (),
) -> Optional[datetime]:
    """数据源最近刷新时间：源表全表 max 与同步最近成功时间的较晚者。"""
    candidates = [await table_max_as_of(db, *columns)]
    if sync_types:
        candidates.append(min_as_of(await load_source_as_of(db, tuple(sync_types))))
    values = [value for value in candidates if value is not None]
    return max(values) if values else None


async def sync_only_as_of(db: AsyncSession, sync_types: Iterable[str]) -> Optional[datetime]:
    """纯同步来源（齐套/供给/库存聚合口径）：多同步类型取 min（薄弱环节）。"""
    return min_as_of(await load_source_as_of(db, tuple(sync_types)))


def freshness_meta(
    data_as_of: Optional[datetime],
    source_label: str,
    *,
    warnings: Iterable[str] = (),
) -> dict:
    """成功响应时效元信息；算不出 data_as_of 即抛 ExternalSourceUnavailable。

    超过 24h 有效期时自动追加一条过期告警（confidence=low / stale=true），
    调用方传入的 warnings 一并透出，供 MCP/Hub 写入 Evidence。
    """
    if data_as_of is None:
        raise ExternalSourceUnavailable(
            f"「{source_label}」数据源不可用：无有效数据且从未成功同步或导入，无法确定数据时效"
        )
    confidence, stale = freshness_of(data_as_of)
    notices = list(warnings)
    if stale:
        notices.append(
            f"数据快照时间 {iso_aware(data_as_of)} 已超过 {STALE_HOURS} 小时有效期，"
            f"置信度不足，不得用于确定性风险结论"
        )
    return {
        "data_as_of": iso_aware(data_as_of),
        "data_confidence": confidence,
        "stale": stale,
        "generated_at": iso_aware(datetime.now()),
        "warnings": notices,
    }
