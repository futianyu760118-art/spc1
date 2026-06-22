# 采购订单模型添加"是否已关闭"字段

## 概述
为采购订单（PurchaseOrder）模型添加 `is_closed` 布尔字段，当订单已关闭时，前端状态列显示"已关闭"标签。

## 现状分析

### 当前状态计算逻辑
- `po_status` 字段存储在数据库中，但实际展示时通过 `_recalc_status()` 函数实时重算
- 状态优先级：`inspected`（已检验）> `arrived`（已到料）> `overdue`（逾期未到）> `pending`（待到料）
- 前端 `STATUS_MAP` 定义了4种状态标签：已检验/已到料/逾期未到/待到料，另有呆滞物料标签
- ERP同步时默认 `po_status = "placed"`

### 关键文件
| 文件 | 作用 |
|------|------|
| `backend/app/models/material/purchase_order.py` | ORM 模型 |
| `backend/app/schemas/material/schemas.py` | Pydantic Schema |
| `backend/app/api/v1/material/purchase_plan.py` | 采购到料计划 API（主要业务逻辑） |
| `backend/app/api/v1/material/purchase_orders.py` | 采购订单 API |
| `frontend/src/pages/MaterialCenter/PurchasePlan/index.tsx` | 前端页面 |

## 修改方案

### 1. 模型层 — 添加 `is_closed` 字段
**文件**: `backend/app/models/material/purchase_order.py`

- 添加 `is_closed = Column(Boolean, nullable=False, server_default='0', default=False)` 字段
- 需要导入 `Boolean` 类型

### 2. Schema 层 — 添加 `is_closed` 字段
**文件**: `backend/app/schemas/material/schemas.py`

- `PurchaseOrderOut`: 添加 `is_closed: bool = False`
- `PurchaseOrderUpdate`: 添加 `is_closed: Optional[bool] = None`（允许手动关闭/重新打开订单）
- `PurchaseOrderBatchUpdate`: 添加 `is_closed: Optional[bool] = None`（允许批量关闭订单）

### 3. 后端业务逻辑 — 状态计算优先处理已关闭
**文件**: `backend/app/api/v1/material/purchase_plan.py`

- `_recalc_status()`: 在最前面判断 `is_closed`，如果为 True 则直接设置 `po_status = 'closed'`，不再走后续状态判断
- `_build_filters()`: 添加 `closed` 状态的筛选条件（`PurchaseOrder.is_closed == True`）
- `STATUS_LABELS`: 添加 `'closed': '已关闭'`
- 单条更新和批量更新逻辑中，如果 `is_closed` 被修改，需要重新计算状态
- 导出逻辑中，`STATUS_LABELS` 已包含 `closed` 映射

**文件**: `backend/app/api/v1/material/purchase_orders.py`

- `update_po_status()`: 无需修改，关闭操作通过 `is_closed` 字段控制，而非 `po_status`

### 4. 前端展示
**文件**: `frontend/src/pages/MaterialCenter/PurchasePlan/index.tsx`

- `PlanRow` 接口：添加 `is_closed: boolean`
- `STATUS_MAP`：添加 `closed: { label: '已关闭', color: 'default' }`
- 状态列渲染：当 `is_closed` 为 true 时，优先显示"已关闭"标签（覆盖其他状态）
- 状态筛选：添加"已关闭"筛选选项
- 编辑弹窗：添加"关闭订单"开关（Switch 组件）
- 批量编辑弹窗：添加"关闭订单"选项

### 5. 数据库迁移
需要创建 Alembic 迁移脚本，添加 `is_closed` 布尔列，默认值为 `False`。

## 假设与决策
1. **`is_closed` 优先级最高**：已关闭的订单不再显示其他状态（如逾期、待到料等），直接显示"已关闭"
2. **手动关闭**：通过编辑弹窗或批量编辑手动设置 `is_closed`，而非自动判断
3. **可重新打开**：`is_closed` 可从 True 改回 False，恢复自动状态计算
4. **ERP同步不受影响**：ERP同步不覆盖 `is_closed` 字段（该字段由用户手动管理）

## 验证步骤
1. 启动后端，确认数据库迁移成功，`is_closed` 列已添加
2. 在前端采购到料计划页面，手动关闭一条订单，确认状态显示"已关闭"
3. 重新打开该订单，确认状态恢复为自动计算的值
4. 批量关闭多条订单，确认批量操作生效
5. 按状态筛选"已关闭"，确认筛选结果正确
6. 导出数据，确认"已关闭"状态正确导出
