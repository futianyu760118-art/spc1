from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ResponseModel, PageResult

router = APIRouter()


@router.get("/log", response_model=ResponseModel[PageResult])
async def list_log(
    writeback_type: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    where = ["1=1"]
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    if writeback_type:
        where.append("writeback_type = :wt"); params["writeback_type"] = writeback_type
    if status:
        where.append("status = :status"); params["status"] = status
    rows = (await db.execute(
        text(f"SELECT * FROM writeback_log WHERE {' AND '.join(where)} "
             f"ORDER BY id DESC LIMIT :limit OFFSET :offset"),
        params,
    )).mappings().all()
    total = (await db.execute(
        text(f"SELECT count(*) FROM writeback_log WHERE {' AND '.join(where)}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )).scalar()
    return ResponseModel(data=PageResult(items=[dict(r) for r in rows], total=total,
                                          page=page, page_size=page_size))
