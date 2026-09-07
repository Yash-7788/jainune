"""
Unit tests for Final Deep Audits:
- Onboarding Step 22 idempotency (network retry lockout prevention)
- Serendipity Arcade wheel paid spin credit preservation on 0 candidates
- Dilemma vote concurrency & atomic counter protection
- WebSocket connection rate limit & resilient frame parsing
- Media processor and ephemeral reaper cloud client fail-safes
"""

import asyncio
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


def _create_mock_conn():
    mock_conn = AsyncMock()
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    return mock_conn


class TestDeepAuditFinalHardening(unittest.IsolatedAsyncioTestCase):

    async def test_01_step22_idempotency_returns_success_when_already_completed(self):
        """Step 22 must return completed status if already completed, not HTTP 409."""
        from app.routers.onboarding import step22_complete
        from app.models.schemas.user import Step22CompleteBody

        user_id = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        # DB returns user who already has onboarding_completed = TRUE
        mock_conn = _create_mock_conn()
        mock_conn.fetchrow.return_value = {
            "onboarding_completed": True,
            "onboarding_step": 22,
            "first_name": "Test",
            "date_of_birth": "1995-01-01",
            "gender": "man",
            "show_me": "women",
            "looking_for": "marriage",
            "dietary_strictness": "pure_jain",
            "community_sect": "shwetambar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "location": "POINT(77.5946 12.9716)",
        }

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn

        mock_redis = AsyncMock()

        with patch("app.routers.onboarding.sliding_window_rate_limit", new_callable=AsyncMock):
            res = await step22_complete(
                body=Step22CompleteBody(confirmed=True),
                current_user=mock_user,
                db=mock_db,
                redis=mock_redis,
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["current_step"], 22)
        self.assertTrue(res["data"]["completed"])

    async def test_02_arcade_spin_refunds_credit_when_no_candidate_available(self):
        """If serendipity wheel spin finds 0 candidates, spin credit is preserved."""
        from app.routers.arcade import spin_serendipity_wheel

        user_id = uuid.uuid4()
        current_user = {
            "user_id": user_id,
            "id": user_id,
            "show_me": "women",
        }

        mock_conn = _create_mock_conn()
        # Atomic deduction returned remaining = 2
        mock_conn.fetchval.return_value = 2
        # Candidate search returned None (no one online matching criteria)
        mock_conn.fetchrow.return_value = None

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_redis = AsyncMock()

        with patch("app.routers.arcade.sliding_window_rate_limit", new_callable=AsyncMock):
            res = await spin_serendipity_wheel(
                current_user=current_user,
                pool=mock_pool,
                redis=mock_redis,
            )

        self.assertFalse(res["success"])
        self.assertEqual(res["remaining_spins"], 3)  # 2 + 1 refunded
        self.assertIsNone(res["chat_id"])
        self.assertIn("preserved", res["message"].lower())

        # Verify update to increment available_spins and insert refund record
        calls = [c[0][0] for c in mock_conn.execute.call_args_list]
        self.assertTrue(any("available_spins = available_spins + 1" in c for c in calls))
        self.assertTrue(any("refund_spin_no_candidate" in c for c in calls))

    async def test_03_arcade_spin_creates_match_and_chat_when_candidate_found(self):
        """Candidate match successfully links 15-minute speed chat."""
        from app.routers.arcade import spin_serendipity_wheel

        user_id = uuid.uuid4()
        cand_id = uuid.uuid4()
        current_user = {
            "user_id": user_id,
            "id": user_id,
            "show_me": "women",
        }

        mock_conn = _create_mock_conn()
        mock_conn.fetchval.return_value = 4  # remaining spins
        mock_conn.fetchrow.side_effect = [
            {"id": cand_id, "first_name": "Pooja", "city": "Mumbai"},  # candidate
            {"id": uuid.uuid4()},  # match_row
            {"id": uuid.uuid4()},  # chat_row
        ]

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_redis = AsyncMock()

        with patch("app.routers.arcade.sliding_window_rate_limit", new_callable=AsyncMock):
            res = await spin_serendipity_wheel(
                current_user=current_user,
                pool=mock_pool,
                redis=mock_redis,
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["remaining_spins"], 4)
        self.assertIsNotNone(res["chat_id"])
        self.assertEqual(res["paired_user"]["first_name"], "Pooja")

    async def test_04_dilemma_vote_prevents_duplicate_vote_races(self):
        """Concurrent vote with ON CONFLICT returns already_voted without double-counting."""
        from app.routers.arcade import vote_on_dilemma, VoteBody

        user_id = uuid.uuid4()
        dilemma_id = uuid.uuid4()
        current_user = {"user_id": user_id}

        mock_conn = _create_mock_conn()
        mock_conn.fetchval.side_effect = [
            dilemma_id,  # exists
            None,        # existing
            None,        # inserted (conflict occurred)
            "A",         # actual choice recorded by other thread
        ]

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_redis = AsyncMock()

        with patch("app.routers.arcade.sliding_window_rate_limit", new_callable=AsyncMock):
            res = await vote_on_dilemma(
                dilemma_id=dilemma_id,
                body=VoteBody(choice="A"),
                current_user=current_user,
                pool=mock_pool,
                redis=mock_redis,
            )

        self.assertTrue(res.get("already_voted"))
        self.assertEqual(res.get("choice"), "A")

    async def test_05_media_processor_safe_fallbacks(self):
        """Media processor helper checks return safe pass when boto3 credentials are mock."""
        from app.services.media_processor import _check_s3_size, _rekognition_check

        with patch("app.services.media_processor.settings.aws_access_key_id", "mock_key"):
            size_ok, size_err = _check_s3_size("uploads/test.jpg", "photo")
            self.assertTrue(size_ok)
            self.assertIsNone(size_err)

            mod_ok, mod_err = _rekognition_check("uploads/test.jpg")
            self.assertTrue(mod_ok)
            self.assertIsNone(mod_err)

    async def test_06_ephemeral_reaper_s3_client_fallback(self):
        """Ephemeral reaper safely returns None client when credentials are mock."""
        from app.workers.ephemeral_reaper import _s3_client

        with patch("app.workers.ephemeral_reaper.settings.aws_access_key_id", "mock_access_key"):
            client = _s3_client()
            self.assertIsNone(client)


if __name__ == "__main__":
    unittest.main()
