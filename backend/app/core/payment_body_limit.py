"""Bound unauthenticated store notification bodies before FastAPI parses JSON."""

_MAX_STORE_WEBHOOK_BYTES = 1024 * 1024
_STORE_WEBHOOK_PATH = "/v1/subscriptions/store-notification"


class StoreWebhookBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope.get("method") != "POST" or
                scope.get("path") != _STORE_WEBHOOK_PATH):
            await self.app(scope, receive, send)
            return

        async def reject(status):
            await send({
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-length", b"0")],
            })
            await send({"type": "http.response.body", "body": b""})

        headers = dict(scope.get("headers", ()))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError:
                await reject(400)
                return
            if declared_size < 0 or declared_size > _MAX_STORE_WEBHOOK_BYTES:
                await reject(413)
                return

        body = bytearray()
        while True:
            frame = await receive()
            if frame["type"] == "http.disconnect":
                return
            if frame["type"] != "http.request":
                continue
            chunk = frame.get("body", b"")
            if len(body) + len(chunk) > _MAX_STORE_WEBHOOK_BYTES:
                await reject(413)
                return
            body.extend(chunk)
            if not frame.get("more_body", False):
                break

        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
