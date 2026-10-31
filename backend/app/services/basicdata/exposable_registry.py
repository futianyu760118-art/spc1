"""内部接口「可暴露」装饰器与注册表。

内部 handler 通过 @exposable 标记可被外部 API Key + 签名调用。
装饰器仅在函数对象上挂标记，method 与 path_template 在 app lifespan
阶段通过扫描 app.router.routes 反向解析并填充 _BY_PATH。
"""

from dataclasses import dataclass, field
from typing import Optional


EXPOSABLE_ATTR = "__exposable_meta__"


@dataclass(frozen=True)
class ExposableEndpoint:
    endpoint_code: str
    method: str
    path: str
    name: str
    description: str = ""
    tags: list = field(default_factory=list)
    module: str = ""


_BY_CODE: dict = {}
_BY_PATH: dict = {}


def exposable(
    endpoint_code: str,
    name: str,
    description: str = "",
    tags: Optional[list] = None,
):
    if not endpoint_code.startswith("int:"):
        raise ValueError(
            f"endpoint_code must start with 'int:': {endpoint_code}"
        )
    if endpoint_code in _BY_CODE:
        raise ValueError(f"Duplicate endpoint_code: {endpoint_code}")

    def decorator(func):
        if hasattr(func, EXPOSABLE_ATTR):
            raise ValueError(
                f"Function already marked exposable: {func.__name__}"
            )
        e = ExposableEndpoint(
            endpoint_code=endpoint_code,
            method="",
            path="",
            name=name,
            description=description,
            tags=list(tags or []),
            module=func.__module__,
        )
        _BY_CODE[endpoint_code] = e
        setattr(func, EXPOSABLE_ATTR, e)
        return func
    return decorator


def resolve_endpoint_code(method: str, path: str) -> Optional[str]:
    return _BY_PATH.get((method.upper(), path))


def list_exposable_endpoints() -> list:
    """admin UI 用，列出全部 @exposable 端点。"""
    return [
        {
            "endpoint_code": e.endpoint_code,
            "method": e.method,
            "path": e.path,
            "name": e.name,
            "description": e.description,
            "tags": e.tags,
            "module": e.module,
        }
        for e in _BY_CODE.values()
    ]


def build_path_index(app) -> None:
    """app lifespan 中调用：扫描 app.router.routes 构建 _BY_PATH。

    与 @router.get / @router.post 完全解耦；装饰器只挂标记，
    由本函数在启动阶段反向解析 path/method。
    """
    from starlette.routing import Route
    _BY_PATH.clear()
    for route in app.routes:
        if not isinstance(route, Route):
            continue
        endpoint = getattr(route, "endpoint", None)
        meta = getattr(endpoint, EXPOSABLE_ATTR, None)
        if meta is None:
            continue
        for m in (route.methods or []):
            if m.upper() in {"HEAD", "OPTIONS"}:
                continue
            key = (m.upper(), route.path)
            if key in _BY_PATH:
                raise RuntimeError(
                    f"Duplicate exposable endpoint: {m.upper()} {route.path}"
                )
            _BY_PATH[key] = meta.endpoint_code
            updated = ExposableEndpoint(
                endpoint_code=meta.endpoint_code,
                method=m.upper(),
                path=route.path,
                name=meta.name,
                description=meta.description,
                tags=list(meta.tags),
                module=meta.module,
            )
            _BY_CODE[meta.endpoint_code] = updated