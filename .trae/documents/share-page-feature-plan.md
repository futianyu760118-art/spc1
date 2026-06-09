# 供应链中台页面分享功能 — 实施计划

## 摘要

为 SPC 中台添加页面分享功能，允许已登录用户将当前页面生成分享链接，他人点击链接后可直接进入该页面进行操作。分享链接支持有效期设置和访问权限控制。

## 当前状态分析

### 前端架构
- **路由**: `App.tsx` 使用 React Router v6，所有页面路由嵌套在 `MainLayout` 下
- **认证守卫**: `PrivateRoute` 组件检查 `token` 是否存在，无 token 跳转 `/login`
- **权限控制**: `MainLayout` 中 `pathToPermission` 映射表 + `hasPermission()` 控制页面访问
- **状态管理**: Zustand (`useAuthStore`) 管理 token/user/permissions，存储在 localStorage
- **API 请求**: axios 实例自动附加 `Authorization: Bearer <token>` 头

### 后端架构
- **认证**: JWT (HS256)，token 有效期 480 分钟，支持 login_version 单点登录控制
- **权限**: `PermissionChecker` 依赖注入类，从数据库实时查询角色权限
- **用户模型**: `SysUser` + `SysRole`，角色权限存储在 `SysRole.permissions` (JSONB)
- **数据库**: PostgreSQL + SQLAlchemy async，`Base` 声明式基类
- **API 结构**: FastAPI，路由挂载在 `/api/v1` 前缀下

### 关键约束
- 所有 API 端点都需要 JWT 认证（通过 `oauth2_scheme`）
- 前端所有页面都在 `PrivateRoute` 保护下
- 无现有的分享/公开访问机制

## 设计决策（假设）

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 访问权限 | 需登录但跳过权限 | 企业系统安全性要求登录，但分享场景需绕过权限 |
| 有效期 | 可选：7天/30天/90天/永久 | 灵活性与安全性平衡 |
| 操作权限 | 与正常用户相同 | 用户明确要求"进行操作"，非只读 |

## 实施方案

### 核心思路

1. **后端**：新增 `share_link` 表和 API，生成唯一分享 token（JWT 短令牌），验证分享 token 后签发临时 JWT
2. **前端**：页面顶部添加"分享"按钮，生成分享链接；新增 `/share/:token` 路由处理分享链接访问
3. **分享流程**：用户点击分享 → 后端生成 share_token → 前端组装 URL → 他人打开链接 → 前端验证 share_token → 后端签发临时 JWT → 跳转目标页面

### 详细变更

---

### 1. 后端：新增分享链接模型

**文件**: `backend/app/models/basicdata/share_link.py`（新建）

```python
class ShareLink(Base):
    __tablename__ = "share_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), nullable=False, unique=True, index=True)  # 分享唯一标识
    target_path = Column(String(512), nullable=False)  # 目标页面路径，如 /orders
    target_params = Column(JSONB, nullable=True)  # 额外参数，如 {"orderNo": "xxx", "lineNo": "1"}
    created_by = Column(Integer, nullable=False)  # 创建人 user_id
    expires_at = Column(DateTime, nullable=True)  # 过期时间，null 表示永久
    is_revoked = Column(Boolean, nullable=False, default=False)  # 是否已撤销
    access_count = Column(Integer, nullable=False, default=0)  # 访问次数
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
```

---

### 2. 后端：新增分享链接 API

**文件**: `backend/app/api/v1/basicdata/share.py`（新建）

端点设计：

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/share` | 创建分享链接 | 需登录 |
| GET | `/share/{token}` | 验证分享链接，返回目标信息 | 无需登录 |
| GET | `/share/list` | 查询我创建的分享链接 | 需登录 |
| DELETE | `/share/{id}` | 撤销分享链接 | 需登录（仅创建者） |

**创建分享链接** `POST /share`:
- 请求体: `{ target_path: string, target_params?: object, expires_in?: "7d"|"30d"|"90d"|"permanent" }`
- 生成 `token`: `uuid4().hex[:16]` 或 `secrets.token_urlsafe(24)`
- 响应: `{ share_url: "http://host/share/<token>" }`

**验证分享链接** `GET /share/{token}`:
- 查询 `share_link` 表，验证 token 有效、未过期、未撤销
- 签发临时 JWT（包含 `share_token` 标记，有效期 24 小时）
- 响应: `{ access_token: string, target_path: string, target_params: object }`

---

### 3. 后端：修改认证依赖，支持分享 token

**文件**: `backend/app/core/dependencies.py`（修改）

新增 `get_current_user_or_share` 依赖函数：
- 优先尝试正常 JWT 认证
- 如果 URL 中包含 `share_token` 参数，验证分享 token 后允许访问
- 分享 token 签发的 JWT 中包含 `"share": true` 标记，用于区分访问来源

**文件**: `backend/app/core/security.py`（修改）

新增 `create_share_access_token` 函数：
- 为分享访问签发临时 JWT，包含 `share: true` 和 `share_target_path` 字段
- 有效期 24 小时，不受 login_version 控制

---

### 4. 后端：注册路由和模型

**文件**: `backend/app/api/v1/basicdata/__init__.py`（修改）
- 导入并注册 `share_router`

**文件**: `backend/app/api/v1/__init__.py`（修改）
- 添加 `api_router.include_router(basicdata.share_router, prefix="/share", tags=["页面分享"])`

---

### 5. 后端：数据库迁移

使用 Alembic 生成迁移脚本，创建 `share_link` 表。

---

### 6. 前端：新增分享 API

**文件**: `frontend/src/services/api.ts`（修改）

新增 `shareApi`:
```typescript
export const shareApi = {
  create: (data: { target_path: string; target_params?: object; expires_in?: string }) =>
    api.post('/share', data),
  verify: (token: string) => api.get(`/share/${token}`),
  list: () => api.get('/share/list'),
  revoke: (id: number) => api.delete(`/share/${id}`),
}
```

---

### 7. 前端：新增分享按钮组件

**文件**: `frontend/src/components/ShareButton/index.tsx`（新建）

- 在页面顶部栏添加分享按钮（图标：ShareAltOutlined）
- 点击弹出 Modal：
  - 显示当前页面路径
  - 有效期选择：7天 / 30天 / 90天 / 永久
  - 生成链接后显示可复制的 URL
  - "复制链接"按钮

---

### 8. 前端：新增分享链接处理页面

**文件**: `frontend/src/pages/ShareAccess/index.tsx`（新建）

- 路由: `/share/:token`
- 功能：
  1. 从 URL 提取 token
  2. 调用 `shareApi.verify(token)` 验证
  3. 验证成功：将返回的 `access_token` 存入 authStore，跳转到 `target_path`
  4. 验证失败：显示"链接无效或已过期"提示页

---

### 9. 前端：修改路由配置

**文件**: `frontend/src/App.tsx`（修改）

- 添加 `/share/:token` 路由（在 PrivateRoute 之外，无需登录即可访问）
- 导入 ShareAccess 组件

---

### 10. 前端：修改 MainLayout 添加分享按钮

**文件**: `frontend/src/layouts/MainLayout.tsx`（修改）

- 在顶部导航栏右侧区域添加 ShareButton 组件

---

### 11. 前端：修改 auth store 支持分享 token

**文件**: `frontend/src/store/auth.ts`（修改）

- 新增 `setShareAuth` 方法：设置分享 token 和受限用户信息
- 分享用户信息标记 `isShareUser: true`，用于 UI 区分（如隐藏某些管理功能）

---

### 12. 前端：修改 API 拦截器

**文件**: `frontend/src/services/api.ts`（修改）

- 分享 token 的 JWT 正常通过 `Authorization: Bearer` 头携带
- 无需特殊处理，现有拦截器已支持

---

## 文件变更清单

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 新建 | `backend/app/models/basicdata/share_link.py` | 分享链接数据模型 |
| 新建 | `backend/app/api/v1/basicdata/share.py` | 分享链接 API 端点 |
| 修改 | `backend/app/core/dependencies.py` | 新增分享认证依赖 |
| 修改 | `backend/app/core/security.py` | 新增分享 JWT 生成函数 |
| 修改 | `backend/app/api/v1/basicdata/__init__.py` | 注册 share_router |
| 修改 | `backend/app/api/v1/__init__.py` | 挂载分享路由 |
| 新建 | `frontend/src/components/ShareButton/index.tsx` | 分享按钮组件 |
| 新建 | `frontend/src/pages/ShareAccess/index.tsx` | 分享链接处理页 |
| 修改 | `frontend/src/App.tsx` | 添加 /share/:token 路由 |
| 修改 | `frontend/src/layouts/MainLayout.tsx` | 顶部栏添加分享按钮 |
| 修改 | `frontend/src/store/auth.ts` | 支持分享认证状态 |
| 修改 | `frontend/src/services/api.ts` | 新增 shareApi |

## 验证步骤

1. **创建分享链接**: 在任意页面点击分享按钮，选择有效期，生成链接
2. **复制并访问**: 在无登录状态的浏览器打开分享链接
3. **自动登录跳转**: 验证通过后自动跳转到目标页面
4. **页面操作**: 确认分享用户可以正常操作页面功能
5. **过期验证**: 创建短期分享链接，等待过期后访问应提示无效
6. **撤销验证**: 撤销分享链接后访问应提示已撤销
7. **权限隔离**: 分享用户不应看到用户管理、系统配置等管理功能
