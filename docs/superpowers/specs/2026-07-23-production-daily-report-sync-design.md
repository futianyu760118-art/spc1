# 生产日报表 ERP 同步 — 设计文档

- 日期: 2026-07-23
- 范围: 后端 ERP/OA SQL 同步 (无前端页面)
- 状态: 已批准, 待实现

## 目标

新增 `production_daily_report` 表, 从 ERP/OA 通过 SQL 同步生产日报数据。
sync_type = `production_daily_reports`。

## 需求 (来自用户)

字段 (12 个业务字段):
日期、销售订单号、生产订单号、规格型号、BOM编号、物料代码、生产工序、颜色、
完工数量、车间、当日工时、总工资。

关键决策 (用户已确认):
1. 数据来源: **ERP/OA SQL 同步** (全部字段来自一个 ERP 源表)。
2. 业务唯一键: **单列 `oa_id`** (ERP 主键), `_bulk_upsert(key_fields=["oa_id"])`。
3. 前端范围: **只要同步功能** (DataIntegration 页自动发现, 无独立前端页面)。
4. 源表 SQL: **先空着**, 部署后在 `sync_sql_config` 表里配置真实 SQL。
   空 SQL 时同步会失败并记入 SyncLog (期望行为, 不静默跳过)。
5. 额外: 加一个**最小只读列表端点**用于验证同步结果 (AGENTS.md 要求端点验证)。

## 表结构 `production_daily_report`

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer PK autoincrement | 自增主键 |
| oa_id | String(64) UNIQUE NOT NULL | ERP 唯一键 (业务主键, dedup) |
| report_date | Date | 日期 |
| sale_order_no | String(64) | 销售订单号 |
| production_order_no | String(64) | 生产订单号 |
| specification | String(128) | 规格型号 |
| bom_no | String(64) | BOM编号 |
| material_code | String(64) | 物料代码 |
| process | String(64) | 生产工序 |
| color | String(64) | 颜色 |
| completed_qty | Numeric(15,2) | 完工数量 |
| workshop | String(128) | 车间 |
| work_hours | Numeric(10,2) | 当日工时 |
| total_wages | Numeric(12,2) | 总工资 |
| data_source | String(32) NOT NULL default 'erp' | 来源守卫列 (manual/excel 行不被覆盖) |
| erp_updated_at | DateTime | 增量同步水位 |
| created_at / updated_at | DateTime | 审计列 |

索引: oa_id (unique partial), report_date, production_order_no, material_code, workshop。

## 改动文件清单 (9 处, 全后端)

| # | 文件 | 改动 | 模板 |
|---|------|------|------|
| 1 | `backend/app/models/production/production_daily_report.py` (NEW) | ORM 模型 | `production_task_order.py` |
| 2 | `backend/app/models/production/__init__.py` | 导入 | L8 |
| 3 | `backend/app/models/__init__.py` | 导入 (create_all 注册) | L19-21 |
| 4 | `backend/app/schemas/production/schemas.py` | `ProductionDailyReportOut` | L150 |
| 5 | `backend/app/services/basicdata/erp_sync_service.py` | import + `sync_production_daily_reports` | L2793-2834, L44 |
| 6 | `backend/app/services/basicdata/sync_scheduler.py` | `sync_method_map` 注册 | L54 |
| 7 | `backend/app/api/v1/basicdata/sync.py` | `VALID_SYNC_TYPES` + `type_map` | L31, L96 |
| 8 | `backend/init_database.py` `seed_sync_sql_config` | 种子 (空 SQL) | L1571-1609 |
| 9 | `backend/app/api/v1/production/production_daily_report.py` (NEW) + `__init__.py` | 最小列表端点 + 挂载 | `front_process.py:72-160` |

## 不触碰

- `migrate_columns` (新表由 create_all 创建)
- 前端任何文件 (DataIntegration 页通过 `GET /sync/config-status` 自动发现新 sync_type)
- Alembic

## 验证

无测试套件。验证方式:
1. `python -c "import app.models; import app.api.v1.production"` 语法/import 检查
2. 启动 uvicorn, 确认表创建
3. `GET /api/v1/basicdata/sync/config-status` 应出现 `production_daily_reports`
4. `POST /api/v1/basicdata/sync/production_daily_reports` 应返回 task_id (空 SQL 会失败, 正常)
5. `GET /api/v1/production/daily-reports` 返回空分页

## 风险

- 空 SQL 导致同步失败是期望行为; 但 sync_method_map/type_map/VALID_SYNC_TYPES 三处必须都注册,
  否则手动触发会报 "不支持的同步类型"。
- 权限 `production.daily_report` 需存在或 PermissionChecker 放行; 现有同步端点用 `settings` 权限,
  列表端点用 `production.daily_report` read — 若该权限未在 role 里配置, 列表端点会 403。
  (本任务不修改权限种子, 由现有 permission_registry 机制处理。)
