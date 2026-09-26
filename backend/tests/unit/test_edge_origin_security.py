"""Origin gate and webhook-body regression checks for the optional API Worker."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.edge_origin import EdgeOriginGate
from app.core.payment_body_limit import StoreWebhookBodyLimit
from app.core.sentry import sentry_before_send
from app.main import app as real_app
from app.routers.subscriptions import _read_bounded_webhook_body


async def _run_gate(scope, required=True):
    events = []

    async def app(inner_scope, receive, send):
        events.append(("passed", inner_scope["type"]))

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        events.append(message)

    with patch("app.core.edge_origin.settings") as settings:
        settings.require_edge_origin = required
        settings.cloudflare_origin_secret = "private-worker-secret"
        await EdgeOriginGate(app)(scope, receive, send)
    return events


@pytest.mark.asyncio
async def test_origin_gate_preserves_health_and_verified_http_and_websocket():
    assert ("passed", "http") in await _run_gate({"type": "http", "path": "/health", "headers": []})
    trusted = [(b"x-edge-secret", b"private-worker-secret")]
    assert ("passed", "http") in await _run_gate({"type": "http", "path": "/v1/feed", "headers": trusted})
    assert ("passed", "websocket") in await _run_gate({"type": "websocket", "path": "/v1/ws/chat/id", "headers": trusted})
    assert ("passed", "http") in await _run_gate({"type": "http", "path": "/v1/feed", "headers": []}, required=False)


@pytest.mark.asyncio
async def test_origin_gate_rejects_direct_or_forged_application_requests():
    for path in ("/v1/auth/otp/request", "/v1/subscriptions/webhook", "/v1/payments/razorpay/verify-web"):
        events = await _run_gate({"type": "http", "path": path, "headers": [(b"x-edge-secret", b"wrong")]})
        assert any(isinstance(event, dict) and event.get("status") == 403 for event in events)
    events = await _run_gate({"type": "websocket", "path": "/v1/ws/chat/id", "headers": []})
    assert {"type": "websocket.close", "code": 1008} in events


@pytest.mark.asyncio
async def test_real_app_preserves_health_and_browser_preflight_when_gate_enabled():
    with patch("app.core.edge_origin.settings") as settings:
        settings.require_edge_origin = True
        settings.cloudflare_origin_secret = "private-worker-secret"
        transport = ASGITransport(app=real_app)
        async with AsyncClient(transport=transport, base_url="https://jainune-backend-api.onrender.com") as client:
            health = await client.get("/livez")
            assert health.status_code == 200

            direct = await client.get("/v1/subscriptions/plans")
            assert direct.status_code == 403

            preflight = await client.options(
                "/v1/auth/google",
                headers={
                    "X-Edge-Secret": "private-worker-secret",
                    "Origin": "https://app.jainune.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == "https://app.jainune.com"


def _request(chunks, declared=None):
    headers = [] if declared is None else [(b"content-length", str(declared).encode())]
    frames = iter([{"type": "http.request", "body": part, "more_body": index < len(chunks) - 1}
                   for index, part in enumerate(chunks)])

    async def receive():
        return next(frames)

    return Request({"type": "http", "headers": headers}, receive)


@pytest.mark.asyncio
async def test_razorpay_webhook_body_is_bounded_even_without_content_length():
    assert await _read_bounded_webhook_body(_request([b"abc", b"def"])) == b"abcdef"
    with pytest.raises(HTTPException) as declared:
        await _read_bounded_webhook_body(_request([b"x"], declared=1024 * 1024 + 1))
    assert declared.value.status_code == 413
    with pytest.raises(HTTPException) as streamed:
        await _read_bounded_webhook_body(_request([b"x" * (1024 * 1024), b"y"]))
    assert streamed.value.status_code == 413


def test_sentry_scrubs_short_lived_websocket_ticket_from_url():
    event = {
        "request": {
            "query_string": "ticket=wst_private&other=ok",
            "url": "wss://example.workers.dev/v1/ws/chat?ticket=wst_private&other=ok",
        },
        "breadcrumbs": [{"message": "Connecting to wss://example.workers.dev/v1/ws/chat?ticket=wst_private"}],
    }
    scrubbed = sentry_before_send(event)
    assert "wst_private" not in scrubbed["request"]["query_string"]
    assert "wst_private" not in scrubbed["request"]["url"]
    assert "wst_private" not in scrubbed["breadcrumbs"][0]["message"]
    assert "other=ok" in scrubbed["request"]["query_string"]


@pytest.mark.asyncio
async def test_store_notification_body_limit_runs_before_json_parsing():
    seen = []

    async def app(scope, receive, send):
        seen.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def check(chunks, declared=None):
        frames = iter({"type": "http.request", "body": part, "more_body": i < len(chunks) - 1}
                      for i, part in enumerate(chunks))

        async def receive():
            return next(frames)

        events = []

        async def send(frame):
            events.append(frame)

        headers = [] if declared is None else [(b"content-length", str(declared).encode())]
        scope = {"type": "http", "method": "POST", "path": "/v1/subscriptions/store-notification", "headers": headers}
        await StoreWebhookBodyLimit(app)(scope, receive, send)
        return events[0]["status"]

    assert await check([b"ok"]) == 200
    assert seen[-1]["body"] == b"ok"
    assert await check([b"x"], declared=1024 * 1024 + 1) == 413
    assert await check([b"x" * (1024 * 1024), b"y"]) == 413
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_real_app_rejects_large_store_notification_without_database_access():
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="https://jainune-backend-api.onrender.com") as client:
        response = await client.post(
            "/v1/subscriptions/store-notification",
            content=b"x" * (1024 * 1024 + 1),
            headers={"X-Store-Webhook-Token": "invalid"},
        )
    assert response.status_code == 413
