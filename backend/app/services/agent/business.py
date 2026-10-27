"""业务对象解析：订单 / 物料缺料 / 品质异常，带数据范围可见性校验。"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exception.quality_issue import QualityIssue
from app.models.material.kitting import KittingShortage
from app.models.order.sale_order import SaleOrder
from app.services.agent.errors import AgentError
from app.services.agent.scope import ScopeContext

SUPPORTED_BIZ_TYPES = ("order", "material_shortage", "quality_issue")


class BusinessObjectError(AgentError):
    pass


async def resolve_business_object(
    db: AsyncSession,
    scope: ScopeContext,
    biz_type: str,
    identifier: str,
    context: Optional[dict] = None,
) -> dict:
    """解析业务对象并校验当前范围；解析不到按 fail-closed 拒绝。"""
    biz_type = (biz_type or "").strip()
    identifier = str(identifier or "").strip()
    if biz_type not in SUPPORTED_BIZ_TYPES:
        raise BusinessObjectError(f"不支持的业务对象类型：{biz_type}")
    if not identifier:
        raise BusinessObjectError("业务对象编号不能为空")

    if biz_type == "order":
        return await _resolve_order(db, scope, identifier)
    if biz_type == "quality_issue":
        return await _resolve_quality_issue(db, scope, identifier)
    return await _resolve_material_shortage(db, scope, identifier, context or {})


async def _resolve_order(db: AsyncSession, scope: ScopeContext, identifier: str) -> dict:
    conditions = [SaleOrder.order_no == identifier, scope.order_condition()]
    if identifier.isdigit():
        conditions = [
            (SaleOrder.order_no == identifier) | (SaleOrder.id == int(identifier)),
            scope.order_condition(),
        ]
    row = (await db.execute(
        select(SaleOrder).where(*conditions).order_by(SaleOrder.id.asc()).limit(1)
    )).scalars().first()
    if not row:
        raise BusinessObjectError(
            "订单不存在或不在你的数据范围内，无法派发该业务任务；可先由管理员调整数据范围或改用通用待办",
            403,
        )
    title = f"订单 {row.order_no}"
    if row.customer:
        title += f" · {row.customer}"
    return {
        "biz_type": "order",
        "biz_id": str(row.id),
        "biz_no": row.order_no,
        "biz_title": title[:256],
        "biz_url": f"/orders/{row.order_no}",
        "biz_context": {
            "order_no": row.order_no,
            "customer": row.customer,
            "product_code": row.product_code,
            "product_name": row.product_name,
            "order_qty": float(row.order_qty) if row.order_qty is not None else None,
            "promised_date": row.promised_date.isoformat() if row.promised_date else None,
            "owner": row.owner,
            "department": row.department,
            "risk_level": row.risk_level,
        },
    }


async def _resolve_quality_issue(db: AsyncSession, scope: ScopeContext, identifier: str) -> dict:
    conditions = [QualityIssue.is_deleted == False, scope.quality_condition()]  # noqa: E712
    if identifier.isdigit():
        conditions.append((QualityIssue.issue_no == identifier) | (QualityIssue.id == int(identifier)))
    else:
        conditions.append(QualityIssue.issue_no == identifier)
    row = (await db.execute(
        select(QualityIssue).where(*conditions).order_by(QualityIssue.id.desc()).limit(1)
    )).scalars().first()
    if not row:
        raise BusinessObjectError(
            "品质异常不存在或不在你的数据范围内，无法派发该业务任务",
            403,
        )
    return {
        "biz_type": "quality_issue",
        "biz_id": str(row.id),
        "biz_no": row.issue_no,
        "biz_title": f"品质异常 {row.issue_no}"[:256],
        "biz_url": f"/quality-issues?keyword={row.issue_no}",
        "biz_context": {
            "issue_no": row.issue_no,
            "order_no": row.order_no,
            "product_code": row.product_code,
            "product_name": row.product_name,
            "status": row.status,
            "defect_type": row.defect_type,
            "responsible_person": row.responsible_person,
            "responsible_dept": row.responsible_dept,
        },
    }


async def _resolve_material_shortage(
    db: AsyncSession,
    scope: ScopeContext,
    identifier: str,
    context: dict,
) -> dict:
    conditions = [
        KittingShortage.is_deleted == 0,
        KittingShortage.demand_no.in_(scope.visible_order_no_select()),
    ]
    order_no = str(context.get("order_no") or "").strip()
    if order_no:
        conditions.append(KittingShortage.demand_no == order_no)
    if identifier.isdigit():
        conditions.append(KittingShortage.id == int(identifier))
    else:
        conditions.append(KittingShortage.material_code == identifier)
    row = (await db.execute(
        select(KittingShortage).where(*conditions).order_by(KittingShortage.id.desc()).limit(1)
    )).scalars().first()
    if not row:
        raise BusinessObjectError(
            "缺料记录不存在或不在你的数据范围内，无法派发该业务任务",
            403,
        )
    return {
        "biz_type": "material_shortage",
        "biz_id": str(row.id),
        "biz_no": row.material_code,
        "biz_title": f"缺料 {row.material_code} · 订单 {row.demand_no}"[:256],
        "biz_url": f"/orders/{row.demand_no}",
        "biz_context": {
            "id": row.id,
            "order_no": row.demand_no,
            "line_no": row.demand_line_no,
            "material_code": row.material_code,
            "material_name": row.material_name,
            "required_qty": float(row.required_qty) if row.required_qty is not None else None,
            "available_qty": float(row.available_qty) if row.available_qty is not None else None,
            "shortage_qty": float(row.shortage_qty) if row.shortage_qty is not None else None,
            "required_date": row.required_date.isoformat() if row.required_date else None,
            "shortage_reason": row.shortage_reason,
            "owner": row.owner,
        },
    }
