"""
Test suite conftest — shared fixtures for unit and integration tests.

Strategy:
  Unit tests   → no real DB/Redis; use MagicMock / fakeredis
  Integration  → real asyncpg + real Redis via docker-compose test services
                 (TEST_DATABASE_URL and TEST_REDIS_URL env vars)

JWT signing for tests uses an in-memory RSA key pair generated once per session.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

if "celery" not in sys.modules:
    celery_mock = MagicMock()
    class MockCelery:
        def __init__(self, *args, **kwargs):
            self.conf = MagicMock()
        def task(self, *args, **kwargs):
            def decorator(fn):
                fn.delay = MagicMock()
                fn.apply_async = MagicMock()
                return fn
            if len(args) == 1 and callable(args[0]):
                return decorator(args[0])
            return decorator
    celery_mock.Celery = MockCelery
    sys.modules["celery"] = celery_mock
    sys.modules["celery.schedules"] = MagicMock()

if "boto3" not in sys.modules:
    sys.modules["boto3"] = MagicMock()
    sys.modules["botocore"] = MagicMock()
    sys.modules["botocore.exceptions"] = MagicMock()

import jwt
import pytest
import pytest_asyncio
import redis
import redis.asyncio
import fakeredis
import fakeredis.aioredis as fakeredis_async
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# RSA key pair — generated once per test session (fast, ~10ms)
# ---------------------------------------------------------------------------

_RSA_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_RSA_PUBLIC = _RSA_PRIVATE.public_key()

_RSA_PRIVATE_PEM = _RSA_PRIVATE.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
)
_RSA_PUBLIC_PEM = _RSA_PUBLIC.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)


@pytest.fixture(scope="session")
def rsa_keys():
    return {"private": _RSA_PRIVATE_PEM, "public": _RSA_PUBLIC_PEM}


# ---------------------------------------------------------------------------
# JWT token helper
# ---------------------------------------------------------------------------

def make_token(
    user_id: str | None = None,
    expired: bool = False,
    private_key: bytes = _RSA_PRIVATE_PEM,
) -> str:
    uid = user_id or str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    if expired:
        exp = now - timedelta(minutes=5)
    else:
        exp = now + timedelta(minutes=15)

    payload = {
        "sub": uid,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": exp,
        "iss": "jainune-api",
        "aud": "jainune-client",
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
def valid_token(rsa_keys) -> str:
    return make_token(private_key=rsa_keys["private"])


@pytest.fixture
def expired_token(rsa_keys) -> str:
    return make_token(expired=True, private_key=rsa_keys["private"])


# ---------------------------------------------------------------------------
# Patch RSA key loading in security.py before app import
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def patch_rsa_keys(rsa_keys):
    """
    security.py loads keys at import time from disk paths.
    Patch those module-level bytes with our in-memory test keys.
    """
    with (
        patch("app.core.security._RSA_PRIVATE_KEY", rsa_keys["private"]),
        patch("app.core.security._RSA_PUBLIC_KEY", rsa_keys["public"]),
    ):
        yield


# ---------------------------------------------------------------------------
# Mock DB pool fixture (unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pool():
    """AsyncMock pool — conn.fetchrow / fetchval / execute all return None by default."""
    pool = MagicMock()
    conn = AsyncMock()
    del conn.acquire
    conn.fetchrow.return_value = None
    conn.fetchval.return_value = None
    conn.fetch.return_value = []
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return pool, conn


# ---------------------------------------------------------------------------
# fakeredis fixture (unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture
async def fake_redis():
    import fakeredis.aioredis as fakeredis_async
    r = fakeredis_async.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ---------------------------------------------------------------------------
# FastAPI test client — patches DB and Redis with mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def app(mock_pool, fake_redis):
    """
    Returns FastAPI app instance with DB pool and Redis replaced by mocks.
    Used for unit-level router tests that don't need a real DB.
    """
    pool, _conn = mock_pool

    import app.core.database as db_mod
    import app.core.redis as redis_mod
    db_mod._pool = pool
    redis_mod._redis = fake_redis

    with (
        patch("app.core.database.create_pool", new_callable=AsyncMock),
        patch("app.core.database.close_pool", new_callable=AsyncMock),
        patch("app.core.redis.create_redis", new_callable=AsyncMock),
        patch("app.core.redis.close_redis", new_callable=AsyncMock),
    ):
        from app.main import app as fastapi_app
        yield fastapi_app
        fastapi_app.dependency_overrides.clear()
        db_mod._pool = None
        redis_mod._redis = None


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth override — bypass JWT for router tests that just want to test logic
# ---------------------------------------------------------------------------

@pytest.fixture
def authed_client(client, app):
    """
    Client where get_current_user is overridden to return a fixed test user.
    Use for router tests that don't care about auth mechanics.
    """
    from app.core.security import get_current_user as sec_get_current_user
    from app.dependencies import get_current_user as dep_get_current_user

    test_user_id = str(uuid.uuid4())
    uid_obj = uuid.UUID(test_user_id)

    class AuthUser(dict):
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError:
                raise AttributeError(key)

    async def _fake_user():
        return AuthUser({
            "user_id": uid_obj,
            "id": uid_obj,
            "first_name": "Test",
            "phone_number": "+919876543210",
            "account_status": "active",
            "subscription_tier": "free",
            "gender": "man",
            "show_me": "women",
            "is_photo_verified": False,
            "dietary_strictness": "pure_jain",
            "eats_root_vegetables": False,
            "eats_onion_garlic": False,
            "community_sect": "shwetambar_murtipujak",
            "city": "Mumbai",
            "state": "Maharashtra",
            "max_distance_km": 30,
            "open_to_relocation": False,
            "paryushan_mode": True,
        })

    app.dependency_overrides[sec_get_current_user] = _fake_user
    app.dependency_overrides[dep_get_current_user] = _fake_user
    yield client, test_user_id
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: seed a user row in mock_conn
# ---------------------------------------------------------------------------

def fake_user_row(overrides: dict | None = None) -> dict:
    base = {
        "id": uuid.uuid4(),
        "phone_number": "+919876543210",
        "first_name": "Rahul",
        "date_of_birth": None,
        "gender": "man",
        "show_me": "women",
        "looking_for": "marriage",
        "city": "Mumbai",
        "state": "Maharashtra",
        "max_distance_km": 30,
        "open_to_relocation": False,
        "dietary_strictness": "pure_jain",
        "eats_root_vegetables": False,
        "eats_onion_garlic": False,
        "community_sect": "shwetambar_murtipujak",
        "paryushan_mode": True,
        "job_title": "Software Engineer",
        "company": "TCS",
        "education": "B.Tech",
        "height_cm": 175,
        "bio": "Test bio",
        "subscription_tier": "free",
        "is_photo_verified": False,
        "account_status": "active",
        "trust_score": 50,
    }
    if overrides:
        base.update(overrides)
    return base
