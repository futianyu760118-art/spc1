"""数据供给模块「内部接口对外暴露」机制联调脚本。

执行：
    cd backend && python test_internal_exposable.py

前置：
    - uvicorn 已启动（监听 8000 端口）
    - 已运行 init_database.py（包含 sys-api-caller 与 api_caller seed）
    - 默认 admin 用户存在
"""

import hashlib
import hmac
import json
import time
import requests

BASE = "http://localhost:8000/api/v1"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
APP_KEY = "ak_smoketest0001"
APP_SECRET = "secret_smoketest0001_xyz"


def _sign(timestamp: str, app_key: str, endpoint_code: str, query: str) -> str:
    s = f"{timestamp}{app_key}{endpoint_code}{query}"
    return hmac.new(APP_SECRET.encode(), s.encode(), hashlib.sha256).hexdigest()


def login() -> str:
    r = requests.post(
        f"{BASE}/basicdata/auth/login",
        data={"login_type": "employee", "username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def create_api_key(token: str):
    r = requests.post(
        f"{BASE}/basicdata/data-supply/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key_name": "smoke-internal-exposable",
            "description": "smoke test for internal endpoint exposure",
            "allowed_data_types": [],
            "allowed_endpoints": ["int:health.ping"],
            "rate_limit": 100,
            "ip_whitelist": "",
            "expires_at": None,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]


def call_with_api_key(method: str, path: str, endpoint_code: str, query: str = ""):
    ts = str(int(time.time()))
    sig = _sign(ts, APP_KEY, endpoint_code, query)
    return requests.request(
        method,
        f"{BASE}{path}",
        params=dict(x.split("=", 1) for x in query.split("&") if x) if query else None,
        headers={
            "X-App-Key": APP_KEY,
            "X-Timestamp": ts,
            "X-Signature": sig,
        },
        timeout=10,
    )


def assert_ok(resp: requests.Response, expect_msg: str):
    body = resp.json()
    assert body.get("code") == 0, f"FAIL: {expect_msg}, got {body}"
    print(f"PASS: {expect_msg} → {body}")


def main():
    print("=== 冒烟：数据供给 内部接口对外暴露 ===")

    token = login()
    print(f"PASS: admin JWT login")

    ak = create_api_key(token)
    print(f"PASS: API Key created id={ak.get('id')}")

    r = requests.get(f"{BASE}/common/ping", headers={"Authorization": f"Bearer {token}"})
    assert_ok(r, "JWT 路径调用 /common/ping")

    r2 = call_with_api_key("GET", "/common/ping", "int:health.ping", query="")
    assert_ok(r2, "HMAC 路径调用 /common/ping（int:health.ping）")

    ts = str(int(time.time()))
    bad = requests.get(
        f"{BASE}/common/ping",
        headers={"X-App-Key": APP_KEY, "X-Timestamp": ts, "X-Signature": "0" * 64},
    )
    assert bad.status_code == 401, f"FAIL: 错误签名应 401，实际 {bad.status_code}"
    print(f"PASS: 错误签名返回 401")

    r4 = call_with_api_key("GET", "/orders/list", endpoint_code="int:orders.list", query="")
    assert r4.status_code in (401, 403), f"未授权路径应 401/403，实际 {r4.status_code}"
    print(f"PASS: 未 @exposable 路径被拒绝（{r4.status_code}）")

    print("\n=== 全部冒烟用例通过 ===\n")


if __name__ == "__main__":
    main()
