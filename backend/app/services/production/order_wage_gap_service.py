"""订单工价缺口统计 + 每日企业微信提醒。

- compute_wage_gap_stats: 复用订单工价查询的匹配口径（BOM 精确/样品去前缀/无产品兜底），
  统计"只含装配一线/精益车间任务单"的活跃未关闭订单行中的工价缺口。
- send_daily_wage_reminder: 统计缺口 -> 建免登分享链接 -> 企微 textcard 推送。
"""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.basicdata.share_link import ShareLink
from app.models.basicdata.user import SysUser
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.production.production_task_order import ProductionTaskOrder
from app.models.production.product_process_capacity import (
    ProductProcessCapacity,
    parse_capacity_metadata,
)
from app.services.basicdata.wecom.client import get_wecom_client

logger = logging.getLogger(__name__)

# 样品单 BOM 前缀: 匹配工价时先去掉前缀再匹配量产 BOM
BOM_SAMPLE_PREFIXES = ("Y-", "P-")
# 订单行级关联的任务单车间: 成品车间, 物料代码与订单行产品一致
TASK_LINE_WORKSHOPS = ["装配一线", "精益车间"]
# 分享链接默认有效期
SHARE_EXPIRES_DAYS = 90
WAGE_LOOKUP_PATH = "/order-wage-lookup"


def bom_candidates(bom: str | None) -> list[str]:
    """工价匹配候选: 样品单 BOM(Y-/P-开头)去掉前缀优先, 原始编码兜底。"""
    raw = (bom or "").strip()
    if not raw:
        return []
    for prefix in BOM_SAMPLE_PREFIXES:
        if raw.startswith(prefix):
            stripped = raw[len(prefix):].strip()
            if stripped and stripped != raw:
                return [stripped, raw]
            break
    return [raw]


def dedupe_capacities(records: list[ProductProcessCapacity]) -> list[ProductProcessCapacity]:
    """按 oa_detail_id 去重, 保留 last_sync_time 最新(次选 id 最大)的一条。"""
    best: dict[str, ProductProcessCapacity] = {}
    for rec in records:
        key = rec.oa_detail_id or f"__row_{rec.id}"
        cur = best.get(key)
        if cur is None:
            best[key] = rec
            continue
        cur_time = cur.last_sync_time or cur.created_at
        rec_time = rec.last_sync_time or rec.created_at
        if (rec_time, rec.id) > (cur_time, cur.id):
            best[key] = rec
    return list(best.values())


def match_wage(
    line_bom: str | None,
    by_bom: dict[str, list[ProductProcessCapacity]],
) -> tuple[str | None, list[ProductProcessCapacity]]:
    """仅 BOM 匹配: 样品BOM去前缀优先, 原始编码兜底, 不做产品兜底。"""
    raw = (line_bom or "").strip()
    for candidate in bom_candidates(line_bom):
        if candidate in by_bom:
            match_type = "bom" if candidate == raw else "bom_stripped"
            return match_type, by_bom[candidate]
    return None, []


def _has_valid_wage(caps: list[ProductProcessCapacity]) -> bool:
    for cap in caps:
        try:
            if float(parse_capacity_metadata(cap.remark).get("gjje") or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


async def compute_wage_gap_stats(db: AsyncSession) -> dict:
    """统计活跃未关闭、且有装配/精益任务单的订单行工价缺口。"""
    rows = (
        await db.execute(
            select(SaleOrderLine, SaleOrder)
            .join(SaleOrder, SaleOrderLine.sale_order_id == SaleOrder.id)
            .where(SaleOrderLine.status != "closed", SaleOrder.is_closed == 0)
        )
    ).all()
    empty = {
        "total_lines": 0, "has_wage": 0, "no_wage": 0,
        "missing_boms": 0, "affected_orders": 0, "checked_at": datetime.now().isoformat(),
    }
    if not rows:
        return empty

    involved_boms: set[str] = set()
    for line, _order in rows:
        involved_boms.update(bom_candidates(line.bom_no))
    by_bom: dict[str, list[ProductProcessCapacity]] = {}
    if involved_boms:
        cap_rows = (
            await db.execute(
                select(ProductProcessCapacity).where(
                    ProductProcessCapacity.is_active == True,  # noqa: E712
                    ProductProcessCapacity.bom_code.in_(list(involved_boms)),
                )
            )
        ).scalars().all()
        for cap in dedupe_capacities(list(cap_rows)):
            if cap.bom_code and cap.bom_code in involved_boms:
                by_bom.setdefault(cap.bom_code, []).append(cap)

    erp_ids = list({order.erp_id for _line, order in rows if order.erp_id})
    task_keys: set[tuple] = set()
    if erp_ids:
        task_rows = (
            await db.execute(
                select(ProductionTaskOrder.sale_order_id, ProductionTaskOrder.material_code).where(
                    ProductionTaskOrder.sale_order_id.in_(erp_ids),
                    ProductionTaskOrder.workshop.in_(TASK_LINE_WORKSHOPS),
                )
            )
        ).all()
        for sid, material in task_rows:
            task_keys.add((sid, (material or "").strip()))

    total = 0
    no_wage = 0
    missing_boms: set[str] = set()
    affected_orders: set[str] = set()
    for line, order in rows:
        if (order.erp_id, (line.product_code or "").strip()) not in task_keys:
            continue
        total += 1
        _mt, caps = match_wage(line.bom_no, by_bom)
        if _has_valid_wage(caps):
            continue
        no_wage += 1
        if (line.bom_no or "").strip():
            missing_boms.add((line.bom_no or "").strip())
        if line.order_no:
            affected_orders.add(line.order_no)

    return {
        "total_lines": total,
        "has_wage": total - no_wage,
        "no_wage": no_wage,
        "missing_boms": len(missing_boms),
        "affected_orders": len(affected_orders),
        "checked_at": datetime.now().isoformat(),
    }


async def _resolve_recipients(db: AsyncSession, usernames: list[str]) -> list[SysUser]:
    if not usernames:
        return []
    result = await db.execute(
        select(SysUser).where(
            SysUser.username.in_(usernames),
            SysUser.is_active == True,  # noqa: E712
            SysUser.wecom_user_id.isnot(None),
            SysUser.wecom_user_id != "",
        )
    )
    return list(result.scalars().all())


async def _resolve_creator_id(db: AsyncSession) -> int:
    """分享链接创建人(用于页面显示), 优先 admin, 否则取第一个用户。"""
    admin_id = (
        await db.execute(select(SysUser.id).where(SysUser.username == "admin"))
    ).scalar_one_or_none()
    if admin_id:
        return int(admin_id)
    any_id = (await db.execute(select(SysUser.id).order_by(SysUser.id).limit(1))).scalar_one_or_none()
    return int(any_id or 1)


def _frontend_base() -> str:
    settings = get_settings()
    base = settings.frontend_base_url or "http://localhost:3000"
    if base and not base.startswith(("http://", "https://")):
        base = "http://" + base
    return base.rstrip("/")


async def send_daily_wage_reminder(db: AsyncSession, usernames: list[str] | None = None) -> dict:
    """统计工价缺口并推送企微(免登分享链接)。"""
    settings = get_settings()
    names = usernames if usernames is not None else [
        n.strip() for n in (settings.wage_reminder_usernames or "").split(",") if n.strip()
    ]
    stats = await compute_wage_gap_stats(db)
    if stats["no_wage"] <= 0:
        logger.info("[工价提醒] 无缺口, 跳过推送")
        return {"skipped": True, "reason": "no_wage_gap", "stats": stats}

    recipients = await _resolve_recipients(db, names)
    if not recipients:
        logger.warning(f"[工价提醒] 未找到已绑定企微的收件人: {names}")
        return {"skipped": True, "reason": "no_wecom_recipient", "stats": stats}

    # 免登分享链接(不设收件人 = 任何拿到链接的人可打开)
    token = secrets.token_urlsafe(24)
    share = ShareLink(
        token=token,
        target_path=WAGE_LOOKUP_PATH,
        target_params={"wage_status": "no", "only_with_tasks": "true"},
        permissions=["read"],
        reason="订单工价补充提醒(每日自动)",
        created_by=await _resolve_creator_id(db),
        expires_at=datetime.now(timezone.utc) + timedelta(days=SHARE_EXPIRES_DAYS),
    )
    db.add(share)
    await db.flush()

    share_url = f"{_frontend_base()}/share/{token}"
    title = "订单工价补充提醒"
    description = (
        f"{date.today().strftime('%Y-%m-%d')} 有 {stats['no_wage']} 个订单行缺少工价"
        f"（涉及 {stats['missing_boms']} 个 BOM / {stats['affected_orders']} 个订单），请及时补充。"
    )
    textcard = {"title": title, "description": description, "url": share_url, "btntxt": "查看详情"}

    try:
        client = get_wecom_client()
        agent_id = int(client._settings.wecom_agent_id or 0)
        payload = {
            "touser": "|".join([u.wecom_user_id for u in recipients]),
            "msgtype": "textcard",
            "agentid": agent_id,
            "textcard": textcard,
        }
        resp = await client.send_app_message(payload)
        errcode = resp.get("errcode", 0)
        if errcode != 0:
            logger.error(f"[工价提醒] 企微推送失败: errcode={errcode} {resp.get('errmsg','')}")
            return {"success": False, "error": f"errcode={errcode}", "stats": stats, "share_url": share_url}
    except Exception as exc:  # 企微未配置/接口异常不应影响主流程
        logger.exception(f"[工价提醒] 推送异常: {exc}")
        return {"success": False, "error": str(exc), "stats": stats, "share_url": share_url}

    logger.info(
        f"[工价提醒] 推送成功 -> {[u.username for u in recipients]} "
        f"no_wage={stats['no_wage']} boms={stats['missing_boms']}"
    )
    return {
        "success": True,
        "recipients": [u.username for u in recipients],
        "share_url": share_url,
        "stats": stats,
    }
