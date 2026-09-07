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

    async def test_07_delete_my_account_alias(self):
        """Account deletion endpoint works via delete_my_account."""
        from app.routers.users import delete_my_account

        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}

        mock_pool = MagicMock()
        mock_conn = _create_mock_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_redis = AsyncMock()

        with patch("app.services.account_service.purge_user_account", new_callable=AsyncMock) as mock_purge:
            mock_purge.return_value = {"status": "purged"}
            res = await delete_my_account(
                hard_delete=True,
                current_user=current_user,
                pool=mock_pool,
                redis=mock_redis,
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["status"], "purged")

    async def test_08_telemetry_event_ingestion(self):
        """Telemetry router accepts valid events and queues to redis."""
        from app.routers.telemetry import ingest_events, TelemetryBatch, TelemetryEvent

        user_id = uuid.uuid4()
        current_user = {"id": user_id}
        mock_db = MagicMock()
        mock_redis = AsyncMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=None)
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("app.routers.telemetry.sliding_window_rate_limit", new_callable=AsyncMock):
            batch = TelemetryBatch(events=[
                TelemetryEvent(
                    event_type="photo_swipe",
                    target_user_id=uuid.uuid4(),
                    duration_ms=1200,
                )
            ])
            res = await ingest_events(
                batch=batch,
                current_user=current_user,
                db=mock_db,
                redis=mock_redis,
            )
            self.assertEqual(res.accepted, 1)
            self.assertEqual(res.dropped, 0)

    async def test_09_purge_blocked_on_active_subscription_forces_soft_delete(self):
        """Users with active paid subscriptions cannot be hard-purged; falls back to soft-delete."""
        from app.services.account_service import purge_user_account
        from datetime import datetime, timezone, timedelta

        user_id = uuid.uuid4()
        mock_conn = _create_mock_conn()
        mock_conn.fetchrow.return_value = {
            "phone_number": "+919876543210",
            "email": "gold_user@jainune.com",
            "subscription_tier": "gold_monthly",
            "subscription_valid_until": datetime.now(timezone.utc) + timedelta(days=20),
        }
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_redis = AsyncMock()

        with patch("app.services.account_service.soft_delete_user_account", new_callable=AsyncMock) as mock_soft:
            mock_soft.return_value = {"status": "soft_deleted", "user_id": str(user_id)}
            res = await purge_user_account(user_id, mock_conn, mock_redis)
            mock_soft.assert_called_once_with(user_id, mock_conn, mock_redis)
            self.assertEqual(res["status"], "soft_deleted")

    async def test_10_financial_audit_logs_archived_during_purge(self):
        """Purging an account copies payment intents and arcade transactions into financial_audit_logs."""
        from app.services.account_service import purge_user_account

        user_id = uuid.uuid4()
        executed_queries = []

        mock_conn = _create_mock_conn()
        mock_conn.fetchrow.return_value = {
            "phone_number": "+919876543210",
            "email": "free_user@jainune.com",
            "subscription_tier": "free",
            "subscription_valid_until": None,
        }
        mock_conn.fetch.return_value = []

        async def fake_execute(query, *args):
            executed_queries.append(query)
            return "DELETE 1"

        mock_conn.execute.side_effect = fake_execute
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))

        res = await purge_user_account(user_id, mock_conn, mock_redis)
        self.assertEqual(res["status"], "purged")

        # Confirm financial_audit_logs insertion
        audit_queries = [q for q in executed_queries if "INSERT INTO financial_audit_logs" in q]
        self.assertEqual(len(audit_queries), 2, "Expected 2 financial archive queries (intents + arcade)")

    async def test_11_delete_my_account_defaults_to_soft_delete(self):
        """DELETE /v1/users/me defaults to soft_delete, preserving grace period & financial logs."""
        from app.routers.users import delete_my_account

        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}

        mock_pool = MagicMock()
        mock_conn = _create_mock_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_redis = AsyncMock()

        with patch("app.services.account_service.soft_delete_user_account", new_callable=AsyncMock) as mock_soft:
            mock_soft.return_value = {"status": "soft_deleted"}
            res = await delete_my_account(
                current_user=current_user,
                pool=mock_pool,
                redis=mock_redis,
            )
            mock_soft.assert_called_once_with(user_id, mock_conn, mock_redis)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["status"], "deactivated")
            self.assertIn("72 hours", res["data"]["message"])

    async def test_12_arcade_purchases_non_refundable_self_service(self):
        """Arcade spin/roll purchases cannot be refunded self-service (B-1)."""
        from app.routers.subscriptions import request_refund, RefundRequestBody

        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "user_id": user_id,
            "amount": 4900,
            "status": "captured",
            "razorpay_order_id": "order_arcade_1",
            "razorpay_payment_id": "pay_arcade_1",
            "plan_id": "arcade_3_pack",
        })
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        body = RefundRequestBody(razorpay_payment_id="pay_arcade_1")
        with self.assertRaises(HTTPException) as ctx:
            await request_refund(body=body, current_user=current_user, pool=mock_pool)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("non-refundable", ctx.exception.detail)

    async def test_13_refund_resolves_payment_id_from_order_input(self):
        """Passing order_* resolves to stored razorpay_payment_id to prevent gateway crash (B-2)."""
        from app.routers.subscriptions import request_refund, RefundRequestBody

        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            # intent by payment_id fails
            None,
            # intent by order_id succeeds
            {
                "user_id": user_id,
                "amount": 49900,
                "status": "captured",
                "razorpay_order_id": "order_stuck_123",
                "razorpay_payment_id": "pay_valid_456",
                "plan_id": "jainune_plus_monthly",
            },
            # user_row (unfulfilled: free and never had valid_until)
            {"subscription_tier": "free", "subscription_valid_until": None},
        ])
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        body = RefundRequestBody(razorpay_payment_id="order_stuck_123")
        with patch("app.services.payment_service.initiate_refund", new_callable=AsyncMock) as mock_init:
            mock_init.return_value = {"success": True, "refund_id": "rfnd_test"}
            res = await request_refund(body=body, current_user=current_user, pool=mock_pool)
            mock_init.assert_called_once_with(
                payment_id="pay_valid_456",
                amount_paise=49900,
                reason="user_cancellation",
                pool=mock_pool,
            )
            self.assertTrue(res["success"])

    async def test_14_partial_refund_preserves_subscription_tier(self):
        """Partial goodwill refunds mark intent partially_refunded without stripping user tier (B-3)."""
        from app.services.payment_service import process_refund

        user_id = uuid.uuid4()
        executed_sqls = []

        mock_conn = _create_mock_conn()
        mock_conn.fetchrow = AsyncMock(return_value={
            "user_id": user_id,
            "plan_id": "jainune_plus_monthly",
            "status": "captured",
            "amount": 49900,
        })

        async def fake_execute(query, *args):
            executed_sqls.append(query)
            return "UPDATE 1"

        mock_conn.execute.side_effect = fake_execute
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        event = {
            "payload": {
                "refund": {
                    "entity": {
                        "payment_id": "pay_partial_1",
                        "amount": 5000,  # ₹50 partial refund on ₹499 plan
                    }
                }
            }
        }

        await process_refund(event=event, pool=mock_pool)
        self.assertFalse(any("subscription_tier        = 'free'" in s for s in executed_sqls))
        self.assertTrue(any("status = 'partially_refunded'" in s for s in executed_sqls))

    async def test_15_full_refund_claws_back_super_connect_credits(self):
        """Full subscription refund revokes tier and claws back super connect credits (B-4)."""
        from app.services.payment_service import process_refund

        user_id = uuid.uuid4()
        executed_sqls = []

        mock_conn = _create_mock_conn()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            # intent
            {
                "user_id": user_id,
                "plan_id": "jainune_plus_monthly",
                "status": "captured",
                "amount": 49900,
            },
            # other_active: None
            None,
        ])

        async def fake_execute(query, *args):
            executed_sqls.append(query)
            return "UPDATE 1"

        mock_conn.execute.side_effect = fake_execute
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        event = {
            "payload": {
                "refund": {
                    "entity": {
                        "payment_id": "pay_full_1",
                        "amount": 49900,
                    }
                }
            }
        }

        await process_refund(event=event, pool=mock_pool)
        self.assertTrue(any("subscription_tier        = 'free'" in s for s in executed_sqls))
        self.assertTrue(any("super_connect_credits = GREATEST(0" in s for s in executed_sqls))

    async def test_16_daily_compatible_batching_and_queue_isolation(self):
        """daily_compatible is isolated on dedicated batch queue and yields properly."""
        from app.celery_app import celery_app
        from app.services.core_people_finder import CorePeopleFinder

        if hasattr(celery_app.conf.update, "call_args") and celery_app.conf.update.call_args:
            called_args = celery_app.conf.update.call_args[0]
            called_kwargs = celery_app.conf.update.call_args[1]
            routes = called_kwargs.get("task_routes") or (called_args[0].get("task_routes") if called_args else {})
            self.assertEqual(routes["app.workers.daily_compatible.*"]["queue"], "batch")
        else:
            self.assertEqual(celery_app.conf.task_routes["app.workers.daily_compatible.*"]["queue"], "batch")

        finder = CorePeopleFinder()
        req = {"id": uuid.uuid4(), "show_me": "women", "dietary_strictness": "pure_jain", "community_sect": "shwetambar"}
        pool = [
            {"id": uuid.uuid4(), "gender": "women", "dietary_strictness": "pure_jain", "community_sect": "shwetambar"}
            for _ in range(300)
        ]
        candidates = await finder.rank_candidates(requester=req, pool_users=pool, top_k=10)
        self.assertEqual(len(candidates), 10)


if __name__ == "__main__":
    unittest.main()
