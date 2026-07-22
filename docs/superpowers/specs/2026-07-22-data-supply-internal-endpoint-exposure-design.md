# 数据供给模块：内部接口对外暴露（API Key + 签名复用）

**状态**：草案（待用户审阅）
**日期**：2026-07-22
**作者**：OpenCode

## 背景与动机

数据供给模块已经实现了 API Key + HMAC-SHA256 签名认证机制（`X-App-Key` / `X-Timestamp` / `X-Signature`），并对外暴露了 18 个手工编写的业务接口（`/api/v1/external/*`）。

当前限制：

- 仅 18 个特定的、由 `@register_external` 显式注册的业务接口支持外部 API Key 调用；
- 所有其他内部接口（`/api/v1/orders/*`、`/api/v1/materials/*`、`/api/v1/production/*` 等）只接受 JWT；
- 内部接口的设计目标是面向登录用户，未考虑「外部系统调用方」这一身份；
- 当业务方想要把一个新内部接口暴露给外部时，需要在 `external/endpoints/` 下复制一份 handler、改响应字段包装方式、维护两份容易漂移的代码。

## 目标

让**已经存在的内部接口**也支持外部系统通过 app_key/app_secret 签名调用，复用数据供给模块的现有 HMAC 认证与审计机制。

非目标（本轮不交付）：

- 不修改任何现有业务接口的代码（仅作为 0-touch 验证）；
- 不在本轮大量新增 `@exposable` 标记（仅交付机制本身 + 1 个冒烟用例）；
- 不改造 `app_secret` 的存储方式；
- 不启用 `rate_limit` 强制；
- 不暴露写类端点（即便机制支持，默认仅 GET）；
- 不重写现有 `external/*` 接口。

## 设计概述

### 总体策略

引入「@exposable 装饰器 + AuthContext 双依赖」机制，使任意内部 GET 接口可在不改源代码的前提下接受 API Key + HMAC 签名；外部系统调用仍走原 URL，路由层根据请求头自动选择鉴权方式。

### 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 暴露范围 | 可配置 + 按端点勾选（admin UI 控制） | 灵活、零代码侵入 |
| 实现架构 | 路由复用 + 鉴权双选（Detect-and-Choice） | 零代码重复、复用现有依赖模式 |
| 装饰器注册 | 装饰器静态注册 `@exposable("int:code", ...)` | 简单可控、与现有 `@register_external` 同源 |
| 对外路径 | 仍走原路径 | 路径一致、Swagger 文档同一份 |
| Code 命名 | `int:` 前缀区分（与现有 external 不冲突） | 复用 `allowed_endpoints_json`，避免新建字段 |
| 最小范围 | 仅交付认证机制 + 冒烟用例 | 验证可行，后续业务自行追加 |

## 详细设计

### 1. @exposable 装饰器

**位置**：`backend/app/services/basicdata/exposable_registry.py`

装饰器**仅在函数对象上挂标记**，路径与方法不由装饰器收集，而是在 app 启动 `lifespan` 阶段通过扫描 `app.router.routes` 解析。这样与 `@router.get(...)` / `@router.post(...)` 等正常 FastAPI 装饰器**解耦**，调用方写作 `@router.get(...) @exposable(...)` 两层叠加（外层是 router，内层是 exposable）。

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ExposableEndpoint:
    endpoint_code: str        # 唯一；"int:<domain>.<verb>"
    method: str               # GET / POST / ...   ← 启动时由 lifespan 填充
    path: str                 # 模板化路径，启动时由 lifespan 填充
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    module: str = ""

# 装饰期只挂标记，不解析 path/method；启动时填实。
_BY_CODE: dict[str, ExposableEndpoint] = {}
_BY_PATH: dict[tuple[str, str], str] = {}  # (METHOD, path) → code，lifespan 时构建

EXPOSABLE_ATTR = "__exposable_meta__"

def exposable(
    endpoint_code: str,
    name: str,
    description: str = "",
    tags: Optional[list[str]] = None,
):
    """装饰器：标记一个内部端点可被外部 API Key 调用。
    
    端点 code 必须以 "int:" 前缀，与现有 external endpoint_code 区分。
    与 FastAPI router 装饰器叠加使用，例如：
    
        @router.get("/orders/list")
        @exposable("int:orders.list", name="订单列表")
        async def list_orders(...): ...
    
    启动时由 lifespan 扫描 app.router.routes 反向解析 path/method 并填充 _BY_PATH。
    """
    if not endpoint_code.startswith("int:"):
        raise ValueError(f"endpoint_code must start with 'int:': {endpoint_code}")
    if endpoint_code in _BY_CODE:
        raise ValueError(f"Duplicate endpoint_code: {endpoint_code}")

    def decorator(func):
        if hasattr(func, EXPOSABLE_ATTR):
            raise ValueError(f"Function already marked exposable: {func.__name__}")
        e = ExposableEndpoint(
            endpoint_code=endpoint_code,
            method="",            # 启动时填
            path="",              # 启动时填
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
    """运行时用：根据 method + 实际请求路径查找 endpoint_code。"""
    return _BY_PATH.get((method.upper(), path))


def list_exposable_endpoints() -> list[dict]:
    """admin UI 列表用，返回全部已注册 @exposable 端点。"""
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
    """在 app lifespan 中调用：扫描 app.router.routes，重建 _BY_PATH。"""
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
            _BY_PATH[(m.upper(), route.path)] = meta.endpoint_code
            # 用 path_template 更新 _BY_CODE 中对应记录
            updated = ExposableEndpoint(
                endpoint_code=meta.endpoint_code,
                method=m.upper(),
                path=route.path,
                name=meta.name,
                description=meta.description,
                tags=meta.tags,
                module=meta.module,
            )
            _BY_CODE[meta.endpoint_code] = updated
```

**端点 code 命名规范**：`int:<domain>.<verb>`，例如 `int:orders.list`、`int:materials.detail`、`int:production.schedule`。

### 2. AuthContext + 双鉴权依赖

**位置**：`backend/app/core/dependencies.py` 新增

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class AuthContext:
    """统一鉴权上下文。
    
    既支持 JWT 路径（user 非空），也支持 API Key 路径（api_key 非空）；
    恰好一个非空。便于 handler 内统一取用 request.state.auth_context。
    """
    user: Optional[object] = None
    api_key: Optional[object] = None

    @property
    def is_api_key(self) -> bool:
        return self.api_key is not None

async def get_current_user_or_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """JWT 与 HMAC 二选一。
    
    优先级：
      1) 若请求头存在 X-App-Key，则走 HMAC 路径（外部调用方不容忍身份冒充）；
      2) 否则回退到 JWT。
    
    当 HMAC 命中时，request.state.current_user 被填为 sys_api_user（见 §3），
    使现有 PermissionChecker 不需要任何修改。
    """
    has_api_key_header = bool(request.headers.get("x-app-key"))
    if has_api_key_header:
        result = await _authenticate_via_api_key(request, db)
        if result is None:
            raise HTTPException(401, "Invalid API key or signature")
        api_key, sys_api_user = result
        request.state.current_user = sys_api_user
        request.state.auth_context = AuthContext(api_key=api_key, user=None)
        return request.state.auth_context

    # JWT 路径：完全复用现有 get_current_user 行为
    user = await get_current_user(request=request, db=db)
    request.state.current_user = user
    request.state.auth_context = AuthContext(user=user, api_key=None)
    return request.state.auth_context


async def _authenticate_via_api_key(request: Request, db: AsyncSession):
    """内部辅助：校验 X-App-Key/X-Timestamp/X-Signature 并返回 (api_key, sys_user)。"""
    from app.services.basicdata.data_supply_service import (
        validate_signature_for_exposable,
    )

    app_key = request.headers.get("x-app-key")
    timestamp = request.headers.get("x-timestamp")
    signature = request.headers.get("x-signature")

    # 1) 解析请求对应的 endpoint_code
    endpoint_code = _resolve_endpoint_code_from_request(request)
    if not endpoint_code:
        return None  # 路径未注册为 @exposable

    # 2) HMAC + allowed_endpoints_json 校验
    ok, api_key, error = await validate_signature_for_exposable(
        app_key=app_key,
        timestamp=timestamp,
        signature=signature,
        endpoint_code=endpoint_code,
        method=request.method,
        query_string=request.url.query,
        db=db,
    )
    if not ok:
        return None

    # 3) 加载 sys_api_user（仅一次）
    sys_api_user = await _get_or_load_sys_api_user(db)
    return api_key, sys_api_user


def _resolve_endpoint_code_from_request(request: Request) -> Optional[str]:
    """从当前请求反查 endpoint_code。

    实现要点：
      1. 优先用 request.scope["route"].path 拿到模板路径（如 "/orders/{order_id}"），
         不需要自实现 path matcher；
      2. 使用 lifespan 阶段构建的 _BY_PATH 索引（精确 (METHOD, template) → code）；
      3. 若中间件先于路由匹配执行、request.scope 中尚无 "route"，则按 status_code == 404
         透传给下一层——这种情况在本 dependency 中不会出现（dependency 在路由匹配后执行）。
    """
    from app.services.basicdata.exposable_registry import resolve_endpoint_code
    route = request.scope.get("route")
    if route is None:
        return None
    return resolve_endpoint_code(request.method, route.path)
```

### 3. system user 占位（避免改 PermissionChecker）

**位置**：`backend/init_database.py` 新增 seed

```python
# 系统级 API 调用占位用户
INS_INTERNAL_API_USER_ID = "sys-api-caller"
INS_API_CALLER_ROLE_ID = "role-api-caller"

# role: api_caller，permissions 等同 admin（覆盖所有 resource 的全部 action）
# user: sys-api-caller，login_type="system"，password 不可登录（仅作 RBAC 占位）
```

理由：

- 现有 internal handler 多通过 `PermissionChecker(resource, action)` 检查 RBAC；
- 当外部 API Key 命中时，让 handler 内的 `request.state.current_user` 是这个 sys_api_user，其 permissions 包含全部 resource → 所有 PermissionChecker 通过；
- handler **不需要任何代码改动**；
- `is_active=True` 但 `login_type="system"`，使其无法被用做普通登录。

### 4. validate_signature_for_exposable

**位置**：`backend/app/services/basicdata/data_supply_service.py` 新增

```python
async def validate_signature_for_exposable(
    app_key: str,
    timestamp: str,
    signature: str,
    endpoint_code: str,
    method: str,
    query_string: str,
    db: AsyncSession,
) -> tuple[bool, Optional[DataSupplyApiKey], Optional[str]]:
    """校验 @exposable 端点的 API Key 签名。
    
    与 validate_signature_for_endpoint 区别：
      - 不检查 DataSupplyConfig（内部接口不走 config）
      - 检查 allowed_endpoints_json 是否包含给定 endpoint_code（必须以 'int:' 前缀）
      - 其余 (TTL / IP / 失效) 与现有规则一致
    """
    # ... 实现复用 validate_signature_for_endpoint 的框架，做以下调整 ...
    # 1) 查 DataSupplyApiKey by app_key
    # 2) api_key.is_active & expires_at 未过期
    # 3) timestamp 在 ±300s 内
    # 4) endpoint_code.startswith("int:") and endpoint_code in allowed_endpoints_json
    # 5) IP 白名单
    # 6) HMAC compare_digest
    # 7) 返回 (True, api_key, None) 或 (False, None, "错误原因")
```

### 5. Admin UI 新增端点

**位置**：`backend/app/api/v1/basicdata/data_supply.py` 新增一个 handler

```python
@router.get("/exposable-internal-endpoints", response_model=ResponseModel[List[dict]])
async def list_exposable_internal_endpoints(
    _: User = Depends(PermissionChecker("basicdata.data_supply", "read")),
):
    """列出所有 @exposable 标记的内部端点，供 API Key 表单勾选。"""
    return ResponseModel(
        code=0, message="ok",
        data=list_exposable_endpoints(),
    )
```

路由前缀：`/api/v1/basicdata/data-supply/exposable-internal-endpoints`

### 6. Admin UI 改造

**位置**：`frontend/src/pages/BasicDataCenter/DataSupply/index.tsx`

在「API Key 表单」内（新建/编辑）增加区块「可调用的内部接口」：

- 数据来源：`GET /api/v1/basicdata/data-supply/exposable-internal-endpoints`
- UI 形态：Checkbox.Group + 按 `module` 折叠
- 提交时合并进 `allowed_endpoints_json`：`["int:orders.list", "int:materials.detail", ...]`
- 与现有「可调用的对外接口」（即 `allowed_endpoints_json` 现存部分）**合并在同一个字段**，通过 `int:` 前缀区分

### 7. 冒烟用例：本轮唯一标记的 `@exposable` 端点

为了验证本轮机制，建议在本轮提交一个**最简** `@exposable` 端点，用于联调：

```python
# app/api/v1/common/health.py （或类似 health 模块；新建或复用）
@router.get("/ping")
@exposable(
    endpoint_code="int:health.ping",
    name="健康检查（外部）",
    description="供外部系统联调签名机制使用",
    tags=["health"],
)
async def ping_int():
    return ResponseModel(code=0, message="pong", data={"ok": True})
```

路由：`GET /api/v1/common/ping`，标记后：

- 内部用户用 JWT 调用照常返回 `pong`；
- 外部系统用 X-App-Key 签名调用返回同样 `pong`，并写入 `DataSupplyCallLog`；
- Admin UI 的 API Key 表单能看到这条 `int:health.ping` 可选项。

若该健康端点已存在路由文件，则就近追加；否则新建 `backend/app/api/v1/common/__init__.py` + `health.py` 即可。

## 调用流程（外部系统视角）

```
外部系统                                  SPC 后端
GET /api/v1/orders/list?status=open
  Headers:
    X-App-Key:     ak_xxxxxxxxxxxxxx
    X-Timestamp:   1719999999
    X-Signature:   hex(HMAC_SHA256(
                       timestamp + app_key
                       + "int:orders.list"
                       + canonical_query))
       
                                       → middleware 命中 internal route
                                       → get_current_user_or_api_key 选 HMAC
                                       → 校验签名/时间戳/IP/白名单
                                       → allowed_endpoints_json 包含 "int:orders.list"
                                       → 注入 sys-api-caller 给 PermissionChecker
                                       → 现有 handler 执行（同源代码）
                                       → 写 DataSupplyCallLog (data_type="int:orders.list")
                                       → 返回 JSON 信封 {code, message, data}
```

Swagger 上同一 URL 显示相同接口定义与字段。

## 交付清单（最小可用）

| # | 位置 | 改动 |
|---|---|---|
| 1 | `backend/app/services/basicdata/exposable_registry.py` | 新增装饰器 + 内存注册表 + `list_exposable_endpoints()` |
| 2 | `backend/app/core/dependencies.py` | 新增 `AuthContext` + `get_current_user_or_api_key` |
| 3 | `backend/app/services/basicdata/data_supply_service.py` | 新增 `validate_signature_for_exposable(...)` |
| 4 | `backend/init_database.py` | 新增 `role-api-caller` 角色 + `sys-api-caller` user；权限合并进 admin |
| 5 | `backend/app/api/v1/basicdata/data_supply.py` | 新增 `GET /exposable-internal-endpoints` 端点 |
| 6 | `frontend/src/pages/BasicDataCenter/DataSupply/index.tsx` | API Key 表单内增加「可调用内部接口」勾选区块 |
| 7 | `backend/app/api/v1/common/health.py`（如不存在则新建） | 新增 `/ping` 路由 + `@exposable("int:health.ping")` 冒烟用例 |
| 8 | `backend/test_internal_exposable.py` | 一个独立测试脚本，模拟外部系统签名调用 `/ping` 并断言成功 |

lifespan 钩子：

```python
# backend/app/main.py 的 lifespan 内（紧随 permission_registry 重建之后追加）
from app.services.basicdata.exposable_registry import build_path_index

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... 原有初始化 ...
    build_path_index(app)        # ← 新增：构建 _BY_PATH 索引
    # ... APScheduler start ...
    yield
    # ... APScheduler shutdown ...
```

## 数据库迁移

本轮新增的字段（如有）与 seed user/role 一同在 `init_database.py` 中以幂等方式创建（参考现有 roles/users 的 seed 模式）。`migrate_columns` 不需要新增——sys-api-caller 是 seed，不是列新增。

如果发现 `DataSupplyApiKey.allowed_endpoints_json` 列已经存在（已存在，见 §背景），则**不需要迁移**。

## 风险与缓解

| 风险 | 缓解 |
|---|---|---|
| sys-api-caller 拥有 admin 全权限，误用时可能绕过 RBAC | 该 user `login_type=system`、`password` 不可登录；仅作后端 RBAC 占位，前端登录接口拒绝 |
| 同一 URL 同时被 JWT 和 X-App-Key 调用，行为应可预测 | 文档明确：X-App-Key 出现时优先 HMAC；JWT 仅在无 X-App-Key 时生效 |
| `_BY_CODE` 是进程内内存，注册信息启动时收集 | 启动时通过 `app/main.py` 的 `lifespan` 一次性扫描各路由模块；与现有 `@register_external` 共存 |
| 路径反查依赖 `request.scope["route"].path` 拿到模板路径 | 该方式由 FastAPI/Starlette 路由匹配阶段自动写入 scope，对 `{param}` 段原样返回；自实现的 path matcher 已剔除，避免路径语法不兼容 |
| `_BY_PATH` 在 lifespan 阶段一次性构建，路由若在之后动态注册会查不到 | uvicorn 当前路由全部在导入阶段静态注册；如有动态注册场景需扩展 `register_route` 钩子，目前无场景 |
| `request.scope["route"]` 在异常路径/中间件提前抛错时可能缺失 | `_resolve_endpoint_code_from_request` 在 route 为 None 时返回 None；HMAC 路径视为「未暴露」，回退到 401，由调用方感知「该路径不对外」 |

## 验证方法

1. **后端冒烟**：运行 `python backend/test_internal_exposable.py`：
   - 用 admin 账号登录拿 JWT；
   - 用 JWT 调 `/api/v1/common/ping`，断言 200；
   - 创建一条 `DataSupplyApiKey`，勾选 `int:health.ping`；
   - 用 X-App-Key/X-Signature 调 `/api/v1/common/ping`，断言 200；
   - 断言 `DataSupplyCallLog` 出现一条 `data_type=int:health.ping`。

2. **Swagger 验证**：浏览器打开 `/docs`，访问 `GET /api/v1/common/ping`，确认参数定义没有变化（仍按现有 schema 展示）。

3. **前端 UI 验证**：登录 admin → `/basicdata/data-supply` → API Key 新建表单，可见「健康检查（外部）」勾选项；勾选并保存后，`allowed_endpoints_json` 内出现 `"int:health.ping"`。

4. **回归**：`npm run build` 通过；其他内部接口的 JWT 调用不受影响（手动测 1-2 条）。

## 不在本轮（YAGNI）

- 不实现 rate_limit 强制；
- 不改 `app_secret` 加密存储；
- 不暴露写类端点（POST/PUT/DELETE）；
- 不批量迁移现存量大接口；
- 不在响应包里加额外段（如 `X-Supply-Source: api-key|jwt` 响应头标记）—— 后续可加；
- 不迁移现有 `/api/v1/external/*` 业务接口到这套新机制——保留双轨。
