"""物料齐套中心 — 齐套分析 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.schemas.material.schemas import (
    KitAnalysisItem,
    KitAnalysisMaterialItem,
    OrderProductKitBreakdownOut,
)
from app.services.material.kit_analysis_service import (
    get_kit_analysis,
    get_order_materials,
    get_order_product_breakdown,
)

router = APIRouter()


@router.get("", response_model=ResponseModel[dict])
async def kit_analysis(
    order_no: Optional[str] = Query(None),
    order_type: Optional[str] = Query(None, description="订单类型，多选逗号分隔：big（大单，HJ开头）, sample（样品单，HJY开头）"),
    risk_level: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    only_pending_shipment: bool = Query(False, description="仅显示发货未完成的订单"),
    promised_date_start: Optional[str] = Query(None, description="合同交期开始日期"),
    promised_date_end: Optional[str] = Query(None, description="合同交期结束日期"),
    current_user: dict = Depends(PermissionChecker("materials.kit_analysis", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await get_kit_analysis(db, order_no=order_no, order_type=order_type, risk_level=risk_level, sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size, only_pending_shipment=only_pending_shipment, promised_date_start=promised_date_start, promised_date_end=promised_date_end)
    return ResponseModel(data=result)


@router.get("/{order_no}/materials", response_model=ResponseModel[list[KitAnalysisMaterialItem]])
async def order_materials(
    order_no: str,
    material_code: Optional[str] = Query(None, description="物料代码筛选"),
    material_name: Optional[str] = Query(None, description="物料名称筛选"),
    material_property: Optional[str] = Query(None, description="物料属性筛选"),
    material_type: Optional[str] = Query(None, description="物料类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    supplier: Optional[str] = Query(None, description="供应商筛选"),
    po_qty_min: Optional[float] = Query(None, description="下单数量最小值"),
    po_qty_max: Optional[float] = Query(None, description="下单数量最大值"),
    received_qty_min: Optional[float] = Query(None, description="收料量最小值"),
    received_qty_max: Optional[float] = Query(None, description="收料量最大值"),
    eta_start: Optional[str] = Query(None, description="ETA开始日期"),
    eta_end: Optional[str] = Query(None, description="ETA结束日期"),
    actual_arrival_date_start: Optional[str] = Query(None, description="实际到料开始日期"),
    actual_arrival_date_end: Optional[str] = Query(None, description="实际到料结束日期"),
    inspection_date_start: Optional[str] = Query(None, description="检验开始日期"),
    inspection_date_end: Optional[str] = Query(None, description="检验结束日期"),
    is_stagnant: Optional[bool] = Query(None, description="是否呆滞"),
    bill_type: Optional[str] = Query(None, description="计划订单单据类型筛选，多值逗号分隔，如 11010,11011,11012"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.kit_analysis", "read")),
    db: AsyncSession = Depends(get_db),
):
    items = await get_order_materials(
        db,
        order_no=order_no,
        material_code_filter=material_code,
        material_name_filter=material_name,
        material_property_filter=material_property,
        material_type_filter=material_type,
        status_filter=status,
        supplier_filter=supplier,
        po_qty_min=po_qty_min,
        po_qty_max=po_qty_max,
        received_qty_min=received_qty_min,
        received_qty_max=received_qty_max,
        eta_start=eta_start,
        eta_end=eta_end,
        actual_arrival_date_start=actual_arrival_date_start,
        actual_arrival_date_end=actual_arrival_date_end,
        inspection_date_start=inspection_date_start,
        inspection_date_end=inspection_date_end,
        is_stagnant=is_stagnant,
        bill_type_filter=bill_type,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ResponseModel(data=items)


@router.get("/{order_no}/product-breakdown", response_model=ResponseModel[OrderProductKitBreakdownOut])
async def order_product_breakdown(
    order_no: str,
    current_user: dict = Depends(PermissionChecker("materials.kit_analysis", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await get_order_product_breakdown(db, order_no=order_no)
    return ResponseModel(data=result)
