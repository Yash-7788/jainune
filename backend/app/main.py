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
    - Reaper tasks ported from ephemeral_reaper (formerly dead Celery tasks): storage purge,
      DPDP-compliant user hard-delete, stale payment intent cleanup.
    """
    from datetime import datetime, timezone, timedelta
    from app.core.database import get_pool

    _mlog = logging.getLogger("app.maintenance")
    _IST = timezone(timedelta(hours=5, minutes=30))

    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            pool = get_pool()
            needs_daily_batch = False
            async with pool.acquire() as conn:
                # 1. Downgrade expired subscriptions (BUG-006 fix: subscription_valid_until)
                # BUG-008 fix: also reset super_connect_credits=0 and NULL out valid_until
                await conn.execute("""
                    UPDATE users
                       SET subscription_tier       = 'free',
                           subscription_valid_until = NULL,
                           super_connect_credits    = 0,
                           updated_at               = NOW()
                     WHERE subscription_valid_until IS NOT NULL
                       AND subscription_valid_until < NOW()
                       AND subscription_tier != 'free'
                """)
                await conn.execute("""
                    UPDATE store_subscriptions
                       SET status = 'expired'
                     WHERE expires_at IS NOT NULL
                       AND expires_at < NOW()
                       AND status = 'active'
                """)

                # 2. Reap stale matches (BUG-006 fix: correct column COALESCE + valid status set)
                # Original had nonexistent matches.expires_at and invalid status 'pending'
                expired_match_rows = await conn.fetch("""
                    UPDATE matches
                       SET status     = 'expired',
                           expired_at = NOW()
                     WHERE status IN ('active', 'matched')
                       AND COALESCE(last_message_at, created_at) < NOW() - INTERVAL '7 days'
                     RETURNING id
                """)
                if expired_match_rows:
                    exp_ids = [r["id"] for r in expired_match_rows]
                    await conn.execute(
                        "UPDATE chats SET is_unmatched = TRUE, updated_at = NOW() WHERE match_id = ANY($1::uuid[])",
                        exp_ids,
                    )
                    _mlog.info("maintenance: expired %d stale matches", len(expired_match_rows))

                # 3. Mark stranded processing/pending media as rejected (>30 min timeout)
                await conn.execute("""
                    UPDATE user_media
                       SET status = 'rejected', rejection_reason = 'PROCESSING_TIMEOUT'
                     WHERE status IN ('processing', 'pending')
                       AND created_at < NOW() - INTERVAL '30 minutes'
                """)

                # 4. Expire stale payment intents (>24h uncaptured)
                await conn.execute("""
                    UPDATE payment_intents
                       SET status = 'expired', updated_at = NOW()
                     WHERE status = 'created'
                       AND created_at < NOW() - INTERVAL '24 hours'
                """)

                # 4b. Purge physically expired revoked_refresh_tokens rows (unbounded growth prevention)
                # Rows are logically expired past expires_at but never deleted without this cleanup.
                await conn.execute(
                    "DELETE FROM revoked_refresh_tokens WHERE expires_at < NOW()"
                )

                # 5. Off-peak daily heavy maintenance (at or after 3:30 AM IST = 22:00 UTC of previous day; IST is UTC+5:30)
                # Slashes maintenance DB IOPS on Supabase by running heavy table scans once daily.
                # Uses atomic DB lease (INSERT ON CONFLICT RETURNING) on system_maintenance_runs for multi-instance safety.
                now_ist = datetime.now(_IST)
                is_time_for_daily = (now_ist.hour > 3) or (now_ist.hour == 3 and now_ist.minute >= 30)

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_maintenance_runs (
                        task_name VARCHAR(64) PRIMARY KEY,
                        last_run_at TIMESTAMPTZ NOT NULL,
                        run_date_ist DATE NOT NULL,
                        locked_until TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01'::timestamptz
                    )
                """)

                if is_time_for_daily:
                    # Atomic DB lease claim: safe across Supavisor port 6543 transaction pooling mode
                    claimed = await conn.fetchval("""
                        INSERT INTO system_maintenance_runs (task_name, last_run_at, run_date_ist, locked_until)
                        VALUES ('daily_cleanup', NOW(), '1970-01-01'::date, NOW() + INTERVAL '15 minutes')
                        ON CONFLICT (task_name) DO UPDATE
                        SET locked_until = NOW() + INTERVAL '15 minutes'
                        WHERE system_maintenance_runs.run_date_ist < $1
                          AND system_maintenance_runs.locked_until < NOW()
                        RETURNING task_name
                    """, now_ist.date())

                    if claimed:
                        try:
                            _mlog.info("maintenance: claimed atomic daily maintenance lease for %s", now_ist.date())

                            # Daily 500 MB Auto-Prune Engine (interactions, admin_audit_log, telemetry_events, chat messages)
                            await conn.execute("""
                                DELETE FROM interactions
                                 WHERE action_type = 'pass'
                                   AND created_at < NOW() - INTERVAL '45 days'
                            """)
                            await conn.execute("""
                                DELETE FROM admin_audit_log
                                 WHERE created_at < NOW() - INTERVAL '90 days'
                            """)
                            await conn.execute("""
                                DELETE FROM telemetry_events
                                 WHERE occurred_at < NOW() - INTERVAL '30 days'
                            """)
                            # Prune chat messages beyond latest 100 per chat thread (500 MB limit defense)
                            await conn.execute("""
                                DELETE FROM messages
                                 WHERE id IN (
                                     SELECT id FROM (
                                         SELECT id, ROW_NUMBER() OVER (
                                             PARTITION BY chat_id
                                             ORDER BY created_at DESC, id DESC
                                         ) as rn
                                         FROM messages
                                     ) ranked
                                     WHERE ranked.rn > 100
                                 )
                            """)

                            # DPDP-compliant hard-delete of users soft-deleted >30 days ago
                            dpdp_rows = await conn.fetch("""
                                SELECT id FROM users
                                 WHERE account_status = 'deleted'
                                   AND deleted_at < NOW() - INTERVAL '30 days'
                                   AND (subscription_tier = 'free'
                                        OR subscription_valid_until IS NULL
                                        OR subscription_valid_until < NOW())
                                 LIMIT 100
                            """)
                            if dpdp_rows:
                                dpdp_ids = [r["id"] for r in dpdp_rows]
                                await conn.execute(
                                    "DELETE FROM users WHERE id = ANY($1::uuid[])",
                                    dpdp_ids,
                                )
                                _mlog.info("maintenance: DPDP hard-deleted %d users", len(dpdp_ids))

                            # Purge stale location waitlist entries >90 days
                            try:
                                await conn.execute("""
                                    DELETE FROM location_waitlist
                                     WHERE created_at < NOW() - INTERVAL '90 days'
                                """)
                            except Exception as exc:
                                _mlog.warning("maintenance: location_waitlist purge failed: %s", exc)

                            # Purge rejected/pending user_media objects from Supabase Storage
                            purge_rows = await conn.fetch("""
                                SELECT id, s3_key FROM user_media
                                 WHERE status IN ('rejected', 'pending')
                                   AND created_at < NOW() - INTERVAL '1 hour'
                                   AND s3_purged = FALSE
                                 LIMIT 200
                            """)
                            if purge_rows:
                                keys_to_delete = [r["s3_key"] for r in purge_rows if r.get("s3_key")]
                                purged_ids = []
                                if keys_to_delete:
                                    try:
                                        from app.services.media_processor import _get_supabase
                                        from app.core.config import settings as _cfg
                                        client = _get_supabase()
                                        await asyncio.to_thread(
                                            client.storage.from_(_cfg.supabase_storage_bucket).remove,
                                            keys_to_delete,
                                        )
                                        purged_ids = [r["id"] for r in purge_rows if r.get("s3_key") in keys_to_delete]
                                    except Exception as exc:
                                        _mlog.warning("maintenance: Supabase storage purge failed: %s", exc)
                                # Mark rows with no s3_key as purged too
                                purged_ids += [r["id"] for r in purge_rows if not r.get("s3_key")]
                                if purged_ids:
                                    await conn.execute(
                                        "UPDATE user_media SET s3_purged = TRUE WHERE id = ANY($1::uuid[])",
                                        purged_ids,
                                    )
                                _mlog.info("maintenance: storage purge attempted %d media rows", len(purge_rows))

                            # Record run completion, set run_date_ist, release lease
                            await conn.execute("""
                                UPDATE system_maintenance_runs
                                   SET last_run_at = NOW(),
                                       run_date_ist = $1,
                                       locked_until = '1970-01-01'::timestamptz
                                 WHERE task_name = 'daily_cleanup'
                            """, now_ist.date())
                            _mlog.info("maintenance: daily heavy cleanup completed and recorded for %s", now_ist.date())
                        except Exception as exc:
                            _mlog.error("maintenance: daily heavy cleanup failed: %s", exc)
                            await conn.execute("""
                                UPDATE system_maintenance_runs
                                   SET locked_until = '1970-01-01'::timestamptz
                                 WHERE task_name = 'daily_cleanup'
                            """)

                # 6. Check if today's Gale-Shapley matching batch has executed
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                latest_run = await conn.fetchval("SELECT MAX(generated_at) FROM feed_queues")
                needs_daily_batch = (latest_run is None) or (latest_run < today_start)

            if needs_daily_batch:
                _mlog.info("Executing daily Gale-Shapley matching pipeline...")
                from app.workers.daily_compatible import run_daily_compatible_async
                await run_daily_compatible_async()

            # 7. Flush in-process impression buffer
            from app.services.core_people_finder import _async_flush_impressions
            await _async_flush_impressions(pool, force=True)

            # 8. Flush in-process telemetry event buffer + dwell vector queue
            from app.routers.telemetry import _async_flush_telemetry
            await _async_flush_telemetry(pool)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logging.getLogger("app.maintenance").warning("Periodic maintenance cycle encountered error: %s", exc)



async def _supabase_keepalive_worker() -> None:
    """
    Fires SELECT 1 every 24 hours to prevent Supabase free-tier 7-day auto-pause.
    Zero Render CPU cost — sleeps 23 hours between pings.
    """
    from app.core.database import get_pool
    _klog = logging.getLogger("app.keepalive")
    while True:
        try:
            await asyncio.sleep(82800)  # 23h — stays within free-tier idle window
            pool = get_pool()
            if pool:
                async with pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                _klog.info("Supabase 24h keepalive dispatched.")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            _klog.warning("Supabase keepalive failed: %s", exc)


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
    k_task = asyncio.create_task(_supabase_keepalive_worker(), name="supabase_keepalive")
    yield
    # Shutdown
    m_task.cancel()
    k_task.cancel()
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
        "X-Edge-Secret",
        "X-Origin-Secret",
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
    req_path = getattr(getattr(request, "url", None), "path", "")
    checkout_page = req_path == "/v1/payments/razorpay/checkout"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), "
        + ('payment=(self "https://checkout.razorpay.com")' if checkout_page else "payment=()")
        + ", usb=()"
    )
    if isinstance(req_path, str) and (req_path.startswith("/v1/") or req_path.startswith("/api/")):
        response.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, private")
        response.headers.setdefault("Pragma", "no-cache")

    if checkout_page and "Content-Security-Policy" in response.headers:
        pass  # Checkout uses a per-response nonce for its payment script.
    elif isinstance(req_path, str) and (
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

    expected = getattr(settings, "metrics_secret_token", "")
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
    if settings.environment.lower() == "production":
        expected = getattr(settings, "metrics_secret_token", "")
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

# Added last so the gate runs before application middleware and route handlers.
# Deployment enables it only after the Worker and all callback URLs are tested.
from app.core.edge_origin import EdgeOriginGate  # noqa: E402
from app.core.payment_body_limit import StoreWebhookBodyLimit  # noqa: E402

app.add_middleware(StoreWebhookBodyLimit)
app.add_middleware(EdgeOriginGate)
