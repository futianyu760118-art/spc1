# 员工同步与系统用户创建分离方案

## 一、现状分析

### 当前实现
在 [erp_sync_service.py](file:///d:/wanghuazheng/project/SPC-v2/backend/app/services/basicdata/erp_sync_service.py) 的 `sync_employees` 方法（L1609-L1848）中，员工同步时**自动创建系统用户**，逻辑如下：

1. 从 ERP 同步员工数据 → 写入 `scm_employee` 表
2. 根据员工岗位+部门自动匹配/创建角色（`resolve_or_create_role`）
3. 查询 `sys_user` 表是否已有该 `emp_code` 对应的用户
4. **如果没有 → 自动创建 SysUser**，密码为配置的默认密码，角色按岗位自动分配
5. **如果有 → 自动更新** username、display_name、role_id、is_active 等字段

### 问题
| 问题 | 说明 |
|------|------|
| **安全风险** | 所有同步进来的员工都自动获得系统账号，包括保洁、门卫等不需要使用系统的岗位，扩大了攻击面 |
| **权限失控** | 自动分配角色可能不准确，岗位映射规则硬编码在 `POSITION_CATEGORY_BY_NAME`，无法覆盖所有岗位 |
| **默认密码** | 所有自动创建的用户使用同一默认密码，虽有 `is_default_password` 标记，但仍有安全隐患 |
| **数据污染** | 大量从不登录的"僵尸账号"存在于 `sys_user` 表中，影响用户管理和审计 |
| **职责混淆** | 员工数据（人事信息）和系统用户（访问权限）是不同维度的概念，不应耦合 |

### 数据模型关系
- `Employee`（scm_employee）：员工人事信息，通过 ERP 同步
- `SysUser`（sys_user）：系统登录账号，含 username、hashed_password、role_id、emp_code
- `SysRole`（sys_role）：角色权限，通过岗位+部门自动生成
- 关联方式：`SysUser.emp_code` → `Employee.emp_code`（松耦合，非外键）

---

## 二、业界方案参考

### 方案 A：JIT（Just-In-Time）自动开通 — 首次登录时创建
> 参考：SCIM 协议、Okta/Azure AD 的 JIT Provisioning

- 员工同步只写入 Employee 表，**不创建 SysUser**
- 员工首次通过企业认证（如 OA/SSO）登录时，系统检测到无 SysUser 记录，**自动创建**
- 创建时根据 Employee 的岗位+部门自动分配角色
- **优点**：零人工操作，只有真正需要登录的人才有账号
- **缺点**：需要 SSO/统一认证入口，当前系统暂无

### 方案 B：管理员审批开通 — 申请+审批流
> 参考：SAP、用友、企业微信后台管理

- 员工同步只写入 Employee 表，**不创建 SysUser**
- 需要使用系统的员工（或其主管）在用户管理页面**提交开通申请**
- 管理员审批后创建 SysUser，分配角色
- **优点**：权限管控严格，可审计
- **缺点**：增加管理成本，需要审批流程

### 方案 C：按规则自动开通 + 管理员可干预（推荐）
> 参考：飞书/钉钉的"按部门/岗位自动授权"、IAM 系统的 Rule-Based Provisioning

- 员工同步只写入 Employee 表，**不自动创建 SysUser**
- 新增**用户开通规则**配置：指定哪些岗位/部门/状态组合的员工自动开通账号
- 同步时按规则判断是否需要自动创建用户，不在规则内的员工需管理员手动开通
- 管理员可在用户管理页面批量选择员工开通账号
- **优点**：兼顾自动化和管控，灵活可配置
- **缺点**：需要新增规则配置功能

---

## 三、推荐方案：方案 C — 按规则自动开通 + 管理员可干预

### 核心设计

#### 1. 新增「用户开通规则」配置
在系统配置中新增规则，定义哪些员工自动开通系统账号：

```python
# 新增模型：UserProvisioningRule
class UserProvisioningRule(Base):
    __tablename__ = "sys_user_provisioning_rule"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), comment="规则名称")
    # 匹配条件（任一为空表示不限制）
    position_category = Column(String(32), comment="岗位类别（如 manager/quality/engineer）")
    position_name_pattern = Column(String(128), comment="岗位名称匹配（支持模糊匹配）")
    org_code = Column(String(64), comment="组织编码")
    min_status = Column(Integer, default=1, comment="最低员工状态（0-试用 1-正式）")
    auto_create = Column(Boolean, default=True, comment="是否自动创建用户")
    default_role_id = Column(Integer, comment="默认角色ID（为空则按岗位自动匹配）")
    is_active = Column(Boolean, default=True, comment="规则是否启用")
    priority = Column(Integer, default=0, comment="优先级，数字越大越优先")
    created_at = Column(DateTime, server_default=func.now())
```

**默认规则**（初始化数据）：
- 岗位类别为 `manager/director/executive/quality/engineer/purchaser/warehouse/finance/sales/hr_admin/assistant/production_lead/readonly` 的员工 → 自动开通
- 岗位类别为 `operator/facility/employee` 的员工 → **不自动开通**

#### 2. 修改 sync_employees 逻辑
将自动创建用户的逻辑从 `sync_employees` 中**剥离**，改为：

```
sync_employees 只做：
  1. 同步员工数据到 scm_employee
  2. 解析岗位、匹配角色（保留现有逻辑）
  3. 检查用户开通规则，符合条件的自动创建 SysUser
  4. 不符合规则的员工 → 仅记录日志，不创建用户
  5. 已有 SysUser 的员工 → 继续更新（保持现有逻辑）
```

#### 3. 新增「批量开通用户」API
管理员可在用户管理页面选择未开通账号的员工，批量开通：

```
POST /api/v1/users/batch-provision
Body: { emp_codes: ["E001", "E002", ...], role_id: 5 (可选) }
```

#### 4. 新增「未开通员工列表」查询
在用户管理页面新增 Tab，展示已同步但未开通系统账号的员工：

```
GET /api/v1/users/unprovisioned-employees?keyword=xxx&position_category=operator
```

#### 5. 员工离职/状态变更处理
- 员工状态变为非活跃（4-解聘、5-离职、6-退休、7-无效）时 → **自动停用** SysUser（设 is_active=false）
- 这部分逻辑保持不变，因为停用是安全必要的

---

## 四、具体改动清单

### 后端改动

| 文件 | 改动 | 说明 |
|------|------|------|
| `backend/app/models/basicdata/user.py` | 新增 `UserProvisioningRule` 模型 | 用户开通规则表 |
| `backend/app/services/basicdata/erp_sync_service.py` | 修改 `sync_employees` | 剥离自动创建用户逻辑，改为按规则判断 |
| `backend/app/api/v1/basicdata/users.py` | 新增 3 个 API | 批量开通、未开通员工列表、开通规则管理 |
| `backend/app/services/basicdata/position_role_service.py` | 新增 `should_auto_provision` 函数 | 判断员工是否应自动开通 |
| `backend/app/core/config.py` | 新增配置项 | `ERP_SYNC_AUTO_PROVISION_ENABLED`（是否启用规则自动开通，默认 true） |
| Alembition migration | 新增迁移 | 创建 `sys_user_provisioning_rule` 表 + 初始化默认规则 |

### 前端改动

| 文件 | 改动 | 说明 |
|------|------|------|
| 用户管理页面 | 新增「未开通员工」Tab | 展示未开通账号的员工列表，支持批量开通 |
| 用户管理页面 | 新增「开通规则」Tab | 管理用户开通规则配置 |
| 系统设置页面 | 新增开关 | 是否启用自动开通 |

---

## 五、实施步骤

### Step 1：新增 UserProvisioningRule 模型 + 迁移
- 创建模型文件
- 生成 Alembic 迁移
- 初始化默认规则数据

### Step 2：修改 sync_employees 逻辑
- 将自动创建用户的代码提取为独立函数 `_provision_user_for_employee`
- 新增 `should_auto_provision` 函数，查询规则判断是否自动开通
- `sync_employees` 中调用 `should_auto_provision` 替代原来的无条件创建

### Step 3：新增 API
- 批量开通用户 API
- 未开通员工列表 API
- 开通规则 CRUD API

### Step 4：前端适配
- 用户管理页面新增 Tab

### Step 5：测试验证
- 同步员工时，operator/facility 类岗位不再自动创建用户
- manager/engineer 等岗位仍自动创建
- 管理员可手动批量开通
- 已有用户不受影响

---

## 六、假设与决策

1. **已有 SysUser 的员工不受影响** — 同步时继续更新已有用户的信息和角色
2. **默认规则基于岗位类别** — 使用 `position_role_service.py` 中已有的 `get_position_category` 分类
3. **开通规则可叠加** — 多条规则按优先级匹配，先匹配到的生效
4. **不引入审批流** — 当前阶段用"管理员手动开通"代替审批流，避免过度设计
5. **员工离职仍自动停用用户** — 这是安全底线，不应受规则影响
