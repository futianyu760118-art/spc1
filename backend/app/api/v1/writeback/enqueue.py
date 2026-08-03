from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ResponseModel
from app.schemas.writeback import (
    EnqueueWritebackRequest, EnqueueWritebackResponse,
    BatchEnqueueRequest, BatchEnqueueResponse,
)
from app.services.basicdata.writeback_service import enqueue_writeback

router = APIRouter()


@router.post("/enqueue", response_model=ResponseModel[EnqueueWritebackResponse])
async def enqueue(req: EnqueueWritebackRequest, current_user: dict = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    from app.core.config import get_settings
    if not get_settings().writeback_enabled:
        raise HTTPException(status_code=503, detail="回写功能已禁用")
    result = await enqueue_writeback(
        db,
        writeback_type=req.writeback_type,
        business_table=req.business_table,
        business_pk=req.business_pk,
        target_keys=req.target_keys,
        payload=req.payload,
        enqueued_by=f"manual:{current_user.get('username','unknown')}",
        enqueued_by_user=current_user.get("username"),
    )
    await db.commit()
    return ResponseModel(data=EnqueueWritebackResponse(**result))
