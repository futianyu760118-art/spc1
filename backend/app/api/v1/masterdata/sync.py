"""
ERP 数据同步 API
提供手动触发同步（异步后台执行）和查询同步任务状态的接口
"""

import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.core.security import PermissionChecker
from app.core.config import get_settings
from app.schemas.common import ResponseModel
from app.services.masterdata.erp_sync_service import ERPSyncService
from app.models.masterdata.sync_sql_config import SyncSqlConfig
from app.models.masterdata.sync_log import SyncLog
from app.models.order.sale_order import SaleOrder

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

VALID_SYNC_TYPES = [
    "orders", "order_details", "materials", "purchase_orders", "customers", "suppliers",
    "materials_masterdata", "skus", "products", "warehouses", "processes",
    "organizations", "employees", "purchase_invoices", "quality_issues", "all",
]


def _parse_interval_seconds(interval: str) -> int:
    """解析同步间隔字符串为秒数"""
    interval_map = {"h": 3600, "d": 86400, "w": 604800}
    interval_str = (interval or "1h").lower()
    try:
        unit = interval_str[-1]
        val = int(interval_str[:-1])
        return val * interval_map.get(unit, 3600)
    except (ValueError, IndexError):
        return 3600


async def _run_sync_background(task_id: str, sync_type: str, sync_params: dict, custom_params: Optional[dict]):
    """后台执行同步任务，更新 SyncLog 和 SyncSqlConfig"""
    async with AsyncSessionLocal() as db:
        try:
            # 1. 标记为 running
            log_result = await db.execute(select(SyncLog).where(SyncLog.task_id == task_id))
            sync_log = log_result.scalar_one()
            sync_log.status = "running"
            sync_log.started_at = datetime.now()
            await db.commit()

            # 2. 执行同步
            service = ERPSyncService(db)
            type_map = {
                "orders": lambda: service.sync_orders(
                    sync_params.get("since"), sync_params.get("order_numbers"), custom_params
                ),
                "order_details": lambda: service.sync_order_details(
                    sync_params.get("since"), custom_params
                ),
                "materials": lambda: service.sync_materials(
                    sync_params.get("since"), sync_params.get("order_numbers"), custom_params
                ),
                "purchase_orders": lambda: service.sync_purchase_orders(
                    sync_params.get("since"), custom_params
                ),
                "customers": lambda: service.sync_customers(sync_params.get("since"), custom_params),
                "suppliers": lambda: service.sync_suppliers(sync_params.get("since"), custom_params),
                "materials_masterdata": lambda: service.sync_materials_masterdata(sync_params.get("since"), custom_params),
                "skus": lambda: service.sync_skus(sync_params.get("since"), custom_params),
                "products": lambda: service.sync_products(sync_params.get("since"), custom_params),
                "warehouses": lambda: service.sync_warehouses(sync_params.get("since"), custom_params),
                "processes": lambda: service.sync_processes(sync_params.get("since"), custom_params),
                "organizations": lambda: service.sync_organizations(sync_params.get("since"), custom_params),
                "employees": lambda: service.sync_employees(sync_params.get("since"), custom_params),
                "purchase_invoices": lambda: service.sync_purchase_invoices(sync_params.get("since"), custom_params),
                "quality_issues": lambda: service.sync_quality_issues(sync_params.get("since"), custom_params),
                "all": lambda: service.sync_all(sync_params.get("since"), custom_params),
            }

            result = await type_map[sync_type]()

            # 3. 更新 SyncLog 为 success
            now = datetime.now()
            sync_log.finished_at = now
            if sync_log.started_at:
                sync_log.duration_seconds = (now - sync_log.started_at).total_seconds()

            # 提取结果统计
            if sync_type == "all":
                total_synced = total_created = total_updated = total_failed = 0
                for v in result.values():
                    if isinstance(v, dict):
                        total_synced += v.get("synced", 0)
                        total_created += v.get("created", 0)
                        total_updated += v.get("updated", 0)
                        total_failed += len(v.get("errors", []))
                sync_log.synced_count = total_synced
                sync_log.created_count = total_created
                sync_log.updated_count = total_updated
                sync_log.failed_count = total_failed
                errors_list = []
                for v in result.values():
                    if isinstance(v, dict):
                        errors_list.extend(v.get("errors", []))
                sync_log.message = f"全量同步完成: 处理{total_synced}条, 新增{total_created}条, 更新{total_updated}条"
                if total_failed:
                    sync_log.message += f", 失败{total_failed}条"
            else:
                sync_log.synced_count = result.get("synced", 0) if isinstance(result, dict) else 0
                sync_log.created_count = result.get("created", 0) if isinstance(result, dict) else 0
                sync_log.updated_count = result.get("updated", 0) if isinstance(result, dict) else 0
                errors_list = result.get("errors", []) if isinstance(result, dict) else []
                sync_log.failed_count = len(errors_list)
                sync_log.message = f"同步完成: 处理{sync_log.synced_count}条, 新增{sync_log.created_count}条, 更新{sync_log.updated_count}条"
                if sync_log.failed_count:
                    sync_log.message += f", 失败{sync_log.failed_count}条"

            sync_log.status = "success" if sync_log.failed_count == 0 else "failed"
            await db.commit()

            # 4. 更新 SyncSqlConfig
            sync_types_to_update = [t for t in VALID_SYNC_TYPES if t != "all"] if sync_type == "all" else [sync_type]
            for st in sync_types_to_update:
                cfg_result = await db.execute(select(SyncSqlConfig).where(SyncSqlConfig.sync_type == st))
                cfg = cfg_result.scalar_one_or_none()
                if cfg:
                    cfg.last_sync_time = now
                    cfg.last_sync_status = "success"
                    sync_result = result.get(st.replace("-", "_"), result) if sync_type == "all" else result
                    if isinstance(sync_result, dict):
                        cfg.last_sync_message = f"手动同步: 处理{sync_result.get('synced', 0)}条, 新增{sync_result.get('created', 0)}条, 更新{sync_result.get('updated', 0)}条"
                    cfg.next_sync_time = now + timedelta(seconds=_parse_interval_seconds(cfg.sync_interval))
            await db.commit()

        except Exception as e:
            # 标记为 failed
            try:
                log_result = await db.execute(select(SyncLog).where(SyncLog.task_id == task_id))
                sync_log = log_result.scalar_one()
                sync_log.status = "failed"
                sync_log.finished_at = datetime.now()
                if sync_log.started_at:
                    sync_log.duration_seconds = (sync_log.finished_at - sync_log.started_at).total_seconds()
                sync_log.message = f"同步失败: {str(e)}"
                sync_log.error_detail = traceback.format_exc()
                await db.commit()
            except Exception:
                logger.exception(f"更新 SyncLog 失败状态时异常, task_id={task_id}")
            logger.exception(f"后台同步任务异常, task_id={task_id}, sync_type={sync_type}")


@router.get("/config-status", response_model=ResponseModel[dict])
async def get_sync_config_status(
    current_user: dict = Depends(PermissionChecker("settings", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SyncSqlConfig))
    configs = result.scalars().all()
    config_map = {c.sync_type: c for c in configs}

    type_labels = {
        "orders": "销售订单",
        "order_details": "订单明细",
        "materials": "物料需求",
        "purchase_orders": "采购订单",
        "customers": "客户主数据",
        "suppliers": "供应商主数据",
        "materials_masterdata": "物料主数据",
        "skus": "SKU主数据",
        "products": "产品主数据",
        "warehouses": "仓库主数据",
        "processes": "工序主数据",
        "organizations": "组织主数据",
        "employees": "人员主数据",
        "purchase_invoices": "采购开票",
        "quality_issues": "品质异常",
    }
    status = {}
    for sync_type, label in type_labels.items():
        c = config_map.get(sync_type)
        condition_params = []
        if c and c.condition_params_json:
            try:
                condition_params = json.loads(c.condition_params_json)
            except json.JSONDecodeError:
                pass

        status[sync_type] = {
            "label": label,
            "configured": c is not None,
            "is_active": c.is_active if c else False,
            "has_sql": bool(c.sql_text.strip()) if c and c.sql_text else False,
            "has_mapping": bool(c.field_mapping_json and c.field_mapping_json.strip() not in ("", "{}")) if c else False,
            "condition_params": condition_params,
        }

    return ResponseModel(data={
        "enabled": settings.ERP_SYNC_ENABLED,
        "erp_db_configured": bool(settings.ERP_DB_URL),
        "types": status,
    })


@router.post("/{sync_type}", response_model=ResponseModel[dict])
async def trigger_sync(
    sync_type: str,
    hours: int = Query(default=24, ge=1, le=720, description="同步最近N小时的数据"),
    order_numbers: Optional[list[str]] = Query(default=None, description="指定订单号列表"),
    custom_params: Optional[dict] = None,
    current_user: dict = Depends(PermissionChecker("settings", "create")),
    db: AsyncSession = Depends(get_db),
):
    """手动触发同步 — 异步后台执行，立即返回 task_id"""
    if not settings.ERP_SYNC_ENABLED:
        return ResponseModel(
            code=400,
            message="ERP 同步未启用，请在系统配置中设置 ERP_SYNC_ENABLED=true",
            data={"enabled": False},
        )

    if sync_type not in VALID_SYNC_TYPES:
        return ResponseModel(
            code=400,
            message=f"不支持的同步类型: {sync_type}，可选: {', '.join(VALID_SYNC_TYPES)}",
            data={},
        )

    # 构建同步参数
    sync_params: dict = {}
    if order_numbers and sync_type in ("orders", "materials"):
        sync_params["order_numbers"] = order_numbers
    else:
        sync_params["since"] = datetime.now() - timedelta(hours=hours)
    if custom_params:
        sync_params.update(custom_params)

    # 创建 SyncLog 记录
    task_id = str(uuid.uuid4())
    sync_log = SyncLog(
        task_id=task_id,
        sync_type=sync_type,
        trigger_mode="manual",
        triggered_by=current_user.get("username", ""),
        status="pending",
        sync_params={"hours": hours, "order_numbers": order_numbers},
    )
    db.add(sync_log)
    await db.commit()

    # 启动后台任务
    asyncio.create_task(_run_sync_background(task_id, sync_type, sync_params, custom_params))

    return ResponseModel(data={
        "task_id": task_id,
        "sync_type": sync_type,
        "status": "pending",
        "message": "同步任务已提交，请通过 GET /sync/task/{task_id} 轮询状态",
    })


@router.get("/task/{task_id}", response_model=ResponseModel[dict])
async def get_sync_task(
    task_id: str,
    current_user: dict = Depends(PermissionChecker("settings", "read")),
    db: AsyncSession = Depends(get_db),
):
    """查询单个同步任务状态（用于前端轮询）"""
    result = await db.execute(select(SyncLog).where(SyncLog.task_id == task_id))
    log = result.scalar_one_or_none()
    if not log:
        return ResponseModel(code=404, message="任务不存在", data={})

    return ResponseModel(data={
        "task_id": log.task_id,
        "sync_type": log.sync_type,
        "trigger_mode": log.trigger_mode,
        "triggered_by": log.triggered_by,
        "status": log.status,
        "started_at": str(log.started_at) if log.started_at else None,
        "finished_at": str(log.finished_at) if log.finished_at else None,
        "duration_seconds": float(log.duration_seconds) if log.duration_seconds else None,
        "synced_count": log.synced_count,
        "created_count": log.created_count,
        "updated_count": log.updated_count,
        "failed_count": log.failed_count,
        "message": log.message,
        "error_detail": log.error_detail,
    })


@router.get("/tasks", response_model=ResponseModel[list])
async def list_sync_tasks(
    sync_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(PermissionChecker("settings", "read")),
    db: AsyncSession = Depends(get_db),
):
    """查询同步任务列表"""
    q = select(SyncLog).order_by(desc(SyncLog.created_at))
    if sync_type:
        q = q.where(SyncLog.sync_type == sync_type)
    if status:
        q = q.where(SyncLog.status == status)
    q = q.limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()

    return ResponseModel(data=[
        {
            "task_id": l.task_id,
            "sync_type": l.sync_type,
            "trigger_mode": l.trigger_mode,
            "triggered_by": l.triggered_by,
            "status": l.status,
            "started_at": str(l.started_at) if l.started_at else None,
            "finished_at": str(l.finished_at) if l.finished_at else None,
            "duration_seconds": float(l.duration_seconds) if l.duration_seconds else None,
            "synced_count": l.synced_count,
            "created_count": l.created_count,
            "updated_count": l.updated_count,
            "failed_count": l.failed_count,
            "message": l.message,
            "created_at": str(l.created_at) if l.created_at else None,
        }
        for l in logs
    ])


@router.get("/status", response_model=ResponseModel[dict])
async def get_sync_status(
    current_user: dict = Depends(PermissionChecker("settings", "read")),
    db: AsyncSession = Depends(get_db),
):
    """查询各类数据最近一次同步状态（从 SyncLog 读取）"""
    type_labels = {
        "orders": "销售订单", "order_details": "订单明细", "materials": "物料需求", "purchase_orders": "采购订单",
        "customers": "客户主数据", "suppliers": "供应商主数据", "materials_masterdata": "物料主数据",
        "skus": "SKU主数据", "products": "产品主数据", "warehouses": "仓库主数据",
        "processes": "工序主数据", "organizations": "组织主数据", "employees": "人员主数据",
        "purchase_invoices": "采购开票",
    }
    last_sync = {}
    for st in type_labels:
        result = await db.execute(
            select(SyncLog)
            .where(SyncLog.sync_type == st, SyncLog.status.in_(["success", "failed"]))
            .order_by(desc(SyncLog.finished_at))
            .limit(1)
        )
        log = result.scalar_one_or_none()
        if log:
            last_sync[st] = {
                "timestamp": str(log.finished_at) if log.finished_at else None,
                "status": log.status,
                "message": log.message,
            }
        else:
            last_sync[st] = None

    return ResponseModel(data={
        "enabled": settings.ERP_SYNC_ENABLED,
        "erp_db_configured": bool(settings.ERP_DB_URL),
        "last_sync": last_sync,
    })


@router.get("/erp-orders", response_model=ResponseModel[list])
async def get_erp_orders(
    current_user: dict = Depends(PermissionChecker("settings", "read")),
    db: AsyncSession = Depends(get_db),
):
    """从 ERP 查询可选订单列表"""
    if not settings.ERP_SYNC_ENABLED:
        return ResponseModel(code=400, message="ERP 同步未启用", data=[])
    if not settings.ERP_DB_URL:
        return ResponseModel(code=400, message="ERP 数据库未配置", data=[])

    try:
        service = ERPSyncService(db)
        await service._connect_erp()
        sql_text, mapping = await service._load_sql_config("orders")
        params = {"since": datetime.now() - timedelta(days=30)}
        rows = await service._execute_erp_sql(sql_text, params)
        result = []
        for row in rows:
            row_dict = service._map_row(row, mapping)
            result.append({
                "order_no": row_dict.get("order_no"),
                "line_no": row_dict.get("line_no"),
                "customer": row_dict.get("customer"),
                "product_name": row_dict.get("product_name"),
                "promised_date": row_dict.get("promised_date"),
                "planned_start_date": row_dict.get("planned_start_date"),
            })
        service._close_erp()
        return ResponseModel(data=result)
    except Exception as e:
        logger.exception(f"查询 ERP 订单列表失败: {e}")
        return ResponseModel(code=500, message=f"查询 ERP 订单列表失败: {e}", data=[])
