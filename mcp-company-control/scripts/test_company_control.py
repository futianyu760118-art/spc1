"""独立测试脚本 — 覆盖 AEOS MCP Integration Spec §20 十二条 + STALE_DATA 补充

运行（在 mcp-company-control/ 目录下）：
    python scripts/test_company_control.py

内置 mock 中台端点（127.0.0.1 随机端口），无需真实中台。
以 stdio 子进程拉起 mcp_server，用 MCP client 完成真实握手与调用。
"""

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
if hasattr(sys.stdout, "reconfigure"):  # GBK 控制台下的中文输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

EXPECTED_TOOLS = {
    "get_system_health",
    "catalog_metrics_list",
    "metric_query",
    "master_material_search",
    "master_supplier_get",
    "detail_orders_list",
}

NOW = "2026-09-20T08:00:00Z"
DATA_AS_OF = "2026-09-19T18:00:00Z"

METRICS = [
    {"metric_code": "OTD", "name": "订单准时交付率", "dimensions": ["day", "week", "month"], "freshness": "T+1 每日 06:00"},
    {"metric_code": "MATERIAL_GAP", "name": "关键物料缺口率", "dimensions": ["day"], "freshness": "T+1 每日 06:00"},
]
METRIC_ROWS = [
    {"date": "2026-09-18", "value": 96.5},
    {"date": "2026-09-19", "value": 97.1},
]
MATERIALS = [
    {"material_code": "MO-8821", "name": "LED 驱动电源 60W", "phone": "13800001111", "cost_price": 42.5},
    {"material_code": "MS-3310", "name": "铝合金压铸件-灯壳", "phone": "13900002222", "cost_price": 18.0},
]
SUPPLIER = {"supplier_code": "SUP-001", "name": "示例供应商", "contact": "张三", "phone": "13700003333"}
ORDERS = [
    {"order_no": "SO-2609-001", "customer": "示例客户A", "product_line": "商业照明", "amount_cny": 1280000, "due_date": "2026-09-20"},
    {"order_no": "SO-2609-002", "customer": "示例客户B", "product_line": "户外照明", "amount_cny": 560000, "due_date": "2026-09-28"},
]

MOCK_STATE = {"mode": "normal"}

# 与 SPC「数据供给」HMAC 机制一致的校验参数
MOCK_APP_KEY = "test-app-key"
MOCK_APP_SECRET = "test-secret"
MOCK_ENDPOINT_CODES = {
    "/common/ping": "int:health.ping",
    "/metrics": "int:mcp.metrics",
    "/metric": "int:mcp.metric",
    "/material": "int:mcp.material",
    "/supplier": "int:mcp.supplier",
    "/orders": "int:mcp.orders",
}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静默，避免刷屏
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # 客户端超时主动断开属预期（timeout 模式）

    def do_POST(self):
        if urlparse(self.path).path == "/oauth/token":
            self._json({"access_token": "mock-token", "expires_in": 3600})
        else:
            self._json({"error": "not found"}, 404)

    def _verify_signature(self, parsed) -> bool:
        """与 SPC validate_signature_for_exposable 同算法：HMAC-SHA256(secret, ts+app_key+endpoint_code+query)"""
        app_key = self.headers.get("X-App-Key")
        if not app_key:
            return True  # Bearer 模式不校验签名
        ts = self.headers.get("X-Timestamp", "")
        sig = self.headers.get("X-Signature", "")
        if app_key != MOCK_APP_KEY or not ts.isdigit() or abs(int(time.time()) - int(ts)) > 300:
            return False
        endpoint_code = MOCK_ENDPOINT_CODES.get(parsed.path)
        if not endpoint_code:
            return False
        expected = hmac.new(
            MOCK_APP_SECRET.encode("utf-8"),
            f"{ts}{app_key}{endpoint_code}{parsed.query}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(sig, expected)

    def do_GET(self):
        mode = MOCK_STATE["mode"]
        if mode == "timeout":
            time.sleep(3.0)
            return self._json({"data": {}, "data_as_of": DATA_AS_OF})
        if mode == "unauth":
            return self._json({"error": "invalid token"}, 401)
        if mode == "forbidden":
            return self._json({"error": "forbidden"}, 403)
        if mode == "unavailable":
            return self._json({"error": "upstream down"}, 503)
        if mode == "ratelimit":
            return self._json({"error": "too many requests"}, 429)
        if mode == "stale":
            return self._json({"data": [], "total": 0, "data_as_of": DATA_AS_OF, "data_confidence": "low", "stale": True})

        parsed = urlparse(self.path)
        if not self._verify_signature(parsed):
            return self._json({"error": "signature invalid"}, 401)
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        route = parsed.path

        if route == "/common/ping":
            return self._json({"code": 0, "message": "pong", "data": {"ok": True}})
        if route == "/metrics":
            page, size = int(q.get("page", 1)), int(q.get("page_size", 20))
            rows = METRICS[(page - 1) * size : page * size]
            return self._json({"data": rows, "total": len(METRICS), "data_as_of": DATA_AS_OF, "data_confidence": "high"})
        if route == "/metric":
            return self._json({"data": METRIC_ROWS, "total": len(METRIC_ROWS), "data_as_of": DATA_AS_OF, "data_confidence": "high"})
        if route == "/material":
            kw = q.get("keyword", "").lower()
            rows = [m for m in MATERIALS if kw in m["name"].lower() or kw in m["material_code"].lower()]
            return self._json({"data": rows, "total": len(rows), "data_as_of": DATA_AS_OF, "data_confidence": "high"})
        if route == "/supplier":
            if q.get("supplier_code") == "SUP-404":
                return self._json({"error": "supplier not found"}, 404)
            return self._json({"data": SUPPLIER, "data_as_of": DATA_AS_OF, "data_confidence": "high"})
        if route == "/orders":
            rows = [o for o in ORDERS if q.get("customer") in (None, "", o["customer"]) and q.get("product_line") in (None, "", o["product_line"])]
            return self._json({"data": rows, "total": len(rows), "data_as_of": DATA_AS_OF, "data_confidence": "medium"})
        return self._json({"error": "not found"}, 404)


def start_mock():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def server_params(base_url):
    env = {
        **os.environ,
        "CONTROL_PLATFORM_BASE_URL": base_url,
        "CONTROL_PLATFORM_APP_KEY": MOCK_APP_KEY,
        "CONTROL_PLATFORM_APP_SECRET": MOCK_APP_SECRET,
        "CONTROL_PLATFORM_TIMEOUT_MS": "800",
        "CONTROL_PLATFORM_CONNECT_TIMEOUT_MS": "500",
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    return StdioServerParameters(command=sys.executable, args=["-m", "mcp_server"], cwd=PROJECT_ROOT, env=env)


async def call_tool(session, name, args):
    """调用 tool，返回 (is_error, 解析后的 JSON 或原始文本)。"""
    result = await session.call_tool(name, args)
    text = result.content[0].text if result.content else ""
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        parsed = None
    return bool(result.is_error), parsed


# ---------------- 十二条检查（规范 §20） ----------------

async def check_01_initialize(session, init_result):
    assert init_result.server_info.name == "company-control", f"server_info.name={init_result.server_info.name}"
    assert init_result.server_info.version == "0.1.0", f"server_info.version={init_result.server_info.version!r}"


async def check_02_tools_list(session):
    tools = await session.list_tools()
    names = {t.name for t in tools.tools}
    assert names == EXPECTED_TOOLS, f"tools={names}"


async def check_03_normal_structured(session):
    _, body = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19", "dimension": "day", "request_id": "req-001"})
    for key in ("source", "capability", "read_only", "generated_at", "data_confidence", "data_as_of", "evidence_refs", "data"):
        assert key in body, f"缺少字段 {key}"
    assert body["source"] == "company-control" and body["read_only"] is True
    assert body["capability"] == "metric_query" and body["data"]
    assert body.get("request_id") == "req-001", f"request_id 未回显: {body.get('request_id')}"


async def check_04_invalid_input(session):
    # 日期跨度超限 → 结构化 INVALID_ARGUMENT
    _, body = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-01-01", "date_to": "2026-09-19"})
    assert body and body.get("error", {}).get("code") == "INVALID_ARGUMENT", f"span 校验失败: {body}"
    # 明细无过滤条件 → INVALID_ARGUMENT
    _, body = await call_tool(session, "detail_orders_list", {})
    assert body and body.get("error", {}).get("code") == "INVALID_ARGUMENT", f"过滤校验失败: {body}"
    # 类型非法 → 被拒绝（Schema 层）
    is_error, body = await call_tool(session, "catalog_metrics_list", {"page_size": "abc"})
    assert is_error or (body and body.get("error", {}).get("code") == "INVALID_ARGUMENT"), "类型非法未被拒绝"
    # 未定义字段 → 被拒绝（§7）
    is_error, body = await call_tool(session, "catalog_metrics_list", {"page": 1, "page_size": 20, "unknown_field": "x"})
    assert is_error or (body and body.get("error", {}).get("code") == "INVALID_ARGUMENT"), "未定义字段未被拒绝"
    # 非法枚举 → 被拒绝（§7）
    is_error, body = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19", "dimension": "bogus"})
    assert is_error or (body and body.get("error", {}).get("code") == "INVALID_ARGUMENT"), "非法枚举未被拒绝"
    # 拒绝后服务仍存活
    _, body = await call_tool(session, "get_system_health", {})
    assert body and body["data"]["status"] == "ok"


async def check_05_unauthorized(session):
    MOCK_STATE["mode"] = "unauth"
    try:
        _, body = await call_tool(session, "master_supplier_get", {"supplier_code": "SUP-001"})
        err = body.get("error", {})
        assert err.get("code") == "UNAUTHORIZED" and err.get("retryable") is False, f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"


async def check_06_upstream_timeout(session):
    MOCK_STATE["mode"] = "timeout"
    try:
        _, body = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19"})
        err = body.get("error", {})
        assert err.get("code") == "UPSTREAM_TIMEOUT" and err.get("retryable") is True, f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"


async def check_07_upstream_unavailable(session):
    MOCK_STATE["mode"] = "unavailable"
    try:
        _, body = await call_tool(session, "master_material_search", {"keyword": "电源"})
        assert body.get("error", {}).get("code") == "UPSTREAM_UNAVAILABLE", f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"
    # 进程未崩溃：恢复正常后可继续调用
    _, body = await call_tool(session, "get_system_health", {})
    assert body and body["data"]["status"] == "ok", "上游不可用导致进程崩溃"


async def check_08_evidence_refs(session):
    _, body = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19"})
    refs = body.get("evidence_refs") or []
    assert refs and all(r.startswith("control-platform://metric/") and "@" in r for r in refs), f"{refs}"
    _, body = await call_tool(session, "detail_orders_list", {"customer": "示例客户A"})
    refs = body.get("evidence_refs") or []
    assert refs and all(r.startswith("control-platform://order/SO-") and "@" in r for r in refs), f"{refs}"


async def check_09_sensitive_fields(session):
    _, body = await call_tool(session, "master_material_search", {"keyword": "电源"})
    raw = json.dumps(body, ensure_ascii=False)
    assert "13800001111" not in raw, "手机号未脱敏"
    row = body["data"][0]
    assert row.get("phone") == "***" and row.get("cost_price") == "***", f"敏感字段未脱敏: {row}"


async def check_10_no_write_tools(session):
    tools = await session.list_tools()
    for t in tools.tools:
        assert t.name in EXPECTED_TOOLS, f"未声明的工具: {t.name}"
        assert "只读" in (t.description or ""), f"{t.name} 描述缺少只读声明"


async def check_11_idempotent_read(session):
    _, a = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19"})
    _, b = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19"})
    assert a["data"] == b["data"] and a["evidence_refs"] == b["evidence_refs"], "重复查询结果不一致"


async def check_12_health(session):
    _, body = await call_tool(session, "get_system_health", {})
    data = body.get("data", {})
    assert data.get("status") == "ok", f"{data}"
    assert data.get("read_only") is True and data.get("version") == "0.1.0"
    assert set(data.get("capabilities", [])) == EXPECTED_TOOLS
    # §16 顶层字段超集
    assert body.get("status") == "ok" and body.get("version") == "0.1.0"
    assert body.get("checked_at") and set(body.get("capabilities", [])) == EXPECTED_TOOLS


async def check_13_stale_data(session):
    MOCK_STATE["mode"] = "stale"
    try:
        _, body = await call_tool(session, "metric_query", {"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19"})
        err = body.get("error", {})
        assert err.get("code") == "STALE_DATA" and err.get("retryable") is True, f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"


CHECKS = [
    ("01 initialize 握手成功", check_01_initialize),
    ("02 tools/list 返回预期 Tool", check_02_tools_list),
    ("03 正常输入返回结构化结果", check_03_normal_structured),
    ("04 非法输入被拒绝且不崩溃", check_04_invalid_input),
    ("05 未授权请求被拒绝", check_05_unauthorized),
    ("06 上游超时返回标准错误", check_06_upstream_timeout),
    ("07 上游不可用不导致进程崩溃", check_07_upstream_unavailable),
    ("08 风险/指标类结果含 evidence_refs", check_08_evidence_refs),
    ("09 敏感字段不出现在结果中", check_09_sensitive_fields),
    ("10 无未声明的写操作工具", check_10_no_write_tools),
    ("11 重复只读请求结果一致", check_11_idempotent_read),
    ("12 get_system_health 返回正确状态", check_12_health),
    ("13 数据过期返回 STALE_DATA（补充）", check_13_stale_data),
]


async def run() -> int:
    mock, port = start_mock()
    base_url = f"http://127.0.0.1:{port}"
    results = []
    try:
        async with stdio_client(server_params(base_url)) as (read, write):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                for name, fn in CHECKS:
                    try:
                        if name.startswith("01"):
                            await fn(session, init_result)
                        else:
                            await fn(session)
                        results.append((name, True, ""))
                        print(f"PASS  {name}")
                    except Exception as exc:  # noqa: BLE001
                        results.append((name, False, str(exc)))
                        print(f"FAIL  {name}: {exc}")
    finally:
        mock.shutdown()

    failed = [r for r in results if not r[1]]
    print(f"\n总计 {len(results)} 项，通过 {len(results) - len(failed)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(run()))
