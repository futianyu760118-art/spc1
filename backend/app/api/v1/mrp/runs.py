"""MRP 批次：触发 / 列表 / 详情 / 日桶。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.basicdata.material import Material
from app.models.mrp.bucket import MrpBucket
from app.models.mrp.run import MrpRun
from app.schemas.common import PageResult, ResponseModel
from app.schemas.mrp.schemas import BucketOut, RunOut, RunTriggerOut, RunTriggerRequest
from app.services.mrp.engine import mrp_engine

runs_router = APIRouter()


@runs_router.post("/runs", response_model=ResponseModel[RunTriggerOut])
async def trigger_run(
    payload: RunTriggerRequest,
    current_user: dict = Depends(PermissionChecker("materials.mrp", "run")),
):
    try:
        run = await mrp_engine.create_run_and_launch(
            "manual", current_user.get("username"), payload.model_dump()
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ResponseModel(data=RunTriggerOut(run_id=run.id, run_no=run.run_no, status=run.status))


@runs_router.get("/runs", response_model=ResponseModel[PageResult[RunOut]])
async def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(MrpRun))).scalar() or 0
    rows = (
        await db.execute(
            select(MrpRun).order_by(MrpRun.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return ResponseModel(
        data=PageResult(
            total=int(total),
            page=page,
            page_size=page_size,
            items=[RunOut.model_validate(r) for r in rows],
        )
    )


@runs_router.get("/runs/{run_id}", response_model=ResponseModel[RunOut])
async def get_run(
    run_id: int,
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    run = (await db.execute(select(MrpRun).where(MrpRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    return ResponseModel(data=RunOut.model_validate(run))


@runs_router.get("/runs/{run_id}/buckets", response_model=ResponseModel[list[BucketOut]])
async def list_buckets(
    run_id: int,
    material_id: Optional[int] = Query(None),
    material_code: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    if material_id is None:
        if not material_code:
            raise HTTPException(status_code=422, detail="material_id 或 material_code 必填")
        material_id = (
            await db.execute(
                select(Material.erp_material_id).where(Material.material_code == material_code).limit(1)
            )
        ).scalar_one_or_none()
        if material_id is None:
            raise HTTPException(status_code=404, detail="物料不存在")
    rows = (
        await db.execute(
            select(MrpBucket)
            .where(MrpBucket.run_id == run_id, MrpBucket.material_id == int(material_id))
            .order_by(MrpBucket.bucket_date)
        )
    ).scalars().all()
    return ResponseModel(data=[BucketOut.model_validate(r) for r in rows])
