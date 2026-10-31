# 供应链与生产协同中台 MVP

## 项目结构

```
SPC-v2/
├── backend/                   # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/            # API 路由
│   │   ├── core/              # 配置/数据库/安全
│   │   ├── models/            # SQLAlchemy 数据模型
│   │   ├── schemas/           # Pydantic 请求/响应
│   │   └── services/          # 业务逻辑
│   ├── alembic/               # 数据库迁移
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                  # React 前端
│   ├── src/
│   │   ├── pages/             # 页面组件
│   │   ├── components/        # 公共组件
│   │   ├── layouts/           # 布局组件
│   │   ├── services/          # API 调用
│   │   └── store/             # 状态管理
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── 供应链与生产协同中台.md     # PRD
└── 技术方案.md                 # 技术设计文档
```

## 快速启动

### 方式一：Docker Compose（推荐）

```bash
docker-compose up -d
```

- 前端: http://localhost:3000
- 后端 API: http://localhost:8000/api/v1/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### 方式二：本地开发

**后端**

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 创建数据库
# CREATE DATABASE spc_db;

# 执行迁移
alembic revision --autogenerate -m "init"
alembic upgrade head

# 启动
uvicorn app.main:app --reload --port 8000
```

**前端**

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 http://localhost:3000，API 请求通过 Vite proxy 转发到后端。

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Ant Design 5 + TailwindCSS + Vite |
| 后端 | Python FastAPI + SQLAlchemy 2.0 + Alembic |
| 数据库 | PostgreSQL 15 |
| 缓存 | Redis 7 |
| 部署 | Docker Compose |

## 核心功能

- **控制塔首页** — 风险灯号总览、订单风险表格、统计卡片
- **订单详情** — 物料需求、PO绑定关系钻取
- **采购订单** — PO 全状态追踪
- **ETA 管理** — 采购维护 ETA，变更历史留痕
- **异常台账** — 问题记录、处置动作、台账导出
- **数据导入** — Excel 导入订单/物料/PO
- **风险扫描** — 自动识别漏下单、ETA延期、长周期等异常
