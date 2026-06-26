"""对外接口注册表

每个对外接口在此用 @register_external 装饰器声明：
- endpoint_code: 唯一标识，与 API Key 的 allowed_endpoints_json 对应
- name: 中文名
- description: 描述
- method: HTTP 方法
- path: 固定路径（相对于 /external 前缀），如 /orders/list
- handler: 异步处理函数 (ctx: ExternalCallContext) -> Any
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Dict, List, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.data_supply import DataSupplyApiKey


@dataclass
class ExternalCallContext:
    """对外接口调用上下文，传给 handler"""
    db: AsyncSession
    request: Request
    params: dict                       # 合并了 query params 和 body 的参数
    key_obj: DataSupplyApiKey          # 已认证的 API Key 对象
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class ExternalEndpoint:
    """对外接口定义"""
    endpoint_code: str                 # 唯一标识，如 orders.list
    name: str                          # 中文名
    description: str = ""
    method: str = "GET"                # HTTP 方法（仅用于文档/校验）
    path: str = ""                     # 固定路径（相对于 /external 前缀）
    handler: Optional[Callable[[ExternalCallContext], Awaitable[Any]]] = None
    tags: List[str] = field(default_factory=list)  # 分组标签


# 注册表
_ENDPOINT_REGISTRY: Dict[str, ExternalEndpoint] = {}
_PATH_INDEX: Dict[str, Dict[str, ExternalEndpoint]] = {}
# _PATH_INDEX 形如 { "GET": { "/orders/list": Endpoint }, "POST": {...} }


def register_external(
    endpoint_code: str,
    name: str,
    *,
    method: str = "GET",
    path: str = "",
    description: str = "",
    tags: Optional[List[str]] = None,
) -> Callable:
    """装饰器：注册一个对外接口

    用法:
        @register_external("orders.list", "订单列表", method="GET", path="/orders/list")
        async def orders_list(ctx: ExternalCallContext) -> dict:
            ...
    """
    def decorator(fn: Callable[[ExternalCallContext], Awaitable[Any]]):
        endpoint = ExternalEndpoint(
            endpoint_code=endpoint_code,
            name=name,
            description=description,
            method=method.upper(),
            path=path or f"/{endpoint_code.replace('.', '/')}",
            handler=fn,
            tags=tags or [],
        )

        if endpoint.endpoint_code in _ENDPOINT_REGISTRY:
            raise ValueError(f"endpoint_code 重复: {endpoint.endpoint_code}")

        method_upper = endpoint.method
        path_map = _PATH_INDEX.setdefault(method_upper, {})
        if endpoint.path in path_map:
            raise ValueError(f"path 重复: {method_upper} {endpoint.path}")

        _ENDPOINT_REGISTRY[endpoint.endpoint_code] = endpoint
        path_map[endpoint.path] = endpoint
        return fn

    return decorator


def get_endpoint_by_code(endpoint_code: str) -> Optional[ExternalEndpoint]:
    return _ENDPOINT_REGISTRY.get(endpoint_code)


def get_endpoint_by_route(method: str, path: str) -> Optional[ExternalEndpoint]:
    """按 HTTP 方法和路径查找已注册的 endpoint"""
    return _PATH_INDEX.get(method.upper(), {}).get(path)


def list_endpoints() -> List[ExternalEndpoint]:
    return list(_ENDPOINT_REGISTRY.values())


def list_endpoint_dicts() -> List[dict]:
    """返回可直接 JSON 序列化的 endpoint 清单"""
    return [
        {
            "endpoint_code": e.endpoint_code,
            "name": e.name,
            "description": e.description,
            "method": e.method,
            "path": f"/external{e.path}",
            "tags": e.tags,
        }
        for e in _ENDPOINT_REGISTRY.values()
    ]
