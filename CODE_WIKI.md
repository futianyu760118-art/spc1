# 供应链与生产协同中台 - Code Wiki

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈](#2-技术栈)
3. [架构设计](#3-架构设计)
4. [模块职责](#4-模块职责)
5. [关键类与函数](#5-关键类与函数)
6. [数据库模型](#6-数据库模型)
7. [依赖关系](#7-依赖关系)
8. [运行方式](#8-运行方式)
9. [API接口总览](#9-API接口总览)
10. [核心业务流程](#10-核心业务流程)

---

## 1. 项目概述

**项目名称**: 供应链与生产协同中台 (SPC-v2)

**项目定位**: 企业级供应链与生产协同管理平台，提供订单交付、物料齐套、生产协同、异常管理等核心功能。

**核心价值**:
- 订单风险实时监控与预警
- 物料需求与采购订单的联动管理
- 生产工序进度追踪
- 异常问题闭环管理
- AI智能助手辅助决策

**项目状态**: MVP版本，已投入生产使用

---

## 2. 技术栈

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 前端 | React | 18.x | UI框架 |
| 前端 | TypeScript | 5.x | 类型安全 |
| 前端 | Ant Design | 5.x | UI组件库 |
| 前端 | TailwindCSS | 3.x | CSS框架 |
| 前端 | Vite | 6.x | 构建工具 |
| 前端 | Zustand | 5.x | 状态管理 |
| 后端 | FastAPI | 0.115.x | API框架 |
| 后端 | SQLAlchemy | 2.0.x | ORM框架 |
| 后端 | Alembic | 1.14.x | 数据库迁移 |
| 后端 | Pydantic | 2.x | 数据验证 |
| 后端 | Redis | 5.x | 缓存/会话 |
| 数据库 | PostgreSQL | 15+ | 主数据库 |
| 部署 | Docker Compose | - | 容器编排 |

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层 (React)                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────────┐   │
│  │ Pages   │ │Layouts  │ │Componets│ │ Services / Store   │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └─────────┬───────────┘   │
└───────┼───────────┼───────────┼─────────────────┼───────────────┘
        │           │           │                 │
        ▼           ▼           ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        API层 (FastAPI)                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Router: /api/v1/orders, /api/v1/materials, /api/v1/...│   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Service层                                │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ Order   │ │Material │ │Risk     │ │ERP Sync │ │AI Agent │  │
│  │Service  │ │Service  │ │Engine   │ │Service  │ │Service  │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Model层 (SQLAlchemy)                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  SaleOrder / PurchaseOrder / RiskIssue / SysUser ...   │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    数据库层 (PostgreSQL + Redis)                │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 模块划分

| 模块 | 职责 | 状态 |
|------|------|------|
| **dashboard** | 供应链驾驶舱、风险总览 | ✅ |
| **order** | 订单交付中心、跑单管理 | ✅ |
| **material** | 物料齐套中心、采购订单 | ✅ |
| **production** | 生产协同中心、工序管理 | ✅ |
| **exception** | 异常与质量中心、风险扫描 | ✅ |
| **rules** | 规则配置中心 | ✅ |
| **basicdata** | 基础数据管理、ERP同步 | ✅ |
| **assistant** | AI智能助手 | ✅ |

---

## 4. 模块职责

### 4.1 后端模块结构

```
backend/app/
├── api/v1/           # REST API路由
│   ├── dashboard/    # 驾驶舱接口
│   ├── order/        # 订单交付接口
│   ├── material/     # 物料齐套接口
│   ├── production/   # 生产协同接口
│   ├── exception/    # 异常管理接口
│   ├── rules/        # 规则配置接口
│   ├── basicdata/    # 基础数据接口
│   └── assistant/    # 智能助手接口
├── core/             # 核心基础设施
│   ├── config.py     # 配置管理
│   ├── database.py   # 数据库连接
│   ├── security.py   # 安全认证
│   ├── dependencies.py # 依赖注入
│   └── storage/      # 文件存储
├── models/           # SQLAlchemy模型
├── schemas/          # Pydantic数据结构
└── services/         # 业务逻辑服务
    ├── ai/           # AI服务抽象层
    ├── assistant/    # 智能助手服务
    ├── basicdata/    # 基础数据服务
    ├── dashboard/    # 仪表盘服务
    ├── exception/    # 异常处理服务
    ├── material/     # 物料服务
    ├── order/        # 订单服务
    └── production/   # 生产服务
```

### 4.2 API模块职责

| 模块 | 路径前缀 | 核心功能 |
|------|----------|----------|
| dashboard | `/api/v1/dashboard` | 风险总览、今日概览、14天滚动风险、订单风险分布 |
| order | `/api/v1/orders` | 订单列表、订单详情、内销订单、出货管理、风险池 |
| material | `/api/v1/materials` | 采购订单、物料需求、齐套分析、长交期物料、供应商风险 |
| production | `/api/v1/production` | SMT、组装、包装、工序异常、生产进度 |
| exception | `/api/v1/exceptions` | 风险扫描、异常总池、品质异常、问题日志、变更日志 |
| rules | `/api/v1/rules` | 点检规则、节点标准、责任归属、状态字典、作业指导书 |
| basicdata | `/api/v1/basicdata` | 用户管理、认证、审计日志、ERP同步、数据导入导出 |
| assistant | `/api/v1/assistant` | AI对话、工具调用、会话管理 |

### 4.3 Core模块职责

| 文件 | 职责 |
|------|------|
| `config.py` | 配置管理（数据库、ERP、JWT、AI等） |
| `database.py` | SQLAlchemy异步会话管理 |
| `security.py` | JWT认证、密码加密、权限检查 |
| `dependencies.py` | FastAPI依赖注入（获取当前用户等） |
| `storage/` | 文件存储抽象（本地/S3） |

---

## 5. 关键类与函数

### 5.1 核心安全类

#### 5.1.1 RoleChecker

**位置**: `backend/app/core/security.py`

**职责**: 角色校验依赖，用于API接口的角色权限控制

**使用方式**:
```python
from app.core.security import RoleChecker

@router.get("/admin", dependencies=[Depends(RoleChecker(["admin"]))])
async def admin_only():
    ...
```

#### 5.1.2 PermissionChecker

**位置**: `backend/app/core/security.py`

**职责**: 细粒度权限校验，支持资源级权限控制

**使用方式**:
```python
from app.core.security import PermissionChecker

@router.get("/orders", dependencies=[Depends(PermissionChecker("orders", "read"))])
async def list_orders():
    ...
```

### 5.2 风险引擎

#### 5.2.1 RiskEngine

**位置**: `backend/app/services/exception/risk_engine.py`

**职责**: 多因子加权风险评估引擎

**核心方法**:

| 方法 | 功能 |
|------|------|
| `assess_order(order)` | 评估单个订单风险 |
| `assess_all_orders(operator)` | 评估所有订单风险 |
| `run_full_scan(operator)` | 全量风险扫描并生成问题 |

**风险因子定义**:

| 因子 | 权重 | 说明 |
|------|------|------|
| delivery_delay | 25 | 交期延期 |
| shortage | 30 | 欠料风险 |
| process_lag | 15 | 工序滞后 |
| quality | 15 | 品质异常 |
| eta_delay | 20 | ETA延期 |
| inspection_ng | 15 | 客检NG |

**风险等级判定**:
- **Red**: 风险分数 >= 60
- **Yellow**: 风险分数 >= 30 且 < 60
- **Blue**: 风险分数 > 0 且 < 30
- **Green**: 风险分数 = 0

### 5.3 智能助手

#### 5.3.1 Agent

**位置**: `backend/app/services/assistant/agent.py`

**职责**: 单层LLM + Tool Calling智能助手

**核心方法**: `run(message, db, session_id, conversation_history, trace_id, user_id)`

**意图识别类型**:
- `QUERY_DATA`: 需要查询系统数据
- `ANALYZE_HISTORY`: 分析已有对话历史
- `GENERAL_CHAT`: 一般对话

**可用工具**:
- `search_orders`: 搜索销售订单
- `search_purchase_orders`: 搜索采购订单
- `search_materials`: 搜索物料
- `search_production`: 搜索生产进度
- `search_run_orders`: 搜索跑单记录
- `search_exceptions`: 搜索异常
- `search_invoices`: 搜索发票
- `search_eta_updates`: 搜索ETA变更
- `search_basicdata`: 搜索基础数据
- `search_users`: 搜索用户
- `get_dashboard_summary`: 获取驾驶舱概览
- `suggest_actions`: 生成行动建议
- `search_kit_analysis`: 查询订单齐套
- `search_bom_details`: 查询产品BOM明细

**稳固性增强（2026-07-10 引入）**:
- **自动上下文摘要**: `context_manager.py` — token 估算 + LLM 摘要，阈值 80k，可通过 `AI_SUMMARY_ENABLED` 关闭
- **优雅重试**: `retry.py` — 指数退避装饰器 `async_retry(RetryConfig(...))`，默认 LLM 3 次、工具 1 次
- **取消机制**: `cancellation.py` — `CancellationRegistry` 管理 `asyncio.Event`，客户端断连 / 后端超时触发
- **结构化日志**: `run_logger.py` — JSONL 异步写入 `backend/logs/assistant/{date}/{trace_id}.jsonl`
- **思考过程透传**: `agent_stream.py` 的 `ThinkTagFilter` 累积 `<think>...</think>` 内容并推送 `event:thinking` 事件
- **SSE 终态事件**: 新增 `event:cancelled`，含 `reason`（client_disconnected / timeout）

**新增 API 端点**:
- `GET /api/v1/assistant/logs`: 列出 Agent 运行日志文件（按 date / session_id 过滤）
- `GET /api/v1/assistant/logs/{trace_id}`: 读取指定 trace 的完整 JSONL 日志

### 5.4 调度器

#### 5.4.1 SyncScheduler

**位置**: `backend/app/services/basicdata/sync_scheduler.py`

**职责**: ERP定时同步调度器，支持配置化同步策略

**核心功能**:
- 支持增量/全量/混合同步策略
- 时间窗口限制
- 优先级排序
- 同步状态追踪

#### 5.4.2 RiskAssessmentScheduler

**位置**: `backend/app/services/exception/risk_scheduler.py`

**职责**: 风险评估定时调度器，每小时自动执行风险评估

### 5.5 仪表盘服务

#### 5.5.1 DashboardService

**位置**: `backend/app/services/dashboard/dashboard_service.py`

**职责**: 驾驶舱数据聚合服务

**核心方法**:

| 方法 | 返回数据 |
|------|----------|
| `get_summary()` | 风险总览摘要 |
| `get_today_overview()` | 今日概览数据 |
| `get_rolling_risk()` | 14天滚动风险 |
| `get_order_risk_distribution()` | 订单风险分布 |
| `get_closure_achievement()` | 闭环达成看板 |

---

## 6. 数据库模型

### 6.1 模型分类

| 模块 | 模型文件 | 核心表 |
|------|----------|--------|
| basicdata | `basicdata/*.py` | sys_user, sys_role, customer, supplier, material, product, sku, warehouse |
| order | `order/*.py` | sale_order, sale_order_line, eta_update, run_order |
| material | `material/*.py` | purchase_order, material_demand, binding, receipt_batch |
| exception | `exception/*.py` | risk_issue, quality_issue, issue_log, change_log |
| production | `production/*.py` | process_progress, work_order, schedule_plan |
| rules | `rules/*.py` | risk_rule, inspection_rule, node_standard |

### 6.2 核心模型关系

```
SaleOrder 1:N SaleOrderLine
  │
  ├─ N:M PurchaseOrder (via OrderMaterialPoBinding)
  ├─ N:M MaterialDemand
  └─ N:M RiskIssue

PurchaseOrder 1:N MaterialDemand
  │
  └─ N:1 Supplier

RiskIssue 1:N IssueLog
  │
  └─ N:1 SysUser (owner)

SysUser N:1 SysRole
```

### 6.3 SaleOrder 关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| order_no | String(64) | 订单号（主键一部分） |
| line_no | String(32) | 行号 |
| customer | String(128) | 客户名称 |
| product_code | String(64) | 产品编码 |
| order_qty | Numeric(15,2) | 订单数量 |
| promised_date | Date | 承诺交期 |
| status | String(32) | 订单状态 |
| risk_level | String(16) | 风险等级 |
| risk_score | Numeric(5,2) | 风险分数 |
| risk_factors | JSONB | 因子分值明细 |

### 6.4 RiskIssue 关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| issue_no | String | 问题编号（自动生成） |
| issue_type | String(32) | 问题类型 |
| risk_level | String(16) | 风险等级 |
| order_no | String(64) | 关联订单号 |
| material_code | String(64) | 关联物料编码 |
| po_no | String(64) | 关联采购订单号 |
| description | Text | 问题描述 |
| owner | String(64) | 负责人 |
| status | String(32) | 状态（open/processing/closed） |
| commit_date | Date | 承诺解决日期 |

---

## 7. 依赖关系

### 7.1 后端依赖（requirements.txt）

| 依赖 | 版本 | 用途 |
|------|------|------|
| fastapi | 0.115.6 | API框架 |
| uvicorn | 0.34.0 | ASGI服务器 |
| sqlalchemy | 2.0.36 | ORM |
| alembic | 1.14.1 | 数据库迁移 |
| asyncpg | 0.30.0 | PostgreSQL异步驱动 |
| pydantic | 2.10.4 | 数据验证 |
| python-jose | 3.3.0 | JWT认证 |
| passlib | 1.7.4 | 密码加密 |
| redis | 5.2.1 | 缓存 |
| pandas | 2.2.3 | 数据处理 |
| openpyxl | 3.1.5 | Excel处理 |
| apscheduler | 3.10.4 | 定时任务 |
| openai | >=1.0.0 | OpenAI API |
| dashscope | >=1.0.0 | 阿里云DashScope |

### 7.2 前端依赖（package.json）

| 依赖 | 版本 | 用途 |
|------|------|------|
| react | 18.3.1 | UI框架 |
| antd | 5.22.6 | UI组件库 |
| axios | 1.7.9 | HTTP客户端 |
| zustand | 5.0.2 | 状态管理 |
| react-router-dom | 6.28.1 | 路由 |
| @ant-design/charts | 2.2.1 | 图表组件 |
| dayjs | 1.11.13 | 日期处理 |

### 7.3 模块依赖关系

```
┌─────────────────────────────────────────────────────────┐
│                      api/v1/                           │
│  ├── dashboard ───→ dashboard_service                  │
│  ├── order      ───→ order_service                     │
│  ├── material   ───→ material_service                  │
│  ├── production ───→ production_service                │
│  ├── exception  ───→ risk_engine + exception_service   │
│  ├── rules      ───→ rules_service                     │
│  ├── basicdata  ───→ erp_sync_service                  │
│  └── assistant  ───→ agent + ai_service                │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                      services/                          │
│  ├── ai/         ───→ openai_provider + dashscope      │
│  ├── assistant/  ───→ tool_registry + session_store    │
│  └── exception/  ───→ risk_engine + risk_scheduler     │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                      core/                             │
│  ├── config.py     (配置)                              │
│  ├── database.py   (数据库连接)                        │
│  ├── security.py   (认证授权)                          │
│  └── dependencies.py (依赖注入)                        │
└─────────────────────────────────────────────────────────┘
```

---

## 8. 运行方式

### 8.1 Docker Compose（推荐）

```bash
cd SPC-v2
docker-compose up -d
```

**服务地址**:
- 前端: http://localhost:3000
- 后端API: http://localhost:8000/api/v1/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### 8.2 本地开发

#### 后端

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 创建数据库
# CREATE DATABASE spc_db;

# 执行迁移
alembic revision --autogenerate -m "init"
alembic upgrade head

# 启动
uvicorn app.main:app --reload --port 8000
```

#### 前端

```bash
cd frontend
npm install
npm run dev
```

### 8.3 配置说明

配置文件: `backend/.env`

**关键配置项**:

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| DATABASE_URL | 主数据库连接 | postgresql+asyncpg://root:123456@localhost:5432/spc_db |
| ERP_DB_URL | ERP中间库连接 | 空（可选） |
| ERP_SYNC_ENABLED | 是否启用ERP同步 | false |
| REDIS_URL | Redis连接 | redis://localhost:6379/0 |
| SECRET_KEY | JWT密钥 | your-secret-key-change-in-production |
| AI_DEFAULT_PROVIDER | AI服务提供商 | rule_based |
| AI_OPENAI_API_KEY | OpenAI密钥 | 空 |
| AI_DASHSCOPE_API_KEY | 阿里云密钥 | 空 |

---

## 9. API接口总览

### 9.1 认证接口

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/basicdata/auth/login` | 用户登录 |
| GET | `/api/v1/basicdata/auth/me` | 获取当前用户 |
| PUT | `/api/v1/basicdata/auth/change-password` | 修改密码 |

### 9.2 订单接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/orders` | 订单列表（支持多条件筛选） |
| GET | `/api/v1/orders/{order_no}` | 订单详情 |
| POST | `/api/v1/orders` | 创建订单 |
| PUT | `/api/v1/orders/{order_no}` | 更新订单 |
| DELETE | `/api/v1/orders/{order_no}` | 删除订单 |
| GET | `/api/v1/orders/export` | 导出订单 |
| GET | `/api/v1/orders/domestic` | 内销订单 |
| GET | `/api/v1/orders/risk-pool` | 订单风险池 |

### 9.3 物料接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/materials/purchase-plan` | 采购到料计划 |
| GET | `/api/v1/materials/issues` | 问题物料 |
| GET | `/api/v1/materials/long-lead` | 长交期物料 |
| GET | `/api/v1/materials/kit-analysis` | 齐套分析 |
| GET | `/api/v1/materials/supplier-risk` | 供应商风险 |

### 9.4 异常接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/exceptions/risk/scan` | 执行风险扫描 |
| GET | `/api/v1/exceptions/pool` | 异常总池 |
| POST | `/api/v1/exceptions/issues` | 创建风险问题 |
| PUT | `/api/v1/exceptions/issues/{issue_no}` | 更新问题状态 |
| GET | `/api/v1/exceptions/quality` | 品质异常 |

### 9.5 仪表盘接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/dashboard/summary` | 风险摘要 |
| GET | `/api/v1/dashboard/today` | 今日概览 |
| GET | `/api/v1/dashboard/rolling-risk` | 14天滚动风险 |
| GET | `/api/v1/dashboard/distribution` | 风险分布 |
| GET | `/api/v1/dashboard/closure-achievement` | 闭环达成 |

### 9.6 智能助手接口

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/assistant/chat` | AI对话 |
| POST | `/api/v1/assistant/chat-stream` | AI对话（流式） |
| GET | `/api/v1/assistant/sessions` | 会话列表 |
| DELETE | `/api/v1/assistant/sessions/{session_id}` | 删除会话 |

---

## 10. 核心业务流程

### 10.1 订单创建流程

```
用户创建订单 → API层验证 → Service层处理 → Model层持久化 → 返回响应
    │              │              │              │
    ▼              ▼              ▼              ▼
  前端表单    Pydantic校验    业务逻辑处理    SQLAlchemy写入
                            - 生成订单号
                            - 计算风险分数
```

### 10.2 风险评估流程

```
定时调度触发 → RiskEngine.assess_all_orders() → 更新订单风险等级 → 记录审计日志
                   │
                   ▼
         遍历所有订单 → 计算6个风险因子 → 加权求和 → 确定风险等级
                   │
                   ▼
         应用规则调整 → 降级/升级风险等级
```

### 10.3 风险扫描流程

```
触发扫描 → 评估订单风险 → 按规则生成RiskIssue → 去重处理 → 保存问题
    │              │                │              │            │
    ▼              ▼                ▼              ▼            ▼
  手动/定时    assess_all_orders  8种规则类型   检查重复     db.add()
                              (delivery_delay, shortage, etc.)
```

### 10.4 ERP同步流程

```
定时调度 → 加载同步配置 → 判断是否执行 → 执行同步 → 更新状态 → 记录日志
    │              │              │              │            │         │
    ▼              ▼              ▼              ▼            ▼         ▼
  每分钟检查    SyncSqlConfig  时间窗口+间隔   ERPSyncService  SyncSqlConfig  SyncLog
```

### 10.5 AI助手对话流程

```
用户提问 → 意图识别 → 调用工具 → 获取结果 → 生成回复 → 保存会话
    │           │            │           │           │          │
    ▼           ▼            ▼           ▼           ▼          ▼
  用户输入   QUERY_DATA    search_orders  数据返回   LLM总结   Redis存储
         /ANALYZE_HISTORY  /search_purchase_orders
         /GENERAL_CHAT     /suggest_actions
```

---

## 附录

### A. 风险等级含义

| 等级 | 颜色 | 含义 | 处理建议 |
|------|------|------|----------|
| red | 🔴 红色 | 高风险 | 立即处理 |
| yellow | 🟡 黄色 | 中风险 | 关注跟进 |
| blue | 🔵 蓝色 | 低风险 | 持续监控 |
| green | 🟢 绿色 | 无风险 | 正常执行 |

### B. 问题类型缩写

| 类型 | 缩写 | 说明 |
|------|------|------|
| delivery_delay | DD | 交期延期 |
| shortage | SH | 欠料风险 |
| eta_delay | ED | ETA延期 |
| process_lag | PL | 工序滞后 |
| quality | QL | 品质异常 |
| inspection_ng | IN | 客检NG |
| holiday_risk | HR | 假期风险 |
| long_lead | LL | 长周期物料 |

### C. 用户角色

| 角色代码 | 说明 | 权限范围 |
|----------|------|----------|
| admin | 管理员 | 全部权限 |
| operator | 操作员 | 业务操作权限 |
| viewer | 查看者 | 只读权限 |

---

**文档版本**: v1.0  
**生成日期**: 2026-06-03  
**项目版本**: 供应链与生产协同中台 MVP