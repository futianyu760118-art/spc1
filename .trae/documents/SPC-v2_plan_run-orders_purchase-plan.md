# SPC-v2 三个需求实现计划

## 需求概述

1. **Run-Orders 排序异常** — `/run-orders` 页面排序功能修复
2. **Purchase-Plan 分析图表 + 逾期自动推送** — `/purchase-plan` 页面增加分析图表，逾期自动推送通知
3. **Purchase-Plan 供应商即时沟通** — `/purchase-plan` 页面增加供应商即时沟通对话框

---

## 需求一：Run-Orders 排序异常修复

### 问题分析
前端 `RunOrderList/index.tsx` 中 `handleTableChange` 存在以下问题：

1. **排序取消不彻底**：当用户点击列头取消排序（第三次点击，`sorter.order` 为 `undefined`）时，`sortField` 仍保留字段名，导致 `sort_by` 仍被发送到后端，后端默认按 `asc` 排序而非清除排序
2. **状态更新可能导致重复请求**：`handleTableChange` 同时更新 `sortInfo` 和 `filters`，两者都在 `fetchOrders` 的 `useCallback` 依赖中，可能导致不必要的重复请求

### 修改方案

**文件：** `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx`

**修改 `handleTableChange` 函数（第 97-105 行）：**

```tsx
const handleTableChange = (pagination: any, tableFilters: any, sorter: any) => {
  const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
  const sortField = sortOrder ? sorter.field : undefined  // 排序取消时清除 sort_by
  const orderTypeFilter = tableFilters?.order_type?.length > 0 ? tableFilters.order_type : []
  const orderStatusFilter = tableFilters?.order_status?.length > 0 ? tableFilters.order_status : []
  const isDomesticFilter = tableFilters?.is_domestic?.length > 0 ? tableFilters.is_domestic : []
  setSortInfo({ sort_by: sortField, sort_order: sortOrder })
  setFilters(f => ({ ...f, order_type: orderTypeFilter, order_status: orderStatusFilter, is_domestic: isDomesticFilter }))
}
```

**关键改动：** `sortField` 仅在 `sortOrder` 有值时赋值，否则为 `undefined`，确保取消排序时不再向后端发送 `sort_by` 参数。

---

## 需求二：Purchase-Plan 分析图表 + 逾期自动推送

### 2.1 后端：分析图表 API

**新增文件：** `backend/app/api/v1/material/purchase_plan_analysis.py`

新增端点：
- `GET /materials/purchase-plan/analysis` — 返回分析图表数据

**返回数据结构：**
```json
{
  "status_distribution": [
    { "name": "待到料", "value": 100, "color": "#94a3b8" },
    { "name": "已到料", "value": 50, "color": "#3b82f6" },
    { "name": "已检验", "value": 30, "color": "#16a34a" },
    { "name": "逾期未到", "value": 20, "color": "#e11d48" }
  ],
  "supplier_overdue_top5": [
    { "name": "供应商A", "value": 15 },
    { "name": "供应商B", "value": 10 }
  ],
  "overdue_trend": [
    { "date": "2026-06-08", "overdue": 12, "total": 120 },
    { "date": "2026-06-09", "overdue": 15, "total": 118 }
  ],
  "material_shortage_top5": [
    { "name": "物料A", "value": 500 }
  ]
}
```

**路由注册：** 在 `backend/app/api/v1/__init__.py` 中注册新路由

### 2.2 前端：分析图表组件

**新增文件：** `frontend/src/pages/MaterialCenter/PurchasePlan/components/AnalysisCharts.tsx`

使用 `@ant-design/charts`（已安装）：
- **状态分布饼图**（Pie）— 待到料/已到料/已检验/逾期未到 分布
- **供应商逾期 Top 5 柱状图**（Column）— 按逾期数量排列
- **缺料物料 Top 5 柱状图**（Column）— 按缺料数量排列

**修改文件：** `frontend/src/pages/MaterialCenter/PurchasePlan/index.tsx`

- 在统计卡片下方、表格上方插入图表区域
- 添加图表显示/隐藏切换按钮
- 图表数据通过 `materialApi.getPurchasePlanAnalysis()` 获取

**新增 API：** `frontend/src/services/api.ts` 中 `materialApi` 新增：
```ts
getPurchasePlanAnalysis: (params: Record<string, any>) =>
  api.get('/materials/purchase-plan/analysis', { params }),
```

### 2.3 后端：逾期自动推送通知

**方案：** 使用 FastAPI 的 `BackgroundTasks` 或在 `startup` 事件中启动定时任务

**新增文件：** `backend/app/services/scheduler/overdue_checker.py`

- 基于 `APScheduler`（需在 `requirements.txt` 中添加 `apscheduler`）
- 每天定时检查逾期未到的采购计划
- 按责任人（owner）分组，为每个责任人创建通知
- 通知类型为 `material_alert`，已对接现有通知系统

**修改文件：** `backend/app/main.py`
- 在应用启动时初始化并启动 `APScheduler`
- 注册逾期检查任务（每天 9:00 执行）

**通知内容示例：**
```
标题：逾期未到料提醒
内容：您负责的采购计划中有 5 条逾期未到物料，请及时跟进处理。
```

**安装依赖：** `backend/requirements.txt` 添加 `apscheduler`

---

## 需求三：供应商即时沟通

### 3.1 后端：消息系统

**新增数据模型：** `backend/app/models/material/supplier_message.py`

```python
class SupplierMessage(Base):
    __tablename__ = "supplier_message"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    supplier_name = Column(String(256), nullable=False, index=True)
    supplier_account = Column(String(128), nullable=True)
    sender_id = Column(Integer, ForeignKey("sys_user.id"), nullable=False)
    sender_name = Column(String(128), nullable=False)
    content = Column(Text, nullable=False)
    po_no = Column(String(64), nullable=True)  # 关联采购单号
    created_at = Column(DateTime, server_default=func.now())
```

**新增 Schema：** `backend/app/schemas/material/schemas.py` 中添加：
```python
class SupplierMessageCreate(BaseModel):
    supplier_name: str
    supplier_account: Optional[str] = None
    content: str
    po_no: Optional[str] = None

class SupplierMessageOut(BaseModel):
    id: int
    supplier_name: str
    supplier_account: Optional[str]
    sender_id: int
    sender_name: str
    content: str
    po_no: Optional[str]
    created_at: datetime
```

**新增 API：** `backend/app/api/v1/material/supplier_message.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/materials/supplier-messages` | 获取与某个供应商的对话历史（分页） |
| `POST` | `/materials/supplier-messages` | 发送消息 |
| `GET` | `/materials/supplier-messages/unread` | 获取未读消息（用于轮询） |

**路由注册：** 在 `backend/app/api/v1/__init__.py` 中注册

### 3.2 前端：即时沟通对话框

**新增文件：** `frontend/src/pages/MaterialCenter/PurchasePlan/components/SupplierChatModal.tsx`

功能：
- 替换现有的"供应商沟通"Modal（当前仅支持复制文本）
- 左侧：消息列表区域（显示对话历史）
- 底部：输入框 + 发送按钮
- 支持按供应商筛选对话
- 自动轮询新消息（每 5 秒）
- 消息气泡样式：我方消息右对齐蓝色，供应商消息左对齐灰色
- 支持引用采购单号（从当前行带入）

**修改文件：** `frontend/src/pages/MaterialCenter/PurchasePlan/index.tsx`

- 将 `openContact` 函数改为打开新的 `SupplierChatModal`
- 移除旧的 `contactModal` 和 `contactText` 相关状态和逻辑
- 保留 `buildSupplierMessage` 作为初始消息模板

**新增 API：** `frontend/src/services/api.ts` 中新增：
```ts
export const supplierMessageApi = {
  list: (supplierName: string, params: Record<string, any>) =>
    api.get('/materials/supplier-messages', { params: { supplier_name: supplierName, ...params } }),
  send: (data: { supplier_name: string; supplier_account?: string; content: string; po_no?: string }) =>
    api.post('/materials/supplier-messages', data),
  unread: (supplierName?: string) =>
    api.get('/materials/supplier-messages/unread', { params: supplierName ? { supplier_name: supplierName } : {} }),
}
```

---

## 实施步骤汇总

### 步骤 1：修复 Run-Orders 排序（需求一）
- [ ] 修改 `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx` 中 `handleTableChange`

### 步骤 2：Purchase-Plan 分析图表后端（需求二-后端）
- [ ] 新增 `backend/app/api/v1/material/purchase_plan_analysis.py`
- [ ] 在 `backend/app/api/v1/__init__.py` 注册路由

### 步骤 3：Purchase-Plan 分析图表前端（需求二-前端）
- [ ] 新增 `frontend/src/pages/MaterialCenter/PurchasePlan/components/AnalysisCharts.tsx`
- [ ] 修改 `frontend/src/pages/MaterialCenter/PurchasePlan/index.tsx` 集成图表
- [ ] 在 `frontend/src/services/api.ts` 新增 API

### 步骤 4：逾期自动推送通知（需求二-逾期）
- [ ] 新增 `backend/app/services/scheduler/overdue_checker.py`
- [ ] 修改 `backend/app/main.py` 集成定时任务
- [ ] 在 `backend/requirements.txt` 添加 `apscheduler`

### 步骤 5：供应商即时沟通后端（需求三-后端）
- [ ] 新增 `backend/app/models/material/supplier_message.py`
- [ ] 在 `backend/app/schemas/material/schemas.py` 添加 Schema
- [ ] 新增 `backend/app/api/v1/material/supplier_message.py`
- [ ] 在 `backend/app/api/v1/__init__.py` 注册路由
- [ ] 创建数据库迁移（或直接建表）

### 步骤 6：供应商即时沟通前端（需求三-前端）
- [ ] 新增 `frontend/src/pages/MaterialCenter/PurchasePlan/components/SupplierChatModal.tsx`
- [ ] 修改 `frontend/src/pages/MaterialCenter/PurchasePlan/index.tsx` 集成聊天
- [ ] 在 `frontend/src/services/api.ts` 新增 API

### 步骤 7：验证与重启
- [ ] 执行 `.\scripts\restart-docker-compose.ps1` 重启项目