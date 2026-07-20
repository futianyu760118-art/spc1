# `users.reset_password` 独立权限拆分 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把"重置密码"从 `users.update` 中拆为独立权限点 `users.reset_password`，前后端均可单独授权。

**Architecture:** 在权限注册表为 `users` 资源扩展动作集；运行时 merge 给 `manager` 默认授该权限；后端两个重置接口换守卫；前端用户管理页两处按钮改用 `hasPermission`；角色管理页硬编码的 `PERMISSION_ACTIONS` 数组追加新动作。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async（后端）；React + TypeScript + Ant Design 5 + Zustand（前端）。

**Spec:** `docs/superpowers/specs/2026-07-20-users-reset-password-permission-design.md`

## Global Constraints

- 后端用 async SQLAlchemy（`get_db()` 自动提交），不要在端点内手动 commit
- 权限注册走 `permission_registry.declare_permission`，启动时 `sync_permissions_to_db` 自动 upsert；不要直接写 `sys_permission` 表
- 前端 `npm run build` 是唯一类型检查（`tsc -b && vite build`）；本仓库**无** lint/test 框架
- 路径别名 `@` → `src/`，本计划用相对路径
- 不修改 `login_version` 行为（保持现状）
- 不动其他 `isAdmin` 写死的按钮（仅重置密码相关两处）
- TS 配置：`noUnusedLocals: false`，但 `strict: true` — 类型必须正确

## Task 1：后端 — 扩展权限注册表

**文件**: `backend/app/core/permission_registry.py`

**当前行 253**:
```python
declare_permission("users", "用户管理", module="basicdata", parent_code="basicdata", route_path="/users", sort_order=6)
```

**改为**:
```python
declare_permission(
    code="users",
    name="用户管理",
    module="basicdata",
    parent_code="basicdata",
    actions=["create", "read", "update", "delete", "reset_password"],
    route_path="/users",
    sort_order=6,
)
```

**为何**：原行走默认 actions（`["create", "read", "update", "delete"]`，见行 21、66）。显式声明后启动时 `sync_permissions_to_db` 会把 `sys_permission.actions` 列 upsert 为含 `reset_password` 的新数组。

**验证**:
- 文件保存后 `python -c "import ast; ast.parse(open('backend/app/core/permission_registry.py', encoding='utf-8').read())"` 无 SyntaxError
- 启动后 `SELECT actions FROM sys_permission WHERE code='users'` 应包含 `reset_password`

---

## Task 2：后端 — `manager` 角色运行时授予权限

**文件**: `backend/app/core/permissions.py`

**当前行 19-26**:
```python
"manager": {
    "production.schedule_plans": ["read", "update"],
    "exceptions.product_samples": ["read", "update"],
    "rules.order_standards": ["read", "update"],
    "rules.work_instructions": ["read", "update"],
    "users": ["read", "update"],
    "roles": ["read", "update"],
},
```

**改为**（仅 `users` 那一行追加 `reset_password`）:
```python
"manager": {
    "production.schedule_plans": ["read", "update"],
    "exceptions.product_samples": ["read", "update"],
    "rules.order_standards": ["read", "update"],
    "rules.work_instructions": ["read", "update"],
    "users": ["read", "update", "reset_password"],
    "roles": ["read", "update"],
},
```

**为何**：`merge_role_permission_additions` 用集合 union 合并（行 30-37），追加后 `manager` 角色在运行时获得 `users.reset_password` 能力，无需手工迁移 `sys_role.permissions` JSONB。`admin` 走 `security.py:312` 的 admin 绕过，不需要改。

**验证**:
- `python -c "import ast; ast.parse(open('backend/app/core/permissions.py', encoding='utf-8').read())"` 无 SyntaxError
- 重启后用 `manager01` 账号调 `PUT /api/v1/basicdata/users/{id}/password` 应返回 200

---

## Task 3：后端 — 单条重置接口换守卫

**文件**: `backend/app/api/v1/basicdata/users.py`

**当前行 745 附近**（端点 `reset_password`）:
```python
@router.put("/{user_id}/password")
async def reset_password(
    user_id: int,
    body: PasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(PermissionChecker("users", "update")),
):
```

**改为**（仅改 PermissionChecker 第二个参数）:
```python
@router.put("/{user_id}/password")
async def reset_password(
    user_id: int,
    body: PasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(PermissionChecker("users", "reset_password")),
):
```

**注意**：`update_user`（行 706）等其他 `users.update` 守卫**保持不变**。

**验证**:
- `python -c "import ast; ast.parse(open('backend/app/api/v1/basicdata/users.py', encoding='utf-8').read())"` 无 SyntaxError
- 用只有 `users.update`（无 `reset_password`）的角色调此接口 → 应 403 "缺少 users.reset_password 权限"

---

## Task 4：后端 — 批量重置接口换守卫

**文件**: `backend/app/api/v1/basicdata/users.py`

**当前行 915 附近**（端点 `batch_reset_password`）:
```python
@router.put("/batch/reset-password")
async def batch_reset_password(
    body: BatchResetPasswordBody,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(PermissionChecker("users", "update")),
):
```

**改为**:
```python
@router.put("/batch/reset-password")
async def batch_reset_password(
    body: BatchResetPasswordBody,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(PermissionChecker("users", "reset_password")),
):
```

**注意**：`batch_toggle_active`（行 886）的 `users.update` 守卫**保持不变**。

**验证**:
- AST 语法检查通过
- 用只有 `users.update`（无 `reset_password`）的角色调此接口 → 应 403

---

## Task 5：前端 — `RoleManagement` 动作数组追加 `reset_password`

**文件**: `frontend/src/pages/BasicDataCenter/RoleManagement.tsx`

**当前行 160-166**:
```typescript
const PERMISSION_ACTIONS = [
  { key: 'create', label: '新增' },
  { key: 'read', label: '查看' },
  { key: 'update', label: '编辑' },
  { key: 'delete', label: '删除' },
  { key: 'import', label: '导入' },
]
```

**改为**:
```typescript
const PERMISSION_ACTIONS = [
  { key: 'create', label: '新增' },
  { key: 'read', label: '查看' },
  { key: 'update', label: '编辑' },
  { key: 'delete', label: '删除' },
  { key: 'import', label: '导入' },
  { key: 'reset_password', label: '重置密码' },
]
```

**为何关键**：此数组被行 241/261/289/641 等多处引用，是角色管理页所有动作勾选框的唯一来源。不追加则新权限点在 UI 中根本不可见、无法分配。`getActions()`（行 241）从节点的 `actions` 字段读取实际值并与该数组求交集，所以多一项不会影响其他权限点。

**验证**:
- 启动 `npm run dev`，进入角色管理页 → `用户管理` 节点应显示 6 个动作勾选框
- 不影响 `订单总控台`、`计划排产` 等其他节点（它们 actions 不含 `reset_password`）

---

## Task 6：前端 — 单条重置密码按钮改用权限判断

**文件**: `frontend/src/pages/BasicDataCenter/UserManagement.tsx`

**当前行 687**:
```tsx
{isAdmin && <Button size="small" icon={<KeyOutlined />} onClick={() => openResetPwd(record)} title="重置密码" />}
```

**改为**:
```tsx
{hasPermission('users', 'reset_password') && <Button size="small" icon={<KeyOutlined />} onClick={() => openResetPwd(record)} title="重置密码" />}
```

**为何**：`hasPermission` 在 `frontend/src/store/auth.ts:252` 对 `role_code === 'admin'` 自动返回 true，admin 用户行为不变。`manager` 角色因 Task 2 的运行时 merge 也能看到按钮。`hasPermission` 和 `isAdmin` 在文件行 89-90 已定义，无需新引入。

**验证**:
- `npm run build` 通过（`tsc -b && vite build`）
- 用 `admin` 登录 → 按钮可见
- 用 `manager01` 登录 → 按钮可见（运行时获得权限）
- 用 `planner01` 登录 → 按钮不可见

---

## Task 7：前端 — 批量重置密码按钮新增权限守卫

**文件**: `frontend/src/pages/BasicDataCenter/UserManagement.tsx`

**当前行 726**（注意：当前**无任何守卫**，是已有 UX 缺陷）:
```tsx
<Button size="small" icon={<KeyOutlined />} loading={batchLoading} onClick={() => openConfirmModal('reset_password')}>批量重置密码</Button>
```

**改为**（用 `hasPermission` 条件渲染）:
```tsx
{hasPermission('users', 'reset_password') && <Button size="small" icon={<KeyOutlined />} loading={batchLoading} onClick={() => openConfirmModal('reset_password')}>批量重置密码</Button>}
```

**为何**：当前按钮在选中行后对任何能进入用户管理页的角色都可见（点击会被后端 403 拦下）。包上守卫后只对有权限的角色可见，与单条按钮策略一致。

**注意**：行 728 的 `批量删除` 按钮（`{isAdmin && ...}`）本次**不动**。

**验证**:
- `npm run build` 通过
- 用 `planner01` 登录 → 选中行后**不应**看到"批量重置密码"按钮（修复了原本可见的缺陷）
- 用 `admin` 登录 → 按钮可见、可操作

---

## Task 8：端到端验证

按 spec 的"验证步骤"小节完整跑一遍：

### 后端

1. 启动 uvicorn（触发 `permission_registry.sync_permissions_to_db`）
2. SQL 校验：
   ```sql
   SELECT actions FROM sys_permission WHERE code = 'users';
   -- 期望: ["create", "read", "update", "delete", "reset_password"]
   ```
3. 用 `manager01`（密码 `admin123`）登录 → 调 `PUT /api/v1/basicdata/users/{任一id}/password` body `{"new_password":"test123"}` → 应 200
4. 用 `planner01` 登录 → 调同样接口 → 应 403，detail 含 "缺少 users.reset_password 权限"

### 前端

1. `cd frontend && npm run build` — 必须 0 error
2. `npm run dev` 启动开发服
3. `admin` 登录 → 用户管理 → 单条/批量重置按钮都可见 → 角色管理 → `用户管理` 节点显示 6 个动作
4. `manager01` 登录 → 重置按钮可见
5. `planner01` 登录 → 重置按钮不可见，选中行后批量重置按钮也不可见

### 回归检查

- 用 `manager01` 编辑用户（`PUT /basicdata/users/{id}`）→ 应仍 200（`users.update` 未受影响）
- RoleManagement 页保存一个角色权限 → 应正常保存

---

## 提交建议（仅在用户要求时执行）

单次提交即可，建议消息：

```
feat(users): split reset_password into a dedicated permission

- Register users.reset_password action in permission_registry
- Grant manager role the new action via ROLE_PERMISSION_ADDITIONS
- Switch single + batch reset endpoints to PermissionChecker("users", "reset_password")
- Frontend: gate reset buttons by hasPermission, add action to RoleManagement
```

文件清单（5 个）：
- `backend/app/core/permission_registry.py`
- `backend/app/core/permissions.py`
- `backend/app/api/v1/basicdata/users.py`
- `frontend/src/pages/BasicDataCenter/UserManagement.tsx`
- `frontend/src/pages/BasicDataCenter/RoleManagement.tsx`
