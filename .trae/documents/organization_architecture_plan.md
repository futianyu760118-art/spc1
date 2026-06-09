
# 组织架构功能实现计划

## 概述
在基础数据与集成中心添加组织架构功能，将现有的部门（组织）和员工数据以树形结构展示，并支持查看部门下的员工。

## 现状分析
1. 已存在 `Organization`（组织/部门）模型和 `Employee`（员工）模型
2. 已存在相应的 CRUD API 接口
3. 前端已有 `Organizations` 和 `Employees` 两个基础页面，但仅为简单表格展示

## 实现方案

### 1. 后端修改

#### 文件：`backend/app/api/v1/basicdata/basicdata.py`
- 添加获取组织树形结构的 API 端点 `/basicdata/organizations/tree`
- 添加获取指定部门下员工的 API 端点（可选，复用现有的列表接口添加筛选参数）

#### 文件：`backend/app/schemas/basicdata/schemas.py`
- 添加组织树节点 schema 类型（类似 MaterialTreeNode）

### 2. 前端修改

#### 文件：`frontend/src/pages/BasicDataCenter/Organizations.tsx`
- 重构页面，使用树形组件展示组织架构
- 左侧显示组织树，右侧显示选中组织下的员工列表
- 保持原有的新增、编辑、删除组织功能

### 3. 功能特性
- 组织树形展示
- 点击组织节点，右侧展示该组织下的员工
- 支持组织和员工的常规 CRUD 操作
- 响应式布局，适配不同屏幕尺寸

## 风险与注意事项
- 确保树形结构的构建逻辑正确处理循环依赖
- 保持现有 API 的兼容性
- 确保数据同步后的展示效果良好

## 实施步骤
1. 先修改后端，添加组织树 API
2. 再修改前端，重构 Organizations 页面
3. 测试功能完整性
4. 若有问题，及时调整

