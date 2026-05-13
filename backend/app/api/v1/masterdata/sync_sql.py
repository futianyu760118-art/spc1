"""
同步 SQL 配置管理 API
管理员在后台配置直接查询 ERP 数据库的 SQL 语句
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.schemas.common import ResponseModel
from app.models.masterdata.sync_sql_config import SyncSqlConfig
from app.core.database import Base
import app.models  # 确保所有模型已注册到 Base

router = APIRouter()

_AUTO_FIELDS = {"id", "created_at", "updated_at"}


def _get_sync_type_overrides() -> dict:
    """前端使用的 sync_type 名称 → Model 映射，覆盖自动生成无法匹配的名称"""
    from app.models.order.sale_order import SaleOrder, SaleOrderLine
    from app.models.material.material_demand import MaterialDemand
    from app.models.material.purchase_order import PurchaseOrder
    from app.models.masterdata.customer import Customer
    from app.models.masterdata.supplier import Supplier
    from app.models.masterdata.material import Material
    from app.models.masterdata.sku import SKU
    from app.models.masterdata.product import Product
    from app.models.masterdata.warehouse import Warehouse
    from app.models.masterdata.process import Process
    from app.models.masterdata.organization import Organization
    from app.models.masterdata.employee import Employee
    return {
        "orders": SaleOrder,
        "order_details": SaleOrderLine,
        "materials": MaterialDemand,
        "purchase_orders": PurchaseOrder,
        "customers": Customer,
        "suppliers": Supplier,
        "materials_masterdata": Material,
        "skus": SKU,
        "products": Product,
        "warehouses": Warehouse,
        "processes": Process,
        "organizations": Organization,
        "employees": Employee,
    }


def _get_model_map() -> dict:
    """动态从所有已注册的 SQLAlchemy 模型构建 sync_type → Model 映射。
    支持的 key 形式（以 Supplier / scm_supplier 为例）：
      - 原始表名:       'scm_supplier'
      - 去前缀表名:     'supplier'
      - 去前缀表名复数:  'suppliers'
      - 类名 snake_case: 'supplier'
    """
    import re
    result: dict = {}

    def _collect(cls):
        for sub in cls.__subclasses__():
            if hasattr(sub, '__tablename__') and hasattr(sub, '__table__'):
                table: str = sub.__tablename__
                result[table] = sub
                stripped = re.sub(r'^(scm_|app_|sys_)', '', table)
                result[stripped] = sub
                result[stripped + 's'] = sub
                snake = re.sub(r'(?<!^)(?=[A-Z])', '_', sub.__name__).lower()
                result[snake] = sub
                result[snake + 's'] = sub
            _collect(sub)

    _collect(Base)
    result.update(_get_sync_type_overrides())
    return result


def _build_erp_engine():
    from app.core.config import get_settings
    from sqlalchemy import create_engine

    settings = get_settings()
    if not settings.ERP_DB_URL:
        raise HTTPException(status_code=400, detail="ERP_DB_URL 未配置")
    url = settings.ERP_DB_URL
    for param in ["TrustServerCertificate=yes", "Encrypt=no"]:
        if param.split("=")[0] not in url:
            url += f"&{param}" if "?" in url else f"?{param}"
    connect_args = {"login_timeout": 15, "timeout": 30}
    if "mssql+pyodbc" in url:
        connect_args["charset"] = "utf-8"
    return create_engine(url, echo=False, connect_args=connect_args)


def _clean_value(v):
    from decimal import Decimal as _Decimal
    if v is None:
        return v
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, _Decimal):
        return float(v)
    if isinstance(v, bytes):
        try:
            return v.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return v.decode('gbk')
            except UnicodeDecodeError:
                return v.decode('latin-1', errors='replace')
    if isinstance(v, str):
        try:
            v.encode('utf-8')
            return v
        except UnicodeEncodeError:
            try:
                return v.encode('latin-1').decode('gbk')
            except (UnicodeDecodeError, UnicodeEncodeError):
                return v.encode('latin-1', errors='replace').decode('utf-8', errors='replace')
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    return str(v)


def _run_erp_test(sql_text: str) -> dict:
    """同步执行 ERP SQL 并返回测试结果（在线程池中调用）"""
    from datetime import datetime, timedelta
    from sqlalchemy import text
    import time

    erp_engine = _build_erp_engine()
    try:
        with erp_engine.connect() as conn:
            since = datetime.now() - timedelta(days=30)
            start_time = time.time()
            rows = conn.execute(
                text(sql_text), {"since": since}
            ).mappings().all()
            elapsed = round(time.time() - start_time, 2)

            preview = []
            for row in rows[:20]:
                row_dict = {}
                for k, v in dict(row).items():
                    row_dict[k] = _clean_value(v)
                preview.append(row_dict)

        return {
            "total_rows": len(rows),
            "preview": preview,
            "columns": list(preview[0].keys()) if preview else [],
            "elapsed_seconds": elapsed,
        }
    finally:
        erp_engine.dispose()


def _run_erp_parse_fields(sql_text: str) -> list:
    """同步解析 ERP SQL 字段名（在线程池中调用）"""
    from datetime import datetime, timedelta
    from sqlalchemy import text

    erp_engine = _build_erp_engine()
    try:
        with erp_engine.connect() as conn:
            since = datetime.now() - timedelta(days=30)
            result = conn.execute(text(sql_text), {"since": since})
            return list(result.keys())
    finally:
        erp_engine.dispose()


class ParseErpFieldsBody(BaseModel):
    sql_text: str


class TestSqlBody(BaseModel):
    sql_text: str


class SyncSqlCreate(BaseModel):
    sync_type: str
    description: Optional[str] = None
    sql_text: str
    field_mapping_json: Optional[str] = None
    condition_params_json: Optional[str] = None
    sync_interval: str = "1h"
    sync_strategy: str = "incremental"
    sync_time_window: Optional[str] = None
    sync_priority: int = 5
    sync_enabled: bool = True


class SyncSqlUpdate(BaseModel):
    description: Optional[str] = None
    sql_text: Optional[str] = None
    field_mapping_json: Optional[str] = None
    condition_params_json: Optional[str] = None
    sync_interval: Optional[str] = None
    sync_strategy: Optional[str] = None
    sync_time_window: Optional[str] = None
    sync_priority: Optional[int] = None
    sync_enabled: Optional[bool] = None


@router.post("/test-sql", response_model=ResponseModel[dict])
async def test_raw_sql(
    body: TestSqlBody,
    current_user: dict = Depends(PermissionChecker("settings", "read")),
):
    """直接测试 SQL 语句，无需保存配置"""
    if not body.sql_text or not body.sql_text.strip():
        raise HTTPException(status_code=400, detail="SQL 语句不能为空")

    try:
        result = await asyncio.to_thread(_run_erp_test, body.sql_text)
        return ResponseModel(data=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL 执行失败: {e}")


@router.get("", response_model=ResponseModel[list])
async def list_sync_sql(
    current_user: dict = Depends(PermissionChecker("settings", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SyncSqlConfig).order_by(SyncSqlConfig.sync_type))
    configs = result.scalars().all()
    return ResponseModel(data=[
        {
            "id": c.id,
            "sync_type": c.sync_type,
            "description": c.description,
            "sql_text": c.sql_text,
            "field_mapping_json": c.field_mapping_json,
            "condition_params_json": c.condition_params_json,
            "is_active": c.is_active,
            "sync_interval": c.sync_interval,
            "sync_strategy": c.sync_strategy,
            "sync_time_window": c.sync_time_window,
            "sync_priority": c.sync_priority,
            "sync_enabled": c.sync_enabled,
            "last_sync_time": str(c.last_sync_time) if c.last_sync_time else None,
            "next_sync_time": str(c.next_sync_time) if c.next_sync_time else None,
            "last_sync_status": c.last_sync_status,
            "last_sync_message": c.last_sync_message,
            "updated_at": str(c.updated_at) if c.updated_at else None,
        }
        for c in configs
    ])


@router.post("", response_model=ResponseModel[dict])
async def create_sync_sql(
    body: SyncSqlCreate,
    current_user: dict = Depends(PermissionChecker("settings", "create")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(SyncSqlConfig).where(SyncSqlConfig.sync_type == body.sync_type)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"sync_type='{body.sync_type}' 已存在，请使用 PUT 更新")

    # 计算初始 next_sync_time
    from datetime import datetime, timedelta
    interval_map = {"h": 3600, "d": 86400, "w": 604800}
    interval_str = (body.sync_interval or "1h").lower()
    try:
        unit = interval_str[-1]
        val = int(interval_str[:-1])
        seconds = val * interval_map.get(unit, 3600)
    except (ValueError, IndexError):
        seconds = 3600
    initial_next = datetime.now() + timedelta(seconds=seconds)

    config = SyncSqlConfig(
        sync_type=body.sync_type,
        description=body.description,
        sql_text=body.sql_text,
        field_mapping_json=body.field_mapping_json,
        condition_params_json=body.condition_params_json,
        is_active=body.sync_enabled,
        sync_interval=body.sync_interval,
        sync_strategy=body.sync_strategy,
        sync_time_window=body.sync_time_window,
        sync_priority=body.sync_priority,
        sync_enabled=body.sync_enabled,
        created_by=current_user.get("username", ""),
        next_sync_time=initial_next,
    )
    db.add(config)
    await db.flush()
    await log_audit(db, "sync_sql_config", config.id, "create", operator=current_user.get("username", ""))
    await db.commit()
    return ResponseModel(data={"id": config.id, "sync_type": config.sync_type})


@router.put("/{config_id}", response_model=ResponseModel[dict])
async def update_sync_sql(
    config_id: int,
    body: SyncSqlUpdate,
    current_user: dict = Depends(PermissionChecker("settings", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SyncSqlConfig).where(SyncSqlConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    if body.sql_text is not None:
        config.sql_text = body.sql_text
    if body.description is not None:
        config.description = body.description
    if body.field_mapping_json is not None:
        config.field_mapping_json = body.field_mapping_json
    if body.condition_params_json is not None:
        config.condition_params_json = body.condition_params_json
    if body.sync_interval is not None:
        config.sync_interval = body.sync_interval
        # 重新计算 next_sync_time
        from datetime import datetime, timedelta
        interval_map = {"h": 3600, "d": 86400, "w": 604800}
        interval_str = (body.sync_interval or "1h").lower()
        try:
            unit = interval_str[-1]
            val = int(interval_str[:-1])
            seconds = val * interval_map.get(unit, 3600)
        except (ValueError, IndexError):
            seconds = 3600
        base = config.last_sync_time or datetime.now()
        config.next_sync_time = base + timedelta(seconds=seconds)
    if body.sync_strategy is not None:
        config.sync_strategy = body.sync_strategy
    if body.sync_time_window is not None:
        config.sync_time_window = body.sync_time_window
    if body.sync_priority is not None:
        config.sync_priority = body.sync_priority
    if body.sync_enabled is not None:
        config.sync_enabled = body.sync_enabled
        config.is_active = body.sync_enabled

    await log_audit(db, "sync_sql_config", config.id, "update", operator=current_user.get("username", ""))
    await db.commit()
    return ResponseModel(data={"id": config.id, "sync_type": config.sync_type})


@router.delete("/{config_id}", response_model=ResponseModel[dict])
async def delete_sync_sql(
    config_id: int,
    current_user: dict = Depends(PermissionChecker("settings", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SyncSqlConfig).where(SyncSqlConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    await log_audit(db, "sync_sql_config", config.id, "delete", operator=current_user.get("username", ""))
    await db.delete(config)
    await db.commit()
    return ResponseModel(data={"deleted": config_id})


@router.get("/spc-fields/{sync_type}", response_model=ResponseModel[list])
async def get_spc_fields(
    sync_type: str,
    current_user: dict = Depends(PermissionChecker("settings", "read")),
):
    model_map = _get_model_map()
    model = model_map.get(sync_type)
    if not model:
        raise HTTPException(
            status_code=400,
            detail=f"未知的同步类型: {sync_type}，系统中无匹配模型",
        )

    columns = []
    for col in model.__table__.columns:
        if col.name in _AUTO_FIELDS:
            continue
        columns.append({
            "name": col.name,
            "type": str(col.type),
            "nullable": col.nullable,
        })
    return ResponseModel(data=columns)


@router.post("/parse-erp-fields", response_model=ResponseModel[list])
async def parse_erp_fields(
    body: ParseErpFieldsBody,
    current_user: dict = Depends(PermissionChecker("settings", "read")),
):
    try:
        columns = await asyncio.to_thread(_run_erp_parse_fields, body.sql_text)
        return ResponseModel(data=columns)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL 字段解析失败: {e}")


@router.post("/{config_id}/test", response_model=ResponseModel[dict])
async def test_sync_sql(
    config_id: int,
    current_user: dict = Depends(PermissionChecker("settings", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SyncSqlConfig).where(SyncSqlConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    try:
        data = await asyncio.to_thread(_run_erp_test, config.sql_text)
        return ResponseModel(data=data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL 执行失败: {e}")
