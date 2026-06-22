# 计划：用户管理根据部门岗位更新角色 & 角色管理显示使用状态

## 摘要

两个需求：
1. **用户管理根据部门和岗位更新角色**：当用户的部门或岗位发生变化时，自动根据部门+岗位组合重新解析并更新角色
2. **角色管理显示是否被使用**：角色列表中显示每个角色被多少用户引用，方便管理员判断角色是否在使用中

---

## 现状分析

### 数据模型关系
- `SysUser` 有 `role_id`（关联角色）和 `emp_code`（关联员工工号）
- `Employee` 有 `org_id`（主部门ID）和 `position_id`（岗位ID）
- `Position` 有 `role_id`（关联系统角色ID）
- `EmployeeOrganization` 记录员工与多部门的关系（含 `is_primary` 标记主部门）
- `SysRole` 是角色表，存储 `role_code`、`role_name`、`permissions`

### 现有角色解析逻辑（`position_role_service.py`）
- `resolve_role_for_employee()` 已实现：根据员工的岗位 + 部门名称，自动创建/查找部门+岗位联合角色
- `sync_user_role_from_employee()` 已实现：根据员工信息同步更新用户的 `role_id`
- `ensure_org_position_role()` 已实现：为部门+岗位组合创建角色（`role_code` 含部门名哈希）

### 当前用户管理前端
- 编辑用户时，选择员工后自动从岗位获取角色（`handleEmployeeChange`）
- 角色选择框在有岗位角色时被禁用（`disabled={hasPositionRole}`）
- **缺失**：当员工的部门或岗位在员工表中发生变化时，用户表中的 `role_id` 不会自动同步更新

### 当前角色管理前端
- 角色列表只显示：角色编码、角色名称、权限概览
- **缺失**：没有显示角色被多少用户使用

---

## 修改方案

### 需求1：用户管理根据部门和岗位更新角色

#### 后端修改

**文件：`backend/app/api/v1/basicdata/users.py`**

1. **新增 API：批量同步用户角色** `POST /sync-roles`
   - 遍历所有有 `emp_code` 的用户，调用 `sync_user_role_from_employee()` 同步角色
   - 返回更新了多少个用户的信息
   - 权限要求：`users:update`

2. **修改用户列表 API** `GET ""`：在返回数据中增加 `org_name` 和 `position_name` 的实时解析（当前已有，但 join 逻辑用的是 `Organization.oa_org_id`，需确认是否正确关联）

3. **修改用户更新 API** `PUT /{user_id}`：当 `emp_code` 变化时，自动调用 `resolve_employee_role_by_code` 重新解析角色（当前已有此逻辑，在 `_resolve_user_role` 中）

**文件：`backend/app/api/v1/basicdata/employees.py`**（或相关同步接口）

4. 在员工数据同步/更新时，自动触发关联用户的角色更新。检查现有员工同步逻辑，在员工更新后调用 `sync_user_role_from_employee()`

#### 前端修改

**文件：`frontend/src/pages/BasicDataCenter/UserManagement.tsx`**

5. **新增"同步角色"按钮**：在工具栏添加按钮，调用 `POST /basicdata/users/sync-roles`，批量同步所有用户的角色
6. **编辑用户弹窗优化**：当选择员工后，如果员工的部门或岗位与当前用户不同，提示角色将自动更新

### 需求2：角色管理显示是否被使用

#### 后端修改

**文件：`backend/app/api/v1/basicdata/users.py`**

7. **修改角色列表 API** `GET /roles`：增加 `user_count` 字段，统计每个角色被多少用户使用
   - 使用子查询或 JOIN 统计 `sys_user` 表中 `role_id` 对应的数量

#### 前端修改

**文件：`frontend/src/pages/BasicDataCenter/RoleManagement.tsx`**

8. **角色列表增加"使用人数"列**：在角色编码和角色名称之间添加一列，显示使用该角色的用户数量
9. **删除角色时的提示优化**：当角色有用户时，在删除确认弹窗中显示使用人数（当前后端已有校验，前端提示可更友好）

---

## 具体实现步骤

### Step 1：后端 — 角色列表增加 `user_count`

**文件**：`backend/app/api/v1/basicdata/users.py`，`list_roles` 函数（第344-367行）

修改查询，为每个角色统计关联用户数：

```python
@router.get("/roles", response_model=ResponseModel[dict])
async def list_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(PermissionChecker("roles", "read")),
    db: AsyncSession = Depends(get_db),
):
    # 查询角色及每个角色的用户数
    user_count_sub = (
        select(SysUser.role_id, func.count().label("user_count"))
        .group_by(SysUser.role_id)
        .subquery()
    )
    result = await db.execute(
        select(SysRole, func.coalesce(user_count_sub.c.user_count, 0))
        .outerjoin(user_count_sub, SysRole.id == user_count_sub.c.role_id)
        .order_by(SysRole.id)
    )
    rows = result.all()
    total = len(rows)
    offset = (page - 1) * page_size
    paged = rows[offset:offset + page_size]
    return ResponseModel(data={
        "items": [
            {
                "id": role.id,
                "role_code": role.role_code,
                "role_name": role.role_name,
                "permissions": merge_role_permission_additions(role.role_code, role.permissions),
                "user_count": user_count,
            }
            for role, user_count in paged
        ],
        "total": total,
    })
```

### Step 2：后端 — 新增批量同步角色 API

**文件**：`backend/app/api/v1/basicdata/users.py`

在角色列表 API 之后添加：

```python
@router.post("/sync-roles", response_model=ResponseModel[dict])
async def sync_user_roles(
    current_user: dict = Depends(PermissionChecker("users", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SysUser, Employee)
        .join(Employee, SysUser.emp_code == Employee.emp_code)
    )
    rows = result.all()
    updated = 0
    for user, employee in rows:
        changed = await sync_user_role_from_employee(db, employee)
        if changed:
            updated += 1
    await db.commit()
    return ResponseModel(data={"total": len(rows), "updated": updated})
```

### Step 3：后端 — 员工同步时自动更新关联用户角色

检查员工数据同步接口，在员工更新后触发角色同步。需要查看 `employees.py` 的同步逻辑。

### Step 4：前端 — 角色管理增加使用人数列

**文件**：`frontend/src/pages/BasicDataCenter/RoleManagement.tsx`

1. `RoleItem` 接口增加 `user_count: number`
2. 在 `roleColumns` 中添加"使用人数"列
3. 删除确认弹窗优化，显示使用人数

### Step 5：前端 — 用户管理增加同步角色按钮

**文件**：`frontend/src/pages/BasicDataCenter/UserManagement.tsx`

1. 在工具栏添加"同步角色"按钮
2. 调用 `POST /basicdata/users/sync-roles`
3. 显示同步结果

### Step 6：前端 API — 添加同步角色接口

**文件**：`frontend/src/services/api.ts`

在 `userApi` 中添加：
```typescript
syncRoles: () => api.post('/basicdata/users/sync-roles'),
```

---

## 假设与决策

1. **角色使用统计只计算 `sys_user` 表中的直接引用**，不计算 `scm_position.role_id` 的间接引用
2. **批量同步角色**是手动触发的，不做自动定时同步（避免复杂性）
3. **员工数据变更时**，如果已有同步钩子则添加角色同步调用；如果没有则仅依赖手动同步按钮
4. 角色列表的 `user_count` 使用子查询统计，性能可接受（角色数量有限）

---

## 验证步骤

1. 角色管理页面应显示"使用人数"列，数值与实际使用该角色的用户数一致
2. 删除有用户的角色时应提示无法删除
3. 用户管理页面点击"同步角色"后，用户的角色应根据其员工的部门+岗位自动更新
4. 编辑用户选择不同员工后，角色应自动跟随员工岗位变化
