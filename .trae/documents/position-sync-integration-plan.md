# 岗位同步集成到数据集成 — 实施计划

## 问题分析

### 当前状态
1. ✅ 前端数据集成页面已有岗位同步 Tab（`positions`）
2. ✅ 后端 `sync_positions` 方法已实现，且已调用 `ensure_position_role` 自动创建角色
3. ✅ 后端 `sync_employees` 方法已实现，且已通过 `resolve_role_for_employee` 从岗位获取角色
4. ✅ 岗位同步已在 `VALID_SYNC_TYPES` 和 `type_map` 中注册
5. ✅ 数据库 `scm_employee` 表已有 `position_id` 列（通过迁移脚本添加）
6. ✅ Pydantic Schema `EmployeeBase` 已包含 `position_id` 字段

### 关键缺陷
1. **Employee ORM 模型缺少 `position_id` 字段**（最关键！）
   - 数据库有 `position_id` 列，Pydantic schema 有该字段，但 ORM 模型 `Employee` 没有定义
   - 导致 `_filter_model_fields()` 会过滤掉 `position_id`，使得员工同步时 `position_id` 永远不会被保存到数据库
   - 人员同步时 `resolve_role_for_employee` 只能通过 `employee.position`（岗位名称字符串）回退匹配，无法通过 ID 精确匹配

2. **岗位同步统计不包含角色创建信息**
   - `sync_positions` 的 stats 只有 `synced/created/updated/skipped/errors`
   - `ensure_position_role` 返回 `(role, role_created, position_linked)` 但没有被收集

3. **`_resolve_position_id` 不支持 `oa_position_id` 匹配**
   - 如果 ERP 数据提供了 `oa_position_id`，当前方法无法通过它匹配到岗位

4. **前端岗位同步 Tab 缺少角色创建统计展示**

5. **人员同步结果不包含角色分配统计**

---

## 实施步骤

### 步骤 1：修复 Employee ORM 模型 — 添加 `position_id` 字段
**文件**: `backend/app/models/basicdata/employee.py`

- 在 `Employee` 模型中添加 `position_id = Column(BigInteger, nullable=True, comment="岗位ID")`
- 这是修复整个链路的关键，确保 `_filter_model_fields` 不会过滤掉 `position_id`

### 步骤 2：增强 `_resolve_position_id` 方法 — 支持 `oa_position_id` 匹配
**文件**: `backend/app/services/basicdata/erp_sync_service.py`

- 在 `_resolve_position_id` 方法中增加 `oa_position_id` 匹配逻辑
- 匹配优先级：`position_code` > `oa_position_id` > `position_name`
- 如果 ERP 员工数据提供了 `oa_position_id`，可以通过它精确匹配到已同步的岗位

### 步骤 3：增强岗位同步统计 — 收集角色创建信息
**文件**: `backend/app/services/basicdata/erp_sync_service.py`

- 在 `sync_positions` 方法的 stats 中添加 `roles_created` 和 `roles_linked` 字段
- 收集 `ensure_position_role` 返回的 `(role, role_created, position_linked)` 信息
- 在日志中输出角色创建统计

### 步骤 4：增强人员同步 — 通过岗位 ID 获取角色
**文件**: `backend/app/services/basicdata/erp_sync_service.py`

- 在 `sync_employees` 方法中，确保 `position_id` 被正确保存到 Employee 记录（步骤 1 修复后自动生效）
- 在 stats 中添加 `roles_from_position` 统计，记录通过岗位 ID 获取到角色的用户数
- 优化角色解析逻辑：优先使用 `employee.position_id` 直接查询 Position → Role，而非回退到名称匹配

### 步骤 5：前端岗位同步 Tab 增强 — 展示角色创建统计
**文件**: `frontend/src/pages/BasicDataCenter/DataIntegration/index.tsx`

- 在岗位同步 Tab 中增加角色创建信息的展示
- 在 `SyncResultCard` 组件中支持显示 `roles_created` 和 `roles_linked` 统计
- 在人员同步 Tab 中增加角色分配统计展示

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/app/models/basicdata/employee.py` | 添加 `position_id` 字段 |
| `backend/app/services/basicdata/erp_sync_service.py` | 增强 `_resolve_position_id`、`sync_positions` 统计、`sync_employees` 角色解析 |
| `frontend/src/pages/BasicDataCenter/DataIntegration/index.tsx` | 增强岗位/人员同步 Tab 展示角色统计 |

---

## 数据流示意

### 修复后的完整链路

```
岗位同步 (sync_positions)
  ├── 从 ERP/OA 拉取岗位数据
  ├── 创建/更新 Position 记录
  └── 调用 ensure_position_role → 自动创建角色 (SysRole)
        └── position.role_id = role.id  ← 岗位关联角色

人员同步 (sync_employees)
  ├── 从 ERP 拉取人员数据
  ├── _resolve_position_id → 通过 oa_position_id / position_code / position_name 匹配岗位
  ├── 保存 employee.position_id = position.id  ← 员工关联岗位（修复后生效）
  ├── resolve_role_for_employee → 通过 position_id 查询 Position → Role
  └── 创建/更新 SysUser → user.role_id = role.id  ← 用户获取岗位对应角色
```
