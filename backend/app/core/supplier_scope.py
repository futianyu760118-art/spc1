from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.supplier import Supplier


def is_supplier_user(current_user: dict) -> bool:
    return current_user.get("role") == "supplier"


async def get_supplier_name_scope(
    current_user: dict,
    db: AsyncSession,
) -> Optional[str]:
    """Return the bound supplier name for supplier users; internal users are unrestricted."""
    if not is_supplier_user(current_user):
        return None

    supplier_name = current_user.get("supplier_name") or ""
    if not supplier_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="\u4f9b\u5e94\u5546\u8d26\u53f7\u672a\u7ed1\u5b9a\u4f9b\u5e94\u5546",
        )

    result = await db.execute(
        select(Supplier.id).where(
            Supplier.supplier_name == supplier_name,
            Supplier.status == 1,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="\u7ed1\u5b9a\u4f9b\u5e94\u5546\u4e0d\u5b58\u5728\u6216\u5df2\u505c\u7528",
        )
    return supplier_name
