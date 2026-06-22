# 角色：根据部门+岗位联合生成

## 概述

当前角色（SysRole）仅根据岗位名称生成，导致同名岗位（如"普工"）在不同部门（如装配车间、精益车间）映射到同一个角色，无法设置不同权限。

**目标**：角色根据部门+岗位联合生成，使"装配车间-普工"和"精益车间-普工"成为不同角色，可独立配置权限。

**方案**：Position 保持全局实体不变，仅在角色生成时联合部门信息。Position.role_id 指向默认角色（无部门信息），实际用户角色按部门区分。

## 当前状态分析

### 核心问题

- `make_position_role_code(position_code, position_name)` 只基于 position_name 生成 role_code → 同名岗位生成相同 role_code → 指向同一个 SysRole
- `make_position_role_name(position_name)` 只基于 position_name → 角色名如"岗位-普工"，无法区分部门
- `ensure_position_role(db, position)` 只接收 Position 对象，无法获取部门信息
- `resolve_role_for_employee(db, employee)` 调用 `ensure_position_role` 时未传入部门信息

### 关键文件

| 文件 | 作用 |
|------|------|
| `backend/app/services/basicdata/position_role_service.py` | 角色生成核心逻辑 |
| `backend/app/services/basicdata/erp_sync_service.py` | ERP 同步（岗位+员工） |
| `backend/app/api/v1/basicdata/basicdata.py` | 员工 CRUD 中调用 `sync_user_role_from_employee` |
| `backend/app/models/basicdata/position.py` | Position 模型（无 org_id） |
| `backend/app/models/basicdata/employee.py` | Employee 模型（有 org_id） |
| `backend/app/models/basicdata/organization.py` | Organization 模型 |

### 数据流

```
Employee (org_id, position_id)
  → resolve_role_for_employee(db, employee)
    → resolve_position_for_employee(db, employee)  # 找到 Position
    → ensure_position_role(db, position)            # 生成角色（当前无部门信息）
  → sync_user_role_from_employee(db, employee)      # 将角色赋给 SysUser
```

## 修改方案

### 1. 修改 `position_role_service.py` — 角色生成逻辑

#### 1.1 修改 `make_position_role_code`

```python
def make_position_role_code(
    position_code: Optional[str],
    position_name: Optional[str],
    org_name: Optional[str] = None,
) -> str:
    source = (position_name or position_code or "position").strip().lower()
    if org_name:
        source = f"{org_name.strip()}_{source}"
    digest = sha1(source.encode("utf-8")).hexdigest()[:24]
    return f"pos_{digest}"
```

- 有 org_name 时：`sha1("装配车间_普工")` → 生成唯一 role_code
- 无 org_name 时：`sha1("普工")` → 保持向后兼容

#### 1.2 修改 `make_position_role_name`

```python
def make_position_role_name(
    position_name: Optional[str],
    org_name: Optional[str] = None,
) -> str:
    name = (position_name or "未命名岗位").strip()
    if org_name:
        return f"岗位-{org_name.strip()}-{name}"
    return f"岗位-{name}"
```

- 有 org_name 时：`"岗位-装配车间-普工"`
- 无 org_name 时：`"岗位-普工"`

#### 1.3 新增 `ensure_org_position_role` 函数

```python
async def ensure_org_position_role(
    db: AsyncSession,
    position: Position,
    org_name: Optional[str] = None,
) -> tuple[SysRole, bool]:
    """Ensure a role exists for a (org, position) combination.

    Returns (role, role_created).
    Unlike ensure_position_role, this does NOT set position.role_id.
    """
    desired_name = make_position_role_name(position.position_name, org_name)
    role_code = make_position_role_code(position.position_code, position.position_name, org_name)

    role_result = await db.execute(select(SysRole).where(SysRole.role_code == role_code))
    role = role_result.scalar_one_or_none()
    role_created = False

    if role:
        if role.role_name != desired_name:
            role.role_name = desired_name
        if not role.permissions:
            role.permissions = get_position_permissions(position.position_name)
    else:
        role = SysRole(
            role_code=role_code,
            role_name=desired_name,
            permissions=get_position_permissions(position.position_name),
        )
        db.add(role)
        await db.flush()
        role_created = True

    return role, role_created
```

#### 1.4 修改 `resolve_role_for_employee`

```python
async def resolve_role_for_employee(db: AsyncSession, employee: Employee) -> tuple[Optional[SysRole], Optional[Position]]:
    position = await resolve_position_for_employee(db, employee)
    if not position:
        return None, None

    # 获取员工的部门名称
    org_name = None
    if employee.org_id:
        from app.models.basicdata.organization import Organization
        org_result = await db.execute(select(Organization).where(Organization.id == employee.org_id))
        org = org_result.scalar_one_or_none()
        if org:
            org_name = org.org_name

    # 有部门信息时，使用部门+岗位联合角色
    if org_name:
        role, _ = await ensure_org_position_role(db, position, org_name)
    else:
        role, _, _ = await ensure_position_role(db, position)

    return role, position
```

### 2. 修改 `erp_sync_service.py` — ERP 同步

#### 2.1 `sync_positions` — 无需修改

岗位同步时没有部门信息，仍创建默认角色（无部门信息）。`ensure_position_role` 保持不变。

#### 2.2 `sync_employees` — 无需修改

员工同步调用 `resolve_role_for_employee`，该函数已修改为自动获取部门信息并生成部门+岗位联合角色。

#### 2.3 `sync_employee_organizations` — 添加角色更新

当回填 `Employee.org_id` 后，需要重新同步用户角色：

```python
# 在回填 org_id 后，重新同步用户角色
if emp and emp.org_id != org.id:
    emp.org_id = org.id
    stats["org_id_backfilled"] += 1
    # 重新同步用户角色（现在有了部门信息，会生成部门+岗位联合角色）
    await sync_user_role_from_employee(self.spc_db, emp)
```

### 3. 修改 `basicdata.py` — 员工 CRUD

#### 3.1 员工创建/更新

当前已在 `create_employee` 和 `update_employee` 中调用 `sync_user_role_from_employee`，无需额外修改。`resolve_role_for_employee` 已自动处理部门信息。

#### 3.2 `ensure_position_roles` API

当前 API 为所有未关联角色的 Position 创建默认角色。保持不变，这些默认角色作为无部门信息时的兜底。

### 4. 前端 — 无需修改

- 角色名会自动显示为 "岗位-装配车间-普工" 格式
- 权限矩阵编辑页面按 role_id 加载，无需改动
- 用户管理页面的角色选择器会显示新的角色名

## 数据迁移策略

**无需主动迁移**。采用"懒迁移"策略：

1. 现有角色（如"岗位-普工"）保持不变，作为默认角色
2. 当员工重新同步或角色重新解析时，自动生成部门+岗位联合角色
3. 用户下次登录或 ERP 同步时，SysUser.role_id 会更新为新的部门+岗位联合角色
4. 旧的默认角色在所有用户迁移完成后可手动清理

## 验证步骤

1. **单元验证**：检查 `make_position_role_code("普工", "装配车间")` 和 `make_position_role_code("普工", "精益车间")` 生成不同的 role_code
2. **ERP 同步验证**：执行员工同步后，检查同一岗位名不同部门的员工是否关联了不同的角色
3. **权限配置验证**：在用户管理页面，分别编辑"岗位-装配车间-普工"和"岗位-精益车间-普工"的权限，确认可以独立配置
4. **前端显示验证**：确认角色名正确显示部门信息
