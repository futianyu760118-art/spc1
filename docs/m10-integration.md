# SPC ↔ M10 微系统互连规范

> 文档编号：SPC-M10.V1 · 对接标准对齐 PLM2（M04）的接入方式：**服务端账号登录 → Bearer → 只读引用**。

## 0. 定位

- SPC（供应链与生产协同中台）是**业务真相源**；M10（岗位与个人运营微系统）只做**只读引用与呈现**，不写 SPC 业务库。
- 写操作（关闭异常、推进订单、调整 ETA 等）一律在 SPC 系统内办理；M10 页面提供「去 SPC 处理」入口，避免双写。

## 1. 连接方式（两种，均可）

| 方式 | 用途 | 说明 |
|---|---|---|
| JWT Bearer | 服务端只读接入（M10 默认） | `POST /api/v1/basicdata/auth/login`（OAuth2 表单 `username/password/login_type=employee/channel=web`）→ `data.access_token`；后续 `Authorization: Bearer <token>` |
| HMAC API Key | 系统对系统（外部集成） | `POST /api/v1/external/*`，头 `X-App-Key` + `X-Timestamp` + `X-Signature`，另含 IP 白名单与限流、逐接口能力鉴权、调用留痕 |

令牌建议 20 分钟缓存，401 自动重登（与 PLM2 一致）。

## 2. M10 只读接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/dashboard/summary` | 控制塔汇总（风险灯号 `risk_summary` / 最近异常 `recent_issues`） |
| GET | `/api/v1/dashboard/today-overview` | 今日概览（应交付、缺料订单、待关闭异常、ETA 逾期采购、订单风险计数） |
| GET | `/api/v1/dashboard/rolling-risk` | 滚动 14 天风险 |
| GET | `/api/v1/dashboard/order-risk-distribution` | 订单风险分布（按客户） |
| GET | `/api/v1/dashboard/closure-achievement` | 异常关闭达成 |
| GET | `/api/v1/dashboard/orders` | 订单风险列表（`page/page_size/risk_level/owner/keyword/status`） |
| GET | `/api/v1/dashboard/materials` | 物料缺料/齐套（`shortage_only`） |
| GET | `/api/v1/exceptions` | 异常台账（`page/page_size/status/risk_level/issue_type/owner`） |
| GET | `/api/v1/materials/supplier-risk` | 供应商风险清单 |
| GET | `/api/v1/m10/status` | **M10 连接自检与契约发现**（本规范实现，公开无鉴权） |

## 3. 统一响应

```json
{ "code": 0, "message": "success", "data": { ... } }
```

- `code = 0` 成功；业务错误 4xx；`data` 为分页时形如 `{ total, page, page_size, items, stats }`。
- 风险等级取值：`red`（严重）/ `yellow`（关注）/ `blue`（一般）/ `green`（正常）。

## 4. 失败语义（不伪造成功）

- 未配置地址/账号 → 明确报错；登录失败 → 401；接口异常 → 4xx/5xx 带 `detail`/`message`。
- M10 侧断连时返回旧数据并标「旧数据（stale）」，不假装最新。

## 5. 与 PLM2 对照

| 项 | PLM2 | SPC |
|---|---|---|
| 登录 | `POST /api/auth/login` → JWT | `POST /api/v1/basicdata/auth/login` → JWT |
| 身份校验 | `GET /api/auth/info` | `GET /api/v1/basicdata/users/...`（外部） |
| 只读引用 | 项目/节点/工作表/ECN | 控制塔/订单/物料/异常/供应商风险 |
| 外部集成 | Bearer（ClientCredentials） | HMAC API Key 签名 |
| 写策略 | M10 经官方接口写透 | M10 只读，写回 SPC 系统 |

## 6. 代码位置

- 自检端点：`backend/app/api/v1/m10/routes.py`（`GET /api/v1/m10/status`）
- 路由注册：`backend/app/api/v1/__init__.py`
