"""审计日志 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.masterdata.audit_log import AuditLog
from app.schemas.common import ResponseModel

router = APIRouter()


@router.get("/logs", response_model=ResponseModel[dict])
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default="", description="搜索操作人/表名/字段"),
    current_user: dict = Depends(PermissionChecker("audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取审计日志列表"""
    query = select(AuditLog)

    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            or_(
                AuditLog.operator.ilike(like),
                AuditLog.table_name.ilike(like),
                AuditLog.field_name.ilike(like),
            )
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(AuditLog.operated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    items = [
        {
            "id": log.id,
            "table_name": log.table_name,
            "record_id": log.record_id,
            "action": log.action,
            "field_name": log.field_name,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "operator": log.operator,
            "operated_at": log.operated_at.strftime("%Y-%m-%d %H:%M:%S") if log.operated_at else None,
        }
        for log in logs
    ]

    return ResponseModel(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })
