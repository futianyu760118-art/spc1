# 数据供给模块：内部接口对外暴露 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 `数据供给` 的 API Key + HMAC 签名机制能够覆盖**已存在的内部 GET 接口**，外部系统可通过 `X-App-Key` / `X-Timestamp` / `X-Signature` 调用同 URL，无需复制 handler，无需业务接口代码改动。

**Architecture:**
- 新增 `@exposable("int:<domain>.<verb>", ...)` 装饰器（仅挂标记到函数对象，`method`/`path` 由 lifespan 阶段扫描 `app.router.routes` 反填）。
- 新增 `get_current_user_or_api_key` 依赖：若请求带 `X-App-Key` 头则走 HMAC 路径，否则回退到 JWT；HMAC 命中时把 `request.state.current_user` 填充为一个拥有全部权限的 system user，使现有 `PermissionChecker` 无需修改即可放行。
- 新增 `validate_signature_for_exposable` 签名校验函数（复用 `validate_signature_for_endpoint` 框架，仅校验 `allowed_endpoints_json` 是否含 `int:<code>`，不查 `DataSupplyConfig`）。

**Tech Stack:**
- 后端：Python 3.12、FastAPI、SQLAlchemy async（asyncpg）、Pydantic、HMAC-SHA256
- 前端：React + TypeScript + Ant Design 5 + Zustand
- 数据库：PostgreSQL
- 测试：`backend/test_internal_exposable.py`（独立脚本，模拟外部签名调用）

**Spec 文档：** `docs/superpowers/specs/2026-07-22-data-supply-internal-endpoint-exposure-design.md`

---

## Global Constraints

- 后端 Python 3.12，路径均为 `backend/` 下相对路径；前端改动均在 `frontend/` 下。
- 不修改任何现有业务 handler 代码。
- 不在本轮批量新增 `@exposable` 标记（仅交付机制 + 1 个冒烟用例 `int:health.ping`）。
- 不暴露 POST/PUT/DELETE（本轮仅 GET，签名层面已支持，约定层面不允许）。
- 现有 `external/*` 业务接口继续按原状工作，不并轨。
- 所有响应必须返回 `{code, message, data}` 信封（`ResponseModel`）。
- 不写 `pytest`/vitest，新交付用 `backend/test_internal_exposable.py` 独立脚本验证。
- 前端 `npm run build` 是唯一 typecheck，本轮交付后必须通过。
- 新增列/字段：必须在 `init_database.py` 的 `migrate_columns`（如有表新增）或 seed 中维护，保持 AGENTS.md 的「运行时源真值」模式。
- **追加「显式互斥」**：当 `X-App-Key` 命中时，忽略任何 `Authorization: Bearer ...` 头（防意外）；JWT-only 路径不受影响。

---

## Task 1：创建 @exposable 装饰器与内存注册表

**Files:**
- 新建：`backend/app/services/basicdata/exposable_registry.py`

**Step 1：写文件**

完整内容：

```python
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
    endpoint_code: str        # 唯一；必须以 "int:" 前缀
    method: str               # 启动时由 lifespan 填：GET / POST / ...
    path: str                 # 启动时由 lifespan 填：模板路径
    name: str
    description: str = ""
    tags: list = field(default_factory=list)
    module: str = ""


# 装饰期只挂标记，method/path 启动时由 build_path_index 填
_BY_CODE: dict = {}
# (METHOD_UPPER, path_template) -> endpoint_code；lifespan 时构建
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
            _BY_PATH[(m.upper(), route.path)] = meta.endpoint_code
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
```

**Step 2：语法静态检查**

```bash
cd backend && python -c "from app.services.basicdata.exposable_registry import exposable, list_exposable_endpoints, build_path_index, resolve_endpoint_code; print('ok')"
```

Expected：`ok`（仅能导入，不应在启动前调用装饰器逻辑）。

**Step 3：commit**

```bash
git add backend/app/services/basicdata/exposable_registry.py
git commit -m "feat(data-supply): add @exposable decorator for internal endpoint exposure"
```

---

## Task 2：在 lifespan 中构建 @exposable path 索引

**Files:**
- 修改：`backend/app/main.py`

**Step 1：在 `lifespan` 函数内（紧贴 permission 同步之后、`scheduler.start()` 之前）插入一行**

完整定位：找到 `await sync_permissions_to_db(db)` 之后、`except Exception as e:` 之前；找到 `scheduler.start()` 之前。在两个之间插入：

```python
    # 启动时：构建 @exposable 内部接口路径索引
    try:
        from app.services.basicdata.exposable_registry import build_path_index
        build_path_index(app)
        from app.services.basicdata.exposable_registry import list_exposable_endpoints
        logger.info(f"[Exposable] 已注册 {len(list_exposable_endpoints())} 个内部可暴露接口")
    except Exception as e:
        logger.warning(f"[Exposable] 构建内部可暴露接口索引失败: {e}")
```

具体插入位置：见文件 `backend/app/main.py:96` 附近。完整修改片段：

```python
            except Exception as e:
                logger.warning(f"[权限注册] 清理废弃权限失败: {e}")
            # 清理上次未完成的同步任务（服务重启导致的僵尸 running/pending 任务）
            try:
                ...
            except Exception as e:
                logger.warning(f"[启动] 清理中断同步任务失败: {e}")
    except Exception as e:
        logger.warning(f"[权限注册] 同步权限定义失败: {e}")
    # ← NEW: 构建 @exposable 内部接口路径索引
    try:
        from app.services.basicdata.exposable_registry import build_path_index, list_exposable_endpoints
        build_path_index(app)
        logger.info(f"[Exposable] 已注册 {len(list_exposable_endpoints())} 个内部可暴露接口")
    except Exception as e:
        logger.warning(f"[Exposable] 构建内部可暴露接口索引失败: {e}")
    # 启动时：开启 ERP 定时同步
    scheduler.start()
```

**Step 2：验证（仅语法 + 模块加载）**

```bash
cd backend && python -c "import app.main; print('ok')" 2>&1 | head -20
```

Expected：输出 `ok` 或权限/Scheduler 类的初始化日志（若有缺失依赖会显式报错）。

**Step 3：commit**

```bash
git add backend/app/main.py
git commit -m "feat(data-supply): build @exposable path index on app lifespan"
```

---

## Task 3：seed `sys-api-caller` system user 与 `api_caller` role

**Files:**
- 修改：`backend/init_database.py`

**Step 1：在 `seed_users` 函数（约 line 888）尾部追加**

在 `await session.commit(); print("System users seeded/updated successfully")` **之前**追加一段 seed 代码，确保幂等：

```python
                # ── 系统级 API 调用占位用户 ──
                # 用于数据供给模块 API Key + HMAC 命中后，
                # 注入 request.state.current_user 使现有 PermissionChecker 无需修改即可放行。
                api_caller_role = await session.execute(
                    text("SELECT id FROM sys_role WHERE role_code = 'api_caller'")
                )
                api_caller_role_id = api_caller_role.scalar()
                if not api_caller_role_id:
                    # admin 拥有的全部 resource 全集拷贝，确保通过任意 PermissionChecker
                    admin_role_row = await session.execute(
                        select(SysRole).where(SysRole.role_code == "admin")
                    )
                    admin_role_obj = admin_role_row.scalar_one_or_none()
                    api_caller_perms = dict(admin_role_obj.permissions) if admin_role_obj and admin_role_obj.permissions else {}
                    new_role = SysRole(
                        role_code="api_caller",
                        role_name="外部API调用方（系统占位）",
                        permissions=api_caller_perms,
                    )
                    session.add(new_role)
                    await session.flush()
                    api_caller_role_id = new_role.id

                sys_api_user_row = await session.execute(
                    select(SysUser).where(SysUser.username == "sys-api-caller")
                )
                if not sys_api_user_row.scalar_one_or_none():
                    # 占位 user：password 不可登录（hash 一个永不会匹配的值）
                    import hashlib
                    dead_hash = hashlib.sha256(b"__never_login__" + b"sys-api-caller").hexdigest()
                    session.add(SysUser(
                        username="sys-api-caller",
                        display_name="外部API调用方（系统占位）",
                        hashed_password=dead_hash,
                        role_id=api_caller_role_id,
                        is_active=True,
                    ))
```

**Step 2：保证 import**

确认 `SysRole`、`SysUser` 已在文件顶部 import（grep 已知）

```bash
grep -n "^from app.models.basicdata.user" backend/init_database.py
```

Expected：能看到 `from app.models.basicdata.user import SysUser, SysRole`（已存在，无需新增 import）。

**Step 3：冒烟**

```bash
cd backend && python init_database.py 2>&1 | tail -30
```

Expected：能看到 `seed_users` 段的 success log；再执行一次仍然幂等不报错。

**Step 4：commit**

```bash
git add backend/init_database.py
git commit -m "feat(data-supply): seed sys-api-caller user + api_caller role (idempotent)"
```

---

## Task 4：实现 `validate_signature_for_exposable`

**Files:**
- 修改：`backend/app/services/basicdata/data_supply_service.py`

**Step 1：在文件末尾（约 line 506）追加**

```python
async def validate_signature_for_exposable(
    db: AsyncSession,
    app_key: str,
    signature: str,
    timestamp: str,
    endpoint_code: str,
    request_query_string: str = "",
) -> tuple:
    """验证 HMAC-SHA256 签名是否可调用指定 @exposable 内部接口。

    与 validate_signature_for_endpoint 区别：
      - 不检查 DataSupplyConfig（内部接口不走 config）
      - 检查 allowed_endpoints_json 是否包含 endpoint_code（必须以 'int:' 前缀）
      - 其余 (TTL / 失效 / IP 由调用方处理) 与现有规则一致
    """
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return None, "时间戳格式无效（应为整数秒）"

    now = int(time.time())
    if abs(now - ts) > SIGNATURE_TTL:
        return None, f"时间戳超出有效期（服务器时间戳 {now}，允许偏差 ±{SIGNATURE_TTL}s）"

    if not endpoint_code.startswith("int:"):
        return None, f"endpoint_code 必须是 'int:' 前缀: {endpoint_code}"

    result = await db.execute(
        select(DataSupplyApiKey).where(DataSupplyApiKey.app_key == app_key)
    )
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        return None, "AppKey 不存在"
    if not key_obj.is_active:
        return None, "API Key 已禁用"
    if not key_obj.app_secret:
        return None, "该 API Key 未配置 AppSecret"
    if key_obj.expires_at and key_obj.expires_at < datetime.now():
        return None, "API Key 已过期"

    # 复用 _key_has_endpoint_access：allowed_endpoints_json 是否含该 endpoint_code
    if not _key_has_endpoint_access(key_obj, endpoint_code):
        return None, f"API Key 未授权调用接口 {endpoint_code}"

    # 与 external 端点签名串一致：timestamp + app_key + endpoint_code + query
    string_to_sign = f"{timestamp}{app_key}{endpoint_code}{request_query_string}"
    expected_sig = hmac.new(
        key_obj.app_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return None, (
            f"签名不匹配。待签名串 = timestamp+app_key+endpoint_code+query_string "
            f"= '{timestamp}{app_key}{endpoint_code}{request_query_string}'"
        )
    return key_obj, ""
```

**Step 2：导入与行尾**

文件顶部 `from datetime import datetime` 已存在；`hmac`, `hashlib`, `time`, `json`, `select` 已存在；不要重复 import。

**Step 3：冒烟**

```bash
cd backend && python -c "
import asyncio
from app.services.basicdata.data_supply_service import validate_signature_for_exposable
print('import ok:', validate_signature_for_exposable.__name__)
"
```

Expected：`import ok: validate_signature_for_exposable`

**Step 4：commit**

```bash
git add backend/app/services/basicdata/data_supply_service.py
git commit -m "feat(data-supply): add validate_signature_for_exposable for internal endpoints"
```

---

## Task 5：实现 `get_current_user_or_api_key` 鉴权依赖

**Files:**
- 修改：`backend/app/core/dependencies.py`

**Step 1：在文件末尾追加**

```python
@dataclass
class AuthContext:
    """统一鉴权上下文：JWT 与 API Key 二选一。"""
    user: Optional[dict] = None
    api_key: object = None

    @property
    def is_api_key(self) -> bool:
        return self.api_key is not None


async def _get_or_load_sys_api_user(db: AsyncSession):
    """加载 sys-api-caller 占位用户。"""
    result = await db.execute(
        select(SysUser).where(SysUser.username == "sys-api-caller")
    )
    user = result.scalar_one_or_none()
    if not user:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="sys-api-caller 占位用户未初始化，请运行 init_database.py",
        )

    # 复用 _build_user_info，得到完整 user dict
    return await _build_user_info(
        db, user,
        user_id=str(user.id),
        username="sys-api-caller",
        role="api_caller",
        supplier_code=None,
    )


def _resolve_endpoint_code_from_request(request: Request) -> Optional[str]:
    """从当前请求反查 endpoint_code。

    依赖 FastAPI/Starlette 在路由匹配后写入 request.scope['route']。
    """
    from app.services.basicdata.exposable_registry import resolve_endpoint_code
    route = request.scope.get("route")
    if route is None:
        return None
    return resolve_endpoint_code(request.method, route.path)


async def _authenticate_via_api_key(request: Request, db: AsyncSession):
    """返回 (api_key_obj, sys_api_user_dict)；失败返回 None。"""
    from app.services.basicdata.data_supply_service import (
        validate_signature_for_exposable,
        check_ip_whitelist,
    )

    app_key = request.headers.get("x-app-key")
    timestamp = request.headers.get("x-timestamp")
    signature = request.headers.get("x-signature")
    if not (app_key and timestamp and signature):
        return None

    endpoint_code = _resolve_endpoint_code_from_request(request)
    if not endpoint_code:
        return None  # 路径未通过 @exposable 注册

    key_obj, reason = await validate_signature_for_exposable(
        db, app_key, signature, timestamp, endpoint_code,
        request_query_string=str(request.url.query),
    )
    if not key_obj:
        return None

    # IP 白名单
    client_ip = request.client.host if request.client else None
    if client_ip and not check_ip_whitelist(key_obj, client_ip):
        return None

    sys_user = await _get_or_load_sys_api_user(db)
    return key_obj, sys_user


async def get_current_user_or_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """JWT 与 HMAC 二选一。

    优先级：
      1) 请求头存在 X-App-Key → HMAC（外部调用不容忍身份冒充）；
      2) 否则 → JWT。

    HMAC 命中时把 request.state.current_user 设为 sys-api-caller（拥有全部权限），
    使现有 PermissionChecker 无需修改。
    """
    if request.headers.get("x-app-key"):
        result = await _authenticate_via_api_key(request, db)
        if result is None:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key 签名认证失败或该路径未对外开放",
            )
        key_obj, sys_user = result
        request.state.current_user = sys_user
        request.state.auth_source = "api_key"
        return sys_user

    # JWT 路径
    user = await get_current_user(request=request, db=db)
    request.state.current_user = user
    request.state.auth_source = "jwt"
    return user
```

顶部追加 `from dataclasses import dataclass` 和 `from typing import Optional`，并 `from fastapi import Request`。

**Step 2：冒烟（仅导入）**

```bash
cd backend && python -c "
from app.core.dependencies import get_current_user_or_api_key, AuthContext
print('ok')
"
```

Expected：`ok`

**Step 3：commit**

```bash
git add backend/app/core/dependencies.py
git commit -m "feat(data-supply): add get_current_user_or_api_key dual-auth dependency"
```

---

## Task 6：admin 端点 `GET /exposable-internal-endpoints`

**Files:**
- 修改：`backend/app/api/v1/basicdata/data_supply.py`

**Step 1：在文件末尾追加一个 handler**

```python
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
```

**Step 2：检查 imports**

`ResponseModel`、`Depends`、`PermissionChecker` 应已在文件头部 import。检查：

```bash
grep -n "^from\|^import" backend/app/api/v1/basicdata/data_supply.py | head -20
```

Expected：能看到 `from app.core.permissions import PermissionChecker` 与 `from app.schemas.common import ResponseModel`（如果缺，则追加）。

**Step 3：commit**

```bash
git add backend/app/api/v1/basicdata/data_supply.py
git commit -m "feat(data-supply): admin endpoint to list exposable internal endpoints"
```

---

## Task 7：冒烟端点 `/api/v1/common/ping`

**Files:**
- 新建：`backend/app/api/v1/common/__init__.py`（如果不存在）
- 新建：`backend/app/api/v1/common/health.py`
- 修改：`backend/app/api/v1/__init__.py`（挂载 common 路由器）

**Step 1：创建 `backend/app/api/v1/common/__init__.py`（空文件）**

```python
"""common 模块：跨域通用接口（健康检查、字典、对外 ping 等）。"""
```

**Step 2：创建 `backend/app/api/v1/common/health.py`**

完整内容：

```python
"""通用健康检查 / 对外联调用 ping 端点。"""

from fastapi import APIRouter

from app.schemas.common import ResponseModel
from app.services.basicdata.exposable_registry import exposable


router = APIRouter()


@router.get("/ping")
@exposable(
    endpoint_code="int:health.ping",
    name="健康检查（对外签名联调）",
    description="供外部系统验证 HMAC 签名机制是否正确配置",
    tags=["health"],
)
async def ping():
    """JWT 与 HMAC 均可调用。

    - JWT 用户：按现有规则返回（要求登录）。
    - API Key + X-App-Key 签名：要求 enabled=1 且 allowed_endpoints_json 含 'int:health.ping'。
    """
    return ResponseModel(code=0, message="pong", data={"ok": True})
```

**Step 3：在 `backend/app/api/v1/__init__.py` 中挂载**

找到现有 `api_router.include_router(...)` 段（约 line 72 后），追加：

```python
from app.api.v1.common import health as common_health  # noqa: E402
api_router.include_router(common_health.router, prefix="/common", tags=["common"])
```

并在文件顶部确认导入 `from app.api.v1 import common` 不与已有 `from app.api.v1 import basicdata, ...` 冲突——基本不冲突，但 Python 不接受同名字段。若 `common` 模块名冲突，则改为：

```python
import app.api.v1.common.health as common_health_module
api_router.include_router(common_health_module.router, prefix="/common", tags=["common"])
```

**Step 4：本地启服验证 JWT 路径**

```bash
# 后端启动（一个后台会话，或现有 uvicorn 仍在运行）
curl -s http://localhost:8000/api/v1/common/ping -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Expected：`{"code": 0, "message": "pong", "data": {"ok": true}}`（其中 `$TOKEN` 是有效 admin JWT——若没有也可以不带 token 观察 401，确认路由可达）。

**Step 5：commit**

```bash
git add backend/app/api/v1/common/
git add backend/app/api/v1/__init__.py
git commit -m "feat(data-supply): add GET /api/v1/common/ping for external signature smoke test"
```

---

## Task 8：前端 API Key 表单增加「内部可暴露接口」勾选

**Files:**
- 修改：`frontend/src/services/api.ts`（新增 `listExposableInternalEndpoints`）
- 修改：`frontend/src/pages/BasicDataCenter/DataSupply/index.tsx`（表单字段 + 提交合并）

**Step 1：在 `frontend/src/services/api.ts` 找到 `dataSupplyApi` 段（约 line 433-448），新增一个方法**

```typescript
  listExposableInternalEndpoints: () =>
    request.get('/basicdata/data-supply/exposable-internal-endpoints'),
```

**Step 2：在 `DataSupply/index.tsx` 中**

a) 在已有 `endpointOptions` 的 `useEffect` 旁边（约 line 285 一带）新增：

```typescript
  const [internalEndpointOptions, setInternalEndpointOptions] = useState<ApiEndpoint[]>([])

  useEffect(() => {
    if (!apiKeyModalOpen) return
    dataSupplyApi.listExposableInternalEndpoints()
      .then((res: any) => {
        const list = res?.data?.data || res?.data || []
        setInternalEndpointOptions(list)
      })
      .catch(() => setInternalEndpointOptions([]))
  }, [apiKeyModalOpen])
```

b) 表单 `Form.Item name="allowed_endpoints"` 之后新增区块：

```tsx
          <Form.Item
            name="allowed_internal_endpoints"
            label="允许调用的内部接口"
            tooltip="控制 @exposable 标记的内部接口的调用权限，使用 int: 前缀；与对外接口在同一字段"
          >
            <Select
              mode="multiple"
              placeholder="选择允许调用的内部接口"
              optionLabelProp="label"
              options={internalEndpointOptions.map(e => ({
                value: e.endpoint_code,
                label: e.name,
                title: `${e.method} ${e.path} — ${e.description}`,
              }))}
              optionRender={(option) => {
                const ep = internalEndpointOptions.find(e => e.endpoint_code === option.value)
                if (!ep) return option.label
                return (
                  <Space direction="vertical" size={0}>
                    <Space size={6}>
                      <Tag color="green" style={{ margin: 0 }}>{ep.method}</Tag>
                      <Text strong>{ep.name}</Text>
                      {ep.tags?.map(t => <Tag key={t} style={{ margin: 0 }}>{t}</Tag>)}
                    </Space>
                    <Text type="secondary" style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))' }}>{ep.path}</Text>
                  </Space>
                )
              }}
            />
          </Form.Item>
```

c) `handleSaveApiKey` 中合并 `allowed_internal_endpoints` 到 `allowed_endpoints_json`：

找到现有的 `JSON.stringify(values.allowed_endpoints || [])`，替换为：

```typescript
          allowed_endpoints_json: JSON.stringify([
            ...(values.allowed_endpoints || []),
            ...(values.allowed_internal_endpoints || []),
          ]),
```

两处（创建与编辑）都要改。

d) 在 `parseArr` 或 `allowed_endpoints` 初始值（line 495 一带）拆分恢复时：

```typescript
      const allAllowed = key.allowed_endpoints_json ? JSON.parse(key.allowed_endpoints_json) : []
      const external = allAllowed.filter((s: string) => !s.startsWith('int:'))
      const internal = allAllowed.filter((s: string) => s.startsWith('int:'))
      // 表单字段分别赋值 external 与 internal
      // ...setFieldsValue({ allowed_endpoints: external, allowed_internal_endpoints: internal })
```

完整融入现有 `setFieldsValue` 调用即可。

**Step 3：类型**

`ApiEndpoint` 类型若未在文件顶部声明，则在顶部添加：

```typescript
type ApiEndpoint = {
  endpoint_code: string
  name: string
  description?: string
  method: string
  path: string
  tags?: string[]
}
```

**Step 4：build**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected：`built in X.XXs`（无 TS 错误）。

**Step 5：commit**

```bash
git add frontend/src/services/api.ts
git add frontend/src/pages/BasicDataCenter/DataSupply/index.tsx
git commit -m "feat(data-supply): API Key form supports internal exposable endpoint selection"
```

---

## Task 9：独立测试脚本 `backend/test_internal_exposable.py`

**Files:**
- 新建：`backend/test_internal_exposable.py`

**Step 1：写文件**

完整内容：

```python
"""数据供给模块「内部接口对外暴露」机制联调脚本。

执行：
    cd backend && python test_internal_exposable.py

前置：
    - uvicorn 已启动（监听 8000 端口）
    - 已运行 init_database.py（包含 sys-api-caller 与 api_caller seed）
    - 默认 admin 用户存在
"""

import hashlib
import hmac
import json
import time
import requests  # type: ignore

BASE = "http://localhost:8000/api/v1"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
APP_KEY = "ak_smoketest0001"
APP_SECRET = "secret_smoketest0001_xyz"


def _sign(timestamp: str, app_key: str, endpoint_code: str, query: str) -> str:
    s = f"{timestamp}{app_key}{endpoint_code}{query}"
    return hmac.new(APP_SECRET.encode(), s.encode(), hashlib.sha256).hexdigest()


def login() -> str:
    r = requests.post(
        f"{BASE}/basicdata/auth/login",
        data={"login_type": "employee", "username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def create_api_key(token: str):
    r = requests.post(
        f"{BASE}/basicdata/data-supply/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key_name": "smoke-internal-exposable",
            "description": "smoke test for internal endpoint exposure",
            "allowed_data_types": [],
            "allowed_endpoints": ["int:health.ping"],
            "rate_limit": 100,
            "ip_whitelist": "",
            "expires_at": None,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]


def call_with_api_key(method: str, path: str, endpoint_code: str, query: str = ""):
    ts = str(int(time.time()))
    sig = _sign(ts, APP_KEY, endpoint_code, query)
    return requests.request(
        method,
        f"{BASE}{path}",
        params=dict(x.split("=", 1) for x in query.split("&") if x) if query else None,
        headers={
            "X-App-Key": APP_KEY,
            "X-Timestamp": ts,
            "X-Signature": sig,
        },
        timeout=10,
    )


def assert_ok(resp: requests.Response, expect_msg: str):
    body = resp.json()
    assert body.get("code") == 0, f"FAIL: {expect_msg}, got {body}"
    print(f"PASS: {expect_msg} → {body}")


def main():
    print("=== 冒烟：数据供给 内部接口对外暴露 ===")

    # 1) admin JWT 登录
    token = login()
    print(f"PASS: admin JWT login")

    # 2) 创建 API Key（勾选 int:health.ping）
    ak = create_api_key(token)
    print(f"PASS: API Key created id={ak.get('id')}")

    # 3) JWT 调 /api/v1/common/ping（应正常返回 pong）
    r = requests.get(f"{BASE}/common/ping", headers={"Authorization": f"Bearer {token}"})
    assert_ok(r, "JWT 路径调用 /common/ping")

    # 4) HMAC 调 /api/v1/common/ping（应正常返回 pong）
    r2 = call_with_api_key("GET", "/common/ping", "int:health.ping", query="")
    assert_ok(r2, "HMAC 路径调用 /common/ping（int:health.ping）")

    # 5) 用错误签名应 401
    ts = str(int(time.time()))
    bad = requests.get(
        f"{BASE}/common/ping",
        headers={"X-App-Key": APP_KEY, "X-Timestamp": ts, "X-Signature": "0" * 64},
    )
    assert bad.status_code == 401, f"FAIL: 错误签名应 401，实际 {bad.status_code}"
    print(f"PASS: 错误签名返回 401")

    # 6) 调用未授权路径（用 /common/ping 但改 endpoint_code 参数不符合实际路由）应 401
    r4 = call_with_api_key("GET", "/orders/list", endpoint_code="int:orders.list", query="")
    assert r4.status_code in (401, 403), f"未授权路径应 401/403，实际 {r4.status_code}"
    print(f"PASS: 未 @exposable 路径被拒绝（{r4.status_code}）")

    print("\n=== 全部冒烟用例通过 ===\n")


if __name__ == "__main__":
    main()
```

**Step 2：本地执行**

```bash
cd backend && pip install requests -q 2>/dev/null; python test_internal_exposable.py
```

Expected：依次打印 `PASS: ...`，最后一行 `=== 全部冒烟用例通过 ===`。

**Step 3：commit**

```bash
git add backend/test_internal_exposable.py
git commit -m "test(data-supply): smoke script for internal endpoint exposure"
```

---

## Task 10：回归与最终验证

**Files:**
- 无文件改动

**Step 1：前端构建**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected：无错误。

**Step 2：后端语法 + 启动**

```bash
cd backend && python -c "import app.main; print('app.main imported ok')"
```

Expected：仅打印 import ok（不应有 ImportError）。

**Step 3：Swagger 路径验证**

```bash
# uvicorn 启动后
curl -s http://localhost:8000/api/v1/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print('/common/ping' in d['paths'], 'int:health.ping 出现在 doc 中?'); print([p for p in d['paths'] if 'ping' in p or 'common' in p])"
```

Expected：`/api/v1/common/ping` 出现在 `paths` 中。

**Step 4：清理未追踪的状态**

```bash
git status --short
```

Expected：仅有本计划产生的 commit（不应有 M 状态遗留——但应忽略执行前已存在的 `material/stock_check*` 等 uncommitted 修改）。

---

## 执行后清理

实施完成后，可选清理：

1. 删除 `backend/test_internal_exposable.py` 中硬编码的 `APP_KEY` / `APP_SECRET`（上线时会通过 admin UI 创建正式 Key）；
2. 在 `admin` 角色 seed 的 permissions 中确保 `basicdata.data_supply` 已有（已存在，无需改）；
3. 在 README 或 wiki 中追加「如何为内部接口打 @exposable」的开发者文档（本轮不做）。
