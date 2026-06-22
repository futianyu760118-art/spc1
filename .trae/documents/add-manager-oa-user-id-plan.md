# 计划：Employee 添加 manager_oa_user_id + 功能权限与数据权限分离

## 概述

实现 **RBAC + 组织层级 + 数据权限分离** 的权限体系：

1. **功能权限**（已有）：由角色决定，如普工=operator，所有普工共享同一套功能权限
2. **数据权限**（增强）：由组织范围决定，装配车间普工只能看装配数据，精益车间普工只能看精益数据
3. **上下级管理**（新增）：通过 `manager_oa_user_id` 建立上下级关系，上级可管理下级人员信息

**权限逻辑示例**：
- 装配车间普工A：角色=operator（功能权限），数据范围=装配车间
- 精益车间普工B：角色=operator（功能权限），数据范围=精益车间
- 装配车间主管C：角色=manager（功能权限），数据范围=装配车间，可管理下级（A等）

## 当前状态分析

- **Employee 模型** (`backend/app/models/basicdata/employee.py`)：已有 `oa_user_id`，无上级字段
- **SysUser 模型** (`backend/app/models/basicdata/user.py`)：通过 `emp_code` 关联 Employee，通过 `role_id` 关联 SysRole
- **UserOrgScope 模型** (`backend/app/models/basicdata/user_org_scope.py`)：**已有**用户-组织数据范围关联，含 `include_sub` 支持子组织
- **组织范围服务** (`backend/app/services/basicdata/org_scope_service.py`)：**已有** `resolve_user_org_scopes` 和 `get_sub_org_ids`，可递归获取用户可访问的组织
- **权限系统** (`backend/app/core/security.py` 的 `PermissionChecker`)：基于角色+资源，admin 自动通过
- **当前用户信息** (`backend/app/core/dependencies.py`)：返回 user_id, username, role, permissions 等，**不包含 oa_user_id 和 org_scope**
- **员工 API** (`backend/app/api/v1/basicdata/basicdata.py`)：CRUD 端点，无数据权限过滤
- **ERP 同步** (`backend/app/services/basicdata/erp_sync_service.py`)：`_filter_model_fields` 自动过滤有效列

## 修改方案

### 1. Employee 模型添加 `manager_oa_user_id` 字段

**文件**: `backend/app/models/basicdata/employee.py`

```python
manager_oa_user_id = Column(String(64), nullable=True, comment="上级人员OA用户ID")
```

### 2. 数据库迁移脚本

**文件**: 新建 `backend/alembic/versions/add_manager_oa_user_id_to_employee.py`

- upgrade: `op.add_column("scm_employee", sa.Column("manager_oa_user_id", sa.String(64), nullable=True, comment="上级人员OA用户ID"))`
- downgrade: `op.drop_column("scm_employee", "manager_oa_user_id")`

### 3. init_database.py 更新

**文件**: `backend/init_database.py`

- 在 `scm_employee` 的额外列定义（约207行）中添加 `"manager_oa_user_id": "VARCHAR(64)"`

### 4. Schemas 更新

**文件**: `backend/app/schemas/basicdata/schemas.py`

- `EmployeeBase`: 添加 `manager_oa_user_id: Optional[str] = None`
- `EmployeeUpdate`: 添加 `manager_oa_user_id: Optional[str] = None`
- `EmployeeOut`: 继承自 EmployeeBase 自动包含 `manager_oa_user_id`；额外添加 `manager_name: Optional[str] = None`

### 5. 当前用户信息扩展 — 添加 oa_user_id 和 org_scope_ids

**文件**: `backend/app/core/dependencies.py`

在 `get_current_user` 和 `get_current_user_or_share` 返回的 dict 中添加：

- `oa_user_id`：通过 `SysUser.emp_code` JOIN `Employee.emp_code` 获取
- `org_scope_ids`：调用 `resolve_user_org_scopes(db, user.id)` 获取用户可访问的组织 ID 集合

这样所有 API 端点都能通过 `current_user["oa_user_id"]` 和 `current_user["org_scope_ids"]` 获取上下级关系和数据范围。

### 6. 员工 API 更新 — 查询关联上级姓名 + 数据权限过滤 + 上下级权限

**文件**: `backend/app/api/v1/basicdata/basicdata.py`

#### 6.1 查询关联上级姓名

- `_employee_out` 函数：增加 `manager_name` 参数
- 员工列表/详情查询：LEFT JOIN Employee 自身（别名 Manager），通过 `Employee.manager_oa_user_id = Manager.oa_user_id` 关联上级姓名

#### 6.2 数据权限过滤（按组织范围）

非 admin 用户的员工列表查询，增加组织范围过滤：

```python
if current_user["role"] != "admin":
    org_scope_ids = current_user.get("org_scope_ids", set())
    if org_scope_ids:
        query = query.where(Employee.org_id.in_(org_scope_ids))
    else:
        query = query.where(Employee.oa_user_id == current_user.get("oa_user_id"))
```

这样装配车间的普工只能看到装配车间组织下的员工，精益车间的普工只能看到精益车间的。

#### 6.3 上下级管理权限

新增辅助函数 `_can_manage_employee(current_user, target_employee)`：

- **admin 角色**：不受限制
- **非 admin 角色**：
  - 可以操作**自己**的信息（`current_oa_user_id == target.oa_user_id`）
  - 可以操作**下级**的信息（`current_oa_user_id == target.manager_oa_user_id`）
  - 无权限返回 403

#### 6.4 各端点修改

- `list_employees`：数据权限过滤（按组织范围）+ 上下级可见
- `get_employee`：查询后检查数据权限
- `update_employee`：检查当前用户是否为目标员工的上级或自己
- `delete_employee`：同 update 逻辑
- `create_employee`：保持现有逻辑（admin 或有 create 权限即可）

### 7. ERP 同步兼容

**无需修改代码**，`_filter_model_fields` 会自动过滤有效列。需在数据库 `sync_sql_config` 表中 employees 的 SQL 配置和字段映射 JSON 里添加 `manager_oa_user_id` 的映射。

## 权限体系总结

| 维度 | 控制方式 | 示例 |
|------|---------|------|
| 功能权限 | 角色（SysRole） | operator 可访问生产模块，不可访问采购模块 |
| 数据权限 | 组织范围（UserOrgScope） | 装配车间普工只能看装配车间数据 |
| 上下级管理 | manager_oa_user_id | 主管可管理其下属的人员信息 |

三者组合：
- **能否访问某功能** → 角色决定
- **能看到哪些数据** → 组织范围决定
- **能否管理某人** → 上下级关系决定

## 假设与决策

1. **manager_oa_user_id 存储上级的 OA 用户 ID**，与 ERP/OA 系统保持一致
2. **上级关系是单层直接上级**，不涉及多级递归（可后续扩展）
3. **admin 角色不受任何限制**
4. **功能权限由角色统一决定**，同岗位不同部门共享同一角色，差异通过数据权限体现
5. **数据权限基于组织范围**，利用已有的 UserOrgScope 模型和 org_scope_service
6. **ERP 同步字段映射**需在数据库配置，代码无需修改

## 验证步骤

1. 运行 Alembic 迁移，确认 `scm_employee` 表新增 `manager_oa_user_id` 列
2. 验证员工列表/详情 API 返回 `manager_oa_user_id` 和 `manager_name`
3. 验证员工创建/更新 API 支持设置 `manager_oa_user_id`
4. 验证 `get_current_user` 返回 `oa_user_id` 和 `org_scope_ids`
5. 验证数据权限：装配车间用户只能看到装配车间的员工
6. 验证上下级权限：上级可管理下级人员信息，非上下级返回 403
7. 验证 admin 不受限制
8. 验证 ERP 同步能正确映射 `manager_oa_user_id`
