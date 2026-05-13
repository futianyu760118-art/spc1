"""审计日志辅助函数"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.masterdata.audit_log import AuditLog


async def log_audit(
    db: AsyncSession,
    table_name: str,
    record_id: int,
    action: str,
    field_name: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    operator: str = "system",
    old_obj=None,
    update_data: dict | None = None,
):
    """写入审计日志（flush 但不 commit，由调用方统一 commit）

    当 action="update" 且提供 old_obj + update_data 时，自动逐字段比较并生成日志，
    跳过值未实际变更的字段。否则按原逻辑写单条日志。
    """
    if action == "update" and old_obj is not None and update_data:
        for field, new_val in update_data.items():
            old_val = getattr(old_obj, field, None)
            if old_val == new_val:
                continue
            audit = AuditLog(
                table_name=table_name,
                record_id=record_id,
                action=action,
                field_name=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                operator=operator,
            )
            db.add(audit)
        await db.flush()
    else:
        audit = AuditLog(
            table_name=table_name,
            record_id=record_id,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            operator=operator,
        )
        db.add(audit)
        await db.flush()
