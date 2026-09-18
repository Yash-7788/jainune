import hmac
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Header, status
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


import asyncio
from app.core.background_tasks import await_background_tasks


async def _periodic_maintenance_loop() -> None:
    """
    Periodic background maintenance supervisor running every 10 minutes.
    - Pure SQL pruning: downgrades expired subscriptions and reaps stale matches.
    - Daily Gale-Shapley matching: checks if today's batch ran; if not, triggers run_daily_compatible().
    - Flushes in-process impression buffer to PostgreSQL.
    """
    from datetime import datetime, timezone
    from app.core.database import get_pool

    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            pool = get_pool()
            needs_daily_batch = False
            async with pool.acquire() as conn:
                # 1. Downgrade expired subscriptions (Pure SQL)
                await conn.execute("""
                    UPDATE users
                    SET subscription_tier = 'free'
                    WHERE subscription_expires_at IS NOT NULL
                      AND subscription_expires_at < NOW()
                      AND subscription_tier != 'free'
                """)
                await conn.execute("""
                    UPDATE store_subscriptions
                    SET status = 'expired'
                    WHERE expires_at IS NOT NULL
                      AND expires_at < NOW()
                      AND status = 'active'
                """)

                # 2. Reap stale matches (Pure SQL)
                await conn.execute("""
                    UPDATE matches
                    SET status = 'expired'
                    WHERE expires_at IS NOT NULL
                      AND expires_at < NOW()
                      AND status IN ('pending', 'active')
                """)

                # 3. Check if today's Gale-Shapley matching batch has executed
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                latest_run = await conn.fetchval("SELECT MAX(generated_at) FROM feed_queues")
                needs_daily_batch = (latest_run is None) or (latest_run < today_start)

            if needs_daily_batch:
                logging.getLogger("app.maintenance").info("Executing daily Gale-Shapley matching pipeline...")
                from app.workers.daily_compatible import run_daily_compatible
                await run_daily_compatible()

            # 4. Flush in-process impression buffer
            from app.services.core_people_finder import _async_flush_impressions
            await _async_flush_impressions(pool, force=True)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logging.getLogger("app.maintenance").warning("Periodic maintenance cycle encountered error: %s", exc)


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
    try:
        await create_redis()
    except Exception as exc:
        logging.getLogger(__name__).warning("Redis startup connection deferred/failed: %s", exc)

    m_task = asyncio.create_task(_periodic_maintenance_loop(), name="periodic_maintenance")
    yield
    # Shutdown
    m_task.cancel()
    try:
        await await_background_tasks(timeout=5.0)
    except Exception:
        pass
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
    if "server" in response.headers:
        del response.headers["server"]
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


# ── Liveness Probes (Process Alive, prevents cascading restart loops) ────────

@app.get("/livez", tags=["Health"], include_in_schema=False)
@app.get("/v1/health/live", tags=["Health"], include_in_schema=False)
async def liveness():
    return JSONResponse(
        status_code=200,
        content={"status": "alive"},
    )


# ── Root & Liveness Probes (Zero-DB Ping for Render / AWS / UptimeRobot) ─────

@app.get("/", tags=["Health"], include_in_schema=False)
async def root():
    return {
        "status": "online",
        "service": "jainune-api",
        "version": "2.0.0",
        "health": "/health",
    }


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check():
    """
    Lightweight keep-alive endpoint for UptimeRobot daemon.
    Zero DB queries, zero Redis calls. Responds in <5ms.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "online",
            "service": "jainune-api",
            "version": "2.0.0",
        },
    )


# ── Health (Deep Connectivity Check / Readiness) ────────────────────────────

@app.get("/v1/health", tags=["Health"])
@app.get("/readyz", tags=["Health"], include_in_schema=False)
async def health(
    x_metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
):
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
    status_str = "healthy" if is_healthy else "degraded"

    expected = getattr(settings, "metrics_secret_token", "") or (getattr(settings, "secret_key", "") if hasattr(settings, "secret_key") else "")
    has_token = bool(expected and x_metrics_token and hmac.compare_digest(x_metrics_token, expected))

    if has_token:
        content = {
            "status": status_str,
            "version": settings.app_version,
            "checks": {
                "database": "connected" if db_ok else "disconnected",
                "redis": "connected" if redis_ok else "disconnected",
            },
        }
    else:
        content = {"status": status_str}

    return JSONResponse(
        status_code=200 if is_healthy else 503,
        content=content,
    )


# ── Prometheus Metrics Exposition ────────────────────────────────────────────

@app.get("/metrics", include_in_schema=False)
async def get_metrics(
    request: Request,
    x_metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
):
    if settings.environment == "production":
        expected = getattr(settings, "metrics_secret_token", "") or settings.secret_key if hasattr(settings, "secret_key") else getattr(settings, "metrics_secret_token", "")
        if not expected or not x_metrics_token or not hmac.compare_digest(x_metrics_token, expected):
            raise HTTPException(status_code=403, detail="Forbidden")

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
app.include_router(subscriptions.payments_router)
app.include_router(arcade.router)
app.include_router(admin.router)
app.include_router(location.router)
app.include_router(legal.router)

