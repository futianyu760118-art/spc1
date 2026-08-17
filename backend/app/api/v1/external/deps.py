"""对外接口认证依赖：签名校验 + IP 白名单（语义与文案照抄旧 router.py）"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.services.basicdata.data_supply_service import (
    validate_signature_for_endpoint,
    check_ip_whitelist,
)


def external_auth(endpoint_code: str):
    """按 endpoint_code 生成认证依赖。

    顺序与旧 _dispatch 一致：签名认证 -> IP 白名单 -> 业务 handler。
    """
    async def dependency(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> DataSupplyApiKey:
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

        client_ip = request.client.host if request.client else None
        if client_ip and not check_ip_whitelist(key_obj, client_ip):
            raise HTTPException(status_code=403, detail=f"IP {client_ip} 不在白名单内")

        return key_obj

    return dependency
