"""M10 微系统互连：连接状态与契约清单（公开只读，不鉴权）。

M10（岗位与个人运营微系统）以「只读引用」方式接入 SPC：
- 读：服务端账号登录 POST /api/v1/basicdata/auth/login → Bearer → 下列 GET 接口；
- 写：一律回 SPC 系统操作，M10 不写 SPC 业务库（与 PLM2 接入标准一致）。
本端点用于 M10 侧连接自检与契约发现。
"""
from fastapi import APIRouter

from app.schemas.common import ResponseModel

router = APIRouter()

M10_READ_ENDPOINTS = [
    {"method": "GET", "path": "/api/v1/dashboard/summary", "desc": "控制塔汇总（风险灯号/最近异常）"},
    {"method": "GET", "path": "/api/v1/dashboard/today-overview", "desc": "今日概览（应交付/缺料/待关闭异常/ETA 逾期）"},
    {"method": "GET", "path": "/api/v1/dashboard/rolling-risk", "desc": "滚动 14 天风险"},
    {"method": "GET", "path": "/api/v1/dashboard/order-risk-distribution", "desc": "订单风险分布（按客户）"},
    {"method": "GET", "path": "/api/v1/dashboard/closure-achievement", "desc": "异常关闭达成"},
    {"method": "GET", "path": "/api/v1/dashboard/orders", "desc": "订单风险列表（分页/筛选）"},
    {"method": "GET", "path": "/api/v1/dashboard/materials", "desc": "物料缺料/齐套列表"},
    {"method": "GET", "path": "/api/v1/exceptions", "desc": "异常台账（分页/筛选）"},
    {"method": "GET", "path": "/api/v1/materials/supplier-risk", "desc": "供应商风险清单"},
]


@router.get("/status", response_model=ResponseModel)
async def m10_status():
    return ResponseModel(data={
        "contract_version": "SPC-M10.V1",
        "tenant_id": "SPC",
        "source": "spc",
        "connected": True,
        "mode": "read-only",
        "auth": {
            "read": "POST /api/v1/basicdata/auth/login (OAuth2 表单) → Bearer，只读",
            "system": "POST /api/v1/external/* (X-App-Key + X-Timestamp + X-Signature HMAC 签名)",
        },
        "endpoints": M10_READ_ENDPOINTS,
        "note": "M10 只读引用 SPC；写操作请在 SPC 系统内办理，避免双写。",
    })
