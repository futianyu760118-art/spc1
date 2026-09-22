"""独立测试脚本 — stdio 13 项 + HTTP 4 项（AEOS MCP Integration Spec §20 十二条 + 双传输补充）

运行（在 mcp-company-control/ 目录下）：
    python scripts/test_company_control.py

内置 mock 中台端点（127.0.0.1 随机端口），无需真实中台：
  - stdio：以子进程拉起 mcp_server，用 MCP client 完成真实握手与调用
  - streamable-http：以子进程拉起 --transport streamable-http，验证鉴权与握手
"""

import asyncio
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
if hasattr(sys.stdout, "reconfigure"):  # GBK 控制台下的中文输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx2  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client  # noqa: E402

EXPECTED_TOOLS = {
    "get_system_health",
    "orders_list",
    "order_details_list",
    "bom_tree",
}

DATA_AS_OF = "2026-09-19T18:00:00Z"

ORDERS = [
    {
        "id": 1,
        "order_no": "SO-2609-001",
        "line_no": "1",
        "customer": "示例客户A",
        "customer_code": "C-001",
        "product_code": "P-100",
        "product_name": "商业照明灯",
        "order_qty": 100.0,
        "completed_qty": 10.0,
        "order_amount": 1280000.0,
        "status": "open",
        "risk_level": "red",
        "promised_date": "2026-09-20",
        "planned_start_date": "2026-09-10",
        "owner": "张三",
        "updated_at": "2026-09-19T10:00:00",
        "phone": "13800001111",  # 仅用于脱敏断言（真实端点无此字段）
    },
    {
        "id": 2,
        "order_no": "SO-2609-002",
        "line_no": "1",
        "customer": "示例客户B",
        "customer_code": "C-002",
        "product_code": "P-200",
        "product_name": "户外照明灯",
        "order_qty": 50.0,
        "completed_qty": 0.0,
        "order_amount": 560000.0,
        "status": "open",
        "risk_level": "yellow",
        "promised_date": "2026-09-28",
        "planned_start_date": "2026-09-15",
        "owner": "李四",
        "updated_at": "2026-09-18T09:00:00",
    },
]

ORDER_DETAILS = [
    {
        "id": 11,
        "sale_order_id": 1,
        "order_no": "SO-2609-001",
        "line_no": "1",
        "product_code": "P-100",
        "product_name": "商业照明灯",
        "product_model": "LED-60W",
        "order_qty": 100.0,
        "order_amount": 1280000.0,
        "promised_date": "2026-09-20",
        "batch_no": "B-2609",
        "bom_no": "BOM-001",
        "bom_id": 1001,
        "labor_price_amount": 3200.0,
        "status": "open",
        "customer": "示例客户A",
        "customer_code": "C-001",
    },
]

BOM_TREE = {
    "bom_id": "BOM-001",
    "bom_no": "BOM-001",
    "material_id": 1001,
    "base_qty": 1.0,
    "demand_qty": 1.0,
    "bom_version": "V1",
    "bom_type": "量产",
    "flatten": False,
    "total_nodes": 2,
    "max_level": 1,
    "tree": [
        {
            "bom_id": "BOM-001",
            "material_id": 1001,
            "material_code": "M-100",
            "material_name": "灯壳",
            "standard_qty": 1.0,
            "level": 1,
            "parent_material_id": None,
            "children": [
                {
                    "bom_id": None,
                    "material_id": 2001,
                    "material_code": "M-200",
                    "material_name": "螺丝",
                    "standard_qty": 4.0,
                    "level": 2,
                    "parent_material_id": 1001,
                    "children": [],
                }
            ],
        }
    ],
}

MOCK_STATE = {"mode": "normal"}

# 与 SPC「数据供给」HMAC 机制一致的校验参数
MOCK_APP_KEY = "test-app-key"
MOCK_APP_SECRET = "test-secret"
MOCK_ENDPOINT_CODES = {
    "/common/ping": "int:health.ping",
    "/external/orders/list": "orders.list",
    "/external/order-details/list": "order_details.list",
    "/external/boms/tree": "boms.tree",
}

MCP_HTTP_TOKEN = "test-http-token"


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
        """与 SPC validate_signature_for_endpoint 同算法：HMAC-SHA256(secret, ts+app_key+endpoint_code+query)"""
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
            return self._json({"code": 0, "message": "ok", "data": {"items": [], "total": 0}})
        if mode == "unauth":
            return self._json({"error": "invalid token"}, 401)
        if mode == "unavailable":
            return self._json({"error": "upstream down"}, 503)
        if mode == "stale":
            return self._json(
                {
                    "code": 0,
                    "message": "ok",
                    "data": {"items": [], "total": 0, "stale": True, "data_confidence": "low"},
                }
            )

        parsed = urlparse(self.path)
        if not self._verify_signature(parsed):
            return self._json({"error": "signature invalid"}, 401)
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        route = parsed.path

        if route == "/common/ping":
            return self._json({"code": 0, "message": "pong", "data": {"ok": True}})
        if route == "/external/orders/list":
            rows = ORDERS
            if q.get("customer_code"):
                rows = [o for o in rows if o["customer_code"] == q["customer_code"]]
            if q.get("keyword"):
                kw = q["keyword"]
                rows = [
                    o
                    for o in rows
                    if kw in o["order_no"] or kw in o["customer"] or kw in o["product_name"]
                ]
            return self._json(
                {
                    "code": 0,
                    "message": "ok",
                    "data": {
                        "items": rows,
                        "total": len(rows),
                        "page": int(q.get("page", 1)),
                        "page_size": int(q.get("page_size", 20)),
                    },
                }
            )
        if route == "/external/order-details/list":
            rows = ORDER_DETAILS
            if q.get("order_no"):
                rows = [r for r in rows if r["order_no"] == q["order_no"]]
            return self._json(
                {
                    "code": 0,
                    "message": "ok",
                    "data": {
                        "items": rows,
                        "total": len(rows),
                        "page": int(q.get("page", 1)),
                        "page_size": int(q.get("page_size", 20)),
                    },
                }
            )
        if route == "/external/boms/tree":
            return self._json({"code": 0, "message": "ok", "data": BOM_TREE})
        return self._json({"error": "not found"}, 404)


def start_mock():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def stdio_server_params(base_url):
    env = {
        **os.environ,
        "CONTROL_PLATFORM_BASE_URL": base_url,
        "CONTROL_PLATFORM_APP_KEY": MOCK_APP_KEY,
        "CONTROL_PLATFORM_APP_SECRET": MOCK_APP_SECRET,
        "CONTROL_PLATFORM_TIMEOUT_MS": "800",
        "CONTROL_PLATFORM_CONNECT_TIMEOUT_MS": "500",
        "MCP_TRANSPORT": "",
        "MCP_HTTP_TOKEN": "",
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


# ---------------- stdio 13 项检查（规范 §20） ----------------

async def check_01_initialize(session, init_result):
    assert init_result.server_info.name == "company-control", f"server_info.name={init_result.server_info.name}"
    assert init_result.server_info.version == "0.2.0", f"server_info.version={init_result.server_info.version!r}"


async def check_02_tools_list(session):
    tools = await session.list_tools()
    names = {t.name for t in tools.tools}
    assert names == EXPECTED_TOOLS, f"tools={names}"


async def check_03_normal_structured(session):
    _, body = await call_tool(session, "orders_list", {"keyword": "示例", "request_id": "req-001"})
    for key in (
        "source",
        "capability",
        "read_only",
        "generated_at",
        "data_confidence",
        "data_as_of",
        "evidence_refs",
        "data",
        "page",
    ):
        assert key in body, f"缺少字段 {key}"
    assert body["source"] == "company-control" and body["read_only"] is True
    assert body["capability"] == "orders_list" and body["data"]
    assert body.get("request_id") == "req-001", f"request_id 未回显: {body.get('request_id')}"


async def check_04_invalid_input(session):
    # 日期格式非法 → 结构化 INVALID_ARGUMENT
    _, body = await call_tool(session, "orders_list", {"promised_date_start": "2026/01/01"})
    assert body and body.get("error", {}).get("code") == "INVALID_ARGUMENT", f"日期校验失败: {body}"
    # updated_after 非 ISO 8601 → INVALID_ARGUMENT
    _, body = await call_tool(session, "order_details_list", {"updated_after": "昨天"})
    assert body and body.get("error", {}).get("code") == "INVALID_ARGUMENT", f"时间校验失败: {body}"
    # 必填缺失（bom_id）→ Schema 层拒绝
    is_error, body = await call_tool(session, "bom_tree", {})
    assert is_error or (body and body.get("error", {}).get("code") == "INVALID_ARGUMENT"), "bom_id 缺失未被拒绝"
    # 类型非法 → 被拒绝（Schema 层）
    is_error, body = await call_tool(session, "orders_list", {"page_size": "abc"})
    assert is_error or (body and body.get("error", {}).get("code") == "INVALID_ARGUMENT"), "类型非法未被拒绝"
    # 未定义字段 → 被拒绝（§7）
    is_error, body = await call_tool(session, "orders_list", {"page": 1, "unknown_field": "x"})
    assert is_error or (body and body.get("error", {}).get("code") == "INVALID_ARGUMENT"), "未定义字段未被拒绝"
    # 数值越界（page_size > 200）→ 被拒绝
    is_error, body = await call_tool(session, "orders_list", {"page_size": 201})
    assert is_error or (body and body.get("error", {}).get("code") == "INVALID_ARGUMENT"), "越界值未被拒绝"
    # 拒绝后服务仍存活
    _, body = await call_tool(session, "get_system_health", {})
    assert body and body["data"]["status"] == "ok"


async def check_05_unauthorized(session):
    MOCK_STATE["mode"] = "unauth"
    try:
        _, body = await call_tool(session, "orders_list", {})
        err = body.get("error", {})
        assert err.get("code") == "UNAUTHORIZED" and err.get("retryable") is False, f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"


async def check_06_upstream_timeout(session):
    MOCK_STATE["mode"] = "timeout"
    try:
        _, body = await call_tool(session, "order_details_list", {"order_no": "SO-2609-001"})
        err = body.get("error", {})
        assert err.get("code") == "UPSTREAM_TIMEOUT" and err.get("retryable") is True, f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"


async def check_07_upstream_unavailable(session):
    MOCK_STATE["mode"] = "unavailable"
    try:
        _, body = await call_tool(session, "bom_tree", {"bom_id": "BOM-001"})
        assert body.get("error", {}).get("code") == "UPSTREAM_UNAVAILABLE", f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"
    # 进程未崩溃：恢复正常后可继续调用
    _, body = await call_tool(session, "get_system_health", {})
    assert body and body["data"]["status"] == "ok", "上游不可用导致进程崩溃"


async def check_08_evidence_refs(session):
    _, body = await call_tool(session, "orders_list", {"customer_code": "C-001"})
    refs = body.get("evidence_refs") or []
    assert refs and all(r.startswith("control-platform://order/SO-") and "@" in r for r in refs), f"{refs}"
    _, body = await call_tool(session, "order_details_list", {"order_no": "SO-2609-001"})
    refs = body.get("evidence_refs") or []
    assert refs and all(r.startswith("control-platform://order-detail/SO-2609-001/") for r in refs), f"{refs}"
    _, body = await call_tool(session, "bom_tree", {"bom_id": "BOM-001"})
    refs = body.get("evidence_refs") or []
    assert refs and refs[0].startswith("control-platform://bom/BOM-001@"), f"{refs}"


async def check_09_sensitive_fields(session):
    _, body = await call_tool(session, "orders_list", {"customer_code": "C-001"})
    raw = json.dumps(body, ensure_ascii=False)
    assert "13800001111" not in raw, "手机号未脱敏"
    row = body["data"][0]
    assert row.get("phone") == "***", f"敏感字段未脱敏: {row}"


async def check_10_no_write_tools(session):
    tools = await session.list_tools()
    for t in tools.tools:
        assert t.name in EXPECTED_TOOLS, f"未声明的工具: {t.name}"
        assert "只读" in (t.description or ""), f"{t.name} 描述缺少只读声明"


async def check_11_idempotent_read(session):
    _, a = await call_tool(session, "orders_list", {"customer_code": "C-001"})
    _, b = await call_tool(session, "orders_list", {"customer_code": "C-001"})
    assert a["data"] == b["data"], "重复查询业务数据不一致"
    # evidence 的 as_of 为观测时间（上游未返回 data_as_of），只比较目标部分
    assert [r.split("@")[0] for r in a["evidence_refs"]] == [
        r.split("@")[0] for r in b["evidence_refs"]
    ], "重复查询 evidence 目标不一致"


async def check_12_health(session):
    _, body = await call_tool(session, "get_system_health", {})
    data = body.get("data", {})
    assert data.get("status") == "ok", f"{data}"
    assert data.get("read_only") is True and data.get("version") == "0.2.0"
    assert set(data.get("capabilities", [])) == EXPECTED_TOOLS
    # §16 顶层字段超集
    assert body.get("status") == "ok" and body.get("version") == "0.2.0"
    assert body.get("checked_at") and set(body.get("capabilities", [])) == EXPECTED_TOOLS


async def check_13_stale_data(session):
    MOCK_STATE["mode"] = "stale"
    try:
        _, body = await call_tool(session, "orders_list", {})
        err = body.get("error", {})
        assert err.get("code") == "STALE_DATA" and err.get("retryable") is True, f"{body}"
    finally:
        MOCK_STATE["mode"] = "normal"


# ---------------- HTTP 4 项检查（双传输补充） ----------------

INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "0"},
    },
}
INIT_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_server_env(base_url: str, token: str) -> dict:
    """HTTP 子进程环境：显式覆盖 CONTROL_PLATFORM_* 与 MCP_*，与真实 .env 隔离"""
    return {
        **os.environ,
        "CONTROL_PLATFORM_BASE_URL": base_url,
        "CONTROL_PLATFORM_APP_KEY": MOCK_APP_KEY,
        "CONTROL_PLATFORM_APP_SECRET": MOCK_APP_SECRET,
        "CONTROL_PLATFORM_TIMEOUT_MS": "800",
        "CONTROL_PLATFORM_CONNECT_TIMEOUT_MS": "500",
        "MCP_TRANSPORT": "",
        "MCP_HTTP_HOST": "",
        "MCP_HTTP_PORT": "",
        "MCP_HTTP_TOKEN": token,
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def start_http_server(base_url: str, token: str):
    port = free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mcp_server",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        env=http_server_env(base_url, token),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc, port


async def wait_http_ready(port: int, timeout_s: float = 20.0) -> bool:
    url = f"http://127.0.0.1:{port}/mcp"
    deadline = time.monotonic() + timeout_s
    async with httpx2.AsyncClient(timeout=1.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.post(url, json=INIT_BODY, headers=INIT_HEADERS)
                if resp.status_code == 401:  # 服务已就绪（未带 token 被拒）
                    return True
            except httpx2.HTTPError:
                pass
            await asyncio.sleep(0.2)
    return False


async def check_14_http_no_token(port: int):
    url = f"http://127.0.0.1:{port}/mcp"
    async with httpx2.AsyncClient(timeout=5.0) as client:
        resp = await client.post(url, json=INIT_BODY, headers=INIT_HEADERS)
    assert resp.status_code == 401, f"无 token 未被拒绝: {resp.status_code} {resp.text[:120]}"


async def check_15_http_bad_token(port: int):
    url = f"http://127.0.0.1:{port}/mcp"
    async with httpx2.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            url, json=INIT_BODY, headers={**INIT_HEADERS, "Authorization": "Bearer wrong-token"}
        )
    assert resp.status_code == 401, f"错误 token 未被拒绝: {resp.status_code} {resp.text[:120]}"


async def check_16_http_authorized(port: int, token: str):
    url = f"http://127.0.0.1:{port}/mcp"
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    async with http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                assert init_result.server_info.name == "company-control", f"{init_result.server_info}"
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == EXPECTED_TOOLS, f"tools={names}"


def check_17_http_requires_token(base_url: str):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mcp_server",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(free_port()),
        ],
        cwd=PROJECT_ROOT,
        env=http_server_env(base_url, ""),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        code = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("未配置 MCP_HTTP_TOKEN 时 HTTP 模式未拒绝启动")
    assert code == 2, f"退出码应为 2，实际 {code}"


CHECKS = [
    ("01 initialize 握手成功", check_01_initialize),
    ("02 tools/list 返回预期 Tool", check_02_tools_list),
    ("03 正常输入返回结构化结果", check_03_normal_structured),
    ("04 非法输入被拒绝且不崩溃", check_04_invalid_input),
    ("05 未授权请求被拒绝", check_05_unauthorized),
    ("06 上游超时返回标准错误", check_06_upstream_timeout),
    ("07 上游不可用不导致进程崩溃", check_07_upstream_unavailable),
    ("08 结果含 evidence_refs", check_08_evidence_refs),
    ("09 敏感字段不出现在结果中", check_09_sensitive_fields),
    ("10 无未声明的写操作工具", check_10_no_write_tools),
    ("11 重复只读请求结果一致", check_11_idempotent_read),
    ("12 get_system_health 返回正确状态", check_12_health),
    ("13 数据过期返回 STALE_DATA", check_13_stale_data),
]


async def run() -> int:
    mock, port = start_mock()
    base_url = f"http://127.0.0.1:{port}"
    results = []
    try:
        async with stdio_client(stdio_server_params(base_url)) as (read, write):
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

        http_proc, http_port = start_http_server(base_url, MCP_HTTP_TOKEN)
        try:
            if not await wait_http_ready(http_port):
                results.append(("14-16 HTTP 检查", False, "HTTP 服务未就绪"))
                print("FAIL  14-16 HTTP 检查: HTTP 服务未就绪")
            else:
                http_checks = [
                    ("14 HTTP 无 token 被拒（401）", lambda: check_14_http_no_token(http_port)),
                    ("15 HTTP 错误 token 被拒（401）", lambda: check_15_http_bad_token(http_port)),
                    ("16 HTTP 正确 token 握手成功", lambda: check_16_http_authorized(http_port, MCP_HTTP_TOKEN)),
                ]
                for name, fn in http_checks:
                    try:
                        await fn()
                        results.append((name, True, ""))
                        print(f"PASS  {name}")
                    except Exception as exc:  # noqa: BLE001
                        results.append((name, False, str(exc)))
                        print(f"FAIL  {name}: {exc}")
        finally:
            http_proc.terminate()
            try:
                http_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                http_proc.kill()

        try:
            check_17_http_requires_token(base_url)
            results.append(("17 HTTP 未配 token 拒绝启动", True, ""))
            print("PASS  17 HTTP 未配 token 拒绝启动")
        except Exception as exc:  # noqa: BLE001
            results.append(("17 HTTP 未配 token 拒绝启动", False, str(exc)))
            print(f"FAIL  17 HTTP 未配 token 拒绝启动: {exc}")
    finally:
        mock.shutdown()

    failed = [r for r in results if not r[1]]
    print(f"\n总计 {len(results)} 项，通过 {len(results) - len(failed)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
