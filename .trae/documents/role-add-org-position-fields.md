# 计划：角色表添加部门和岗位ID字段

## 摘要

在 `sys_role` 表中添加 `org_id`（部门ID）和 `position_id`（岗位ID）字段，使角色与部门、岗位建立直接关联。这样 `sys_user` 的角色匹配就可以直接通过部门+岗位查找角色，简化现有的基于哈希编码的间接匹配逻辑。

---

## 现状分析

### 当前角色匹配流程（间接匹配）

1. `SysRole` 表只有 `id, role_code, role_name, permissions, created_at`，**没有**部门和岗位字段
2. 角色与部门/岗位的关联完全依赖 `role_code` 的哈希编码：
   - `make_position_role_code()` 将 `position_name` 或 `org_name + position_name` 哈希为 `pos_{sha1_digest}` 编码
   - 查找角色时通过 `role_code` 匹配，无法直接按 `org_id + position_id` 查询
3. `ensure_org_position_role()` 创建部门+岗位联合角色时，只存储了 `role_code`（含哈希），没有存储原始的 `org_id` 和 `position_id`
4. `Position` 表有 `role_id` 字段，但只关联全局岗位角色，不关联部门+岗位联合角色

### 问题

- 无法通过 `org_id + position_id` 直接查询角色，必须先查部门名称再拼哈希编码
- 角色列表无法直观显示该角色属于哪个部门、哪个岗位
- 数据库层面缺少外键约束，角色与部门/岗位的关系仅靠编码约定维持

---

## 修改方案

### Step 1：模型 — `SysRole` 添加 `org_id` 和 `position_id` 字段

**文件**：`backend/app/models/basicdata/user.py`

在 `SysRole` 类中添加：
```python
org_id = Column(BigInteger, nullable=True, comment="关联部门ID")
position_id = Column(BigInteger, nullable=True, comment="关联岗位ID")
```

- 两个字段均可为 NULL（admin、supplier 等系统角色不关联部门/岗位）
- `org_id` 关联 `scm_organization.id`，`position_id` 关联 `scm_position.id`
- 不添加外键约束（保持与现有模式一致，项目不使用数据库外键）

### Step 2：数据库迁移 — 添加列

**文件**：新建 Alembic 迁移脚本

执行 `alembic revision --autogenerate` 生成迁移，或手动编写 SQL：
```sql
ALTER TABLE sys_role ADD COLUMN org_id BIGINT;
ALTER TABLE sys_role ADD COLUMN position_id BIGINT;
COMMENT ON COLUMN sys_role.org_id IS '关联部门ID';
COMMENT ON COLUMN sys_role.position_id IS '关联岗位ID';
```

### Step 3：角色解析逻辑 — 修改 `ensure_org_position_role` 和 `ensure_position_role`

**文件**：`backend/app/services/basicdata/position_role_service.py`

修改 `ensure_org_position_role()`：
- 接收 `org_id` 参数（新增）
- 创建角色时设置 `org_id` 和 `position_id`
- 查找角色时优先通过 `org_id + position_id` 查询，fallback 到 `role_code` 查询

修改 `ensure_position_role()`：
- 创建角色时设置 `position_id`（全局岗位角色，`org_id` 为 NULL）

修改 `resolve_role_for_employee()`：
- 传递 `employee.org_id` 给 `ensure_org_position_role()`

### Step 4：角色列表 API — 返回部门和岗位信息

**文件**：`backend/app/api/v1/basicdata/users.py`

修改 `list_roles` API：
- JOIN `Organization` 和 `Position` 表
- 返回 `org_id`, `org_name`, `position_id`, `position_name` 字段

### Step 5：前端 — 角色管理页面显示部门和岗位

**文件**：`frontend/src/pages/BasicDataCenter/RoleManagement.tsx`

- `RoleItem` 接口增加 `org_id`, `org_name`, `position_id`, `position_name`
- 角色列表增加"部门"和"岗位"列
- 角色编辑弹窗显示关联的部门和岗位（只读，由系统自动关联）

### Step 6：数据回填 — 为现有角色填充 org_id 和 position_id

**文件**：`backend/app/services/basicdata/position_role_service.py`

新增 `backfill_role_org_position()` 函数：
- 遍历所有 `role_code` 以 `pos_` 开头的角色
- 通过 `Position.role_id` 反查岗位
- 通过角色名解析部门名称（`岗位-{部门名}-{岗位名}` 格式）查找部门
- 回填 `org_id` 和 `position_id`

---

## 具体实现细节

### Step 1：SysRole 模型修改

```python
class SysRole(Base):
    __tablename__ = "sys_role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_code = Column(String(32), nullable=False, unique=True)
    role_name = Column(String(64), nullable=False)
    permissions = Column(JSONB)
    org_id = Column(BigInteger, nullable=True, comment="关联部门ID")
    position_id = Column(BigInteger, nullable=True, comment="关联岗位ID")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
```

### Step 3：角色解析逻辑修改

**`ensure_position_role`** 修改：
```python
async def ensure_position_role(db: AsyncSession, position: Position) -> tuple[SysRole, bool, bool]:
    # ... 现有逻辑不变 ...
    # 创建角色时增加 position_id
    role = SysRole(
        role_code=role_code,
        role_name=desired_name,
        permissions=get_position_permissions(position.position_name),
        position_id=position.id,  # 新增
    )
```

**`ensure_org_position_role`** 修改签名和逻辑：
```python
async def ensure_org_position_role(
    db: AsyncSession,
    position: Position,
    org_name: Optional[str] = None,
    org_id: Optional[int] = None,  # 新增参数
) -> tuple[SysRole, bool]:
    # 优先通过 org_id + position_id 查找
    if org_id and position.id:
        existing = await db.execute(
            select(SysRole).where(
                SysRole.org_id == org_id,
                SysRole.position_id == position.id,
            )
        )
        role = existing.scalar_one_or_none()
        if role:
            # 更新名称（如果需要）
            if role.role_name != desired_name:
                role.role_name = desired_name
            if not role.permissions:
                role.permissions = get_position_permissions(position.position_name)
            return role, False

    # Fallback: 通过 role_code 查找（兼容旧数据）
    role_code = make_position_role_code(position.position_code, position.position_name, org_name)
    role_result = await db.execute(select(SysRole).where(SysRole.role_code == role_code))
    role = role_result.scalar_one_or_none()
    role_created = False

    if role:
        if role.role_name != desired_name:
            role.role_name = desired_name
        if not role.permissions:
            role.permissions = get_position_permissions(position.position_name)
        # 回填 org_id 和 position_id
        if org_id and not role.org_id:
            role.org_id = org_id
        if position.id and not role.position_id:
            role.position_id = position.id
    else:
        role = SysRole(
            role_code=role_code,
            role_name=desired_name,
            permissions=get_position_permissions(position.position_name),
            org_id=org_id,         # 新增
            position_id=position.id, # 新增
        )
        db.add(role)
        await db.flush()
        role_created = True

    return role, role_created
```

**`resolve_role_for_employee`** 修改：
```python
async def resolve_role_for_employee(db: AsyncSession, employee: Employee) -> tuple[Optional[SysRole], Optional[Position]]:
    position = await resolve_position_for_employee(db, employee)
    if not position:
        return None, None

    org_name = None
    org_id = None
    if employee.org_id:
        from app.models.basicdata.organization import Organization
        org_result = await db.execute(select(Organization).where(Organization.id == employee.org_id))
        org = org_result.scalar_one_or_none()
        if org:
            org_name = org.org_name
            org_id = org.id  # 新增

    if org_name:
        role, _ = await ensure_org_position_role(db, position, org_name, org_id=org_id)  # 传递 org_id
    else:
        role, _, _ = await ensure_position_role(db, position)

    return role, position
```

### Step 4：角色列表 API 修改

```python
@router.get("/roles", response_model=ResponseModel[dict])
async def list_roles(...):
    user_count_sub = (
        select(SysUser.role_id, func.count().label("user_count"))
        .group_by(SysUser.role_id)
        .subquery()
    )
    result = await db.execute(
        select(SysRole, func.coalesce(user_count_sub.c.user_count, 0), Organization, Position)
        .outerjoin(user_count_sub, SysRole.id == user_count_sub.c.role_id)
        .outerjoin(Organization, SysRole.org_id == Organization.id)
        .outerjoin(Position, SysRole.position_id == Position.id)
        .order_by(SysRole.id)
    )
    rows = result.all()
    # ...
    return ResponseModel(data={
        "items": [
            {
                "id": role.id,
                "role_code": role.role_code,
                "role_name": role.role_name,
                "permissions": merge_role_permission_additions(role.role_code, role.permissions),
                "user_count": user_count,
                "org_id": role.org_id,
                "org_name": org.org_name if org else None,
                "position_id": role.position_id,
                "position_name": position.position_name if position else None,
            }
            for role, user_count, org, position in paged
        ],
        "total": total,
    })
```

### Step 6：数据回填

新增函数，在 `sync-roles` API 中调用，为现有角色回填 `org_id` 和 `position_id`：

```python
async def backfill_role_org_position(db: AsyncSession) -> int:
    """回填现有角色的 org_id 和 position_id，返回更新数量"""
    result = await db.execute(select(SysRole))
    roles = result.scalars().all()
    updated = 0
    for role in roles:
        changed = False
        # 通过 position_id 反查
        if not role.position_id:
            pos_result = await db.execute(
                select(Position).where(Position.role_id == role.id)
            )
            pos = pos_result.scalar_one_or_none()
            if pos:
                role.position_id = pos.id
                changed = True
        # 通过角色名解析部门
        if not role.org_id and role.role_name.startswith("岗位-"):
            parts = role.role_name.split("-", 2)
            if len(parts) == 3:
                org_name = parts[1]
                org_result = await db.execute(
                    select(Organization).where(Organization.org_name == org_name)
                )
                org = org_result.scalar_one_or_none()
                if org:
                    role.org_id = org.id
                    changed = True
        if changed:
            updated += 1
    return updated
```

---

## 假设与决策

1. **`org_id` 和 `position_id` 均可为 NULL**：admin、supplier 等系统角色不关联部门/岗位
2. **不添加数据库外键约束**：与项目现有模式保持一致
3. **查找角色时优先通过 `org_id + position_id`**，fallback 到 `role_code` 哈希匹配（兼容旧数据）
4. **角色列表 JOIN Organization/Position** 获取名称，性能可接受（角色数量有限）
5. **数据回填在 `sync-roles` API 中执行**，不需要单独的迁移脚本（除了添加列）

---

## 验证步骤

1. 数据库 `sys_role` 表新增 `org_id` 和 `position_id` 列
2. 调用 `sync-roles` API 后，现有岗位角色的 `org_id` 和 `position_id` 被正确回填
3. 角色管理页面显示部门和岗位列
4. 新创建的部门+岗位联合角色自动填充 `org_id` 和 `position_id`
5. 通过 `org_id + position_id` 能直接查询到对应角色
