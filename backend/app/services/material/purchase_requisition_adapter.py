"""采购申请单 - 审批中心代码接入 Adapter。"""

import json

from sqlalchemy import text

from app.services.common.approval_adapters import ApprovalBizAdapter, approval_adapter

# 审批状态 → 业务自身 status 列的映射（purchase_requisition.status）
OWN_STATUS = {"pending": "approving", "approved": "approved",
              "rejected": "rejected", "recalled": "draft"}

# 主表无 total_amount 列，金额恒为明细行 数量×单价 的合计
_AMOUNT_EXPR = ("COALESCE((SELECT SUM(l.req_qty * l.unit_price) FROM purchase_requisition_line l"
                " WHERE l.req_id = p.id), 0)")


@approval_adapter
class PurchaseRequisitionAdapter(ApprovalBizAdapter):
    biz_type = "purchase_requisition"
    biz_name = "采购申请单"
    deep_link_template = "/purchase-requisitions/{id}"

    async def submit_payload(self, db, entity_id: int) -> dict:
        row = (await db.execute(text(
            f"SELECT p.req_no, p.applicant, {_AMOUNT_EXPR} AS total_amount"
            " FROM purchase_requisition p WHERE p.id = :i"),
            {"i": entity_id})).fetchone()
        if not row:
            raise ValueError("采购申请单不存在")
        return {"no": row[0], "title": f"采购申请单 {row[0]}",
                "summary": f"申请金额 {float(row[2] or 0):,.2f} 元",
                "applicant": row[1], "amount": row[2], "extra": {}}

    async def fetch_detail(self, db, entity_id: int) -> dict:
        row = (await db.execute(text(
            f"SELECT p.req_no, p.applicant, p.department, p.remark, {_AMOUNT_EXPR} AS total_amount"
            " FROM purchase_requisition p WHERE p.id = :i"),
            {"i": entity_id})).fetchone()
        if not row:
            return {"fields": [], "attachments": []}
        d = dict(row._mapping)
        return {"fields": [
            {"label": "申请单号", "value": d.get("req_no") or "-"},
            {"label": "申请人", "value": d.get("applicant") or "-"},
            {"label": "申请部门", "value": d.get("department") or "-"},
            {"label": "申请金额", "value": f"{float(d.get('total_amount') or 0):,.2f} 元", "emphasis": True},
            {"label": "备注", "value": d.get("remark") or "-"},
        ], "attachments": []}

    async def on_transition(self, db, entity_id: int, state: dict) -> None:
        await db.execute(text("""
            UPDATE purchase_requisition SET status = :own, approval_status = :st, approval_level = :lv,
                approval_snapshot = :snap, submitted_at = :sa, approved_by = :ab,
                approved_at = :at, version = :v
            WHERE id = :id
        """), {"own": OWN_STATUS.get(state["status"], "draft"), "st": state["status"],
               "lv": state["level"], "snap": json.dumps(state["snapshot"], ensure_ascii=False),
               "sa": state["submitted_at"], "ab": state["approved_by"], "at": state["approved_at"],
               "v": state["version"], "id": entity_id})

    async def fetch_drafts(self, db, username: str) -> list[dict]:
        rows = await db.execute(text(
            "SELECT id, req_no, applicant, created_at FROM purchase_requisition"
            " WHERE applicant = :u AND status IN ('draft', 'rejected') AND submitted_at IS NULL"
            " ORDER BY id DESC"), {"u": username})
        return [{"id": r[0], "no": r[1], "title": f"采购申请单 {r[1]}", "applicant": r[2],
                 "created_at": r[3], "summary": "",
                 "deep_link": f"/purchase-requisitions/{r[0]}"} for r in rows]
