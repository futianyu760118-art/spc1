
# 权限取消后页面仍可见问题分析报告

## 问题描述

用户反馈已在用户管理中取消了"基础数据与集成中心"下的多个菜单权限（数据集成、基础数据管理、问题反馈、文件管理），但：
1. 这些菜单仍然显示在左侧导航栏
2. 相关接口仍然可以访问

## 问题根源分析

### 1. 权限别名机制导致权限绕过

在前端 `auth.ts` 和后端 `security.py` 中都存在权限别名映射：

```typescript
// 前端 auth.ts
const permissionAliases: Record<string, string[]> = {
  'basicdata.feedback': ['masterdata.feedback'],
  'basicdata.files': ['masterdata.files'],
  // ...双向映射
}
```

当检查权限时，系统会同时检查原始权限和其别名权限：

```typescript
const resourcesToCheck = [resource, ...(permissionAliases[resource] || [])]
for (const candidate of resourcesToCheck) {
  const actions = perms[candidate]
  if (Array.isArray(actions) && actions.includes(action)) return true
}
```

**问题**：如果用户只取消了 `basicdata.feedback` 的权限，但角色仍然拥有 `masterdata.feedback` 的权限，通过别名映射，权限检查仍然会通过。

### 2. 前端权限缓存问题

前端用户权限信息存储在 `localStorage` 中，当管理员在后台修改角色权限后：
- 后端 `PermissionChecker` 会**实时从数据库查询权限**，所以接口权限会立即生效
- 前端菜单过滤使用的是 `localStorage` 中缓存的旧权限数据

在 `MainLayout.tsx` 中有定期刷新逻辑：
```typescript
useEffect(() => {
  if (!originalToken || isShareUser()) return
  authApi.getMe()
    .then((res: any) => {
      if (res.data) {
        setAuth(originalToken, res.data)
      }
    })
    .catch(() => {})
}, [originalToken, isShareUser, setAuth])
```

但这个刷新只在页面加载时执行一次，后续权限变更无法自动感知。

### 3. 菜单配置缺少父级权限控制

在 `MainLayout.tsx` 的菜单配置中，"基础数据与集成中心"没有设置 `permission` 属性：

```typescript
{
  key: 'basicdata-center',
  icon: <DatabaseOutlined />,
  label: '基础数据与集成中心',
  children: [  // 没有 permission 属性，导致父菜单始终显示
    { key: '/import', icon: <ImportOutlined />, label: '数据集成', permission: 'basicdata.import' },
    // ...
  ],
}
```

由于父菜单没有权限控制，即使所有子菜单都被过滤，父菜单仍然会显示（只是没有子项）。

## 修复方案

### 方案一：修复权限别名导致的权限绕过（核心修复）

**问题**：当取消 `basicdata.*` 权限时，如果角色仍然拥有 `masterdata.*` 权限，通过别名映射仍然可以访问。

**修复**：取消权限时，需要同时取消对应的别名权限。

在用户管理的权限更新逻辑中，当移除某个权限时，需要同时移除其别名对应的权限。

### 方案二：强制刷新前端权限缓存

**问题**：前端缓存的权限数据不会自动更新。

**修复**：在权限变更后，强制相关用户重新登录或刷新权限。

在后端权限变更接口中，增加 `login_version` 递增逻辑，使旧 token 失效。

### 方案三：为父菜单添加权限控制

**问题**：父菜单没有权限控制，始终显示。

**修复**：为"基础数据与集成中心"添加 `permission` 属性。

## 具体修复步骤

### 步骤 1：修复前端菜单配置

修改 `frontend/src/layouts/MainLayout.tsx`：
- 为 `basicdata-center` 添加权限控制

### 步骤 2：修复后端权限检查逻辑

修改 `backend/app/core/security.py`：
- 确保权限检查严格按照数据库中的权限配置，避免别名导致的权限绕过

### 步骤 3：修复权限更新逻辑

修改 `backend/app/api/v1/basicdata/users.py`：
- 在权限变更时，同时处理别名权限
- 递增用户的 `login_version`，使旧 token 失效

### 步骤 4：前端权限刷新优化

修改 `frontend/src/layouts/MainLayout.tsx`：
- 增加权限过期检测，自动刷新

## 实施优先级

1. **高优先级**：步骤 1 + 步骤 2（修复菜单显示和权限绕过问题）
2. **中优先级**：步骤 3（确保权限变更立即生效）
3. **低优先级**：步骤 4（用户体验优化）

## 风险评估

- **步骤 1**：修改菜单配置，风险低，仅影响菜单显示逻辑
- **步骤 2**：修改权限检查逻辑，需要测试确保不影响正常权限验证
- **步骤 3**：修改用户版本号，会导致用户重新登录，需要告知用户
- **步骤 4**：前端优化，风险低
