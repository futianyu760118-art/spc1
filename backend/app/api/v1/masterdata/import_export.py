from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.masterdata.import_service import ImportService
from app.services.masterdata.export_service import ExportService

router = APIRouter()


@router.post("/orders", response_model=ResponseModel[dict])
async def import_orders(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("orders.list", "import")),
    db: AsyncSession = Depends(get_db),
):
    service = ImportService(db, operator=current_user["username"])
    result = await service.import_orders(file)
    return ResponseModel(data=result)


@router.post("/materials", response_model=ResponseModel[dict])
async def import_materials(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "import")),
    db: AsyncSession = Depends(get_db),
):
    service = ImportService(db, operator=current_user["username"])
    result = await service.import_materials(file)
    return ResponseModel(data=result)


@router.post("/purchase-orders", response_model=ResponseModel[dict])
async def import_purchase_orders(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "import")),
    db: AsyncSession = Depends(get_db),
):
    service = ImportService(db, operator=current_user["username"])
    result = await service.import_purchase_orders(file)
    return ResponseModel(data=result)


@router.get("/weekly-report")
async def export_weekly_report(
    current_user: dict = Depends(PermissionChecker("exceptions.pool", "read")),
    db: AsyncSession = Depends(get_db),
):
    service = ExportService(db)
    output = await service.generate_weekly_report()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=weekly_report.xlsx"},
    )


@router.get("/issues")
async def export_issues(
    current_user: dict = Depends(PermissionChecker("exceptions.pool", "read")),
    db: AsyncSession = Depends(get_db),
):
    service = ExportService(db)
    output = await service.export_issues()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=issues.xlsx"},
    )
