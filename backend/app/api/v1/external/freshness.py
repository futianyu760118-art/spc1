"""对外接口数据时效公共组件

统一口径（设计：docs/superpowers/specs/2026-09-28-external-data-freshness-design.md）：
- data_as_of = 源表全表最大修改时间 与 相关同步类型最近成功时间的较晚者；
  多同步类型共担同一数据集时取 min（薄弱环节），再与源表时间取 max；
- 全部来源皆空 → ExternalSourceUnavailable（信封级结构化错误，code=503）；
- confidence/stale 复用 6h/24h 阈值（kitting_calc_service.freshness_of）；
- baseline=True（历史快照类）有数据即 stale=false、置信度下限 medium。
"""

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.material.kitting_calc_service import freshness_of, load_source_as_of, min_as_of

from .common import ExternalEnvelopeError


class ExternalSourceUnavailable(ExternalEnvelopeError):
    """对外接口数据源不可用：算不出 data_as_of，由 log_external_call 转 code=503 信封错误"""

    def __init__(self, message: str):
        super().__init__(503, message)


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
    data_as_of: Optional[datetime], source_label: str, *, baseline: bool = False,
) -> dict:
    """成功响应时效元信息；算不出 data_as_of 即抛 ExternalSourceUnavailable。"""
    if data_as_of is None:
        raise ExternalSourceUnavailable(
            f"「{source_label}」数据源不可用：无有效数据且从未成功同步，无法确定数据时效"
        )
    confidence, stale = freshness_of(data_as_of)
    if baseline:
        confidence = "medium" if confidence == "low" else confidence
        stale = False
    return {
        "data_as_of": data_as_of.isoformat(),
        "data_confidence": confidence,
        "stale": stale,
    }
