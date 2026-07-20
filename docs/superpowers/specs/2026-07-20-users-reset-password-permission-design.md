# 设计：拆分 `users.reset_password` 独立权限

**日期**: 2026-07-20
**状态**: 已确认，待实现
**作者**: brainstorming session

## 背景

当前"重置密码"功能挂在 `users.update` 权限下，无法单独授权。需求是把"重置密码"拆为独立权限点 `users.reset_password`，可在角色管理页单独勾选授予。

### 现状

- 后端已有两个重置密码接口（`backend/app/api/v1/basicdata/users.py`）:
  - `PUT /basicdata/users/{user_id}/password` (行 745) — 单条重置
  - `PUT /basicdata/users/batch/reset-password` (行 915) — 批量重置
  - 两者都用 `PermissionChecker("users", "update")` 守卫
- 前端 `UserManagement.tsx` 已有重置密码弹窗（行 876），但按钮（行 687、726）被 `isAdmin` 写死，非权限判断
- 权限注册表 `permission_registry.py:253` 的 `users` 资源走默认动作 `["create", "read", "update", "delete"]`
- `RoleManagement.tsx:160-166` 的 `PERMISSION_ACTIONS` **硬编码**为 `create/read/update/delete/import`，不含 `reset_password` — 这意味着新动作不加入此数组则在角色配置 UI 中不可见
- 后端 `/api/v1/basicdata/permissions/tree` 接口 (`permissions.py:51`) 已正确返回 `actions` 数组，**后端无需改动**

## 决策（用户已确认）

1. ✅ 完整拆分独立权限（前后端 + 角色管理 UI）
2. ✅ 不修改 `login_version` 行为（保持现状：重置密码不强制下线）
3. ✅ `admin` 走原有 admin 绕过；`manager` 通过运行时 merge 默认获得该权限

## 改动清单

### 1. 后端：权限注册表

**文件**: `backend/app/core/permission_registry.py:253`

将 `users` 改为显式声明动作集，新增 `reset_password`：

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

启动时 `sync_permissions_to_db` 会 upsert `sys_permission` 表，把 `actions` 数组更新为新值。已有的 `sys_role.permissions` JSONB 不受影响（只是多了一个可勾选项）。

### 2. 后端：运行时权限合并

**文件**: `backend/app/core/permissions.py:24`

给 `manager` 角色的 `users` 列表追加 `reset_password`，保持当前能重置密码的实际能力：

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

`merge_role_permission_additions` 使用集合 union 合并，幂等。`admin` 走 `security.py:312` 的 admin 绕过，无需修改。

### 3. 后端：API 权限检查

**文件**: `backend/app/api/v1/basicdata/users.py`

两处 `PermissionChecker("users", "update")` 改为 `PermissionChecker("users", "reset_password")`：

| 行号 | 接口 | 改动 |
|---|---|---|
| 745 | `PUT /{user_id}/password` (单条重置) | `update` → `reset_password` |
| 915 | `PUT /batch/reset-password` (批量重置) | `update` → `reset_password` |

其他 `users.update` 守卫（`update_user` 行 706、`sync_user_roles` 行 480、`batch_toggle_active` 行 886）**保持不变**。

### 4. 前端：用户管理页按钮

**文件**: `frontend/src/pages/BasicDataCenter/UserManagement.tsx`

实际现状（self-review 时核实）：

- **行 687**：单条"重置密码" Action — 当前 `{isAdmin && <Button .../>}`，仅 admin 可见
- **行 726**：批量"批量重置密码"按钮 — **当前完全没有任何权限守卫**，只要选中了行就显示（任何能进入用户管理页的角色都能看到，点击会被后端 403 拦下）。这是已有 UX 缺陷。
- **行 728**：批量"批量删除"按钮 — `{isAdmin && ...}`，仅 admin 可见（本次不动）

改动：

- 行 687：`isAdmin &&` → `hasPermission('users', 'reset_password') &&`
- 行 726：给无守卫的按钮**新增** `{hasPermission('users', 'reset_password') && <Button .../>}` 包裹
- 行 944 附近（如果存在）的批量操作触发条件同步检查

`hasPermission('users', 'reset_password')` 对 `role_code === 'admin'` 自动返回 true（`auth.ts:252`），admin 用户看到的按钮不变。

> 实现注意：当前还有"新增用户"按钮（行 740）等也用 `isAdmin` 写死。本次**不动**这些，只改重置密码两处。后续可单独治理此不一致。

### 5. 前端：角色管理页动作列表

**文件**: `frontend/src/pages/BasicDataCenter/RoleManagement.tsx:160-166`

`PERMISSION_ACTIONS` 数组追加一项：

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

**这是关键步骤**。若漏掉，新权限在角色配置页根本不显示勾选框，权限点等于不可分配。该数组被行 241/261/289/641 等多处引用，统一来源即生效。

### 6. 前端：权限树渲染逻辑（验证，无需改）

`RoleManagement.tsx` 行 241 `getActions(node.key, node.children)` 从节点 `actions` 字段读取（已对齐后端返回），未硬编码动作列表。已确认无需改动。

## 不在范围内

- ❌ 不改 `login_version`（保持现有：重置密码不强制下线）
- ❌ 不改 `create_user`、`change_password`（自助改密走 `auth.py`）
- ❌ 不改 ERP 同步、不改 `init_database.py` 迁移逻辑（无新增列）
- ❌ 不动其他 `isAdmin` 写死的按钮（仅重置密码相关）

## 验证步骤

### 后端

1. 启动 uvicorn（触发 `permission_registry.sync_permissions_to_db`）
2. SQL 校验：
   ```sql
   SELECT code, actions FROM sys_permission WHERE code = 'users';
   -- 应包含 reset_password
   ```
3. 创建测试角色 `helpdesk`，仅授 `users.read` + `users.reset_password`（不含 `users.update`）
4. 用 `helpdesk` 账号调 `PUT /api/v1/basicdata/users/{id}/password` → 应 200
5. 用 `helpdesk` 账号调 `PUT /api/v1/basicdata/users/{id}`（普通更新）→ 应 403 "缺少 users.update 权限"
6. 用 `planner01`（无任何 users 权限）调重置接口 → 应 403 "缺少 users.reset_password 权限"
7. `manager` 账号调重置接口 → 应 200（运行时 merge 生效）

### 前端

1. `npm run build`（= `tsc -b && vite build`，唯一的类型检查）必须通过
2. 用 `admin` 登录 → 重置密码按钮可见、可操作（行为不变）
3. 用 `manager` 登录 → 重置密码按钮可见（运行时获得权限）
4. 用 `planner01` 登录 → 重置密码按钮不可见
5. RoleManagement 页 → `用户管理` 节点下显示 6 个动作勾选框：新增/查看/编辑/删除/导入/重置密码
6. 在 RoleManagement 给 `planner` 角色勾选 `用户管理.重置密码` → 保存 → 重登 → 按钮出现

## 风险与回滚

- **风险**：现存 DB 中 `manager` 角色的 `sys_role.permissions.users` 不包含 `reset_password`，但运行时 merge 会兜底，无需手工迁移
- **回滚**：将 `permission_registry.py` 的 actions 改回默认、`permissions.py` 移除 manager 的新增动作、前端两个文件 revert 即可。`sys_permission.actions` 列下次启动会被覆盖回旧值
- **兼容性**：`sys_role.permissions` JSONB 中存量数据无需迁移；多出来的 `reset_password` action 对未被授予的角色是 no-op

## 关键文件清单

| 关注点 | 路径 |
|---|---|
| 权限注册表 | `backend/app/core/permission_registry.py:253` |
| 运行时权限合并 | `backend/app/core/permissions.py:24` |
| 用户 API | `backend/app/api/v1/basicdata/users.py:745, 915` |
| 权限检查依赖 | `backend/app/core/security.py:154-388` |
| 用户管理前端 | `frontend/src/pages/BasicDataCenter/UserManagement.tsx:687, 726` |
| 角色管理前端 | `frontend/src/pages/BasicDataCenter/RoleManagement.tsx:160-166` |
| 前端权限判断 | `frontend/src/store/auth.ts:221-268` |
