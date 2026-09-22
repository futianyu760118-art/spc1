"""company-control MCP Server — Tool 注册与实现（规范 §6/§7/§8/§10/§14/§16）

运行：
  python -m mcp_server                                    # stdio（默认，AEOS Hub 拉起）
  python -m mcp_server --transport streamable-http ...    # HTTP（需 MCP_HTTP_TOKEN）
目录名用 mcp_server 而非 mcp，避免与 SDK 的 mcp 包在 sys.path 中冲突。
日志只写 stderr，绝不写 stdout（规范 §4）。
"""

from __future__ import annotations

import functools
import hmac
import logging
import os
import re
from datetime import datetime
from typing import Annotated, Any, Callable, Dict, Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.mcpserver import MCPServer as FastMCP  # mcp SDK 2.x：FastMCP 已更名 MCPServer
from mcp.server.mcpserver.server import AuthSettings
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

# HTTP 模式静态 Bearer Token（env 注入，禁止硬编码）；为空则不启用 auth（stdio 模式不受影响）
HTTP_TOKEN = os.getenv("MCP_HTTP_TOKEN", "")
HTTP_PUBLIC_URL = os.getenv("MCP_HTTP_PUBLIC_URL", "").rstrip("/") or (
    f"http://127.0.0.1:{os.getenv('MCP_HTTP_PORT') or '8902'}"
)


class StaticTokenVerifier(TokenVerifier):
    """HTTP 模式静态 Bearer Token 校验；常数时间比较，避免时序侧信道"""

    def __init__(self, expected_token: str):
        self._expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if self._expected_token and hmac.compare_digest(token, self._expected_token):
            return AccessToken(token=token, client_id="static-bearer", scopes=[])
        return None


mcp = FastMCP(
    "company-control",
    version=__version__,
    token_verifier=StaticTokenVerifier(HTTP_TOKEN) if HTTP_TOKEN else None,
    auth=(
        AuthSettings(
            issuer_url=HTTP_PUBLIC_URL,
            resource_server_url=HTTP_PUBLIC_URL,
            validate_token_resource=False,
        )
        if HTTP_TOKEN
        else None
    ),
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_EVIDENCE_PER_CALL = 50

EXPECTED_TOOLS = [
    "get_system_health",
    "orders_list",
    "order_details_list",
    "bom_tree",
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


def _parse_iso_datetime(value: str, field: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BizError("INVALID_ARGUMENT", f"{field} 必须为 ISO 8601 时间：{value!r}") from exc


def _as_of_confidence(payload: Dict[str, Any]):
    if payload.get("stale") is True:
        raise UpstreamError("STALE_DATA", "上游数据已过期，超出新鲜度阈值")
    as_of = str(payload.get("data_as_of") or contracts.utc_now_iso())
    confidence = str(payload.get("data_confidence") or "high").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "high"
    return as_of, confidence


def _filter_params(**values: Any) -> Dict[str, Any]:
    """省略未填写的空值参数（透传上游时保持与 SPC 对外接口默认行为一致）"""
    return {key: value for key, value in values.items() if value}


def _list_result(
    capability: str,
    payload: Dict[str, Any],
    *,
    page: int,
    page_size: int,
    request_id: str,
    evidence_entity: str,
    evidence_id: Callable[[Dict[str, Any]], str],
) -> Dict[str, Any]:
    """列表类 Tool 公共返回：解包 items/total、脱敏、分页信息、Evidence（规范 §8/§9/§13/§17）"""
    as_of, confidence = _as_of_confidence(payload)
    rows = contracts.redact(payload.get("items") or [])
    total = int(payload.get("total") or len(rows))
    refs = []
    for row in rows:
        ref_id = evidence_id(row)
        if ref_id:
            refs.append(contracts.evidence(evidence_entity, ref_id, as_of))
    return contracts.ok(
        capability,
        rows,
        data_as_of=as_of,
        data_confidence=confidence,
        evidence_refs=refs[:_MAX_EVIDENCE_PER_CALL],
        page=contracts.page_envelope(page, page_size, total, total > page * page_size),
        request_id=request_id or None,
    )


_Page = Annotated[int, Field(ge=1, description="页码，从 1 开始")]
_PageSize = Annotated[int, Field(ge=1, le=200, description="每页条数，上限 200")]
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
async def orders_list(
    keyword: Annotated[str, Field(max_length=80, description="关键字（订单号 / 客户 / 产品名 模糊匹配）")] = "",
    status: Annotated[str, Field(max_length=200, description="订单状态，逗号分隔多选，如 open,closed")] = "",
    customer_code: Annotated[str, Field(max_length=80, description="客户编码精确匹配")] = "",
    risk_level: Annotated[str, Field(max_length=40, description="风险等级，逗号分隔多选，如 red,yellow")] = "",
    promised_date_start: Annotated[str, Field(max_length=10, description="合同交期范围起 YYYY-MM-DD（含）")] = "",
    promised_date_end: Annotated[str, Field(max_length=10, description="合同交期范围止 YYYY-MM-DD（含）")] = "",
    updated_after: Annotated[str, Field(max_length=40, description="增量同步锚点 ISO 8601，仅返回 updated_at 不早于该时间的记录")] = "",
    page: _Page = 1,
    page_size: _PageSize = 20,
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """分页查询销售订单列表（只读）。过滤条件均可选；单页最多 200 条。"""
    if promised_date_start:
        _parse_date(promised_date_start, "promised_date_start")
    if promised_date_end:
        _parse_date(promised_date_end, "promised_date_end")
    if updated_after:
        _parse_iso_datetime(updated_after, "updated_after")

    params = _filter_params(
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
        customer_code=customer_code,
        risk_level=risk_level,
        promised_date_start=promised_date_start,
        promised_date_end=promised_date_end,
        updated_after=updated_after,
        request_id=request_id,
    )
    payload = await upstream("/external/orders/list", params)
    return _list_result(
        "orders_list",
        payload,
        page=page,
        page_size=page_size,
        request_id=request_id,
        evidence_entity="order",
        evidence_id=lambda row: str(row.get("order_no") or ""),
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def order_details_list(
    order_no: Annotated[str, Field(max_length=80, description="订单号精确匹配（拉取某订单的全部明细行）")] = "",
    keyword: Annotated[str, Field(max_length=80, description="关键字（订单号 / 产品名 / 产品型号 模糊匹配）")] = "",
    product_code: Annotated[str, Field(max_length=80, description="产品编码精确匹配")] = "",
    status: Annotated[str, Field(max_length=200, description="明细行状态，逗号分隔多选，如 open,closed")] = "",
    bom_no: Annotated[str, Field(max_length=80, description="BOM 编号精确匹配")] = "",
    promised_date_start: Annotated[str, Field(max_length=10, description="合同交期范围起 YYYY-MM-DD（含）")] = "",
    promised_date_end: Annotated[str, Field(max_length=10, description="合同交期范围止 YYYY-MM-DD（含）")] = "",
    updated_after: Annotated[str, Field(max_length=40, description="增量同步锚点 ISO 8601，仅返回 updated_at 不早于该时间的记录")] = "",
    page: _Page = 1,
    page_size: _PageSize = 20,
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """分页查询销售订单明细行列表（只读）。过滤条件均可选；单页最多 200 条。"""
    if promised_date_start:
        _parse_date(promised_date_start, "promised_date_start")
    if promised_date_end:
        _parse_date(promised_date_end, "promised_date_end")
    if updated_after:
        _parse_iso_datetime(updated_after, "updated_after")

    params = _filter_params(
        page=page,
        page_size=page_size,
        order_no=order_no,
        keyword=keyword,
        product_code=product_code,
        status=status,
        bom_no=bom_no,
        promised_date_start=promised_date_start,
        promised_date_end=promised_date_end,
        updated_after=updated_after,
        request_id=request_id,
    )
    payload = await upstream("/external/order-details/list", params)
    return _list_result(
        "order_details_list",
        payload,
        page=page,
        page_size=page_size,
        request_id=request_id,
        evidence_entity="order-detail",
        evidence_id=lambda row: "/".join(
            part for part in (row.get("order_no"), row.get("line_no")) if part
        ),
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
@tool_error_envelope
async def bom_tree(
    bom_id: Annotated[str, Field(min_length=1, max_length=80, description="顶层 BOM ID（必填），以其为根向下展开多级")],
    demand_qty: Annotated[Optional[float], Field(ge=0, description="根需求量；缺省取根 BOM 基础用量，再缺省取 1")] = None,
    flatten: Annotated[bool, Field(description="true 返回扁平列表 items，false 返回嵌套树 tree")] = False,
    request_id: _RequestId = "",
) -> Dict[str, Any]:
    """查询已组装好的多级 BOM 树（只读）。仅支持按 bom_id 查询；子件需求量为沿树连乘结果。"""
    params = _filter_params(
        bom_id=bom_id,
        flatten="true" if flatten else "false",
        demand_qty=str(demand_qty) if demand_qty is not None else "",
        request_id=request_id,
    )
    payload = await upstream("/external/boms/tree", params)
    as_of, confidence = _as_of_confidence(payload)
    return contracts.ok(
        "bom_tree",
        contracts.redact(payload),
        data_as_of=as_of,
        data_confidence=confidence,
        evidence_refs=[contracts.evidence("bom", bom_id, as_of)],
        request_id=request_id or None,
    )
