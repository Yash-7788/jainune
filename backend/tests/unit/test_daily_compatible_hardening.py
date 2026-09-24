import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
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
    async def test_02_cached_read_revalidates_current_candidate_visibility(self):
        """A cached daily candidate is returned only if it remains eligible in the database."""
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
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": cand_id}])
        mock_db = MagicMock()
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_db.acquire.return_value = mock_acquire

        result = await fetch_daily_compatible(user_id=user_id, db=mock_db, redis=mock_redis)

        assert result is not None
        assert result["first_name"] == "Riya"
        mock_conn.fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_02b_cached_read_discards_candidate_who_is_no_longer_eligible(self):
        """A cached candidate is purged when deletion, pause, blocks, or swipes invalidate it."""
        user_id = uuid.uuid4()
        cand_id = uuid.uuid4()
        cached_data = {"id": str(cand_id), "first_name": "Riya"}

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        mock_redis.delete = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_db = MagicMock()
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_db.acquire.return_value = mock_acquire

        result = await fetch_daily_compatible(user_id=user_id, db=mock_db, redis=mock_redis)

        assert result is None
        mock_redis.delete.assert_awaited_once_with(f"daily_compatible:{user_id}")

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

    @pytest.mark.asyncio
    async def test_04_feed_cache_purges_corrupted_string_list_and_falls_back(self):
        """Corrupted feed:cache containing raw ID strings is detected and purged without 500 crash."""
        from app.services.core_people_finder import _get_cached_feed, fetch_recommended_feed

        user_id = uuid.uuid4()
        mock_redis = AsyncMock()

        # 1. Corrupted cache contains list of strings instead of dicts
        mock_redis.get = AsyncMock(return_value=json.dumps(["uuid-1", "uuid-2"]))
        mock_redis.delete = AsyncMock()

        cached = await _get_cached_feed(user_id, mock_redis)
        assert cached is None
        mock_redis.delete.assert_called_once_with(f"feed:cache:{user_id}")

        # 2. fetch_recommended_feed with corrupted eval result purges key and falls through
        mock_redis.reset_mock()
        mock_redis.eval = AsyncMock(return_value=json.dumps(["uuid-1", "uuid-2"]))
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.pipeline = MagicMock(return_value=AsyncMock())

        with patch("app.services.core_people_finder._run_pipeline", AsyncMock(return_value=[])):
            result = await fetch_recommended_feed(
                user_id=user_id,
                user_data={},
                db=MagicMock(),
                redis=mock_redis,
                limit=10,
                force_refresh=False,
            )
            assert result["from_cache"] is False
            assert result["candidates"] == []
            mock_redis.delete.assert_called_with(f"feed:cache:{user_id}")

    @pytest.mark.asyncio
    async def test_05_daily_compatible_worker_writes_to_feed_queue_not_feed_cache(self):
        """Worker persists candidate IDs to feed_queue:{uid}, strictly keeping feed:cache:{uid} pristine."""
        from app.workers.daily_compatible import _run_async

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.eval = AsyncMock(return_value=1)
        mock_pipe = MagicMock()
        recorded_keys = []

        def record_set(key, *args, **kwargs):
            recorded_keys.append(key)

        mock_pipe.set = MagicMock(side_effect=record_set)
        mock_pipe.execute = AsyncMock(return_value=[])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.aclose = AsyncMock()

        mock_conn = AsyncMock()
        user_id = uuid.uuid4()
        users_sample = [{"id": user_id, "gender": "men", "city": "Mumbai", "show_me": "women"}]

        mock_conn.fetch = AsyncMock(return_value=users_sample)
        mock_conn.executemany = AsyncMock(return_value=None)
        mock_conn.close = AsyncMock()

        with patch("app.workers.daily_compatible._get_redis", AsyncMock(return_value=mock_redis)), \
             patch("app.workers.daily_compatible._get_conn", AsyncMock(return_value=mock_conn)), \
             patch("app.services.core_people_finder.CorePeopleFinder.rank_candidates", AsyncMock(return_value=[])):
            await _run_async()

        # Must write to feed_queue:{uid}, NEVER to feed:cache:{uid}
        assert any(f"feed_queue:{user_id}" in k for k in recorded_keys)
        assert not any("feed:cache:" in k for k in recorded_keys)
