"""company-control MCP Server — Tool 注册与实现（规范 §6/§7/§8/§10/§14/§16）

运行：python -m mcp_server（stdio 传输，由 AEOS Hub 作为 MCP client 拉起）。
目录名用 mcp_server 而非 mcp，避免与 SDK 的 mcp 包在 sys.path 中冲突。
日志只写 stderr，绝不写 stdout（规范 §4）。
"""

from __future__ import annotations

import functools
import logging
import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, Literal

from mcp.server.mcpserver import MCPServer as FastMCP  # mcp SDK 2.x：FastMCP 已更名 MCPServer
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
from mcp.types import ToolAnnotations
from pydantic import ConfigDict, Field

from . import __version__, contracts
from .contracts import BizError
from .upstream_client import UpstreamError
from .upstream_client import call as upstream

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")  # 默认 stderr

# 规范 §7：不允许接受任意未定义字段。SDK 生成的参数模型继承此配置，必须在注册 Tool 之前设置。
ArgModelBase.model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

# 规范 §10：机器可读的只读声明（readOnlyHint），配合 AEOS Policy 强制执行
READ_ONLY_TOOL = ToolAnnotations(readOnlyHint=True)

mcp = FastMCP("company-control", version=__version__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_METRIC_SPAN_DAYS = 92
_MAX_EVIDENCE_PER_CALL = 50

EXPECTED_TOOLS = [
    "get_system_health",
    "catalog_metrics_list",
    "metric_query",
    "master_material_search",
    "master_supplier_get",
    "detail_orders_list",
]


def tool_error_envelope(fn):
    """Tool 内异常 → 规范 §12 结构化错误返回，保证非法输入不导致进程崩溃（规范 §7）"""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (BizError, UpstreamError) as exc:
            return contracts.err(exc.code, exc.message)
        except Exception:
            logger.exception("tool internal error: %s", fn.__name__)
            return contracts.err("INTERNAL_ERROR", "内部错误，详情见服务端 stderr 日志")

    return wrapper


def _parse_date(value: str, field: str):
    if not _DATE_RE.match(value or ""):
        raise BizError("INVALID_ARGUMENT", f"{field} 格式必须为 YYYY-MM-DD：{value!r}")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise BizError("INVALID_ARGUMENT", f"{field} 不是合法日期：{value!r}") from exc


def _as_of_confidence(payload: Dict[str, Any]):
    if payload.get("stale") is True:
        raise UpstreamError("STALE_DATA", "上游数据已过期，超出新鲜度阈值")
    as_of = str(payload.get("data_as_of") or contracts.utc_now_iso())
    confidence = str(payload.get("data_confidence") or "high").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "high"
    return as_of, confidence


_Page = Annotated[int, Field(ge=1, le=100)]
_PageSize = Annotated[int, Field(ge=1, le=100)]
_RequestId = Annotated[str, Field(max_length=64, description="调用方请求 ID（审计/链路追踪用，可选）")]


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def get_system_health() -> Dict[str, Any]:
    """连接自检（只读）。返回 company-control 能力状态与版本，用于验证 AEOS Agent → MCP → 中台链路连通性。"""
    upstream_status = "ok"
    upstream_error = None
    try:
        await upstream("/common/ping")  # SPC 对外联调端点（int:health.ping，验证 HMAC 签名配置）
    except UpstreamError as exc:
        upstream_status = "degraded"
        upstream_error = {"code": exc.code, "message": exc.message}

    data: Dict[str, Any] = {
        "status": "ok" if upstream_status == "ok" else "degraded",
        "read_only": True,
        "version": __version__,
        "checked_at": contracts.utc_now_iso(),
        "upstream_status": upstream_status,
        "capabilities": EXPECTED_TOOLS,
    }
    if upstream_error:
        data["upstream_error"] = upstream_error
    envelope = contracts.ok("get_system_health", data, data_as_of=contracts.utc_now_iso(), data_confidence="high")
    # 规范 §16：顶层字段超集（同时保留 §8 标准信封字段）
    envelope.update(
        {
            "status": data["status"],
            "version": data["version"],
            "checked_at": data["checked_at"],
            "capabilities": data["capabilities"],
        }
    )
    return envelope


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def catalog_metrics_list(
    page: Annotated[int, Field(ge=1, le=100, description="页码，从 1 开始")] = 1,
    page_size: Annotated[int, Field(ge=1, le=100, description="每页条数，上限 100")] = 20,
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """列出中台可查询的指标目录（只读）。Agent 应先查目录获取指标编码，再调用 metric_query。"""
    params: Dict[str, Any] = {"page": page, "page_size": page_size}
    if request_id:
        params["request_id"] = request_id
    payload = await upstream("/metrics", params)
    as_of, confidence = _as_of_confidence(payload)
    rows = contracts.redact(payload.get("data") or [])
    total = int(payload.get("total") or len(rows))
    return contracts.ok(
        "catalog_metrics_list",
        rows,
        data_as_of=as_of,
        data_confidence=confidence,
        evidence_refs=[contracts.evidence("metric-catalog", "all", as_of)],
        page=contracts.page_envelope(page, page_size, total, total > page * page_size),
        request_id=request_id or None,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def metric_query(
    metric_code: Annotated[str, Field(min_length=1, max_length=80, description="指标编码，可先经 catalog_metrics_list 查询")],
    date_from: Annotated[str, Field(description="开始日期 YYYY-MM-DD（含）")],
    date_to: Annotated[str, Field(description="结束日期 YYYY-MM-DD（含）")],
    dimension: Annotated[Literal["day", "week", "month"], Field(description="聚合粒度：day / week / month")] = "day",
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """查询中台指标数据（只读）。日期跨度不超过 92 天；结果含 data_as_of 数据新鲜度与 evidence_refs。"""
    d_from = _parse_date(date_from, "date_from")
    d_to = _parse_date(date_to, "date_to")
    if d_from > d_to:
        raise BizError("INVALID_ARGUMENT", "date_from 不能晚于 date_to")
    if (d_to - d_from) > timedelta(days=_MAX_METRIC_SPAN_DAYS):
        raise BizError("INVALID_ARGUMENT", f"日期跨度不能超过 {_MAX_METRIC_SPAN_DAYS} 天")

    params: Dict[str, Any] = {
        "metric_code": metric_code,
        "date_from": date_from,
        "date_to": date_to,
        "dimension": dimension,
    }
    if request_id:
        params["request_id"] = request_id
    payload = await upstream("/metric", params)
    as_of, confidence = _as_of_confidence(payload)
    rows = contracts.redact(payload.get("data") or [])
    return contracts.ok(
        "metric_query",
        rows,
        data_as_of=as_of,
        data_confidence=confidence,
        evidence_refs=[contracts.evidence("metric", metric_code, as_of)],
        request_id=request_id or None,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def master_material_search(
    keyword: Annotated[str, Field(min_length=2, max_length=80, description="物料编码或名称关键词")],
    page: Annotated[int, Field(ge=1, le=100, description="页码，从 1 开始")] = 1,
    page_size: Annotated[int, Field(ge=1, le=100, description="每页条数，上限 100")] = 20,
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """按关键词检索物料主数据（只读）。敏感字段（联系方式/成本价等）已脱敏。"""
    params: Dict[str, Any] = {"keyword": keyword, "page": page, "page_size": page_size}
    if request_id:
        params["request_id"] = request_id
    payload = await upstream("/material", params)
    as_of, confidence = _as_of_confidence(payload)
    rows = contracts.redact(payload.get("data") or [])
    total = int(payload.get("total") or len(rows))
    refs = [contracts.evidence("material", r["material_code"], as_of) for r in rows if r.get("material_code")]
    return contracts.ok(
        "master_material_search",
        rows,
        data_as_of=as_of,
        data_confidence=confidence,
        evidence_refs=refs[:_MAX_EVIDENCE_PER_CALL],
        page=contracts.page_envelope(page, page_size, total, total > page * page_size),
        request_id=request_id or None,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def master_supplier_get(
    supplier_code: Annotated[str, Field(min_length=1, max_length=80, description="供应商编码")],
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """获取供应商主数据详情（只读）。不存在时返回 NOT_FOUND。"""
    params: Dict[str, Any] = {"supplier_code": supplier_code}
    if request_id:
        params["request_id"] = request_id
    payload = await upstream("/supplier", params)
    as_of, confidence = _as_of_confidence(payload)
    row = contracts.redact(payload.get("data") or {})
    refs = [contracts.evidence("supplier", supplier_code, as_of)] if row else []
    return contracts.ok(
        "master_supplier_get",
        row,
        data_as_of=as_of,
        data_confidence=confidence,
        evidence_refs=refs,
        request_id=request_id or None,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def detail_orders_list(
    customer: Annotated[str, Field(max_length=80, description="客户名称（过滤条件之一）")] = "",
    product_line: Annotated[str, Field(max_length=40, description="产品线（过滤条件之一）")] = "",
    date_from: Annotated[str, Field(max_length=10, description="下单开始日期 YYYY-MM-DD（与 date_to 成对）")] = "",
    date_to: Annotated[str, Field(max_length=10, description="下单结束日期 YYYY-MM-DD（与 date_from 成对）")] = "",
    page: Annotated[int, Field(ge=1, le=100, description="页码，从 1 开始")] = 1,
    page_size: Annotated[int, Field(ge=1, le=100, description="每页条数，上限 100，默认 20")] = 20,
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """分页查询订单明细（只读）。必须至少提供 customer / product_line / date_from+date_to 之一，防止全表拉取。"""
    if not (customer or product_line or (date_from and date_to)):
        raise BizError("INVALID_ARGUMENT", "至少需要一个过滤条件：customer / product_line / date_from+date_to")
    if date_from or date_to:
        _parse_date(date_from, "date_from")
        _parse_date(date_to, "date_to")

    params: Dict[str, Any] = {"page": page, "page_size": page_size}
    if customer:
        params["customer"] = customer
    if product_line:
        params["product_line"] = product_line
    if date_from and date_to:
        params["date_from"] = date_from
        params["date_to"] = date_to
    if request_id:
        params["request_id"] = request_id

    payload = await upstream("/orders", params)
    as_of, confidence = _as_of_confidence(payload)
    rows = contracts.redact(payload.get("data") or [])
    total = int(payload.get("total") or len(rows))
    refs = [contracts.evidence("order", r["order_no"], as_of) for r in rows if r.get("order_no")]
    return contracts.ok(
        "detail_orders_list",
        rows,
        data_as_of=as_of,
        data_confidence=confidence,
        evidence_refs=refs[:_MAX_EVIDENCE_PER_CALL],
        page=contracts.page_envelope(page, page_size, total, total > page * page_size),
        request_id=request_id or None,
    )
