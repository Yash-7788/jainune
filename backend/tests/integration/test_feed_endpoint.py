"""
Integration tests for BRRE Feed & Daily Compatible endpoints:
- Cache hits (L4 session cache sub-1ms)
- Cache misses & DB fallback
- Cache bypass via ?refresh=true
- Daily Compatible matching and IST lock computation
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_feed_unauthenticated(client: AsyncClient):
    """GET /v1/feed without credentials must return 401 or 403."""
    resp = await client.get("/v1/feed")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_feed_cache_hit(authed_client, fake_redis, mock_pool):
    """If candidates are pre-cached in Redis, return from cache."""
    client, user_id = authed_client
    pool, conn = mock_pool

    # DB extra query mock
    conn.fetchrow.return_value = {
        "location": None,
        "revealed_preference_vector": None,
    }

    # Pre-seed Redis feed cache
    candidate_id = str(uuid.uuid4())
    cached_candidates = [
        {
            "id": candidate_id,
            "first_name": "Pooja",
            "city": "Ahmedabad",
            "state": "Gujarat",
            "distance_display": "Under 2 km away",
            "dietary_strictness": "pure_jain",
            "eats_root_vegetables": False,
            "eats_onion_garlic": False,
            "community_sect": "shwetambar_murtipujak",
            "paryushan_mode": True,
            "is_photo_verified": True,
            "photos": [],
            "prompts": [],
        }
    ]
    await fake_redis.set(f"feed:cache:{user_id}", json.dumps(cached_candidates))

    resp = await client.get("/v1/feed?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_cache"] is True
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["first_name"] == "Pooja"


@pytest.mark.asyncio
async def test_feed_cache_bypass(authed_client, fake_redis, mock_pool):
    """refresh=true parameter forces bypass of Redis cache."""
    client, user_id = authed_client
    pool, conn = mock_pool

    conn.fetchrow.return_value = {
        "location": None,
        "revealed_preference_vector": None,
    }
    # Mock candidate pipeline return empty list from DB
    conn.fetch.return_value = []

    # Pre-seed Redis cache
    await fake_redis.set(f"feed:cache:{user_id}", json.dumps([{"id": str(uuid.uuid4()), "first_name": "Cached"}]))

    resp = await client.get("/v1/feed?refresh=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_cache"] is False


@pytest.mark.asyncio
async def test_daily_compatible_cached(authed_client, fake_redis, mock_pool):
    """Pre-computed Daily Compatible pairing returned with IST locked_until."""
    client, user_id = authed_client

    pair_id = str(uuid.uuid4())
    pairing = {
        "id": pair_id,
        "first_name": "Aarav",
        "city": "Mumbai",
        "state": "Maharashtra",
        "community_sect": "shwetambar_murtipujak",
        "dietary_strictness": "pure_jain",
        "compatibility_rationale": "High reciprocal dietary and sect alignment.",
        "pairing_algorithm": "gale_shapley",
    }
    await fake_redis.set(f"daily_compatible:{user_id}", json.dumps(pairing))

    resp = await client.get("/v1/feed/daily-compatible")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pairing_algorithm"] == "gale_shapley"
    assert data["candidate"]["id"] == pair_id
    assert "locked_until" in data
    assert data["locked_until"] is not None


@pytest.mark.asyncio
async def test_daily_compatible_fallback_when_empty(authed_client, fake_redis, mock_pool):
    """When nightly job has not run and DB returns no candidates, candidate is None."""
    client, user_id = authed_client
    pool, conn = mock_pool

    # No Redis cache and no DB match
    conn.fetchrow.return_value = None

    resp = await client.get("/v1/feed/daily-compatible")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate"] is None
    assert data["pairing_algorithm"] == "none"
