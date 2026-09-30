"""审批中心 - 统一待我审批 / 审批配置 API。

查询直接读中心三表（approval_instance / approval_task / approval_record）：真分页、
无聚合行数上限；审批链配置只允许操作「已接入」的 biz_type（builtin Adapter ∪ 表内
声明式业务），避免与其它模块的配置页产生双写路径。
"""

import json
import logging
import re
import time
from datetime import date, datetime, time as dt_time, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.common.approval_adapters import adapter_instance, get_adapter_class
from app.services.common.approval_center_service import (
    ApprovalCenterService,
    ApprovalConflictError,
)
from app.services.common.approval_chain import validate_nodes
from app.services.common.approval_metrics import (
    approved_stats,
    enrich_pending_item,
    parse_dt,
    pending_stats,
    submitted_stats,
)
from app.services.common.approval_sql import (
    FIELD_LABELS,
    OPTIONAL_MAPPINGS,
    REQUIRED_MAPPINGS,
    preview_readonly_sql,
    render_deep_link,
    validate_field_mapping,
    validate_readonly_sql,
    validate_sql_and_mapping,
    validate_writeback_config,
)
# builtin Adapter 注册：import 即注册（审批配置 / 中心详情 / 草稿聚合都依赖）
from app.services.quality import supplier_claim_adapter  # noqa: F401
from app.services.material import purchase_requisition_adapter  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter()

# 我已审批 / 我发起的默认时间窗（未显式传日期时限定，避免全历史扫描）
DEFAULT_MY_WINDOW_DAYS = 90
MAX_BATCH_SIZE = 50

# SQL 业务标识：小写字母开头，避免与前端路由 / 数据库对象命名习惯冲突
BIZ_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


def _match_keyword(item: dict, keyword: str) -> bool:
    kw = (keyword or "").strip().lower()
    if not kw:
        return True
    haystack = " ".join(str(item.get(k) or "") for k in ("no", "title", "summary", "applicant", "current_node"))
    return kw in haystack.lower()


def _in_date_range(value, date_from: Optional[date], date_to: Optional[date]) -> bool:
    dt = parse_dt(value)
    if not dt:
        return not (date_from or date_to)
    if date_from and dt.date() < date_from:
        return False
    if date_to and dt.date() > date_to:
        return False
    return True


def _resolve_window(date_from: Optional[date], date_to: Optional[date]) -> tuple[Optional[date], Optional[date]]:
    if date_from or date_to:
        return date_from, date_to
    return date.today() - timedelta(days=DEFAULT_MY_WINDOW_DAYS), None


def _paginate(items: list[dict], page: int, page_size: int) -> list[dict]:
    start = (page - 1) * page_size
    return items[start:start + page_size]


def _sort_key(value):
    """统一排序键：来源可能是 datetime 或 ISO 字符串，混用直接比较会 TypeError。"""
    return parse_dt(value) or datetime.min


def _clean_comment(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_today(value) -> bool:
    dt = parse_dt(value)
    return bool(dt and dt.date() == date.today())


def _clean_bool(value, *, default: bool) -> bool:
    """请求体布尔值容错：字符串 "false" / "0" 不能被 bool() 当成 True。"""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "0", "no", "off")
    return bool(value)


def _clean_version(value) -> Optional[int]:
    """expected_version 来自请求体，非法值应判为参数错误而不是让引擎 int() 抛 500。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1  # 哨兵：不可能与任何真实 version 相等，交由引擎返回乐观锁冲突


def _snapshot_of(inst: dict) -> list:
    raw = inst.get("snapshot_json")
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []


def _render_deep_link(template, inst: dict) -> str:
    return render_deep_link(template, {"id": inst.get("biz_id"), "no": inst.get("biz_no"),
                                       "title": inst.get("title")})


def _instance_to_item(inst: dict, metas: dict[str, dict]) -> dict:
    meta = metas.get(inst["biz_type"]) or {}
    snap = _snapshot_of(inst)
    level = inst.get("current_level") or 1
    node = next((n for n in snap if n.get("seq") == level), None)
    return {
        "biz_type": inst["biz_type"],
        "biz_name": meta.get("biz_name") or inst["biz_type"],
        "mode": meta.get("mode"),
        "id": inst["biz_id"],
        "no": inst.get("biz_no"),
        "title": inst.get("title"),
        "summary": inst.get("summary"),
        "applicant": inst.get("applicant"),
        "submitted_at": inst.get("submitted_at"),
        "current_level": level,
        "current_node": node.get("label") if node else None,
        "timeout_hours": (node or {}).get("timeout_hours"),
        "version": inst.get("version"),
        "status": inst.get("status"),
        "deep_link": _render_deep_link(meta.get("deep_link_template"), inst),
    }


@router.post("/instances", response_model=ResponseModel)
async def submit_approval_instance(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.initiate", "read")),
    db: AsyncSession = Depends(get_db),
):
    """提交审批实例：builtin 与声明式业务共用；声明式业务由中心按取数 SQL 生成摘要。"""
    biz_type = (data.get("biz_type") or "").strip()
    try:
        biz_id = int(data.get("biz_id"))
    except (TypeError, ValueError):
        return ResponseModel(code=1, message="biz_id 必须是数字主键")
    try:
        result = await ApprovalCenterService(db).submit(biz_type, biz_id, current_user["username"])
    except ValueError as exc:
        return ResponseModel(code=1, message=str(exc))
    return ResponseModel(data=result, message="已提交审批")


@router.get("/pending", response_model=ResponseModel)
async def list_pending_approvals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    biz_type: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    overdue_only: bool = Query(False),
    wait_level: Optional[str] = Query(None, pattern="^(soon|overdue)$"),
    today_only: bool = Query(False),
    provider_mode: Optional[str] = Query(None, pattern="^(builtin|sql)$"),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    """待我审批 = 我的 active 任务（admin 看全部在途实例）。stats 恒为「全部待办」口径。"""
    svc = ApprovalCenterService(db)
    metas = {m["biz_type"]: m for m in await svc.list_biz_metas()}
    if current_user["role"] == "admin":
        rows = await db.execute(text(
            "SELECT * FROM approval_instance WHERE status = 'pending'"
            " ORDER BY submitted_at DESC NULLS LAST"))
    else:
        rows = await db.execute(text("""
            SELECT i.* FROM approval_instance i
            JOIN approval_task t ON t.instance_id = i.id AND t.status = 'active'
            WHERE i.status = 'pending' AND t.approver = :u
            ORDER BY i.submitted_at DESC NULLS LAST
        """), {"u": current_user["username"]})
    items = []
    for r in rows:
        item = _instance_to_item(dict(r._mapping), metas)
        item["can_act"] = True  # 能看到即有权操作（admin 旁路在引擎侧二次校验）
        items.append(enrich_pending_item(item))
    stats = pending_stats(items)
    allowed = None
    if provider_mode:
        allowed = {bt for bt, m in metas.items() if m["mode"] == provider_mode}
    filtered = [
        it for it in items
        if (not biz_type or it.get("biz_type") == biz_type)
        and (allowed is None or it.get("biz_type") in allowed)
        and _match_keyword(it, keyword)
        and _in_date_range(it.get("submitted_at"), date_from, date_to)
        and (not overdue_only or it.get("wait_level") == "overdue")
        and (not wait_level or it.get("wait_level") == wait_level)
        and (not today_only or _is_today(it.get("submitted_at")))
    ]
    return ResponseModel(data={
        "items": _paginate(filtered, page, page_size), "total": len(filtered),
        "page": page, "page_size": page_size, "stats": stats,
    })


@router.get("/approved", response_model=ResponseModel)
async def list_my_approved(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    biz_type: Optional[str] = Query(None), keyword: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None),
    action: Optional[str] = Query(None, pattern="^(approve|reject)$"),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    """我已审批：我在任务上做出的通过/驳回（默认近 90 天）。"""
    win_from, _ = _resolve_window(date_from, date_to)
    # 只传 date_to 时 _resolve_window 返回 None 起点——回退默认窗，避免 combine(None) 抛错
    win_from = win_from or (date.today() - timedelta(days=DEFAULT_MY_WINDOW_DAYS))
    rows = await db.execute(text("""
        SELECT i.*, t.status AS task_status, t.comment AS my_comment, t.acted_at
        FROM approval_task t JOIN approval_instance i ON i.id = t.instance_id
        WHERE t.approver = :u AND t.status IN ('approved', 'rejected') AND t.acted_at >= :win
        ORDER BY t.acted_at DESC
    """), {"u": current_user["username"], "win": datetime.combine(win_from, dt_time.min)})
    svc = ApprovalCenterService(db)
    metas = {m["biz_type"]: m for m in await svc.list_biz_metas()}
    items = []
    for r in rows:
        d = dict(r._mapping)
        item = _instance_to_item(d, metas)
        item.update({
            "my_action": "approve" if d.get("task_status") == "approved" else "reject",
            "my_comment": d.get("my_comment"), "acted_at": d.get("acted_at"), "can_act": False,
        })
        items.append(item)
    items = [
        it for it in items
        if (not biz_type or it.get("biz_type") == biz_type)
        and _match_keyword(it, keyword)
        and _in_date_range(it.get("acted_at"), date_from, date_to)
        and (not action or it.get("my_action") == action)
    ]
    return ResponseModel(data={"items": _paginate(items, page, page_size), "total": len(items),
                               "page": page, "page_size": page_size, "stats": approved_stats(items)})


@router.get("/submitted", response_model=ResponseModel)
async def list_my_submitted(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    biz_type: Optional[str] = Query(None), keyword: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None),
    status: Optional[str] = Query(None, pattern="^(draft|pending|approved|rejected|recalled)$"),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    """我发起的：我的审批实例（默认近 90 天）+ builtin 业务草稿（未提交、无实例）。"""
    win_from, _ = _resolve_window(date_from, date_to)
    rows = await db.execute(text(
        "SELECT * FROM approval_instance WHERE applicant = :a"
        " ORDER BY submitted_at DESC NULLS LAST"), {"a": current_user["username"]})
    svc = ApprovalCenterService(db)
    metas = {m["biz_type"]: m for m in await svc.list_biz_metas()}
    items = []
    for r in rows:
        item = _instance_to_item(dict(r._mapping), metas)
        item["can_act"] = False
        item["can_recall"] = item.get("status") == "pending"
        items.append(item)
    for bt, meta in metas.items():
        if meta["mode"] != "builtin" or (biz_type and biz_type != bt):
            continue
        adapter = adapter_instance(db, bt)
        if adapter is None:
            continue
        for draft in await adapter.fetch_drafts(db, current_user["username"]):
            draft.setdefault("biz_type", bt)
            draft.setdefault("biz_name", meta["biz_name"])
            draft.setdefault("status", "draft")
            draft.setdefault("can_act", False)
            draft.setdefault("can_recall", False)
            items.append(draft)
    items = [
        it for it in items
        if (not biz_type or it.get("biz_type") == biz_type)
        and _match_keyword(it, keyword)
        # 草稿无 submitted_at（未提交），入窗与排序回退创建时间，保证草稿可在「我发起的」编辑
        and _in_date_range(it.get("submitted_at") or it.get("created_at"), win_from, date_to)
        and (not status or it.get("status") == status)
    ]
    items.sort(key=lambda x: _sort_key(x.get("submitted_at") or x.get("created_at")), reverse=True)
    return ResponseModel(data={"items": _paginate(items, page, page_size), "total": len(items),
                               "page": page, "page_size": page_size, "stats": submitted_stats(items)})


@router.get("/configs", response_model=ResponseModel)
async def list_approval_configs(
    _: dict = Depends(PermissionChecker("approval.config", "read")),
    db: AsyncSession = Depends(get_db),
):
    """审批链列表：已接入的业务流程（builtin Adapter + 表内 SQL 业务，含停用）∪ 其 approval_config 配置行。"""
    rows = await db.execute(text(
        "SELECT biz_type, biz_name, nodes, is_active, updated_by, updated_at FROM approval_config"
    ))
    existing: dict[str, dict] = {}
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("nodes"), str):
            d["nodes"] = json.loads(d.get("nodes") or "[]")
        if isinstance(d.get("updated_at"), datetime):
            d["updated_at"] = d["updated_at"].isoformat()
        existing[d["biz_type"]] = d

    counts = {r[0]: r[1] for r in await db.execute(text(
        "SELECT biz_type, COUNT(*) FROM approval_instance WHERE status = 'pending' GROUP BY biz_type"))}
    items = []
    for meta in await ApprovalCenterService(db).list_biz_metas():
        row = existing.pop(meta["biz_type"], {
            "biz_type": meta["biz_type"], "biz_name": meta["biz_name"],
            "nodes": [], "is_active": True, "updated_by": None, "updated_at": None,
        })
        row["condition_field_options"] = meta["condition_field_options"] or []
        # 列表要按接入方式区分展示（内置 Adapter / SQL 配置），这里直接给出，避免前端再查一次业务清单
        row["mode"] = meta["mode"]
        # 系统视角统计该业务在途待办数，供「在途 N 单沿用旧快照」提示；停用业务不误报为 0
        row["pending_count"] = counts.get(meta["biz_type"], 0) if meta["is_active"] else None
        items.append(row)
    return ResponseModel(data={"items": items})


@router.get("/configs/{biz_type}", response_model=ResponseModel)
async def get_approval_config(
    biz_type: str,
    _: dict = Depends(PermissionChecker("approval.config", "read")),
    db: AsyncSession = Depends(get_db),
):
    meta = await ApprovalCenterService(db).biz_meta(biz_type)
    if not meta:
        return ResponseModel(code=1, message="该业务流程未接入审批中心")
    row = await db.execute(text(
        "SELECT biz_type, biz_name, nodes, is_active, updated_by, updated_at FROM approval_config WHERE biz_type = :bt LIMIT 1"
    ), {"bt": biz_type})
    r = row.fetchone()
    if not r:
        return ResponseModel(data={"biz_type": biz_type, "nodes": [], "is_active": True,
                                   "condition_field_options": meta["condition_field_options"] or []})
    d = dict(r._mapping)
    if isinstance(d.get("nodes"), str):
        d["nodes"] = json.loads(d.get("nodes") or "[]")
    if isinstance(d.get("updated_at"), datetime):
        d["updated_at"] = d["updated_at"].isoformat()
    d["condition_field_options"] = meta["condition_field_options"] or []
    return ResponseModel(data=d)


@router.put("/configs/{biz_type}", response_model=ResponseModel)
async def save_approval_config(
    biz_type: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.config", "update")),
    db: AsyncSession = Depends(get_db),
):
    meta = await ApprovalCenterService(db).biz_meta(biz_type)
    if not meta:
        return ResponseModel(code=1, message="该业务流程未接入审批中心")
    nodes = data.get("nodes", [])
    allowed = [o.get("value") for o in (meta["condition_field_options"] or []) if o.get("value")]
    err = validate_nodes(nodes, allowed_condition_fields=allowed)
    if err:
        return ResponseModel(code=1, message=err)
    biz_name = data.get("biz_name") or meta["biz_name"]
    is_active = _clean_bool(data.get("is_active"), default=True)
    row = await db.execute(text("SELECT id FROM approval_config WHERE biz_type = :bt LIMIT 1"), {"bt": biz_type})
    if row.fetchone():
        await db.execute(text("""
            UPDATE approval_config SET biz_name = :bn, nodes = :nodes, is_active = :ia,
                                       updated_by = :ub, updated_at = NOW()
            WHERE biz_type = :bt
        """), {"bn": biz_name, "nodes": json.dumps(nodes), "ia": is_active,
               "ub": current_user["username"], "bt": biz_type})
    else:
        await db.execute(text("""
            INSERT INTO approval_config (biz_type, biz_name, nodes, is_active, updated_by)
            VALUES (:bt, :bn, :nodes, :ia, :ub)
        """), {"bt": biz_type, "bn": biz_name, "nodes": json.dumps(nodes),
               "ia": is_active, "ub": current_user["username"]})
    return ResponseModel(data={"biz_type": biz_type, "nodes": nodes, "is_active": is_active}, message="保存成功")


@router.get("/businesses", response_model=ResponseModel)
async def list_approval_businesses(
    _: dict = Depends(PermissionChecker("approval.business", "read")),
    db: AsyncSession = Depends(get_db),
):
    """业务接入清单：builtin Adapter + 表内声明式业务（含停用），附在途数与链节点数。

    管理员专用端点：SQL 业务额外返回 sql_text / field_mapping / condition_fields /
    deep_link_template / writeback 供前端向导编辑回填；内置业务这几项为空。
    """
    metas = await ApprovalCenterService(db).list_biz_metas()
    chain_rows = await db.execute(text("SELECT biz_type, nodes FROM approval_config"))
    chains: dict[str, list] = {}
    for r in chain_rows:
        nodes = r[1]
        if isinstance(nodes, str):
            nodes = json.loads(nodes or "[]")
        chains[r[0]] = nodes or []
    counts = {r[0]: r[1] for r in await db.execute(text(
        "SELECT biz_type, COUNT(*) FROM approval_instance WHERE status = 'pending' GROUP BY biz_type"))}
    items = []
    for m in metas:
        is_sql = m["mode"] == "sql"
        items.append({
            "biz_type": m["biz_type"], "biz_name": m["biz_name"], "mode": m["mode"],
            "is_active": m["is_active"], "description": m["description"],
            "pending_count": counts.get(m["biz_type"], 0) if m["is_active"] else None,
            "chain_node_count": len(chains.get(m["biz_type"], [])),
            "has_sql": bool(m["sql_text"]), "updated_by": m["updated_by"], "updated_at": m["updated_at"],
            "sql_text": m["sql_text"] if is_sql else None,
            "field_mapping": (m["field_mapping"] or {}) if is_sql else {},
            "condition_fields": (m["condition_field_options"] or []) if is_sql else [],
            "deep_link_template": m["deep_link_template"] if is_sql else None,
            "writeback": m["writeback"] if is_sql else None,
        })
    return ResponseModel(data={"items": items, "mapping_fields": [
        {"key": k, "label": FIELD_LABELS.get(k, k), "required": k in REQUIRED_MAPPINGS}
        for k in REQUIRED_MAPPINGS + OPTIONAL_MAPPINGS
    ]})


async def _validate_sql_business_payload(
    db: AsyncSession, data: dict, *, for_create: bool, run_sql_check: bool = True,
) -> Optional[str]:
    """校验业务接入请求体；返回错误信息，None 表示通过。

    run_sql_check=True 时会实跑一次取数（LIMIT 5）验证：SQL 能执行、映射列存在、id 行值可取整数。
    """
    if for_create:
        biz_type = (data.get("biz_type") or "").strip()
        if not BIZ_TYPE_RE.match(biz_type):
            return "业务标识需为小写字母开头、仅含小写字母/数字/下划线的 3~64 位字符串"
        if get_adapter_class(biz_type):
            return "该业务标识已被内置业务占用"
    if not (data.get("biz_name") or "").strip():
        return "业务名称不能为空"
    if run_sql_check:
        err = await validate_sql_and_mapping(db, data.get("sql_text"), data.get("field_mapping"))
    else:
        err = validate_readonly_sql(data.get("sql_text")) or validate_field_mapping(data.get("field_mapping"))
    if err:
        return err
    options = data.get("condition_fields") or []
    if not isinstance(options, list) or any(not isinstance(o, dict) or not (o.get("value") or "").strip() for o in options):
        return "条件字段声明格式不正确"
    err = await validate_writeback_config(db, data.get("writeback"))
    if err:
        return err
    return None


@router.post("/businesses", response_model=ResponseModel)
async def create_approval_business(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.business", "update")),
    db: AsyncSession = Depends(get_db),
):
    """注册声明式 SQL 业务：中心每次查询按表内配置聚合，无需重启进程。"""
    # 先查表判断重名，交给下面校验会漏掉表内同名行（内置占用检查只看 Adapter 注册表）
    biz_type = (data.get("biz_type") or "").strip()
    exists = (await db.execute(text("SELECT id FROM approval_business WHERE biz_type = :bt"), {"bt": biz_type})).fetchone()
    if exists:
        return ResponseModel(code=1, message="该业务标识已注册")
    err = await _validate_sql_business_payload(db, data, for_create=True)
    if err:
        return ResponseModel(code=1, message=err)
    try:
        await db.execute(text("""
            INSERT INTO approval_business
                (biz_type, biz_name, mode, sql_text, field_mapping_json, condition_fields_json,
                 deep_link_template, description, is_active, created_by, updated_by, writeback_json)
            VALUES (:bt, :bn, 'sql', :sql, :fm, :cf, :dl, :desc, TRUE, :ub, :ub, :wb)
        """), {"bt": biz_type, "bn": data["biz_name"].strip(), "sql": data["sql_text"],
               "fm": json.dumps(data.get("field_mapping") or {}, ensure_ascii=False),
               "cf": json.dumps(data.get("condition_fields") or [], ensure_ascii=False),
               "dl": (data.get("deep_link_template") or "").strip() or None,
               "desc": (data.get("description") or "").strip() or None, "ub": current_user["username"],
               "wb": json.dumps(data.get("writeback") or {}, ensure_ascii=False)})
    except IntegrityError:
        # 并发注册同名业务：唯一约束兜底，返回业务错误而不是 500
        await db.rollback()
        return ResponseModel(code=1, message="该业务标识已注册")
    return ResponseModel(data={"biz_type": biz_type}, message="已接入，待办工作台将自动聚合该业务")


@router.put("/businesses/{biz_type}", response_model=ResponseModel)
async def update_approval_business(
    biz_type: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.business", "update")),
    db: AsyncSession = Depends(get_db),
):
    """更新声明式 SQL 业务（含启停）；内置业务由代码接入，不可经此修改。"""
    meta = await ApprovalCenterService(db).biz_meta(biz_type)
    if not meta:
        return ResponseModel(code=1, message="该业务未注册")
    if meta["mode"] != "sql":
        return ResponseModel(code=1, message="内置业务由代码接入，不支持在此修改")
    # 只改启停/说明时不重跑取数：否则源表失效的坏业务将无法停用（管理员失去自救手段）
    sql_changed = (data.get("sql_text") or "") != (meta["sql_text"] or "")
    mapping_changed = (data.get("field_mapping") or {}) != (meta["field_mapping"] or {})
    err = await _validate_sql_business_payload(
        db, data, for_create=False, run_sql_check=sql_changed or mapping_changed,
    )
    if err:
        return ResponseModel(code=1, message=err)
    is_active = _clean_bool(data.get("is_active"), default=meta["is_active"])
    await db.execute(text("""
        UPDATE approval_business SET biz_name = :bn, sql_text = :sql, field_mapping_json = :fm,
               condition_fields_json = :cf, deep_link_template = :dl, description = :desc,
               is_active = :ia, updated_by = :ub, updated_at = NOW(), writeback_json = :wb
        WHERE biz_type = :bt
    """), {"bn": data["biz_name"].strip(), "sql": data["sql_text"],
           "fm": json.dumps(data.get("field_mapping") or {}, ensure_ascii=False),
           "cf": json.dumps(data.get("condition_fields") or [], ensure_ascii=False),
           "dl": (data.get("deep_link_template") or "").strip() or None,
           "desc": (data.get("description") or "").strip() or None,
           "ia": is_active, "ub": current_user["username"],
           "wb": json.dumps(data.get("writeback") or {}, ensure_ascii=False), "bt": biz_type})
    return ResponseModel(data={"biz_type": biz_type, "is_active": is_active}, message="保存成功")


@router.post("/businesses/test-sql", response_model=ResponseModel)
async def test_approval_business_sql(
    data: dict = Body(...),
    _: dict = Depends(PermissionChecker("approval.business", "update")),
    db: AsyncSession = Depends(get_db),
):
    """测试取数 SQL：只读校验 + 预览前 5 行（不落库）。"""
    sql_text = data.get("sql_text")
    err = validate_readonly_sql(sql_text)
    if err:
        return ResponseModel(code=1, message=err)
    started = time.perf_counter()
    try:
        result = await preview_readonly_sql(db, sql_text)
    except Exception as exc:
        logger.warning("测试取数失败: %s", exc)
        return ResponseModel(code=1, message=f"SQL 执行失败：{exc}")
    return ResponseModel(data={**result, "elapsed_ms": int((time.perf_counter() - started) * 1000)},
                         message="取数成功")


@router.get("/users", response_model=ResponseModel)
async def list_user_options(
    keyword: Optional[str] = Query(None),
    _: dict = Depends(PermissionChecker("approval.config", "read")),
    db: AsyncSession = Depends(get_db),
):
    """审批链编辑器「指定人员」下拉数据源（审批域自有权限，不依赖用户管理读权限）。"""
    conditions = ["u.is_active = TRUE"]
    params: dict = {"lim": 50}
    if keyword:
        conditions.append("(u.username ILIKE :kw OR COALESCE(u.display_name, u.username) ILIKE :kw)")
        params["kw"] = f"%{keyword}%"
    rows = await db.execute(text(f"""
        SELECT u.id, u.username, COALESCE(u.display_name, u.username) AS display_name, r.role_name
        FROM sys_user u
        LEFT JOIN sys_role r ON r.id = u.role_id
        WHERE {' AND '.join(conditions)}
        ORDER BY u.id
        LIMIT :lim
    """), params)
    return ResponseModel(data={"items": [dict(r._mapping) for r in rows]})


@router.get("/roles", response_model=ResponseModel)
async def list_role_options(
    _: dict = Depends(PermissionChecker("approval.config", "read")),
    db: AsyncSession = Depends(get_db),
):
    """审批链编辑器角色下拉数据源（审批域自有权限，不依赖「角色管理」读权限）。"""
    rows = await db.execute(text("SELECT role_code, role_name FROM sys_role ORDER BY id"))
    return ResponseModel(data={"items": [{"role_code": r[0], "role_name": r[1]} for r in rows]})


async def _run_center_action(biz_type: str, item_id: int, action: str, data: dict,
                             user: dict, db: AsyncSession) -> ResponseModel:
    svc = ApprovalCenterService(db)
    meta = await svc.biz_meta(biz_type)
    if not meta:
        return ResponseModel(code=1, message="该业务流程未接入审批中心")
    payload = data if isinstance(data, dict) else {}
    comment = _clean_comment(payload.get("comment"))
    if action == "reject" and not comment:
        return ResponseModel(code=1, message="驳回必须填写审批意见")
    kwargs = {"operator_role": user["role"], "expected_version": _clean_version(payload.get("expected_version"))}
    handlers = {
        "approve": lambda: svc.approve(biz_type, item_id, user["username"], comment, **kwargs),
        "reject": lambda: svc.reject(biz_type, item_id, user["username"], comment, **kwargs),
        "recall": lambda: svc.recall(biz_type, item_id, user["username"], operator_role=user["role"]),
    }
    try:
        result = await handlers[action]()
    except ApprovalConflictError as exc:
        # 写后冲突：事务里已有孤儿流水，必须整体回滚后再返回业务错误
        await db.rollback()
        return ResponseModel(code=1, message=str(exc) or "数据已被他人更新，请刷新后重试")
    if not result.get("success"):
        return ResponseModel(code=1, message=result.get("message") or "操作失败")
    action_messages = {"approve": "已通过", "reject": "已驳回", "recall": "已撤回，单据已退回可修改状态"}
    return ResponseModel(data=result, message=action_messages.get(action, "操作成功"))


@router.get("/items/{biz_type}/{item_id}", response_model=ResponseModel)
async def get_item_preview(
    biz_type: str, item_id: int,
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    """审批详情页：实例 + 进度（真实流水）+ 业务字段（Adapter 或声明式映射）。"""
    data = await ApprovalCenterService(db).get_detail(
        biz_type, item_id, current_user["username"], current_user["role"])
    if not data:
        return ResponseModel(code=1, message="单据不存在或未提交过审批")
    return ResponseModel(data=data)


@router.post("/items/{biz_type}/{item_id}/approve", response_model=ResponseModel)
async def approve_item(
    biz_type: str,
    item_id: int,
    data: dict = Body(default={}),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    return await _run_center_action(biz_type, item_id, "approve", data, current_user, db)


@router.post("/items/{biz_type}/{item_id}/reject", response_model=ResponseModel)
async def reject_item(
    biz_type: str,
    item_id: int,
    data: dict = Body(default={}),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    return await _run_center_action(biz_type, item_id, "reject", data, current_user, db)


@router.post("/items/{biz_type}/{item_id}/recall", response_model=ResponseModel)
async def recall_item(
    biz_type: str,
    item_id: int,
    data: dict = Body(default={}),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    """撤回我发起的单据（中心服务内校验仅发起人可撤回；审批记录保留留档）。"""
    return await _run_center_action(biz_type, item_id, "recall", data, current_user, db)


@router.post("/batch-approve", response_model=ResponseModel)
async def batch_approve(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    """批量通过：逐条 SAVEPOINT 隔离，失败/不支持的业务逐条报告，不影响其它单据。"""
    requested = data.get("items") or [] if isinstance(data, dict) else []
    if not requested:
        return ResponseModel(code=1, message="请先选择待审批单据")
    if len(requested) > MAX_BATCH_SIZE:
        return ResponseModel(code=1, message=f"单次批量审批最多 {MAX_BATCH_SIZE} 条")
    comment = _clean_comment(data.get("comment"))
    passed: list[dict] = []
    failed: list[dict] = []
    skipped: list[dict] = []
    for it in requested:
        if not isinstance(it, dict):
            failed.append({"biz_type": None, "id": None, "reason": "请求条目格式不正确"})
            continue
        biz_type, item_id = it.get("biz_type"), it.get("id")
        if not biz_type or not await ApprovalCenterService(db).biz_meta(biz_type):
            skipped.append({"biz_type": biz_type, "id": item_id, "reason": "该业务流程未接入审批中心"})
            continue
        try:
            entity_id = int(item_id)
        except (TypeError, ValueError):
            failed.append({"biz_type": biz_type, "id": item_id, "reason": "单据 ID 不正确"})
            continue
        savepoint = await db.begin_nested()
        try:
            result = await ApprovalCenterService(db).approve(
                biz_type, entity_id, current_user["username"], comment,
                operator_role=current_user["role"],
                expected_version=_clean_version(it.get("expected_version")))
        except ApprovalConflictError:
            await savepoint.rollback()
            failed.append({"biz_type": biz_type, "id": item_id, "reason": "数据已被他人更新，请刷新后重试"})
            continue
        except Exception as exc:  # 单条异常不拖垮整批（SAVEPOINT 回滚后外层事务仍可用）
            logger.warning("批量审批异常 biz=%s id=%s: %s", biz_type, item_id, exc)
            await savepoint.rollback()
            failed.append({"biz_type": biz_type, "id": item_id, "reason": "系统异常，请稍后重试"})
            continue
        if result.get("success"):
            await savepoint.commit()
            passed.append({"biz_type": biz_type, "id": item_id, "finished": bool(result.get("finished"))})
        else:
            # 失败路径必须回滚：引擎在乐观锁失败前可能已写入流水，否则会留下「未生效的审批记录」
            await savepoint.rollback()
            failed.append({"biz_type": biz_type, "id": item_id, "reason": result.get("message") or "操作失败"})
    return ResponseModel(data={"passed": passed, "failed": failed, "skipped": skipped})
