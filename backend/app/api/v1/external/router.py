"""对外接口统一路由

所有对外接口统一挂在 /api/v1/external 前缀下，路径在 endpoints/ 中按 @register_external 声明。
认证复用 data_supply 的 API Key 体系（X-API-Key 或 X-App-Key 签名）。
权限按 API Key 的 allowed_endpoints_json 字段控制（管理员勾选允许调用的接口）。
调用日志复用 DataSupplyCallLog 表（data_type 字段存 endpoint_code）。
"""

import json
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.schemas.common import ResponseModel
from app.services.basicdata.data_supply_service import (
    validate_signature_for_endpoint,
    check_ip_whitelist,
    log_call,
)

from .registry import (
    ExternalCallContext,
    get_endpoint_by_route,
    list_endpoint_dicts,
)
# 触发 endpoints 包导入，使所有 @register_external 装饰器生效
from . import endpoints  # noqa: F401


router = APIRouter()


async def _authenticate_external_request(
    request: Request, endpoint_code: str, db: AsyncSession
) -> DataSupplyApiKey:
    """对外接口签名认证：X-App-Key + X-Timestamp + X-Signature"""
    app_key = request.headers.get("X-App-Key")
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")

    if not (app_key and signature and timestamp):
        raise HTTPException(
            status_code=401,
            detail="缺少认证信息：请提供 X-App-Key + X-Timestamp + X-Signature",
        )

    query_string = str(request.url.query) if request.url.query else ""
    key_obj, reason = await validate_signature_for_endpoint(
        db, app_key, signature, timestamp, endpoint_code, query_string
    )
    if not key_obj:
        raise HTTPException(status_code=403, detail=f"签名认证失败：{reason}")
    return key_obj


async def _merge_params(request: Request) -> dict:
    """合并 query 参数和 JSON body 参数"""
    params: dict = dict(request.query_params)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        try:
            body = await request.json()
            if isinstance(body, dict):
                # body 字段优先级低于 query（防止覆盖路径参数）
                for k, v in body.items():
                    params.setdefault(k, v)
        except Exception:
            pass
    return params


async def _dispatch(method: str, path: str, request: Request, db: AsyncSession) -> Any:
    """统一分发：按 method + path 查找 endpoint 并执行"""
    endpoint = get_endpoint_by_route(method, path)
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"未找到对外接口: {method} /external{path}")

    if not endpoint.handler:
        raise HTTPException(status_code=500, detail=f"接口 {endpoint.endpoint_code} 未实现")

    start_time = time.time()

    # 认证
    key_obj = await _authenticate_external_request(request, endpoint.endpoint_code, db)

    # IP 白名单
    client_ip = request.client.host if request.client else None
    if client_ip and not check_ip_whitelist(key_obj, client_ip):
        raise HTTPException(status_code=403, detail=f"IP {client_ip} 不在白名单内")

    # 合并参数
    params = await _merge_params(request)

    ctx = ExternalCallContext(
        db=db,
        request=request,
        params=params,
        key_obj=key_obj,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )

    # 执行 handler
    try:
        result = await endpoint.handler(ctx)
        response_status = 200
        response_count = (
            len(result.get("items", []))
            if isinstance(result, dict) and "items" in result
            else (1 if result else 0)
        )
    except HTTPException:
        raise
    except Exception as e:
        result = None
        response_status = 500
        response_count = 0
        # 记录日志后重新抛出
        duration_ms = (time.time() - start_time) * 1000
        await log_call(
            db=db,
            api_key_id=key_obj.id,
            api_key_name=key_obj.key_name,
            data_type=endpoint.endpoint_code,
            request_params=params,
            response_status=response_status,
            response_count=response_count,
            ip_address=client_ip,
            user_agent=ctx.user_agent,
            duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=f"接口内部错误: {e}")

    # 记录调用日志
    duration_ms = (time.time() - start_time) * 1000
    await log_call(
        db=db,
        api_key_id=key_obj.id,
        api_key_name=key_obj.key_name,
        data_type=endpoint.endpoint_code,
        request_params=params,
        response_status=response_status,
        response_count=response_count,
        ip_address=client_ip,
        user_agent=ctx.user_agent,
        duration_ms=duration_ms,
    )

    return ResponseModel(data=result)


# ── 管理接口：列出所有已注册对外接口（需要登录权限） ──
# 这个接口走 data_supply 的 PermissionChecker，放到 data_supply.py 中


# ── 对外接口入口（catch-all）──

@router.get("/{full_path:path}")
async def external_get(full_path: str, request: Request, db: AsyncSession = Depends(get_db)):
    path = "/" + full_path if not full_path.startswith("/") else full_path
    return await _dispatch("GET", path, request, db)


@router.post("/{full_path:path}")
async def external_post(full_path: str, request: Request, db: AsyncSession = Depends(get_db)):
    path = "/" + full_path if not full_path.startswith("/") else full_path
    return await _dispatch("POST", path, request, db)
