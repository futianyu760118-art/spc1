"""外部接口测试公共模块

提供签名生成、请求发送、响应解析、表格格式化的通用逻辑。
"""

import hmac
import hashlib
import time
import os
from typing import Optional, Callable, Any

import httpx


APP_KEY = os.environ.get("APP_KEY", "ak_a59c9845a95b48b3")
APP_SECRET = os.environ.get("APP_SECRET", "bfbf2bcee2ed482286505f83392b5fbc92e53cef44b34fb684c01039c2f0e9a9")
BASE_URL = os.environ.get("BASE_URL", "http://192.168.0.178:8000")


def generate_signature(timestamp: int, app_key: str, app_secret: str,
                       endpoint_code: str, query_string: str) -> tuple:
    string_to_sign = f"{timestamp}{app_key}{endpoint_code}{query_string}"
    sig = hmac.new(
        app_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return string_to_sign, sig


def build_headers(app_key: str, signature: str, timestamp: int) -> dict:
    return {
        "X-App-Key": app_key,
        "X-Timestamp": str(timestamp),
        "X-Signature": signature,
    }


def print_request_info(url: str, timestamp: int, sign_str: str, signature: str) -> None:
    print(f"URL:         {url}")
    print(f"Timestamp:   {timestamp}")
    print(f"Sign String: {sign_str}")
    print(f"Signature:   {signature}")
    print()


async def call_external_api(endpoint_code: str, endpoint_path: str,
                            query_string: str = "",
                            app_key: str = APP_KEY,
                            app_secret: str = APP_SECRET,
                            base_url: str = BASE_URL) -> Optional[dict]:
    """调用外部接口，返回解析后的响应 body dict"""
    timestamp = int(time.time())
    sign_str, signature = generate_signature(timestamp, app_key, app_secret, endpoint_code, query_string)
    headers = build_headers(app_key, signature, timestamp)

    separator = "&" if "?" in endpoint_path else "?"
    url = f"{base_url}{endpoint_path}{separator}{query_string}" if query_string else f"{base_url}{endpoint_path}"

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as e:
        print(f"[HTTP {e.response.status_code}] {e.response.text[:1500]}")
        return None
    except httpx.RequestError as e:
        print(f"[连接失败] {e}")
        return None

    code = body.get("code", -1)
    if code != 0:
        print(f"[API 错误] code={code}, message={body.get('message', '')}")
        return None

    return body


def format_table(items: list, headers: list, keys: list, max_col_width: int = 45) -> str:
    """将数据列表格式化为表格字符串"""
    if not items:
        return "（无数据）"

    rows = []
    for item in items:
        row = [str(item.get(k, "")) if item.get(k) is not None else "" for k in keys]
        rows.append(row)

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    col_widths = [min(w, max_col_width) for w in col_widths]

    def fmt_row(cells, widths):
        return " | ".join(c + " " * (w - len(c)) for c, w in zip(cells, widths))

    lines = []
    lines.append(fmt_row(headers, col_widths))
    lines.append("-+-".join("-" * w for w in col_widths))
    for row in rows:
        lines.append(fmt_row([c[:max_col_width] for c in row], col_widths))

    return "\n".join(lines)


def print_result(data: dict, title: str, headers: list, keys: list,
                 page: int = 1, page_size: int = 20) -> None:
    """打印接口返回结果的标准输出"""
    items = data.get("items", [])
    total = data.get("total", 0)
    resp_page = data.get("page", page)
    resp_size = data.get("page_size", page_size)

    print("=" * 80)
    print(f"{title} — 第 {resp_page} 页 (每页 {resp_size} 条)")
    print("=" * 80)

    print(f"总数: {total}    当前页: {resp_page}    每页: {resp_size}")
    print()

    print(format_table(items, headers, keys))

    if not items:
        print()
        print("提示: 数据库可能没有数据，请确认同步已完成。")

    print()
    print(f"完成。本页共 {len(items)} 条记录。")
