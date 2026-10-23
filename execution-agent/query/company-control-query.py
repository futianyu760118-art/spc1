"""执行面查询 CLI — importlib 直载 mcp-company-control 的 upstream_client.py 查单个 path。

用法：python company-control-query.py <path> <params_json>
输出：stdout 单行 JSON {"ok":true,"data":...} / {"ok":false,"error":{"code","message"}}；
     结构化错误 exit 0（由 Node 侧转 run_failed），意外崩溃 exit 1，用法错误 exit 2。
"""
import asyncio
import importlib.util
import json
import os
import sys
import traceback

# execution-agent/query/ 上三级 = 仓库根
_DEFAULT_UPSTREAM = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "mcp-company-control",
    "mcp_server",
    "upstream_client.py",
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _emit_fail(code, message):
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}, ensure_ascii=False))
    return 0


def _load_upstream_client(client_path):
    spec = importlib.util.spec_from_file_location("upstream_client", client_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 3:
        print("usage: company-control-query.py <path> <params_json>", file=sys.stderr)
        return 2
    path_arg, params_arg = sys.argv[1], sys.argv[2]

    try:
        params = json.loads(params_arg) if params_arg.strip() else {}
    except json.JSONDecodeError as exc:
        return _emit_fail("INVALID_ARGUMENT", f"params 不是合法 JSON: {exc}")
    if not isinstance(params, dict):
        return _emit_fail("INVALID_ARGUMENT", "params 必须是 JSON 对象")

    client_path = os.getenv("UPSTREAM_CLIENT_PATH") or _DEFAULT_UPSTREAM
    if not os.path.isfile(client_path):
        return _emit_fail("INTERNAL_ERROR", f"找不到 upstream_client: {client_path}")

    module = _load_upstream_client(client_path)
    try:
        data = asyncio.run(module.call(path_arg, params))
    except module.UpstreamError as exc:
        return _emit_fail(exc.code, exc.message)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
