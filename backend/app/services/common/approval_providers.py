"""审批中心 - 各业务流程待审批提供者注册（未来新流程在此追加注册即可接入统一列表）。"""

from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.common.approval_engine import resolve_node_approver_user_ids
from app.services.common.approval_registry import (
    ApprovalActionRequest,
    ApprovalPendingProvider,
    register_pending_provider,
)
from app.services.material.purchase_requisition_service import PurchaseRequisitionService
from app.services.quality.supplier_claim_service import SupplierClaimService

CLAIM_REASON_LABELS = {
    "field_customer_claim": "现场/客户投诉",
    "supply_performance": "供应业绩",
}
ACTION_LABELS = {"submit": "提交单据", "approve": "通过", "reject": "驳回", "recall": "撤回单据", "auto_skip": "自动跳过", "revoked": "撤回审批"}
CLAIM_CONDITION_FIELDS = [{"value": "claim_amount", "label": "索赔金额"}]


def _fmt(value) -> str:
    if value is None:
        return "-"
    return str(value)[:16].replace("T", " ")


def _current_node(d: dict) -> Optional[dict]:
    snap = d.get("approval_snapshot") or []
    return next((n for n in snap if n.get("seq") == d.get("approval_level")), None)


def _normalize_claim(d: dict) -> dict:
    node = _current_node(d)
    amount = d.get("claim_amount")
    return {
        "biz_type": "supplier_claim",
        "biz_name": "供应商索赔单",
        "id": d["id"],
        "no": d.get("claim_no"),
        "title": d.get("supplier_name"),
        "summary": f"索赔 {float(amount):,.2f} 元" if amount is not None else "",
        "applicant": d.get("applicant"),
        "submitted_at": d.get("submitted_at"),
        "created_at": d.get("created_at"),
        "current_level": d.get("approval_level"),
        "current_node": node.get("label") if node else None,
        "timeout_hours": (node or {}).get("timeout_hours"),
        "version": d.get("version"),
        "status": d.get("approval_status"),
        "deep_link": f"/quality/supplier-claims/{d['id']}",
        "can_act": True,
    }


def _approver_label(node: dict) -> str:
    approvers = node.get("approvers")
    if approvers:
        names = [a.get("username") or str(a.get("user_id")) for a in approvers]
        return "指定人员：" + "、".join(n for n in names if n)
    return f"角色：{node.get('role')}" if node.get("role") else "-"


def _approval_progress(snapshot: list[dict], logs: list[dict], level: int, current_round: int) -> list[dict]:
    """进度只看当前轮次（驳回重提后上一轮的审批记录不能把当前节点标成已处理）。"""
    node_log = {
        lg.get("approval_level"): lg
        for lg in logs
        if lg.get("action") in ("approve", "reject", "auto_skip") and lg.get("round") == current_round
    }
    progress = []
    for n in snapshot:
        lg = node_log.get(n.get("seq"))
        progress.append({
            "seq": n.get("seq"),
            "label": n.get("label"),
            "approver_label": _approver_label(n),
            "state": "done" if lg else ("current" if n.get("seq") == level else "todo"),
            "acted_at": lg.get("operated_at") if lg else None,
            "comment": lg.get("comment") if lg else None,
        })
    return progress


def _approval_log_items(logs: list[dict]) -> list[dict]:
    return [
        {"time": lg.get("operated_at"), "who": lg.get("approver"),
         "action": lg.get("action"), "action_label": ACTION_LABELS.get(lg.get("action"), lg.get("action")),
         "comment": lg.get("comment")}
        for lg in logs
    ]


def _action_hint(status: str, node_missing: bool, can_act: bool) -> str:
    if status != "pending":
        return "该单据当前状态不可审批"
    if node_missing:
        return "审批链未配置或当前节点缺失，请联系管理员"
    if not can_act:
        return "当前节点由其他审批人处理，您可在此查看详情"
    return ""


async def _fill_approver_user_ids(db: AsyncSession, raws: list[dict], items: list[dict]) -> None:
    """按当前节点补齐审批人用户 ID：指定人员直取，角色节点按角色去重查询。"""
    role_cache: dict[str, list[int]] = {}
    for d, item in zip(raws, items):
        node = _current_node(d) or {}
        if node.get("approvers"):
            item["approver_user_ids"] = await resolve_node_approver_user_ids(db, node)
        else:
            role_code = node.get("role") or ""
            if role_code and role_code not in role_cache:
                role_cache[role_code] = await resolve_node_approver_user_ids(db, node)
            item["approver_user_ids"] = role_cache.get(role_code, [])


def _as_approved_items(raws: list[dict], normalize: Callable[[dict], dict]) -> list[dict]:
    items = []
    for d in raws:
        item = normalize(d)
        item.update({
            "my_action": d.get("my_action"),
            "my_comment": d.get("my_comment"),
            "acted_at": d.get("acted_at"),
            "can_act": False,
        })
        items.append(item)
    return items


def _as_submitted_items(raws: list[dict], normalize: Callable[[dict], dict]) -> list[dict]:
    items = []
    for d in raws:
        item = normalize(d)
        item.update({
            "can_act": False,
            "can_recall": d.get("approval_status") == "pending",
        })
        items.append(item)
    return items


def _claim_fields(d: dict) -> list[dict]:
    return [
        {"label": "申请人", "value": d.get("applicant") or "-"},
        {"label": "提交时间", "value": _fmt(d.get("submitted_at"))},
        {"label": "供应商", "value": d.get("supplier_name") or "-"},
        {"label": "索赔原因", "value": CLAIM_REASON_LABELS.get(d.get("claim_reason"), d.get("claim_reason") or "-")},
        {"label": "索赔金额", "value": f"¥{float(d.get('claim_amount') or 0):,.2f}", "emphasis": True},
        {"label": "索赔日期", "value": _fmt(d.get("claim_date"))},
        {"label": "退回要求", "value": d.get("return_requirement") or "-"},
        {"label": "计算说明", "value": d.get("calc_explanation") or "-"},
        {"label": "备注", "value": d.get("remarks") or "-"},
    ]


async def _fetch_supplier_claim_pending(db, username: str, role: str) -> list[dict]:
    raws = await SupplierClaimService(db).pending_approvals(approver_username=username, approver_role=role)
    items = [_normalize_claim(d) for d in raws]
    await _fill_approver_user_ids(db, raws, items)
    return items


async def _fetch_supplier_claim_approved(db, username: str) -> list[dict]:
    rows = await SupplierClaimService(db).approved_by_me(username)
    return _as_approved_items(rows, _normalize_claim)


async def _fetch_supplier_claim_submitted(db, username: str) -> list[dict]:
    rows = await SupplierClaimService(db).submitted_by_me(username)
    return _as_submitted_items(rows, _normalize_claim)


async def _preview_supplier_claim(db: AsyncSession, username: str, role: str, entity_id: int) -> Optional[dict]:
    service = SupplierClaimService(db)
    d = await service.get_claim(entity_id)
    if not d:
        return None
    snap = d.get("approval_snapshot") or []
    level = d.get("approval_level") or 1
    status = d.get("approval_status")
    node_missing = not any(n.get("seq") == level for n in snap)
    can_act = status == "pending" and service.engine.is_current_node_approver(d, username, role)
    item = _normalize_claim(d)
    item.update({
        "fields": _claim_fields(d),
        "progress": _approval_progress(snap, d.get("approval_logs") or [], level, d.get("approval_round") or 0),
        "logs": _approval_log_items(d.get("approval_logs") or []),
        "can_act": can_act,
        "action_hint": _action_hint(status, node_missing, can_act),
    })
    return item


async def _approve_supplier_claim(db, req: ApprovalActionRequest) -> dict:
    return await SupplierClaimService(db).approve(
        req.entity_id, req.approver, req.comment,
        approver_role=req.approver_role, expected_version=req.expected_version,
    )


async def _reject_supplier_claim(db, req: ApprovalActionRequest) -> dict:
    if not (req.comment or "").strip():
        return {"success": False, "message": "驳回必须填写审批意见"}
    return await SupplierClaimService(db).reject(
        req.entity_id, req.approver, req.comment,
        approver_role=req.approver_role, expected_version=req.expected_version,
    )


async def _recall_supplier_claim(db, req: ApprovalActionRequest) -> dict:
    try:
        ok = await SupplierClaimService(db).recall(req.entity_id, req.approver, caller_role=req.approver_role)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}
    return {"success": bool(ok), "message": None if ok else "单据不存在或当前状态不可撤回"}


register_pending_provider(ApprovalPendingProvider(
    biz_type="supplier_claim",
    biz_name="供应商索赔单",
    fetch=_fetch_supplier_claim_pending,
    fetch_approved=_fetch_supplier_claim_approved,
    fetch_submitted=_fetch_supplier_claim_submitted,
    preview=_preview_supplier_claim,
    approve=_approve_supplier_claim,
    reject=_reject_supplier_claim,
    recall=_recall_supplier_claim,
    condition_field_options=CLAIM_CONDITION_FIELDS,
))


def _normalize_pr(d: dict) -> dict:
    node = _current_node(d)
    summary_parts = []
    if d.get("line_count") is not None:
        summary_parts.append(f"{int(d['line_count'])} 行")
    if d.get("total_amount") is not None:
        summary_parts.append(f"预估 {float(d['total_amount']):,.2f} 元")
    return {
        "biz_type": "purchase_requisition",
        "biz_name": "采购申请单",
        "id": d["id"],
        "no": d.get("req_no"),
        "title": d.get("department") or d.get("applicant"),
        "summary": " · ".join(summary_parts),
        "applicant": d.get("applicant"),
        "submitted_at": d.get("submitted_at"),
        "created_at": d.get("created_at"),
        "current_level": d.get("approval_level"),
        "current_node": node.get("label") if node else None,
        "timeout_hours": (node or {}).get("timeout_hours"),
        "version": d.get("version"),
        "status": d.get("approval_status"),
        "deep_link": f"/purchase-requisitions/{d['id']}",
        "can_act": True,
    }


def _pr_fields(d: dict) -> list[dict]:
    return [
        {"label": "申请单号", "value": d.get("req_no") or "-"},
        {"label": "申请人", "value": d.get("applicant") or "-"},
        {"label": "部门", "value": d.get("department") or "-"},
        {"label": "申请日期", "value": _fmt(d.get("created_at"))},
        {"label": "明细行数", "value": str(d.get("line_count") or 0)},
        {"label": "预估金额", "value": f"¥{float(d.get('total_amount') or 0):,.2f}", "emphasis": True},
    ]


async def _fetch_pr_pending(db, username: str, role: str) -> list[dict]:
    raws = await PurchaseRequisitionService().pending_approvals(
        db, approver_username=username, approver_role=role)
    items = [_normalize_pr(d) for d in raws]
    await _fill_approver_user_ids(db, raws, items)
    return items


async def _fetch_pr_approved(db, username: str) -> list[dict]:
    rows = await PurchaseRequisitionService().approved_requisitions(db, username)
    return _as_approved_items(rows, _normalize_pr)


async def _fetch_pr_submitted(db, username: str) -> list[dict]:
    rows = await PurchaseRequisitionService().submitted_requisitions(db, username)
    return _as_submitted_items(rows, _normalize_pr)


async def _preview_pr(db: AsyncSession, username: str, role: str, entity_id: int) -> Optional[dict]:
    service = PurchaseRequisitionService()
    d = await service.get_detail(db, entity_id)
    if not d:
        return None
    snap = d.get("approval_snapshot") or []
    level = d.get("approval_level") or 1
    status = d.get("approval_status")
    node_missing = not any(n.get("seq") == level for n in snap)
    can_act = status == "pending" and service._engine(db).is_current_node_approver(d, username, role)
    item = _normalize_pr(d)
    item.update({
        "fields": _pr_fields(d),
        "progress": _approval_progress(snap, d.get("approval_logs") or [], level, d.get("approval_round") or 0),
        "logs": _approval_log_items(d.get("approval_logs") or []),
        "can_act": can_act,
        "action_hint": _action_hint(status, node_missing, can_act),
    })
    return item


async def _approve_pr(db, req: ApprovalActionRequest) -> dict:
    return await PurchaseRequisitionService().approve(db, req)


async def _reject_pr(db, req: ApprovalActionRequest) -> dict:
    if not (req.comment or "").strip():
        return {"success": False, "message": "驳回必须填写审批意见"}
    return await PurchaseRequisitionService().reject(db, req)


async def _recall_pr(db, req: ApprovalActionRequest) -> dict:
    return await PurchaseRequisitionService().recall(db, req)


register_pending_provider(ApprovalPendingProvider(
    biz_type="purchase_requisition",
    biz_name="采购申请单",
    fetch=_fetch_pr_pending,
    fetch_approved=_fetch_pr_approved,
    fetch_submitted=_fetch_pr_submitted,
    preview=_preview_pr,
    approve=_approve_pr,
    reject=_reject_pr,
    recall=_recall_pr,
))
