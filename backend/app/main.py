import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response

from app.core.config import settings
from app.core.database import close_pool, create_pool
from app.core.metrics import metrics_registry
from app.core.redis import close_redis, create_redis
from app.core.sentry import init_sentry


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


if settings.environment == "production":
    _h = logging.StreamHandler()
    _h.setFormatter(JsonFormatter())
    logging.root.handlers = [_h]
    logging.root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if getattr(settings, "sentry_dsn", ""):
        init_sentry(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1,
        )
    await create_pool()
    await create_redis()
    yield
    # Shutdown
    await close_pool()
    await close_redis()


app = FastAPI(
    title="Jainune API",
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Idempotency-Key",
        "X-Store-Webhook-Token",
        "X-Razorpay-Signature",
        "X-Turnstile-Token",
        "X-Client-Platform",
        "X-App-Version",
    ],
)


# ── Security headers middleware ───────────────────────────────────────────────

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    req_path = getattr(getattr(request, "url", None), "path", "")
    if isinstance(req_path, str) and (
        req_path.startswith("/legal") or req_path in (
            "/privacy", "/terms", "/child-safety", "/community-guidelines", "/delete-account"
        )
    ):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers.pop("server", None)
    response.headers.pop("Server", None)
    return response


# ── Prometheus metrics collection middleware ─────────────────────────────────

@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    metrics_registry.record_request_start()
    start_time = time.monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.monotonic() - start_time
        metrics_registry.record_request_end(
            method=request.method,
            endpoint=request.url.path,
            status=status_code,
            duration_seconds=duration,
        )


# ── Standard response envelope helpers ───────────────────────────────────────
from app.core.responses import err, ok


# ── Global exception handlers ──────────────────────────────────────────────────
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.errors import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


# ── Health (Deep Connectivity Check) ─────────────────────────────────────────

@app.get("/v1/health", tags=["Health"])
async def health():
    db_ok = False
    redis_ok = False

    try:
        from app.core.database import get_pool
        pool = get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            db_ok = True
    except Exception:
        db_ok = False

    try:
        from app.core.redis import get_redis
        r = get_redis()
        if r and await r.ping():
            redis_ok = True
    except Exception:
        redis_ok = False

    is_healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if is_healthy else 503,
        content={
            "status": "healthy" if is_healthy else "degraded",
            "version": settings.app_version,
            "checks": {
                "database": "connected" if db_ok else "disconnected",
                "redis": "connected" if redis_ok else "disconnected",
            },
        },
    )


# ── Prometheus Metrics Exposition ────────────────────────────────────────────

@app.get("/metrics", include_in_schema=False)
async def get_metrics():
    content = metrics_registry.generate_prometheus_output(
        version=settings.app_version,
        environment=settings.environment,
    )
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


# ── Routers (registered after all imports to avoid circular deps) ─────────────
from app.routers import auth, onboarding, feed, interactions, telemetry  # noqa: E402
from app.routers import chats, websockets, media                          # noqa: E402
from app.routers import users, subscriptions, arcade, admin, location, legal     # noqa: E402

app.include_router(auth.router, prefix="/v1")
app.include_router(onboarding.router, prefix="/v1")
app.include_router(feed.router)
app.include_router(interactions.router)
app.include_router(telemetry.router)
app.include_router(chats.router)
app.include_router(websockets.router)
app.include_router(media.router)
app.include_router(users.router)
app.include_router(subscriptions.router)
app.include_router(arcade.router)
app.include_router(admin.router)
app.include_router(location.router)
app.include_router(legal.router)

