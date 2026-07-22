"""基础数据与集成中心 — 数据供给 API 路由"""

import json
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.schemas.basicdata.data_supply_schemas import (
    DataSupplyConfigCreate, DataSupplyConfigUpdate, DataSupplyConfigOut,
    DataSupplyApiKeyCreate, DataSupplyApiKeyUpdate, DataSupplyApiKeyOut,
    DataSupplyApiKeyCreateResult,
    DataSupplyCallLogOut,
    DataSupplyCallStatistics,
)
from app.models.basicdata.data_supply import DataSupplyConfig, DataSupplyApiKey, DataSupplyCallLog
from app.services.basicdata.data_supply_service import (
    get_available_data_types, get_data_type_options,
    validate_signature, check_ip_whitelist,
    query_data, query_single_record,
    log_call, get_call_statistics,
    generate_api_key, generate_app_key, generate_app_secret,
    resolve_model, get_model_fields,
)
from app.services.basicdata.data_supply_registry import DATA_TYPE_REGISTRY, get_data_type_definition

router = APIRouter()


# ═══════════════════════════════════════════
# 管理接口（需要登录 + 权限）
# ═══════════════════════════════════════════

# ── 数据供给配置 ──

@router.get("/configs/available-types", response_model=ResponseModel[list])
async def list_available_data_types(
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取所有已注册的数据实体类型（含配置状态）"""
    result = await get_available_data_types(db)
    return ResponseModel(data=result)


@router.get("/data-type-options", response_model=ResponseModel[list])
async def list_data_type_options(
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取已启用的数据类型选项（供 API Key 表单下拉选择）"""
    result = await get_data_type_options(db)
    return ResponseModel(data=result)


@router.get("/configs", response_model=ResponseModel[dict])
async def list_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
    db: AsyncSession = Depends(get_db),
):
    """查询数据供给配置列表"""
    query = select(DataSupplyConfig).order_by(DataSupplyConfig.id)
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [DataSupplyConfigOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.post("/configs", response_model=ResponseModel[DataSupplyConfigOut])
async def create_config(
    data: DataSupplyConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "create")),
):
    """创建数据供给配置（基于 Registry 中注册的数据类型）"""
    # 验证 data_type 在 Registry 中
    definition = get_data_type_definition(data.data_type)
    if not definition:
        raise HTTPException(status_code=400, detail=f"未注册的数据类型: {data.data_type}，请在 Registry 中注册")

    # 验证模型存在
    model_cls = resolve_model(definition.model_name)
    if not model_cls:
        raise HTTPException(status_code=400, detail=f"未找到模型: {definition.model_name}")

    existing = await db.execute(
        select(DataSupplyConfig).where(DataSupplyConfig.data_type == data.data_type)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"数据类型 {data.data_type} 已配置")

    create_data = data.model_dump()
    if not create_data.get("allowed_fields_json"):
        create_data["allowed_fields_json"] = json.dumps(definition.exposed_fields)
    if not create_data.get("filter_fields_json") and definition.filter_fields:
        create_data["filter_fields_json"] = json.dumps(definition.filter_fields)
    if not create_data.get("mask_fields_json") and definition.mask_fields:
        create_data["mask_fields_json"] = json.dumps(definition.mask_fields)

    db_item = DataSupplyConfig(**create_data)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return ResponseModel(data=DataSupplyConfigOut.model_validate(db_item))


@router.put("/configs/{config_id}", response_model=ResponseModel[DataSupplyConfigOut])
async def update_config(
    config_id: int,
    data: DataSupplyConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "update")),
):
    """更新数据供给配置"""
    result = await db.execute(select(DataSupplyConfig).where(DataSupplyConfig.id == config_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="配置不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return ResponseModel(data=DataSupplyConfigOut.model_validate(db_item))


@router.delete("/configs/{config_id}", response_model=ResponseModel)
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "delete")),
):
    """删除数据供给配置"""
    result = await db.execute(select(DataSupplyConfig).where(DataSupplyConfig.id == config_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="配置不存在")
    await db.delete(db_item)
    await db.commit()
    return ResponseModel(message="删除成功")


# ── API Key 管理 ──

@router.get("/endpoints", response_model=ResponseModel[list])
async def list_registered_endpoints(
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
):
    """获取所有已注册的对外接口 endpoint 清单（供 API Key 表单勾选）"""
    from app.api.v1.external.registry import list_endpoint_dicts
    return ResponseModel(data=list_endpoint_dicts())


@router.get("/api-keys", response_model=ResponseModel[dict])
async def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
    db: AsyncSession = Depends(get_db),
):
    """查询 API Key 列表"""
    query = select(DataSupplyApiKey).order_by(desc(DataSupplyApiKey.id))
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [DataSupplyApiKeyOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.post("/api-keys", response_model=ResponseModel[DataSupplyApiKeyCreateResult])
async def create_api_key(
    data: DataSupplyApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "create")),
):
    """创建 API Key（AppKey + AppSecret 仅在创建时返回一次）"""
    api_key = generate_api_key()
    app_key = generate_app_key()
    app_secret = generate_app_secret()
    db_item = DataSupplyApiKey(
        key_name=data.key_name,
        api_key=api_key,
        app_key=app_key,
        app_secret=app_secret,
        description=data.description,
        is_active=True,
        allowed_data_types_json=data.allowed_data_types_json,
        allowed_endpoints_json=data.allowed_endpoints_json,
        rate_limit=data.rate_limit,
        expires_at=data.expires_at,
        ip_whitelist_json=data.ip_whitelist_json,
        created_by=current_user.get("username", ""),
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return ResponseModel(data=DataSupplyApiKeyCreateResult.model_validate(db_item))


@router.put("/api-keys/{key_id}", response_model=ResponseModel[DataSupplyApiKeyOut])
async def update_api_key(
    key_id: int,
    data: DataSupplyApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "update")),
):
    """更新 API Key"""
    result = await db.execute(select(DataSupplyApiKey).where(DataSupplyApiKey.id == key_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return ResponseModel(data=DataSupplyApiKeyOut.model_validate(db_item))


@router.delete("/api-keys/{key_id}", response_model=ResponseModel)
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "delete")),
):
    """删除 API Key"""
    result = await db.execute(select(DataSupplyApiKey).where(DataSupplyApiKey.id == key_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    await db.delete(db_item)
    await db.commit()
    return ResponseModel(message="删除成功")


# ── 调用日志 ──

@router.get("/call-logs", response_model=ResponseModel[dict])
async def list_call_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    api_key_id: Optional[int] = Query(None),
    data_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
    db: AsyncSession = Depends(get_db),
):
    """查询调用日志"""
    query = select(DataSupplyCallLog).order_by(desc(DataSupplyCallLog.called_at))
    if api_key_id:
        query = query.where(DataSupplyCallLog.api_key_id == api_key_id)
    if data_type:
        query = query.where(DataSupplyCallLog.data_type == data_type)
    if start_date:
        query = query.where(DataSupplyCallLog.called_at >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.where(DataSupplyCallLog.called_at <= datetime.fromisoformat(end_date + "T23:59:59"))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [DataSupplyCallLogOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/statistics", response_model=ResponseModel[dict])
async def get_statistics(
    api_key_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取调用统计"""
    sd = datetime.fromisoformat(start_date) if start_date else None
    ed = datetime.fromisoformat(end_date + "T23:59:59") if end_date else None
    result = await get_call_statistics(db, api_key_id, sd, ed)
    return ResponseModel(data=result)


# ═══════════════════════════════════════════
# 数据供给接口（第三方调用）
# 认证方式：HMAC-SHA256 签名认证（X-App-Key + X-Timestamp + X-Signature）
# ═══════════════════════════════════════════

async def _authenticate_request(request: Request, data_type: str, db: AsyncSession) -> DataSupplyApiKey:
    """签名认证：X-App-Key + X-Timestamp + X-Signature"""
    app_key = request.headers.get("X-App-Key")
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")

    if not (app_key and signature and timestamp):
        raise HTTPException(
            status_code=401,
            detail="缺少认证信息：请提供 X-App-Key + X-Timestamp + X-Signature",
        )

    query_string = str(request.url.query) if request.url.query else ""
    key_obj = await validate_signature(db, app_key, signature, timestamp, data_type, query_string)
    if not key_obj:
        raise HTTPException(status_code=403, detail="签名验证失败：签名不匹配、已过期或无权访问")
    return key_obj


@router.get("/data/{data_type}", response_model=ResponseModel[dict])
async def supply_data(
    data_type: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="关键字搜索"),
    updated_after: Optional[str] = Query(None, description="增量同步：只返回此时间之后更新的数据 (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
):
    """获取指定类型数据（支持签名认证和 API Key 认证）"""
    start_time = time.time()

    # 统一认证
    key_obj = await _authenticate_request(request, data_type, db)

    # IP 白名单检查
    client_ip = request.client.host if request.client else None
    if client_ip and not check_ip_whitelist(key_obj, client_ip):
        raise HTTPException(status_code=403, detail=f"IP {client_ip} 不在白名单内")

    # 检查数据类型是否在 Registry 中注册
    definition = get_data_type_definition(data_type)
    if not definition:
        raise HTTPException(status_code=404, detail=f"数据类型 {data_type} 未注册")

    # 检查数据类型是否启用
    config_result = await db.execute(
        select(DataSupplyConfig).where(DataSupplyConfig.data_type == data_type, DataSupplyConfig.is_active == True)
    )
    config = config_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"数据类型 {data_type} 未启用或未配置")

    # 解析 updated_after
    ua_datetime = None
    if updated_after:
        try:
            ua_datetime = datetime.fromisoformat(updated_after)
        except ValueError:
            raise HTTPException(status_code=400, detail="updated_after 格式无效，请使用 ISO 8601 格式")

    # 查询数据
    try:
        result = await query_data(db, data_type, config, page, page_size, keyword, updated_after=ua_datetime)
        response_status = 200
        response_count = len(result.get("items", []))
    except Exception as e:
        result = {"items": [], "total": 0, "page": page, "page_size": page_size}
        response_status = 500
        response_count = 0

    # 记录调用日志
    duration_ms = (time.time() - start_time) * 1000
    await log_call(
        db=db,
        api_key_id=key_obj.id,
        api_key_name=key_obj.key_name,
        data_type=data_type,
        request_params={"page": page, "page_size": page_size, "keyword": keyword, "updated_after": updated_after},
        response_status=response_status,
        response_count=response_count,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
        duration_ms=duration_ms,
    )

    return ResponseModel(data=result)


@router.get("/data/{data_type}/{record_id}", response_model=ResponseModel[dict])
async def supply_single_data(
    data_type: str,
    record_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取单条数据（支持签名认证和 API Key 认证）"""
    start_time = time.time()

    # 统一认证
    key_obj = await _authenticate_request(request, data_type, db)

    # IP 白名单检查
    client_ip = request.client.host if request.client else None
    if client_ip and not check_ip_whitelist(key_obj, client_ip):
        raise HTTPException(status_code=403, detail=f"IP {client_ip} 不在白名单内")

    # 检查数据类型是否在 Registry 中注册
    definition = get_data_type_definition(data_type)
    if not definition:
        raise HTTPException(status_code=404, detail=f"数据类型 {data_type} 未注册")

    # 检查数据类型是否启用
    config_result = await db.execute(
        select(DataSupplyConfig).where(DataSupplyConfig.data_type == data_type, DataSupplyConfig.is_active == True)
    )
    config = config_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"数据类型 {data_type} 未启用或未配置")

    # 查询数据
    try:
        result = await query_single_record(db, data_type, config, record_id)
        response_status = 200
        response_count = 1 if result else 0
    except Exception:
        result = None
        response_status = 500
        response_count = 0

    if not result:
        raise HTTPException(status_code=404, detail="记录不存在")

    # 记录调用日志
    duration_ms = (time.time() - start_time) * 1000
    await log_call(
        db=db,
        api_key_id=key_obj.id,
        api_key_name=key_obj.key_name,
        data_type=data_type,
        request_params={"record_id": record_id},
        response_status=response_status,
        response_count=response_count,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
        duration_ms=duration_ms,
    )

    return ResponseModel(data=result)


@router.get("/exposable-internal-endpoints", response_model=ResponseModel)
async def list_exposable_internal_endpoints(
    current_user: dict = Depends(PermissionChecker("basicdata.data_supply", "read")),
):
    """列出所有 @exposable 标记的内部接口，给 API Key 表单勾选用。"""
    from app.services.basicdata.exposable_registry import list_exposable_endpoints
    return ResponseModel(
        code=0,
        message="ok",
        data=list_exposable_endpoints(),
    )
