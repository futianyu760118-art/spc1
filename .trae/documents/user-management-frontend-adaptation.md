# 计划：用户管理前端适配 — 添加组织范围和上级信息

## 概述

后端已添加 `manager_oa_user_id`、`oa_user_id`、`org_scope_ids` 等字段，但前端用户管理页面尚未同步。需要调整的地方：

1. **用户管理表格**：显示"所属组织"和"上级"列
2. **员工选项接口**：返回 `oa_user_id` 和 `manager_oa_user_id`
3. **用户列表接口**：返回 `org_name` 和 `manager_name`

## 当前状态分析

### 后端

- **用户列表 API** (`users.py:184-202`)：返回 user/role/employee/position 信息，**缺少** `org_name`（组织名称）和 `manager_name`（上级姓名）
- **员工选项 API** (`users.py:348-361`)：返回 emp_code/emp_name/position/role 信息，**缺少** `oa_user_id` 和 `manager_oa_user_id`
- **Employee 模型**：已有 `manager_oa_user_id` 和 `oa_user_id` 字段
- **Organization 模型**：有 `id` 和 `org_name` 字段

### 前端

- **UserManagement.tsx**：用户管理页面，有用户列表表格和新增/编辑用户弹窗
  - `UserItem` 接口（第170-186行）：**缺少** `org_name` 和 `manager_name`
  - `EmployeeOption` 接口（第24-34行）：**缺少** `oa_user_id` 和 `manager_oa_user_id`
  - 用户表格列（第711-763行）：**缺少**"所属组织"和"上级"列
  - 导出列（第195-208行）：**缺少**"所属组织"和"上级"列

## 修改方案

### 1. 后端：用户列表 API 返回 org_name 和 manager_name

**文件**: `backend/app/api/v1/basicdata/users.py`

在 `list_users` 函数中：
- 添加 `Organization` 和 `Manager`（Employee 别名）的 JOIN
- 在返回数据中添加 `org_name` 和 `manager_name` 字段

```python
from sqlalchemy.orm import aliased
from app.models.basicdata.organization import Organization

# 在 list_users 中：
Manager = aliased(Employee)
query = (
    select(SysUser, SysRole, Employee, Position, Organization, Manager)
    .join(SysRole, SysUser.role_id == SysRole.id)
    .outerjoin(Employee, SysUser.emp_code == Employee.emp_code)
    .outerjoin(Position, Employee.position_id == Position.id)
    .outerjoin(Organization, Employee.org_id == Organization.id)
    .outerjoin(Manager, Employee.manager_oa_user_id == Manager.oa_user_id)
)

# 返回数据添加：
"org_name": org.org_name if org else None,
"manager_name": manager.emp_name if manager else None,
```

### 2. 后端：员工选项 API 返回 oa_user_id 和 manager_oa_user_id

**文件**: `backend/app/api/v1/basicdata/users.py`

在 `list_employee_options` 返回数据中添加：
```python
"oa_user_id": employee.oa_user_id,
"manager_oa_user_id": employee.manager_oa_user_id,
```

### 3. 前端：UserItem 接口添加新字段

**文件**: `frontend/src/pages/BasicDataCenter/UserManagement.tsx`

```typescript
interface UserItem {
  // ... 现有字段
  org_name: string | null       // 新增
  manager_name: string | null   // 新增
}
```

### 4. 前端：EmployeeOption 接口添加新字段

**文件**: `frontend/src/pages/BasicDataCenter/UserManagement.tsx`

```typescript
interface EmployeeOption {
  // ... 现有字段
  oa_user_id?: string           // 新增
  manager_oa_user_id?: string   // 新增
}
```

### 5. 前端：用户表格添加"所属组织"和"上级"列

**文件**: `frontend/src/pages/BasicDataCenter/UserManagement.tsx`

在 `userColumns` 的"岗位"列后添加：
```typescript
{
  title: '所属组织',
  dataIndex: 'org_name',
  key: 'org_name',
  width: 140,
  render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
},
{
  title: '上级',
  dataIndex: 'manager_name',
  key: 'manager_name',
  width: 100,
  render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
},
```

### 6. 前端：导出列添加新字段

**文件**: `frontend/src/pages/BasicDataCenter/UserManagement.tsx`

在 `USER_EXPORT_COLUMNS` 中添加：
```typescript
{ field: 'org_name', label: '所属组织' },
{ field: 'manager_name', label: '上级' },
```

### 7. 前端：表格 scroll.x 调整

用户表格当前 `scroll.x: 1260`，新增两列（140+100=240），调整为 `scroll.x: 1500`。

## 验证步骤

1. 后端启动无报错
2. 用户列表 API 返回 `org_name` 和 `manager_name`
3. 员工选项 API 返回 `oa_user_id` 和 `manager_oa_user_id`
4. 前端用户管理表格显示"所属组织"和"上级"列
5. 导出 Excel 包含新字段
6. Docker 构建成功
