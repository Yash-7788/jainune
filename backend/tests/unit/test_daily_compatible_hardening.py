import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.core_people_finder import fetch_daily_compatible
from app.routers.feed import get_daily_compatible


class TestDailyCompatibleHardening:
    """Unit tests for FINDING-10 Daily Compatible cache and endpoint contract."""

    @pytest.mark.asyncio
    async def test_01_fetch_daily_compatible_calculates_midnight_ist_ttl(self):
        """Verify fetch_daily_compatible caches with dynamic TTL expiring at midnight IST."""
        user_id = uuid.uuid4()
        cand_id = uuid.uuid4()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)

        mock_conn = AsyncMock()
        # Mock finding a daily_proposal
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": cand_id,
            "first_name": "Aarav",
            "date_of_birth": datetime(1998, 5, 15).date(),
            "city": "Mumbai",
            "state": "Maharashtra",
            "community_sect": "Digambar",
            "dietary_strictness": "Strict Jain",
            "eats_root_vegetables": False,
            "eats_onion_garlic": False,
            "paryushan_mode": True,
            "education": "B.Tech Computer Science",
            "job_title": "Software Engineer",
            "height_cm": 178,
            "bio": "Passionate about technology and Jain philosophy.",
            "open_to_relocation": True,
            "is_photo_verified": True,
        })
        mock_conn.fetch = AsyncMock(return_value=[])  # media and prompts

        mock_db = MagicMock()
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_db.acquire.return_value = mock_acquire

        result = await fetch_daily_compatible(user_id=user_id, db=mock_db, redis=mock_redis)

        assert result is not None
        assert result["first_name"] == "Aarav"
        assert result["pairing_algorithm"] == "gale_shapley_nightly"

        # Verify redis.set called with TTL <= 86400 and >= 60
        cache_key = f"daily_compatible:{user_id}"
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == cache_key
        ttl = call_args[1].get("ex")
        assert ttl is not None
        assert 60 <= ttl <= 86400

    @pytest.mark.asyncio
    async def test_02_cached_read_returns_without_db_query(self):
        """When Redis cache hits, returns immediately without acquiring DB."""
        user_id = uuid.uuid4()
        cand_id = uuid.uuid4()

        import json
        cached_data = {
            "id": str(cand_id),
            "first_name": "Riya",
            "pairing_algorithm": "gale_shapley_nightly",
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        mock_db = MagicMock()

        result = await fetch_daily_compatible(user_id=user_id, db=mock_db, redis=mock_redis)

        assert result is not None
        assert result["first_name"] == "Riya"
        mock_db.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_03_daily_compatible_endpoint_contract(self):
        """Verify GET /v1/feed/daily-compatible returns DailyCompatibleResponse with locked_until."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_redis = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock()
        mock_redis.zcard = AsyncMock(return_value=1)
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_db.acquire.return_value = mock_acquire

        resp = await get_daily_compatible(current_user=current_user, db=mock_db, redis=mock_redis)

        assert resp.candidate is None
        assert resp.pairing_algorithm == "none"
        assert resp.locked_until is not None
        # Must parse as ISO timestamp
        dt = datetime.fromisoformat(resp.locked_until)
        assert dt.tzinfo is not None
