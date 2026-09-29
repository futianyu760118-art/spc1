"""审批中心 - SQL 接入业务：元数据解析 + 动态 provider + 注册表同步。

内置业务由代码 provider 提供（只聚合不在此表）；SQL 业务由管理员在「业务接入」里配置。
注册表在进程内存中，故：写配置后立刻同步（本进程即时生效），启动时同步一次；
多实例部署时其它实例需重启才看到新业务（与权限注册表同款限制）。
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.common import approval_providers  # noqa: F401 — 导入即注册内置 provider
from app.services.common.approval_engine import check_node_permission, resolve_node_approver_user_ids
from app.services.common.approval_registry import (
    ApprovalPendingProvider, get_pending_providers, get_provider,
    register_pending_provider, unregister_provider,
)
from app.services.common.approval_sql import (
    FIELD_LABELS, FETCH_LIMIT, execute_readonly_sql, normalize_sql_row, pick_mapped_value, render_deep_link,
)

logger = logging.getLogger(__name__)

# 本模块注册过的 SQL 业务标识：同步时据此注销，绝不误删内置 provider
_sql_registered: set[str] = set()


@dataclass(frozen=True)
class BizMeta:
    biz_type: str
    biz_name: str
    mode: str
    is_active: bool
    condition_field_options: list[dict] = field(default_factory=list)
    sql_text: Optional[str] = None
    field_mapping: Optional[dict] = None
    deep_link_template: Optional[str] = None
    description: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None


def _loads(raw, default):
    if not raw:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _row_to_meta(row: dict) -> BizMeta:
    updated_at = row.get("updated_at")
    return BizMeta(
        biz_type=row["biz_type"], biz_name=row.get("biz_name") or row["biz_type"], mode="sql",
        is_active=bool(row.get("is_active", True)),
        condition_field_options=_loads(row.get("condition_fields_json"), []),
        sql_text=row.get("sql_text"), field_mapping=_loads(row.get("field_mapping_json"), {}),
        deep_link_template=row.get("deep_link_template"), description=row.get("description"),
        updated_by=row.get("updated_by"),
        updated_at=updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at,
    )


async def list_sql_businesses(db: AsyncSession) -> list[dict]:
    rows = await db.execute(text("SELECT * FROM approval_business ORDER BY id"))
    return [dict(r._mapping) for r in rows]


async def list_biz_metas(db: AsyncSession) -> list[BizMeta]:
    """业务清单：内置 provider（代码注册）+ 表内 SQL 业务（含停用，便于重新启用）。"""
    sql_rows = await list_sql_businesses(db)
    sql_types = {r["biz_type"] for r in sql_rows}
    metas = [
        BizMeta(biz_type=p.biz_type, biz_name=p.biz_name, mode="builtin", is_active=True,
                condition_field_options=p.condition_field_options or [])
        for p in get_pending_providers() if p.biz_type not in sql_types
    ]
    metas.extend(_row_to_meta(r) for r in sql_rows)
    return metas


async def resolve_biz_meta(db: AsyncSession, biz_type: str) -> Optional[BizMeta]:
    row = (await db.execute(text("SELECT * FROM approval_business WHERE biz_type = :bt LIMIT 1"),
                            {"bt": biz_type})).fetchone()
    if row:
        return _row_to_meta(dict(row._mapping))
    provider = get_provider(biz_type)
    if not provider:
        return None
    return BizMeta(biz_type=provider.biz_type, biz_name=provider.biz_name, mode="builtin", is_active=True,
                   condition_field_options=provider.condition_field_options or [])


async def _load_chain_nodes(db: AsyncSession, biz_type: str) -> list[dict]:
    row = (await db.execute(text(
        "SELECT nodes FROM approval_config WHERE biz_type = :bt AND is_active = TRUE"), {"bt": biz_type})).fetchone()
    if not row:
        return []
    return _loads(row[0], [])


def _match_chain_node(nodes: list[dict], current_node) -> tuple[Optional[dict], int]:
    """按节点名匹配审批链节点，返回 (节点, 1-based 序号)；匹配不到返回 (None, 0)。"""
    label = str(current_node or "").strip()
    if not label:
        return None, 0
    for i, node in enumerate(nodes, 1):
        if str(node.get("label") or "").strip() == label:
            return node, i
    return None, 0


def _can_view(node: Optional[dict], username: str, role: str) -> bool:
    """节点匹配不到时仅 admin 可见（与引擎「审批链异常的单子不展示」一致）。"""
    if not node:
        return role == "admin"
    ok, _ = check_node_permission(node, username, role)
    return ok


async def _run_readonly(db: AsyncSession, sql_text: str, biz_type: str) -> Optional[list[dict]]:
    """在 SAVEPOINT 里跑取数：失败只回滚本业务的语句，避免整条请求的 session 事务进入 aborted 态
    而让「之后」的业务被静默跳过（共享 session 下这是最隐蔽的连锁故障）。"""
    savepoint = await db.begin_nested()
    try:
        rows = await execute_readonly_sql(db, sql_text, limit=FETCH_LIMIT)
    except Exception as exc:
        await savepoint.rollback()
        logger.warning("[审批中心] SQL 接入业务取数失败 biz=%s: %s", biz_type, exc)
        return None
    await savepoint.commit()
    return rows


async def _fetch_sql_pending(db: AsyncSession, username: str, role: str, biz_type: str) -> list[dict]:
    meta = await resolve_biz_meta(db, biz_type)
    if not meta or not meta.is_active or not meta.sql_text:
        return []
    rows = await _run_readonly(db, meta.sql_text, biz_type)
    if rows is None:
        return []
    nodes = await _load_chain_nodes(db, biz_type)
    mapping = meta.field_mapping or {}
    items = []
    for row in rows:
        item = normalize_sql_row({
            "biz_type": meta.biz_type, "biz_name": meta.biz_name,
            "field_mapping": mapping, "deep_link_template": meta.deep_link_template,
        }, row)
        try:
            item["id"] = int(item.get("id"))
        except (TypeError, ValueError):
            logger.warning("[审批中心] 跳过 id 非数字的取数行 biz=%s id=%r", biz_type, item.get("id"))
            continue
        node, level = _match_chain_node(nodes, item.get("current_node"))
        if not _can_view(node, username, role):
            continue
        item["current_level"] = level
        item["timeout_hours"] = (node or {}).get("timeout_hours")
        item["approver_user_ids"] = await resolve_node_approver_user_ids(db, node) if node else []
        item["deep_link"] = render_deep_link(meta.deep_link_template, item)
        items.append(item)
    return items


async def _preview_sql_item(db: AsyncSession, username: str, role: str, biz_type: str, entity_id: int) -> Optional[dict]:
    """抽屉预览：重跑取数 SQL 找到该行，按映射生成字段，按链节点位置推算进度。"""
    meta = await resolve_biz_meta(db, biz_type)
    if not meta or not meta.sql_text:
        return None
    rows = await _run_readonly(db, meta.sql_text, biz_type)
    if rows is None:
        return None
    mapping = meta.field_mapping or {}
    target = None
    for row in rows:
        source_id = pick_mapped_value(row, mapping, "id")
        # 来源列可能是字符串数字，与整数 entity_id 统一按字符串比较
        if source_id is not None and str(source_id) == str(entity_id):
            target = row
            break
    if target is None:
        return None
    item = normalize_sql_row({
        "biz_type": meta.biz_type, "biz_name": meta.biz_name,
        "field_mapping": mapping, "deep_link_template": meta.deep_link_template,
    }, target)
    nodes = await _load_chain_nodes(db, biz_type)
    node, level = _match_chain_node(nodes, item.get("current_node"))
    progress = [
        {"seq": i, "label": n.get("label"),
         "approver_label": ("指定人员：" + "、".join(str(a.get("username") or a.get("user_id")) for a in (n.get("approvers") or [])))
                            if n.get("approvers") else (f"角色：{n.get('role')}" if n.get("role") else "-"),
         "state": "done" if i < level else ("current" if i == level else "todo"),
         "acted_at": None, "comment": None}
        for i, n in enumerate(nodes, 1)
    ]
    return {
        **item,
        "current_level": level,
        "timeout_hours": (node or {}).get("timeout_hours"),
        "deep_link": render_deep_link(meta.deep_link_template, item),
        "fields": [{"label": FIELD_LABELS[k], "value": item.get(k)} for k in FIELD_LABELS if item.get(k) is not None],
        "progress": progress,
        "logs": [],
        "can_act": False,
        "action_hint": "该业务为 SQL 接入，审批动作需在业务系统内完成",
    }


def build_sql_provider(meta: BizMeta) -> ApprovalPendingProvider:
    async def _fetch(db, username: str, role: str):
        return await _fetch_sql_pending(db, username, role, meta.biz_type)

    async def _preview(db, username: str, role: str, entity_id: int):
        return await _preview_sql_item(db, username, role, meta.biz_type, entity_id)

    return ApprovalPendingProvider(
        biz_type=meta.biz_type, biz_name=meta.biz_name, mode="sql",
        fetch=_fetch, preview=_preview,
        condition_field_options=meta.condition_field_options or [],
    )


async def sync_sql_providers(db: AsyncSession) -> dict:
    """把表内启用的 SQL 业务注册进 provider 注册表，停用的注销。"""
    metas = [_row_to_meta(r) for r in await list_sql_businesses(db)]
    active: dict[str, BizMeta] = {}
    for meta in metas:
        # 防御：若有人直接把内置 biz_type 写进表，跳过以免覆盖代码注册的 provider
        if meta.is_active and get_provider(meta.biz_type) and meta.biz_type not in _sql_registered:
            logger.warning("[审批中心] 业务标识与内置业务冲突，跳过 SQL 注册: %s", meta.biz_type)
            continue
        if meta.is_active:
            active[meta.biz_type] = meta
    unregistered = 0
    for biz_type in list(_sql_registered - set(active)):
        unregister_provider(biz_type)
        _sql_registered.discard(biz_type)
        unregistered += 1
        logger.info("[审批中心] SQL 接入业务已停用，注销 provider: %s", biz_type)
    for biz_type, meta in active.items():
        register_pending_provider(build_sql_provider(meta))
        _sql_registered.add(biz_type)
    return {"registered": len(active), "unregistered": unregistered}
