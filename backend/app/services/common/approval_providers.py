"""审批中心 - 各业务流程待审批提供者注册（未来新流程在此追加注册即可接入统一列表）。"""

from app.services.common.approval_registry import ApprovalPendingProvider, register_pending_provider
from app.services.quality.supplier_claim_service import SupplierClaimService


async def _fetch_supplier_claim_pending(db, username: str, role: str) -> list[dict]:
    items = await SupplierClaimService(db).pending_approvals(approver_username=username, approver_role=role)
    result = []
    for d in items:
        snap = d.get("approval_snapshot") or []
        node = next((n for n in snap if n.get("seq") == d.get("approval_level")), None)
        amount = d.get("claim_amount")
        result.append({
            "biz_type": "supplier_claim",
            "biz_name": "供应商索赔单",
            "id": d["id"],
            "no": d.get("claim_no"),
            "title": d.get("supplier_name"),
            "summary": f"索赔 {amount:,.2f} 元" if amount is not None else "",
            "applicant": d.get("applicant"),
            "submitted_at": d.get("submitted_at"),
            "current_level": d.get("approval_level"),
            "current_node": node.get("label") if node else None,
            "deep_link": f"/quality/supplier-claims/{d['id']}",
        })
    return result


register_pending_provider(ApprovalPendingProvider(
    biz_type="supplier_claim",
    biz_name="供应商索赔单",
    fetch=_fetch_supplier_claim_pending,
))
