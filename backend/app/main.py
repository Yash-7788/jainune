from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import close_pool, create_pool
from app.core.redis import close_redis, create_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Idempotency-Key"],
)


# ── Standard response envelope helpers ───────────────────────────────────────

def ok(data: dict | list, meta: dict | None = None) -> dict:
    import time, uuid
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": meta or {
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "request_id": f"req_{uuid.uuid4().hex[:16]}",
        },
    }


def err(code: str, message: str, details: list | None = None) -> dict:
    import uuid
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details or []},
        "meta": {
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "request_id": f"req_{uuid.uuid4().hex[:16]}",
        },
    }


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=err("INTERNAL_ERROR", "An unexpected error occurred."),
    )


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/v1/health", tags=["Health"])
async def health():
    return {"status": "healthy", "version": settings.app_version}


# ── Routers (registered after all imports to avoid circular deps) ─────────────
from app.routers import auth, onboarding, feed, interactions, telemetry  # noqa: E402
from app.routers import chats, websockets, media                          # noqa: E402
from app.routers import users, subscriptions, arcade, admin               # noqa: E402

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
