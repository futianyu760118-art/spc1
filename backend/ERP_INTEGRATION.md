# ERP 数据对接方案

## 一、对接架构

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│   ERP 系统   │ <── │   SPC 系统       │ ──> │   SPC 数据库  │
│  (只读访问)  │     │  (定时同步)       │     │  (存储同步数据)│
└─────────────┘     └──────────────────┘     └─────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
  订单数据同步        物料需求同步         采购订单同步
  (自定义SQL)         (自定义SQL)          (自定义SQL)
```

**核心思路**：SPC 系统通过配置的 SQL 语句直接查询 ERP 数据库，SQL 配置存储在 `sync_sql_config` 表中，可在前端"系统配置 → 同步SQL配置"页面管理。

## 二、对接步骤

### 步骤 1：获取 ERP 数据库连接信息

向 ERP 管理员或 IT 部门获取以下信息：
- 数据库类型（SQL Server / PostgreSQL / MySQL / Oracle）
- 数据库地址、端口、数据库名
- 只读账号的用户名、密码
- 相关表的表结构（字段名、类型）

**关键要求**：
- SPC 连接账号只需要 **只读权限**
- 确保 SPC 服务器到 ERP 数据库的网络连通性
- 确认 ERP 表中有用于增量同步的时间字段（如 `update_time`, `modified_at`）

### 步骤 2：配置 SPC 系统连接

在 `backend/.env` 中添加 ERP 数据库连接信息：

```env
# === SQL Server ===
ERP_DB_URL=mssql+pyodbc://spc_reader:YourPassword@192.168.x.x:1433/erp_db?driver=ODBC+Driver+17+for+SQL+Server
ERP_SYNC_ENABLED=true
ERP_SYNC_BATCH_SIZE=500

# === PostgreSQL ===
# ERP_DB_URL=postgresql+psycopg2://spc_reader:YourPassword@192.168.x.x:5432/erp_db

# === MySQL ===
# ERP_DB_URL=mysql+pymysql://spc_reader:YourPassword@192.168.x.x:3306/erp_db

# === Oracle ===
# ERP_DB_URL=oracle+cx_oracle://spc_reader:YourPassword@192.168.x.x:1521/orcl
```

### 步骤 3：配置同步 SQL

在 SPC 前端页面 **系统配置 → 同步SQL配置** 中配置 SQL 语句：

1. 点击「添加配置」
2. 选择同步类型（orders / materials / purchase_orders）
3. 编写 SQL 语句（使用 `:since` 作为增量时间参数）
4. 点击「分析 SQL 字段」提取 ERP 字段
5. 配置字段映射（ERP 字段 → SPC 字段）
6. 配置条件参数（可选，用于自定义筛选条件）
7. 点击「测试」验证 SQL 执行
8. 保存配置

**SQL 示例**（SQL Server）：
```sql
-- 订单数据同步
SELECT 
    FBillNo AS order_no,
    FEntryID AS line_no,
    FCustName AS customer,
    FItemNumber AS product_code,
    FItemName AS product_name,
    FQty AS order_qty,
    FDate AS promised_date,
    FPlanner AS owner,
    FStatus AS status,
    FModifyDate AS erp_updated_at
FROM SEOrder
WHERE FModifyDate >= :since

-- 物料需求同步
SELECT 
    FOrderNo AS order_no,
    FEntryID AS line_no,
    FMaterialNo AS material_code,
    FMaterialName AS material_name,
    FReqQty AS req_qty,
    FReqDate AS req_date,
    FAllocQty AS allocated_qty,
    FModifyDate AS erp_updated_at
FROM PP_MRPResult
WHERE FModifyDate >= :since

-- 采购订单同步
SELECT 
    FBillNo AS po_no,
    FMaterialNo AS material_code,
    FSupplierNo AS supplier_code,
    FSupplierName AS supplier_name,
    FQty AS po_qty,
    FStatus AS po_status,
    FETA AS eta,
    FOriginalETA AS original_eta,
    FActualDate AS actual_arrival_date,
    FPurchaser AS owner,
    FModifyDate AS erp_updated_at
FROM POOrder
WHERE FModifyDate >= :since
```

### 步骤 4：字段映射配置

如果 SQL 查询结果的字段名与 SPC 字段名不一致，在字段映射面板中配置：

| ERP 字段（SQL 查询结果） | SPC 字段（目标） |
|---|---|
| `FBillNo` | `order_no` |
| `FEntryID` | `line_no` |
| `FCustName` | `customer` |
| ... | ... |

点击「自动匹配」可自动匹配同名字段。

### 步骤 5：条件参数配置（可选）

如果需要在同步时传入自定义条件参数（如按客户筛选），配置条件参数：

| 参数名 | 参数类型 | 显示标签 | 默认值 | 必填 | 说明 |
|---|---|---|---|---|---|
| `customer_code` | string | 客户代码 | | 否 | 筛选指定客户的订单 |

在 SQL 中使用 `:parameter_name` 作为参数占位符：
```sql
SELECT ... FROM SEOrder
WHERE FModifyDate >= :since
  AND (:customer_code IS NULL OR FCustCode = :customer_code)
```

### 步骤 6：验证连接和同步

```bash
# 1. 手动触发一次全量同步（最近 720 小时 = 30 天）
curl -X POST "http://localhost:8000/api/v1/import-export/sync/all?hours=720" \
  -H "Authorization: Bearer <token>"

# 2. 查看同步状态
curl "http://localhost:8000/api/v1/import-export/sync/status" \
  -H "Authorization: Bearer <token>"

# 3. 按订单号同步（测试特定订单）
curl -X POST "http://localhost:8000/api/v1/import-export/sync/orders" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"order_numbers": ["SO001", "SO002"]}'
```

### 步骤 7：启用定时同步

SPC 系统启动后会自动启用定时同步（默认每 60 分钟）。可以通过修改调度器配置调整频率。

## 四、同步策略

### 4.1 增量同步（默认）

- **触发方式**：定时（每小时）+ 手动
- **同步范围**：`erp_updated_at >= 最近 N 小时`
- **冲突策略**：ERP 数据覆盖 SPC 中 `data_source='erp'` 的记录，不覆盖 `data_source='manual'` 或 `'excel'` 的手动数据

### 4.2 全量同步（首次/修复）

- **触发方式**：手动，设置 `hours=720`（30天）
- **场景**：首次对接、数据修复

### 4.3 数据保护

- ERP 同步**只覆盖**来源为 `erp` 的记录
- 用户**手动修改**的数据（`data_source='manual'`）不会被覆盖
- Excel 导入的数据（`data_source='excel'`）不会被覆盖
- 所有 ERP 同步操作都会写入**审计日志**

## 五、数据流向图

```
ERP 数据库
  │
  │ (SPC 通过 SQL 直接查询)
  ▼
SPC 同步服务
  │
  │ data_source='erp'
  │
  ▼                          Excel 文件           手动录入
  │                          │                    │
┌──────────────────────────────────────────────────────┐
│                    SPC 数据库                         │
│  sale_order | material_demand | purchase_order       │
│  (每条记录带 data_source 标识)                        │
└──────────────────────────────────────────────────────┘
  │
  ▼
风险计算引擎 → Dashboard → 预警 → 人工处理
```

## 六、可配置同步方式

### 6.1 同步配置字段

在 `sync_sql_config` 表中，每个同步任务可以独立配置以下字段：

| 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `sync_type` | String(32) | | 同步类型（唯一标识），如 orders, customers, materials_master |
| `sync_interval` | String(20) | 1h | 同步间隔：1h/2h/6h/12h/1d/1w |
| `sync_strategy` | String(20) | incremental | 同步策略：incremental/full/hybrid |
| `sync_time_window` | String(50) | null | 时间窗口：如 02:00-04:00，null表示不限 |
| `sync_priority` | Integer | 5 | 优先级：1-10，数字越小优先级越高 |
| `sync_enabled` | Boolean | true | 是否启用该同步任务 |
| `last_sync_time` | DateTime | null | 上次同步时间 |
| `next_sync_time` | DateTime | null | 下次计划同步时间 |
| `last_sync_status` | String(20) | null | 上次同步状态：success/failed/running |
| `last_sync_message` | Text | null | 上次同步消息 |

### 6.2 同步间隔（sync_interval）

支持以下间隔配置：
- `1h` - 每小时同步一次
- `2h` - 每2小时同步一次
- `6h` - 每6小时同步一次
- `12h` - 每12小时同步一次
- `1d` - 每天同步一次
- `1w` - 每周同步一次

**建议配置**：
- 业务数据（订单、物料需求、采购订单）：`1h` 或 `2h`
- 主数据（客户、供应商、物料）：`1d` 或 `1w`
- 配置数据（仓库、工序、组织）：`1d` 或 `1w`

### 6.3 同步策略（sync_strategy）

#### 6.3.1 增量同步（incremental）

**说明**：只同步指定时间之后的数据

**since参数计算**：
- 首次同步：使用30天前的时间
- 日常同步：使用 `last_sync_time`

**适用场景**：
- 业务数据（订单、物料需求、采购订单）
- 变化频率高的主数据

**SQL要求**：
- 必须包含时间字段（如 `erp_updated_at`）
- SQL中使用 `:since` 作为增量时间参数

```sql
SELECT ... FROM SEOrder
WHERE FModifyDate >= :since
```

#### 6.3.2 全量同步（full）

**说明**：每次同步全部数据，不限制时间范围

**since参数**：始终为 `None`

**适用场景**：
- 数据量小的配置数据（仓库、工序）
- 需要全量校验的数据

**SQL要求**：
- 不需要时间字段
- 不需要 `:since` 参数

```sql
SELECT ... FROM t_ICItem
WHERE FStatus = 1
```

#### 6.3.3 混合同步（hybrid）

**说明**：首次全量，日常增量，定期全量校验

**since参数计算**：
- 首次同步：`None`（全量）
- 日常同步：使用 `last_sync_time`（增量）
- 超过7天：`None`（全量校验）

**适用场景**：
- 主数据（客户、供应商、物料）
- 需要定期校验但日常增量同步的数据

**SQL要求**：
- 必须包含时间字段
- SQL中使用 `:since` 作为增量时间参数

```sql
SELECT ... FROM t_Organization
WHERE FModifyDate >= :since OR :since IS NULL
```

### 6.4 时间窗口（sync_time_window）

**说明**：限制同步任务在指定时间窗口内执行

**格式**：`HH:MM-HH:MM`，如 `02:00-04:00`

**示例**：
- `02:00-04:00` - 只在凌晨2点到4点之间执行
- `22:00-02:00` - 跨天时间窗口，晚上10点到凌晨2点
- `null` - 不限时间，随时可执行

**建议配置**：
- 主数据同步：`02:00-04:00`（业务低峰期）
- 业务数据同步：`null`（不限时间）

### 6.5 优先级（sync_priority）

**说明**：数字越小优先级越高，调度器按优先级顺序执行同步任务

**建议配置**：
- `1-3`：核心主数据（物料、客户、供应商）
- `4-6`：业务数据（订单、物料需求、采购订单）
- `7-10`：配置数据（仓库、工序、组织）

### 6.6 默认配置建议

#### 6.6.1 业务数据配置

```json
{
  "sync_type": "orders",
  "description": "订单数据同步",
  "sync_interval": "1h",
  "sync_strategy": "incremental",
  "sync_time_window": null,
  "sync_priority": 5,
  "sync_enabled": true
}
```

```json
{
  "sync_type": "materials",
  "description": "物料需求同步",
  "sync_interval": "1h",
  "sync_strategy": "incremental",
  "sync_time_window": null,
  "sync_priority": 5,
  "sync_enabled": true
}
```

```json
{
  "sync_type": "purchase_orders",
  "description": "采购订单同步",
  "sync_interval": "1h",
  "sync_strategy": "incremental",
  "sync_time_window": null,
  "sync_priority": 5,
  "sync_enabled": true
}
```

#### 6.6.2 主数据配置

```json
{
  "sync_type": "customers",
  "description": "客户主数据同步",
  "sync_interval": "1d",
  "sync_strategy": "hybrid",
  "sync_time_window": "02:00-04:00",
  "sync_priority": 2,
  "sync_enabled": true
}
```

```json
{
  "sync_type": "suppliers",
  "description": "供应商主数据同步",
  "sync_interval": "1d",
  "sync_strategy": "hybrid",
  "sync_time_window": "02:00-04:00",
  "sync_priority": 2,
  "sync_enabled": true
}
```

```json
{
  "sync_type": "materials_master",
  "description": "物料主数据同步",
  "sync_interval": "1d",
  "sync_strategy": "hybrid",
  "sync_time_window": "02:00-04:00",
  "sync_priority": 1,
  "sync_enabled": true
}
```

### 6.7 调度器行为

**检查频率**：调度器每分钟检查一次所有启用的同步任务

**执行条件**：
1. `sync_enabled = true`
2. 当前时间在 `sync_time_window` 内（如果配置了）
3. 当前时间 >= `next_sync_time`（或首次执行）

**执行顺序**：按 `sync_priority` 升序执行

**状态跟踪**：
- 执行前：更新 `last_sync_status = running`
- 执行成功：更新 `last_sync_status = success`，记录 `last_sync_time`，计算 `next_sync_time`
- 执行失败：更新 `last_sync_status = failed`，记录错误消息

### 6.8 手动触发同步

除了定时调度，也可以通过API手动触发同步：

```bash
# 触发所有同步任务
curl -X POST "http://localhost:8000/api/v1/import-export/sync/all?hours=720" \
  -H "Authorization: Bearer <token>"

# 触发特定类型的同步
curl -X POST "http://localhost:8000/api/v1/import-export/sync/orders" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"order_numbers": ["SO001", "SO002"]}'
```

手动触发的同步不会更新 `last_sync_time` 和 `next_sync_time`，避免影响定时调度。

## 七、SQL 配置详细说明

### 7.1 SQL 配置存储位置

SQL 配置存储在 `sync_sql_config` 表中，包含以下字段：
- `sync_type`: 同步类型（orders / materials / purchase_orders）
- `description`: 配置说明
- `sql_text`: SQL 语句
- `field_mapping_json`: 字段映射 JSON（ERP 字段 → SPC 字段）
- `condition_params_json`: 条件参数配置 JSON
- `is_active`: 是否启用

### 7.2 SQL 编写规范

- 使用 `:since` 作为增量时间参数（系统自动传入最近同步时间）
- 使用 `:parameter_name` 作为自定义参数占位符（需在条件参数中配置）
- SELECT 的列名将作为 ERP 字段名用于映射
- 建议在 SQL 中使用 AS 别名直接映射到 SPC 字段名
- 确保查询包含必要的主键字段（如 order_no, line_no, material_code）
- 确保查询包含时间字段用于增量同步（如 erp_updated_at）

### 7.3 字段映射配置

字段映射以 JSON 格式存储，格式如下：
```json
{
  "ERP字段名": "SPC字段名",
  "FBillNo": "order_no",
  "FEntryID": "line_no",
  "FCustName": "customer"
}
```

如果 SQL 中已经使用 AS 别名，则可以省略映射配置。

### 7.4 条件参数配置

条件参数以 JSON 格式存储，格式如下：
```json
[
  {
    "parameter_name": "customer_code",
    "parameter_type": "string",
    "label": "客户代码",
    "default_value": "",
    "required": false,
    "description": "筛选指定客户的订单"
  }
]
```

支持的参数类型：
- `string`: 字符串
- `number`: 数字
- `date`: 日期
- `list`: 列表（用于 IN 查询）
- `boolean`: 布尔值

### 7.5 SQL 测试功能

在前端配置页面点击「测试」按钮，系统会：
1. 连接 ERP 数据库
2. 使用 `:since = 当前时间 - 30天` 执行 SQL
3. 返回查询结果预览（前 5 条）
4. 显示字段列表和总行数

## 八、常见 ERP 系统字段对照参考

### SAP
| SPC 字段 | SAP 表 | SAP 字段 |
|---|---|---|
| order_no | VBAK | VBELN |
| line_no | VBAP | POSNR |
| customer | KNA1 | NAME1 |
| product_code | VBAP | MATNR |
| po_no | EKKO | EBELN |
| material_code | EKPO | MATNR |
| supplier_code | EKKO | LIFNR |

### 用友 U8
| SPC 字段 | U8 表 | U8 字段 |
|---|---|---|
| order_no | SO_SOMain | cSOCode |
| line_no | SO_SODetails | iRowNo |
| customer | Customer | cCusName |
| product_code | SO_SODetails | cInvCode |
| po_no | PO_Pomain | cPOID |
| material_code | PO_Podetails | cInvCode |

### 金蝶 K3
| SPC 字段 | K3 表 | K3 字段 |
|---|---|---|
| order_no | SEOrder | FBillNo |
| line_no | SEOrderEntry | FEntryID |
| customer | t_Organization | FName |
| product_code | SEOrderEntry | FMaterialId |
| po_no | POOrder | FBillNo |
| material_code | POOrderEntry | FMaterialId |

## 九、需要 IT/ERP 管理员配合的事项

### 必须提供的：
1. **ERP 数据库连接信息**：IP、端口、数据库名、用户名、密码
2. **只读账号**：为 SPC 系统创建只读数据库账号
3. **表结构信息**：提供相关表的字段名、类型说明
4. **网络连通性**：确保 SPC 服务器可以访问 ERP 数据库
5. **时间字段确认**：确认 ERP 表中有可用于增量同步的时间字段

### 可选的：
6. **历史数据范围**：确认初始同步需要多长时间的历史数据
7. **数据量评估**：评估同步数据量，优化 SQL 查询性能
8. **索引建议**：为常用查询字段（如时间字段、订单号）创建索引

## 十、FAQ

**Q: ERP 数据库不支持直接访问怎么办？**
A: 可以由 IT 搭建一个中间库（推荐），通过 ETL 工具定时从 ERP 同步到中间库，SPC 连接中间库。或者使用 API 对接方式（需要开发）。

**Q: 同步频率多少合适？**
A: 建议每小时同步一次。如果业务需要更实时，可以调整到 15-30 分钟。同步频率过高会增加 ERP 数据库负载。

**Q: ERP 数据和手动修改的数据冲突怎么办？**
A: SPC 系统通过 `data_source` 字段区分数据来源。ERP 同步只覆盖 `data_source='erp'` 的记录，手动修改的数据不会被覆盖。

**Q: 第一次上线如何导入历史数据？**
A: 手动触发全量同步，设置 `hours=720`（30天）或更大值。也可以直接用 Excel 批量导入历史数据。

**Q: 支持哪些数据库类型？**
A: SQL Server、PostgreSQL、MySQL、Oracle 均支持。只需修改 `ERP_DB_URL` 连接串即可。

**Q: SQL 查询超时怎么办？**
A: 可以优化 SQL 查询（添加索引、限制查询范围），或者调整 `ERP_SYNC_BATCH_SIZE` 参数减少批次大小。

**Q: 如何按订单号筛选同步？**
A: 调用同步 API 时传入 `order_numbers` 参数，系统会自动在 SQL 中添加 `FContractNo IN (...)` 条件。

**Q: 字段映射不生效怎么办？**
A: 检查 field_mapping_json 格式是否正确，确保 ERP 字段名与 SQL 查询结果的列名一致。

**Q: 如何查看同步日志？**
A: 在「系统配置 → 审计日志」中查看所有同步操作的记录，包括同步时间、同步数量、错误信息等。

**Q: 如何配置同步策略？**
A: 在前端「系统配置 → 同步SQL配置」页面，可以配置每个同步任务的间隔、策略、时间窗口、优先级等参数。

**Q: 不同同步策略有什么区别？**
A: 增量同步只同步指定时间后的数据；全量同步每次同步全部数据；混合同步首次全量，日常增量，每周全量校验。

## 十一、错误处理和故障排查

### 11.1 常见错误

| 错误信息 | 原因 | 解决方案 |
|---|---|---|
| ERP_DB_URL 未配置 | .env 中未配置 ERP 连接 | 在 .env 中配置 ERP_DB_URL |
| ERP 数据库连接失败 | 网络不通、账号密码错误、数据库不可达 | 检查网络连通性、验证账号密码、确认数据库服务正常 |
| 未配置 sync_type='xxx' 的同步 SQL | sync_sql_config 表中缺少对应配置 | 在前端「同步SQL配置」页面添加配置 |
| SQL 字段解析失败 | SQL 语法错误、ERP 数据库不支持该语法 | 检查 SQL 语法，参考 ERP 数据库文档 |
| SQL 执行失败 | SQL 语法错误、表名错误、字段名错误 | 使用「测试」功能验证 SQL，检查表名和字段名 |
| 字段映射 JSON 解析失败 | field_mapping_json 格式错误 | 检查 JSON 格式，确保是有效的 JSON 对象 |

### 11.2 日志查看

- **后端日志**：查看 `backend/logs/` 目录下的日志文件，搜索关键词 `ERP` 或 `sync`
- **审计日志**：在前端「系统配置 → 审计日志」中查看同步操作记录
- **同步状态**：在前端「同步SQL配置」页面查看每个同步任务的 `last_sync_status` 和 `last_sync_message`

### 11.3 调试步骤

1. 检查 .env 中 ERP_DB_URL 是否正确配置
2. 在前端「同步SQL配置」页面点击「测试」验证 SQL
3. 查看后端日志确认错误信息
4. 检查 ERP 数据库网络连通性
5. 确认 ERP 数据库账号权限（只读即可）
6. 验证 SQL 查询的字段名和类型是否正确
7. 检查同步配置的间隔、策略、时间窗口是否合理

## 十二、性能优化建议

### 12.1 SQL 优化

- 在 WHERE 条件中使用的时间字段上创建索引
- 避免使用 SELECT *，只查询需要的字段
- 对于大数据量表，添加时间范围限制（如只查询最近 6 个月数据）
- 使用 EXISTS 替代 IN（当子查询数据量大时）
- 避免复杂的 JOIN 和子查询

### 12.2 批次优化

- 调整 `ERP_SYNC_BATCH_SIZE` 参数（默认 500）
- 数据量大时减小批次大小，避免内存溢出
- 数据量小时增大批次大小，提高同步速度

### 12.3 网络优化

- 确保 SPC 服务器和 ERP 数据库在同一内网
- 如果跨网络，考虑使用 VPN 或专线
- 监控网络延迟，避免网络瓶颈

### 12.4 数据库优化

- 定期清理 SPC 数据库的历史数据
- 为 SPC 数据库的常用查询字段创建索引
- 定期分析表统计信息（PostgreSQL ANALYZE）

## 十三、监控和告警

### 13.1 同步监控指标

- 同步成功率
- 同步耗时
- 同步数据量
- 错误率

### 13.2 告警建议

- 同步失败时发送告警
- 同步耗时超过阈值时发送告警
- 同步数据量异常（突然为 0 或暴增）时发送告警
- ERP 数据库连接失败时发送告警

### 13.3 监控实现

- 使用后端日志分析同步状态
- 在 Dashboard 中添加同步状态展示
- 集成第三方监控工具（如 Prometheus + Grafana）
- 在前端「同步SQL配置」页面实时展示同步状态
