# K3 ICMrpResult 计划订单 vs 采购订单对比分析

## 概述

实现一个新功能：从 K3 ERP 的 ICMrpResult（MRP 运算结果/计划订单）数据中，对比采购订单，列出哪些计划订单还没下单、哪些已经关闭。

## 现状分析

### 已有基础设施
1. **`mrp_plan_order` 表**：迁移脚本 `7314cacebdb6` 已创建该表，包含字段：
   - `fbill_no`（计划订单号）、`fmaterial_id`（物料内码）、`material_code`、`material_name`
   - `fplan_qty`（计划数量）、`fplan_start_date`、`fplan_finish_date`、`fneed_date`（需求日期）
   - `forder_type`（订单类型：采购/生产/委外）、`fstatus`（0=计划,1=已下达,2=已关闭,3=已作废）
   - `fsupply_org`、`frequire_org`、`fsource_bill_no`（源单号）
   - **但尚未创建对应的 ORM Model、Schema、API、前端页面**

2. **`purchase_order` 表**：已有完整的 ORM Model、Schema、API、前端页面

3. **ERP 同步机制**：`sync_sql_config` 表 + `erp_sync_service` 已支持从 K3 拉取数据，`materials` sync_type 的 SQL 已引用 `T_PLN_MRPRESULT` 表

4. **前端物料中心**：已有多个子页面（采购到料计划、齐套分析、长交期物料等），路由结构清晰

### 核心对比逻辑
- **计划订单（mrp_plan_order）**中 `forder_type='采购'` 的记录，按 `material_code` 关联 `purchase_order`
- **没下单**：计划订单状态为"计划"(fstatus=0) 或"已下达"(fstatus=1)，且在 `purchase_order` 中找不到对应 `material_code` 的采购订单
- **已关闭**：计划订单 `fstatus=2`（已关闭）或 `fstatus=3`（已作废）
- **已下单**：计划订单已下达(fstatus=1) 且 `purchase_order` 中存在对应物料的采购订单

## 实现方案

### 1. 后端 — ORM Model

**文件**: `backend/app/models/material/mrp_plan_order.py`（新建）

创建 `MrpPlanOrder` 模型，字段与迁移脚本 `7314cacebdb6` 中 `mrp_plan_order` 表一致：
- `id`, `fbill_no`, `fmaterial_id`, `material_code`, `material_name`, `fplan_qty`, `fplan_start_date`, `fplan_finish_date`, `fneed_date`, `forder_type`, `fstatus`, `fsupply_org`, `frequire_org`, `fsource_bill_no`, `data_source`, `created_at`, `updated_at`

**文件**: `backend/app/models/material/__init__.py`（修改）

添加 `from app.models.material.mrp_plan_order import MrpPlanOrder`

### 2. 后端 — Schema

**文件**: `backend/app/schemas/material/schemas.py`（修改）

新增：
- `MrpPlanOrderOut`：计划订单输出 Schema
- `MrpPlanComparisonItem`：对比结果项，包含计划订单信息 + 对比状态（未下单/已下单/已关闭）+ 关联的采购订单信息
- `MrpPlanComparisonStats`：统计信息（总数、未下单数、已下单数、已关闭数、已作废数）

### 3. 后端 — API

**文件**: `backend/app/api/v1/material/mrp_plan_comparison.py`（新建）

提供以下接口：

1. `GET /materials/mrp-plan-comparison` — 对比分析列表
   - 查询参数：`fstatus`（状态筛选）、`forder_type`（订单类型筛选，默认"采购"）、`material_code`、`material_name`、`comparison_status`（未下单/已下单/已关闭）、`keyword`、分页、排序
   - 逻辑：LEFT JOIN `purchase_order` ON `material_code`，根据 fstatus 和是否有关联 PO 判断对比状态

2. `GET /materials/mrp-plan-comparison/stats` — 统计概览
   - 返回各状态数量统计

3. `GET /materials/mrp-plan-comparison/export` — 导出对比结果

**文件**: `backend/app/api/v1/material/__init__.py`（修改）

添加 `mrp_plan_comparison_router`

**文件**: `backend/app/api/v1/__init__.py`（修改）

注册路由：`api_router.include_router(material.mrp_plan_comparison_router, prefix="/materials/mrp-plan-comparison", tags=["物料齐套中心-计划订单对比"])`

### 4. 后端 — 同步配置

**文件**: `backend/init_database.py`（修改）

在 `seed_sync_sql_config` 中新增 `mrp_plan_orders` sync_type，SQL 查询 K3 的 `ICMrpResult` 表（即 `T_PLN_MRPRESULT`），字段映射到 `mrp_plan_order` 表。

### 5. 前端 — 页面

**文件**: `frontend/src/pages/MaterialCenter/MrpPlanComparison/index.tsx`（新建）

页面功能：
- 顶部统计卡片：总计划订单数、未下单数、已下单数、已关闭/已作废数
- 筛选栏：订单类型（默认采购）、对比状态、物料代码/名称搜索、需求日期范围
- 数据表格：计划订单号、物料代码、物料名称、计划数量、需求日期、订单类型、计划订单状态、对比状态（标签颜色区分）、关联采购订单号、采购订单状态
- 导出按钮

### 6. 前端 — 路由

**文件**: `frontend/src/App.tsx`（修改）

在物料中心菜单下添加"计划订单对比"路由

## 对比状态判断逻辑

```
对比状态 = CASE
  WHEN mrp.fstatus IN (2, 3) THEN '已关闭'        -- fstatus=2已关闭, fstatus=3已作废
  WHEN mrp.fstatus = 0 THEN '未下单'               -- fstatus=0计划状态，还没下达
  WHEN mrp.fstatus = 1 AND po IS NULL THEN '未下单' -- 已下达但无对应采购订单
  WHEN mrp.fstatus = 1 AND po IS NOT NULL THEN '已下单' -- 已下达且有对应采购订单
END
```

关联逻辑：`mrp_plan_order.material_code = purchase_order.material_code`，且采购订单 `po_status` 不是已关闭/已作废状态。

## 假设与决策

1. **关联方式**：按 `material_code` 关联（而非计划订单号→采购订单号），因为 K3 MRP 结果和采购订单之间可能没有直接的单号关联
2. **只看采购类型**：默认筛选 `forder_type='采购'`，因为生产/委外类型不涉及采购订单
3. **数据来源**：计划订单数据通过 ERP 同步获取，存入 `mrp_plan_order` 表
4. **权限**：复用 `materials.purchase_plan` 的 read 权限

## 验证步骤

1. 运行数据库迁移确保 `mrp_plan_order` 表存在
2. 通过 ERP 同步或手动插入测试数据到 `mrp_plan_order`
3. 调用 `/materials/mrp-plan-comparison` 接口验证对比结果
4. 前端页面展示对比数据，筛选和统计功能正常
5. 导出功能正常
