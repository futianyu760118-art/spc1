# 供应商付款排程 — 下月应付金额列设计

日期：2026-10-13
状态：已获用户确认（方案 A）

## 需求

供应商付款排程页面表格新增一列「下月应付金额」：以每个供应商「实际付款到哪个月份」为基准，显示基准月之后第一个有应付金额的月份及金额（下月没有就下下月，依此类推）。

## 澄清结论

1. **基准月推导（按供应商各自推导，从付款数据自动得出）**：该供应商最晚的「付款申请单据日期」所在月 = 付款进度月。数据源走 purchase_invoice 新增的 `payment_apply_date` 列（付款申请主表 `t_RP_PayApplyBill.FDate`，现有 purchase_invoices 同步 SQL 已 JOIN 该表，仅需加选该字段）。
2. **下月应付金额** = 从进度月+1 开始，找第一个有效应付金额 > 0 的排款月（排款月 = 到票日期 + 账期天数；有效应付 = `_effective_payable`，与「月到期应付金额」同口径），取该月合计。找不到则显示 `-`。
3. **无付款申请记录的供应商**（进度月不可推导）→ 以最早应付月为基准，即直接取最早有应付金额的排款月的金额。
4. 同时返回实际月份 `next_month`（可能不是字面下月），列表金额旁标注该月份；导出加「下月应付金额」「下月应付月份」两列。
5. 展示范围：列表 + 导出；汇总卡片不变。

## 方案（A）：扩展同步 SQL + purchase_invoice 新列 + 服务层计算

### 后端

- `backend/app/models/material/purchase_invoice.py`
  - 新增 `payment_apply_date = Column(Date, comment="付款申请日期")`。
- `backend/init_database.py`
  - `migrate_columns` 增加 `"purchase_invoice": {"payment_apply_date": "DATE"}`。
  - 种子 SQL（purchase_invoices 模板）补 `付款申请日期` 字段与映射（新环境用；现有库用一次性脚本改运行时配置）。
- `backend/alembic/versions/` 新增迁移文件（与 migrate_columns 同语句，幂等 ADD COLUMN）。
- 运行时 `sync_sql_config`（sync_type=purchase_invoices，生产 id=16）：
  - SELECT 增加 `aa.FDate AS 付款申请日期`；
  - field_mapping 增加 `"付款申请日期": {"target": "payment_apply_date", ...}`。
  - 一次性脚本 `backend/scripts/oneoff/update_purchase_invoice_sync_payment_apply_date.py` 更新现有库配置（用后删）。因该 SQL 无 :since 限制（year(p.FDate)>=2025 全量），下次定时同步自动回填历史数据。
- `backend/app/services/material/supplier_payment_service.py`
  - `_get_supplier_all_invoices` 查询增加 `payment_apply_date` 字段。
  - 新增 `_compute_next_month_due(invoices)` 纯函数：按排款月分组有效应付；进度月 = max(payment_apply_date 所在月)；无进度月时取最早应付月；返回 `(next_month, next_month_due)`，找不到返回 `(None, None)`。
  - 列表/导出流程对每个聚合行附 `next_month_due`、`next_month`；`SORT_LABELS` 增加 `next_month_due`；`EXPORT_COLUMNS` 增加「下月应付金额」「下月应付月份」。
- `backend/app/schemas/material/schemas.py`
  - `SupplierPaymentOut` 增加 `next_month_due: Optional[float] = None`、`next_month: Optional[str] = None`。

### 前端

- `frontend/src/pages/MaterialCenter/SupplierPayment/index.tsx`
  - `SupplierPaymentRow` 接口增加 `next_month_due`、`next_month`。
  - 新列「下月应付金额」（置于「实际到期未付」之后，右对齐，sorter 用 `next_month_due`）：金额下方小字显示实际月份（`YYYY年M月`）；金额为 null 显示灰色 `-`。

### 测试

- `backend/tests/unit/test_supplier_payment_next_month.py`：纯函数单测覆盖进度月推导、空月跳过、无付款申请记录回退最早应付月、进度月之后全空返回 None、在途票据不计入。

## 约束与注意

- 同步延迟过滤（`_not_paid_clause` / sync_filters）与 `_effective_payable` 口径与现有查询一致。
- ERP 同步只覆盖 `data_source='erp'` 行的守卫与此改动无关（purchase_invoice 无该列），不改同步代码逻辑，只改 SQL 配置。
- 供应商维度权限（`get_supplier_name_scope`）已在 API 层生效，服务层沿用现有 `supplier_name` 传参。
- 响应结构维持 `{ code, message, data }` 包装。
- 只读页面，无任何写操作。

## 验证

- `cd backend && python -m pytest`（既有套件 + 新单测须通过）。
- `cd frontend && npm run build`（唯一 typecheck）。
- 手动：更新同步 SQL 配置后触发一次采购开票同步，检查 `payment_apply_date` 回填；列表新列数值/月份标注、排序、导出两列。
