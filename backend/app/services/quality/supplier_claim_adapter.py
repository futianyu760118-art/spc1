"""供应商索赔单 - 审批中心代码接入 Adapter。"""

import json

from sqlalchemy import text

from app.services.common.approval_adapters import ApprovalBizAdapter, approval_adapter


def _fmt(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M") if hasattr(v, "strftime") else (v or "-")


@approval_adapter
class SupplierClaimAdapter(ApprovalBizAdapter):
    biz_type = "supplier_claim"
    biz_name = "供应商索赔单"
    deep_link_template = "/quality/supplier-claims/{id}"
    condition_field_options = [{"value": "claim_amount", "label": "索赔金额"}]

    async def submit_payload(self, db, entity_id: int) -> dict:
        row = (await db.execute(text(
            "SELECT claim_no, supplier_name, applicant, claim_amount FROM supplier_claim WHERE id = :i"),
            {"i": entity_id})).fetchone()
        if not row:
            raise ValueError("索赔单不存在")
        return {"no": row[0], "title": row[1], "summary": f"索赔 {float(row[3] or 0):,.2f} 元",
                "applicant": row[2], "amount": row[3], "extra": {"claim_amount": row[3]}}

    async def fetch_detail(self, db, entity_id: int) -> dict:
        row = (await db.execute(text(
            "SELECT applicant, submitted_at, supplier_name, claim_amount, claim_reason, attachments"
            " FROM supplier_claim WHERE id = :i"), {"i": entity_id})).fetchone()
        if not row:
            return {"fields": [], "attachments": []}
        d = dict(row._mapping)
        fields = [
            {"label": "申请人", "value": d.get("applicant") or "-"},
            {"label": "提交时间", "value": _fmt(d.get("submitted_at"))},
            {"label": "供应商", "value": d.get("supplier_name") or "-"},
            {"label": "索赔金额", "value": f"{float(d.get('claim_amount') or 0):,.2f} 元", "emphasis": True},
            {"label": "索赔原因", "value": d.get("claim_reason") or "-"},
        ]
        try:
            attachments = json.loads(d.get("attachments") or "[]")
        except (TypeError, ValueError):
            attachments = []
        return {"fields": fields, "attachments": attachments}

    async def on_transition(self, db, entity_id: int, state: dict) -> None:
        await db.execute(text("""
            UPDATE supplier_claim SET approval_status = :st, approval_level = :lv,
                approval_snapshot = :snap, submitted_at = :sa, approved_by = :ab,
                approved_at = :at, version = :v
            WHERE id = :id
        """), {"st": state["status"], "lv": state["level"],
               "snap": json.dumps(state["snapshot"], ensure_ascii=False),
               "sa": state["submitted_at"], "ab": state["approved_by"],
               "at": state["approved_at"], "v": state["version"], "id": entity_id})

    async def fetch_drafts(self, db, username: str) -> list[dict]:
        rows = await db.execute(text(
            "SELECT id, claim_no, supplier_name, applicant, created_at FROM supplier_claim"
            " WHERE applicant = :u AND approval_status = 'draft' ORDER BY id DESC"), {"u": username})
        return [{"id": r[0], "no": r[1], "title": r[2], "applicant": r[3],
                 "created_at": r[4], "summary": "",
                 "deep_link": f"/quality/supplier-claims/{r[0]}"} for r in rows]
