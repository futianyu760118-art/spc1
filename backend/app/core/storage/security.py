"""附件服务安全头（本地静态挂载与 S3 代理路由共用）

历史遗留或绕过校验的文件若被浏览器按 HTML/SVG 同源渲染会造成存储型 XSS：
nosniff 阻止 MIME 嗅探，CSP sandbox 阻断脚本执行。
"""
from __future__ import annotations

SECURITY_HEADERS = [
    ("x-content-type-options", "nosniff"),
    ("content-security-policy", "sandbox"),
]


class StaticSecurityHeaders:
    """为静态附件响应附加安全头的 ASGI 包装。"""

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.asgi_app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend([(k.encode("latin-1"), v.encode("latin-1")) for k, v in SECURITY_HEADERS])
            await send(message)

        await self.asgi_app(scope, receive, send_with_headers)
