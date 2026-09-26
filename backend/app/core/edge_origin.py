"""Optional origin gate for traffic routed through the Jainune API Worker.

Keep disabled until every client and webhook has moved to the Worker. Render
health probes remain direct; all application HTTP and WebSocket paths require
the private Worker-to-origin secret when the gate is enabled.
"""

import hmac

from app.core.config import settings


_DIRECT_HEALTH_PATHS = frozenset({"/", "/health", "/livez", "/readyz", "/v1/health/live"})


class EdgeOriginGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not settings.require_edge_origin:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http" and scope.get("path") in _DIRECT_HEALTH_PATHS:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", ()))
        supplied = headers.get(b"x-edge-secret", b"")
        expected = settings.cloudflare_origin_secret.encode("utf-8")
        if expected and hmac.compare_digest(supplied, expected):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return

        body = b'{"detail":"Forbidden"}'
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
