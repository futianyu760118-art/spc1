"""测试外部库存列表接口

调用外部接口 GET /api/v1/external/inventory/list 并打印第一页数据。

签名机制：HMAC-SHA256
签名字符串 = {timestamp}{app_key}{endpoint_code}{query_string}
"""

import hmac
import hashlib
import time
import os
import asyncio

import httpx


# ── 配置（可通过环境变量覆盖） ──
APP_KEY = os.environ.get("APP_KEY", "ak_a59c9845a95b48b3")
APP_SECRET = os.environ.get("APP_SECRET", "bfbf2bcee2ed482286505f83392b5fbc92e53cef44b34fb684c01039c2f0e9a9")
BASE_URL = os.environ.get("BASE_URL", "https://192.168.0.127:18084")
ENDPOINT_CODE = "inventory.list"
ENDPOINT_PATH = "/api/v1/external/inventory/list"
PAGE = int(os.environ.get("PAGE", "1"))
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "20"))


def generate_signature(timestamp: int, app_key: str, app_secret: str,
                       endpoint_code: str, query_string: str) -> str:
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


def format_table(items: list) -> str:
    if not items:
        return "（无数据）"

    headers = ["id", "物料编码", "物料名称", "仓库", "库位",
               "现有量", "锁定量", "结存量", "在途量", "单价", "期末余额", "批次号", "更新时间"]
    keys = ["id", "material_code", "material_name", "wh_name", "location_name",
            "qty_on_hand", "locked_qty", "balance_qty", "qty_in_transit",
            "unit_price", "ending_balance", "batch_no", "updated_at"]

    rows = []
    for item in items:
        row = [str(item.get(k, "")) if item.get(k) is not None else "" for k in keys]
        rows.append(row)

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    col_widths = [min(w, 45) for w in col_widths]

    def fmt_row(cells, widths):
        return " | ".join(c + " " * (w - len(c)) for c, w in zip(cells, widths))

    lines = []
    lines.append(fmt_row(headers, col_widths))
    lines.append("-+-".join("-" * w for w in col_widths))
    for row in rows:
        lines.append(fmt_row([c[:45] for c in row], col_widths))

    return "\n".join(lines)


async def main():
    timestamp = int(time.time())
    query_string = f"page={PAGE}&page_size={PAGE_SIZE}"
    sign_str, signature = generate_signature(timestamp, APP_KEY, APP_SECRET, ENDPOINT_CODE, query_string)
    headers = build_headers(APP_KEY, signature, timestamp)
    url = f"{BASE_URL}{ENDPOINT_PATH}?{query_string}"

    print("=" * 80)
    print(f"外部库存列表 — 第 {PAGE} 页 (每页 {PAGE_SIZE} 条)")
    print("=" * 80)
    print(f"URL:         {url}")
    print(f"Timestamp:   {timestamp}")
    print(f"Sign String: {sign_str}")
    print(f"Signature:   {signature}")
    print()

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as e:
        print(f"[HTTP {e.response.status_code}] {e.response.text[:800]}")
        return
    except httpx.RequestError as e:
        print(f"[连接失败] {e}")
        return

    code = body.get("code", -1)
    message = body.get("message", "")
    data = body.get("data", {}) or {}

    if code != 0:
        print(f"[API 错误] code={code}, message={message}")
        return

    items = data.get("items", [])
    total = data.get("total", 0)
    resp_page = data.get("page", PAGE)
    resp_size = data.get("page_size", PAGE_SIZE)

    print(f"总数: {total}    当前页: {resp_page}    每页: {resp_size}")
    print()

    print(format_table(items))

    if not items:
        print()
        print("提示: 数据库可能没有库存数据，请确认 ERP 同步已完成。")

    print()
    print(f"完成。本页共 {len(items)} 条记录。")


if __name__ == "__main__":
    asyncio.run(main())
