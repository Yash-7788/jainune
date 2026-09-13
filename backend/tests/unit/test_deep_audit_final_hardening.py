"""
Unit tests for Final Deep Audits:
- Onboarding Step 22 idempotency (network retry lockout prevention)
- Serendipity Arcade wheel paid spin credit preservation on 0 candidates
- Dilemma vote concurrency & atomic counter protection
- WebSocket connection rate limit & resilient frame parsing
- Media processor and ephemeral reaper cloud client fail-safes
"""

import asyncio
import sys
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

for mod in ["asyncpg", "redis", "redis.asyncio", "boto3", "botocore", "botocore.config", "botocore.exceptions"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

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
        """Account deletion endpoint: hard_delete=True is downgraded to soft delete on user endpoint (N-16)."""
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
                hard_delete=True,   # N-16: always downgraded to False on user endpoint
                current_user=current_user,
                pool=mock_pool,
                redis=mock_redis,
            )
            self.assertTrue(res["success"])
            # N-16: hard_delete is silently forced to False, so soft delete path runs
            self.assertEqual(res["data"]["status"], "deactivated")
            mock_soft.assert_called_once()

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

    async def test_17_interactions_insert_sets_interaction_type_and_action_type(self):
        """P1: interactions action endpoint must set both action_type and interaction_type."""
        from app.routers.interactions import record_interaction_action
        from app.models.schemas.interaction import InteractionActionRequest

        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()

        mock_user = {"id": str(actor_id), "subscription_tier": "free"}

        mock_conn = _create_mock_conn()
        executed_sqls = []

        async def track_execute(sql, *args):
            executed_sqls.append((sql, args))
            return "INSERT 0 1"

        mock_conn.execute = AsyncMock(side_effect=track_execute)
        mock_conn.fetchval = AsyncMock(return_value=None)

        async def mock_fetchrow(sql, *args):
            if "FROM users" in sql:
                return {
                    "id": target_id,
                    "account_status": "active",
                    "deleted_at": None,
                    "subscription_tier": "free",
                    "subscription_valid_until": None,
                }
            return None

        mock_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.get = AsyncMock(return_value=None)

        body = InteractionActionRequest(
            target_id=target_id,
            action="like",
            prompt_id=None,
        )

        with patch("app.routers.interactions.sliding_window_rate_limit", new_callable=AsyncMock):
            res = await record_interaction_action(
                body=body,
                current_user=mock_user,
                db=mock_pool,
                redis=mock_redis,
            )

        self.assertTrue(res.success)
        insert_calls = [args for sql, args in executed_sqls if "INSERT INTO interactions" in sql]
        self.assertEqual(len(insert_calls), 1)
        args = insert_calls[0]
        # Check that actor_id, target_id, action_type, interaction_type are passed
        self.assertEqual(args[0], actor_id)
        self.assertEqual(args[1], target_id)
        self.assertEqual(args[2], "like")
        self.assertEqual(args[3], "like")  # interaction_type populated!

    def test_18_location_verifier_origin_lock_and_client_ip(self):
        """P2: verify_location_anti_spoofing validates client_ip and enforces edge origin-lock."""
        from app.services.location_verifier import verify_location_anti_spoofing
        from app.core.config import settings

        # 1. Invalid client IP format rejected
        valid, err = verify_location_anti_spoofing(
            lat=19.0760,
            lon=72.8777,
            client_ip="not_an_ip",
        )
        self.assertFalse(valid)
        self.assertIn("Invalid network client IP", err)

        # 2. Valid client IP accepted
        valid, err = verify_location_anti_spoofing(
            lat=19.0760,
            lon=72.8777,
            client_ip="103.21.244.1",
        )
        self.assertTrue(valid)

        # 3. Origin secret configured: untrusted edge headers without secret rejected
        orig_secret = settings.cloudflare_origin_secret
        try:
            settings.cloudflare_origin_secret = "secret_edge_pass_999"
            valid, err = verify_location_anti_spoofing(
                lat=19.0760,
                lon=72.8777,
                headers={"cf-ipcountry": "IN", "cf-iplatitude": "19.07", "cf-iplongitude": "72.87"},
            )
            self.assertFalse(valid)
            self.assertIn("Untrusted edge network headers", err)

            # 4. Valid edge secret provided: accepted
            valid, err = verify_location_anti_spoofing(
                lat=19.0760,
                lon=72.8777,
                headers={
                    "x-edge-secret": "secret_edge_pass_999",
                    "cf-ipcountry": "IN",
                    "cf-iplatitude": "19.07",
                    "cf-iplongitude": "72.87",
                },
            )
            self.assertTrue(valid)
            self.assertIsNone(err)
        finally:
            settings.cloudflare_origin_secret = orig_secret

    def test_19_migrations_deterministic_and_unique(self):
        """P3: All migration files must have unique prefixes and no duplicate numbers."""
        from pathlib import Path
        import re

        migrations_dir = Path(__file__).resolve().parent.parent.parent / "migrations"
        migration_files = sorted(migrations_dir.glob("*.sql"))
        self.assertTrue(len(migration_files) >= 14)

        prefixes = []
        for f in migration_files:
            match = re.match(r"^(\d{4})_", f.name)
            self.assertIsNotNone(match, f"Invalid migration naming format: {f.name}")
            prefixes.append(match.group(1))

        # Check all prefixes are strictly unique
        duplicate_prefixes = [p for p in prefixes if prefixes.count(p) > 1]
        self.assertEqual(len(duplicate_prefixes), 0, f"Duplicate migration numbers found: {duplicate_prefixes}")

    async def test_20_promotional_broadcast_enforces_marketing_consent(self):
        """P4: broadcast_promotional_campaign target query must join consent_records."""
        from app.services.messaging_service import broadcast_promotional_campaign
        from app.routers.onboarding import step21_consent
        from app.models.schemas.user import Step21ConsentBody

        captured_query = []

        mock_conn = _create_mock_conn()
        async def mock_fetch(query, *params):
            captured_query.append(query)
            return []

        mock_conn.fetch = AsyncMock(side_effect=mock_fetch)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await broadcast_promotional_campaign(
            pool=mock_pool,
            campaign_name="festive_push",
            title="Happy Paryushan",
            message="Connect with members of the Jain community.",
            channels=["email"],
            target_segment="free",
        )

        self.assertEqual(len(captured_query), 1)
        sql = captured_query[0]
        self.assertIn("consent_records", sql)
        self.assertIn("consent_type = 'marketing'", sql)
        self.assertIn("granted = TRUE", sql)

        # Also test onboarding Step 21 saves marketing consent
        user_id = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        step21_sqls = []
        async def mock_step21_execute(sql, *args):
            step21_sqls.append((sql, args))

        mock_conn.execute = AsyncMock(side_effect=mock_step21_execute)
        mock_conn.fetchrow = AsyncMock(return_value={"onboarding_completed": False})

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn
        mock_redis = AsyncMock()

        body = Step21ConsentBody(
            core_matchmaking=True,
            family_contact_gotra=True,
            relocation_intercity=False,
            marketing=True,
        )

        with patch("app.routers.onboarding.sliding_window_rate_limit", new_callable=AsyncMock):
            await step21_consent(
                body=body,
                current_user=mock_user,
                db=mock_db,
                redis=mock_redis,
            )

        marketing_consent_saved = any(
            len(args) >= 3 and args[1] == "marketing" and args[2] is True
            for sql, args in step21_sqls
        )
        self.assertTrue(marketing_consent_saved)

    def test_21_trusted_client_ip_origin_verification(self):
        """get_trusted_client_ip rejects spoofed headers unless cloudflare_origin_secret matches."""
        from app.core.security import get_trusted_client_ip

        class DummyClient:
            host = "203.0.113.195"

        class DummyRequest:
            def __init__(self, headers: dict):
                self.headers = headers
                self.client = DummyClient()

        # Attack scenario: malicious client sends spoofed CF-Connecting-IP & X-Forwarded-For directly
        req_spoofed = DummyRequest({
            "cf-connecting-ip": "1.1.1.1",
            "x-forwarded-for": "8.8.8.8",
        })

        with patch("app.core.security.settings.cloudflare_origin_secret", "secret_origin_key_123"), \
             patch("app.core.security.settings.environment", "production"):
            ip = get_trusted_client_ip(req_spoofed)
            # Must NOT trust spoofed IP, must return direct peer IP
            self.assertEqual(ip, "203.0.113.195")

        # Legitimate scenario: Cloudflare edge passes matching origin secret
        req_legit = DummyRequest({
            "cf-connecting-ip": "49.37.10.25",
            "x-edge-secret": "secret_origin_key_123",
        })
        with patch("app.core.security.settings.cloudflare_origin_secret", "secret_origin_key_123"), \
             patch("app.core.security.settings.environment", "production"):
            ip = get_trusted_client_ip(req_legit)
            self.assertEqual(ip, "49.37.10.25")

    def test_22_docker_compose_worker_listens_to_batch_queue(self):
        """Celery worker in docker-compose.prod.yml and docker-compose.yml must listen to -Q default,notifications,batch."""
        import os

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        prod_compose = os.path.join(repo_root, "docker-compose.prod.yml")
        dev_compose = os.path.join(repo_root, "docker-compose.yml")

        self.assertTrue(os.path.exists(prod_compose), f"{prod_compose} not found")
        with open(prod_compose, "r", encoding="utf-8") as f:
            prod_content = f.read()
        self.assertIn("-Q default,notifications,batch", prod_content)

        self.assertTrue(os.path.exists(dev_compose), f"{dev_compose} not found")
        with open(dev_compose, "r", encoding="utf-8") as f:
            dev_content = f.read()
        self.assertIn("-Q default,notifications,batch", dev_content)

    async def test_23_arcade_wallet_for_update_concurrency_lock(self):
        """Arcade spins and rolls execute SELECT ... FOR UPDATE before deducting balances."""
        from app.routers.arcade import spin_serendipity_wheel, roll_lucky_dice

        user_id = uuid.uuid4()
        current_user = {"user_id": user_id, "id": user_id, "show_me": "women"}

        executed_sqls = []

        mock_conn = _create_mock_conn()
        async def mock_execute(sql, *args):
            executed_sqls.append(sql)

        mock_conn.execute = AsyncMock(side_effect=mock_execute)
        mock_conn.fetchval = AsyncMock(return_value=2)
        mock_conn.fetchrow = AsyncMock(return_value={"id": uuid.uuid4(), "first_name": "Aditi", "city": "Bengaluru"})

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_redis = AsyncMock()

        with patch("app.routers.arcade.sliding_window_rate_limit", new_callable=AsyncMock):
            await spin_serendipity_wheel(current_user=current_user, pool=mock_pool, redis=mock_redis)

        self.assertTrue(any("SELECT available_spins FROM user_arcade_wallet WHERE user_id = $1 FOR UPDATE" in s for s in executed_sqls))

        executed_sqls.clear()
        with patch("app.routers.arcade.sliding_window_rate_limit", new_callable=AsyncMock):
            await roll_lucky_dice(current_user=current_user, pool=mock_pool, redis=mock_redis)

        self.assertTrue(any("SELECT available_dice_rolls FROM user_arcade_wallet WHERE user_id = $1 FOR UPDATE" in s for s in executed_sqls))

    async def test_24_fcm_unregistered_token_cleanup(self):
        """send_push automatically executes cleanup query when FCM returns 404/UNREGISTERED."""
        from app.services.push_notifications import send_push

        cleanup_sqls = []

        mock_conn = MagicMock()
        async def mock_execute(sql, *args):
            cleanup_sqls.append((sql, args))

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.services.push_notifications._get_access_token", new_callable=AsyncMock) as mock_token, \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_token.return_value = "mock_token"
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.text = '{"error": {"code": 404, "details": [{"errorCode": "UNREGISTERED"}]}}'
            mock_post.return_value = mock_resp

            dead_token = "dead_device_token_abc123"
            success = await send_push(dead_token, "Title", "Body", db_conn=mock_conn)
            self.assertFalse(success)

        self.assertEqual(len(cleanup_sqls), 1)
        sql, args = cleanup_sqls[0]
        self.assertIn("UPDATE users SET fcm_token = NULL WHERE fcm_token = $1", sql)
        self.assertEqual(args[0], dead_token)

    async def test_25_sms_gateway_downtime_fails_over_to_whatsapp(self):
        """When SMS gateway returns 503, dispatch_phone_otp automatically fails over to WhatsApp."""
        from fastapi import HTTPException
        from app.services.messaging_service import dispatch_phone_otp

        phone = "+919876543210"
        otp = "123456"

        with patch("app.services.messaging_service.settings.debug", False), \
             patch("app.services.messaging_service.send_sms_otp", new_callable=AsyncMock) as mock_sms, \
             patch("app.services.messaging_service.send_whatsapp_otp", new_callable=AsyncMock) as mock_wa:
            mock_sms.side_effect = HTTPException(status_code=503, detail="SMS gateway down")
            mock_wa.return_value = None

            # Must not raise 503, must succeed via WhatsApp failover
            await dispatch_phone_otp(phone, otp, channel="sms")
            mock_sms.assert_called_once_with(phone, otp)
            mock_wa.assert_called_once_with(phone, otp)

    async def test_26_db_pool_timeout_maps_to_503_retry_after(self):
        """Pool exhaustion TimeoutError in unhandled_exception_handler returns 503 with Retry-After header."""
        from app.core.errors import unhandled_exception_handler
        from fastapi import Request

        scope = {"type": "http", "method": "GET", "path": "/v1/feed", "headers": []}
        req = Request(scope)

        timeout_exc = TimeoutError("Connection acquisition timed out (5.0s)")
        resp = await unhandled_exception_handler(req, timeout_exc)

        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.headers.get("retry-after"), "2")

    async def test_27_websocket_slow_consumer_and_zombie_timeout(self):
        """WebSocket chat handler encapsulates producer and consumer with timeout protections."""
        from app.routers.websockets import websocket_chat
        from starlette.websockets import WebSocketDisconnect

        mock_ws = AsyncMock()
        mock_ws.headers = {}
        mock_ws.receive_json.side_effect = TimeoutError("Zombie connection timeout (60s)")

        mock_redis = AsyncMock()
        mock_pubsub = MagicMock()
        async def mock_listen():
            while True:
                await asyncio.sleep(100)
                yield {"type": "message", "data": "{}"}
        mock_pubsub.listen = mock_listen
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
        mock_redis.get.return_value = str(uuid.uuid4())
        mock_redis.delete.return_value = 1

        mock_db = MagicMock()
        mock_conn = _create_mock_conn()
        mock_conn.fetchrow.return_value = {
            "id": uuid.uuid4(),
            "match_id": uuid.uuid4(),
            "other_id": uuid.uuid4(),
            "account_status": "active",
            "is_unmatched": False,
        }
        mock_conn.fetchval.return_value = False  # not blocked
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn

        with patch("app.routers.websockets.get_pool", return_value=mock_db), \
             patch("app.routers.websockets.get_redis", return_value=mock_redis), \
             patch("app.routers.websockets.sliding_window_rate_limit", new_callable=AsyncMock):
            await websocket_chat(websocket=mock_ws, chat_id=uuid.uuid4(), ticket="valid_ticket")

        # Must cleanly clean up pubsub and close websocket
        mock_pubsub.close.assert_called_once()
        mock_ws.close.assert_called_once()

    async def test_28_super_connect_for_update_concurrency_lock(self):
        """Super connect action executes SELECT ... FOR UPDATE before deducting credits."""
        from app.routers.interactions import record_interaction_action
        from app.models.schemas.interaction import InteractionActionRequest

        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()
        current_user = {"id": actor_id, "user_id": actor_id}

        executed_sqls = []
        mock_conn = _create_mock_conn()
        async def mock_execute(sql, *args):
            executed_sqls.append(sql)

        mock_conn.execute = AsyncMock(side_effect=mock_execute)
        # First fetchval is block check (None), second is credit deduction returning remaining = 1
        mock_conn.fetchval = AsyncMock(side_effect=[None, 1])
        
        async def mock_fetchrow(query, *args):
            if "subscription_tier" in query:
                return {"subscription_tier": "plus", "subscription_valid_until": None}
            if "FROM users WHERE id" in query:
                return {"id": target_id, "account_status": "active", "deleted_at": None}
            return None
        mock_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_redis = AsyncMock()

        body = InteractionActionRequest(
            target_user_id=target_id,
            action="super_connect",
        )

        with patch("app.routers.interactions.sliding_window_rate_limit", new_callable=AsyncMock):
            res = await record_interaction_action(
                body=body,
                current_user=current_user,
                db=mock_pool,
                redis=mock_redis,
            )

        self.assertTrue(res.success)
        self.assertTrue(any("SELECT super_connect_credits FROM users WHERE id = $1 FOR UPDATE" in s for s in executed_sqls))

    async def test_29_razorpay_webhook_chaos_and_refund_aliases(self):
        """Webhook routes order.paid and refund aliases (refund.processed, refund.created) correctly."""
        import json
        from app.routers.subscriptions import razorpay_webhook
        from app.services import payment_service

        mock_pool = MagicMock()
        mock_conn = _create_mock_conn()
        user_id = uuid.uuid4()
        executed_sqls = []

        async def mock_execute(sql, *args):
            executed_sqls.append(sql)

        mock_conn.execute = AsyncMock(side_effect=mock_execute)
        mock_conn.fetchrow.return_value = {
            "user_id": user_id,
            "plan_id": "jainune_plus_monthly",
            "status": "captured",
            "amount": 49900,
            "razorpay_payment_id": "pay_test123",
        }
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # 1. order.paid event alias
        req = AsyncMock()
        req.body.return_value = json.dumps({
            "event": "order.paid",
            "payload": {
                "order": {"entity": {"id": "order_test123", "amount": 49900, "status": "paid"}},
                "payment": {"entity": {"id": "pay_test123", "order_id": "order_test123"}},
            }
        }).encode("utf-8")

        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.payment_service.verify_webhook_signature", return_value=True), \
             patch("app.core.redis.get_redis", return_value=mock_redis), \
             patch("app.services.payment_service.process_payment_captured", new_callable=AsyncMock) as mock_capture:
            resp = await razorpay_webhook(request=req, x_razorpay_signature="valid_sig", pool=mock_pool)
            self.assertTrue(resp.get("received"))
            mock_capture.assert_called_once()

        # 2. refund.processed event alias with nested refund payment_id
        refund_event = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_test123",
                        "payment_id": "pay_test123",
                        "amount": 49900,
                    }
                }
            }
        }
        await payment_service.process_refund(refund_event, mock_pool)
        self.assertTrue(any("SET subscription_tier        = 'free'" in s for s in executed_sqls))

    async def test_30_storekit_and_play_billing_lifecycle(self):
        """StoreKit and Play Billing state transitions: grace period, account hold, and revocation."""
        from datetime import datetime, timezone, timedelta
        from app.services import payment_service

        user_id = uuid.uuid4()
        mock_pool = MagicMock()
        mock_conn = _create_mock_conn()
        executed_sqls = []

        async def mock_execute(sql, *args):
            executed_sqls.append(sql)

        mock_conn.execute = AsyncMock(side_effect=mock_execute)
        mock_conn.fetchrow.return_value = {
            "id": user_id,
            "subscription_tier": "jainune_plus",
            "subscription_valid_until": datetime.now(timezone.utc) + timedelta(days=20),
            "super_connect_credits": 5,
        }
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_redis = AsyncMock()
        redis_store = {}

        async def mock_r_set(k, v, **kwargs):
            redis_store[k] = v

        async def mock_r_get(k):
            return redis_store.get(k)

        async def mock_r_del(k):
            redis_store.pop(k, None)

        mock_redis.set = AsyncMock(side_effect=mock_r_set)
        mock_redis.get = AsyncMock(side_effect=mock_r_get)
        mock_redis.delete = AsyncMock(side_effect=mock_r_del)

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            # Grace period retains tier and records status
            res_grace = await payment_service.process_store_subscription_event(
                user_id=user_id,
                store="apple",
                event_type="in_grace_period",
                pool=mock_pool,
            )
            self.assertEqual(res_grace["status"], "in_grace_period")
            self.assertEqual(redis_store.get(f"user:{user_id}:billing_status"), "in_grace_period")

            # Account hold suspends tier to free in effective tier calculation
            res_hold = await payment_service.process_store_subscription_event(
                user_id=user_id,
                store="google",
                event_type="account_hold",
                pool=mock_pool,
            )
            self.assertEqual(res_hold["status"], "account_hold")
            tier_during_hold = await payment_service.get_effective_user_tier(user_id, mock_conn)
            self.assertEqual(tier_during_hold, "free")

            # Revocation downgrades to free and claws back credits
            res_revoked = await payment_service.process_store_subscription_event(
                user_id=user_id,
                store="apple",
                event_type="revoked",
                pool=mock_pool,
            )
            self.assertEqual(res_revoked["status"], "revoked")
            self.assertTrue(any("SET subscription_tier        = 'free'" in s for s in executed_sqls))
            # N-02 fix: credit claw-back is now parameterized ($3) not hardcoded (-5)
            self.assertTrue(any("super_connect_credits    = GREATEST(0, COALESCE(super_connect_credits, 0) - $3)" in s for s in executed_sqls))

    async def test_31_apns_bad_device_token_pruning(self):
        """APNs BadDeviceToken / DeviceTokenNotForTopic error triggers token nullification."""
        from app.services.push_notifications import send_push

        mock_db = MagicMock()
        mock_conn = _create_mock_conn()
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn

        executed_sqls = []
        async def mock_execute(sql, *args):
            executed_sqls.append(sql)

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        # 1. FCM APNs BadDeviceToken response
        mock_resp_fcm = MagicMock()
        mock_resp_fcm.status_code = 400
        mock_resp_fcm.text = '{"error": {"code": 400, "message": "The registration token is not valid: BadDeviceToken"}}'

        # 2. Expo DeviceTokenNotForTopic response
        mock_resp_expo = MagicMock()
        mock_resp_expo.status_code = 200
        mock_resp_expo.text = '{"data": [{"status": "error", "message": "DeviceTokenNotForTopic"}]}'

        with patch("app.services.push_notifications._get_access_token", return_value="mock_access_token"), \
             patch("httpx.AsyncClient.post", side_effect=[mock_resp_fcm, mock_resp_expo]), \
             patch("app.core.database.get_pool", return_value=mock_db):

            res_fcm = await send_push(
                device_token="bad_apns_token_hex_64_characters",
                title="Hello",
                body="World",
                db_conn=mock_conn,
            )
            self.assertFalse(res_fcm)

            res_expo = await send_push(
                device_token="ExponentPushToken[invalid_topic]",
                title="Hello",
                body="World",
                db_conn=mock_conn,
            )
            self.assertTrue(res_expo)

        # Both dead tokens must have triggered pruning
        self.assertGreaterEqual(len(executed_sqls), 2)
        self.assertTrue(all("UPDATE users SET fcm_token = NULL" in s for s in executed_sqls))


    async def test_32_idor_boundary_protections(self):
        """Verify strict IDOR rejection across media, chat, payment, reporting, and interaction boundaries."""
        from app.routers.media import delete_media
        from app.routers.chats import _assert_participant
        from app.routers.subscriptions import verify_payment, VerifyPaymentBody
        from app.routers.users import block_user
        from app.routers.interactions import record_interaction_action
        from app.services.dignity_engine import file_report
        from app.models.schemas.interaction import InteractionActionRequest

        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        chat_id = uuid.uuid4()
        media_id = uuid.uuid4()

        mock_conn = _create_mock_conn()
        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn
        mock_redis = AsyncMock()

        # 1. Media IDOR: deleting unowned media returns 404
        mock_conn.fetchrow.return_value = None
        with patch("app.routers.media.sliding_window_rate_limit", new_callable=AsyncMock):
            with self.assertRaises(HTTPException) as ctx:
                await delete_media(media_id=media_id, current_user={"id": str(user_a)}, db=mock_db, redis=mock_redis)
            self.assertEqual(ctx.exception.status_code, 404)

        # 2. Chat IDOR: unauthorized participant access returns 404
        mock_conn.fetchrow.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            await _assert_participant(chat_id=chat_id, user_id=user_a, db=mock_db)
        self.assertEqual(ctx.exception.status_code, 404)

        # 3. Subscription IDOR: verifying another user's payment intent returns 403
        mock_conn.fetchrow.return_value = {
            "user_id": str(user_b),
            "status": "created",
            "amount": 29900,
            "plan_id": "gold_monthly",
        }
        body = VerifyPaymentBody(
            razorpay_order_id="order_foreign_123",
            razorpay_payment_id="pay_123",
            razorpay_signature="sig_123",
        )
        with patch("app.routers.subscriptions.sliding_window_rate_limit", new_callable=AsyncMock):
            with self.assertRaises(HTTPException) as ctx:
                await verify_payment(
                    body=body,
                    current_user={"user_id": str(user_a)},
                    pool=mock_db,
                    redis=mock_redis,
                )
            self.assertEqual(ctx.exception.status_code, 403)

        # 4. Self-reporting is rejected with ValueError
        with self.assertRaises(ValueError) as ctx_err:
            await file_report(
                reporter_id=user_a,
                reported_id=user_a,
                reason="harassment",
                detail="self",
                pool=mock_db,
            )
        self.assertIn("Cannot report yourself", str(ctx_err.exception))

        # 5. Self-blocking returns 400
        with self.assertRaises(HTTPException) as ctx:
            await block_user(
                user_id=user_a,
                current_user={"user_id": str(user_a)},
                pool=mock_db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # 6. Self-interaction returns 400
        with patch("app.routers.interactions.sliding_window_rate_limit", new_callable=AsyncMock):
            with self.assertRaises(HTTPException) as ctx:
                await record_interaction_action(
                    body=InteractionActionRequest(target_id=user_a, action="like"),
                    current_user={"id": str(user_a)},
                    db=mock_db,
                    redis=mock_redis,
                )
            self.assertEqual(ctx.exception.status_code, 400)

    def test_33_rate_limit_evasion_and_header_spoofing(self):
        """Verify client IP resolver prevents header spoofing and sanitizes candidate IPs with native ipaddress."""
        from app.core.security import get_trusted_client_ip, _clean_ip
        from app.core.config import settings

        # Direct IP validation and CRLF sanitization
        self.assertEqual(_clean_ip("203.0.113.195"), "203.0.113.195")
        self.assertEqual(_clean_ip("2001:db8::1"), "2001:db8::1")
        self.assertIsNone(_clean_ip("203.0.113.195\r\nSET evil 1"))
        self.assertIsNone(_clean_ip("not_an_ip_address"))
        self.assertIsNone(_clean_ip("999.999.999.999"))

        # Mock request objects
        class MockClient:
            def __init__(self, host):
                self.host = host

        class MockRequest:
            def __init__(self, headers, host="192.168.1.50"):
                self.headers = headers
                self.client = MockClient(host)

        # 1. In production without origin secret match, proxy headers are ignored (spoofing prevented)
        with patch.object(settings, "environment", "production"), \
             patch.object(settings, "cloudflare_origin_secret", "prod_secret_token"):
            # Attacker provides spoofed X-Forwarded-For and CF-Connecting-IP
            req_spoofed = MockRequest(
                headers={
                    "x-forwarded-for": "198.51.100.77",
                    "cf-connecting-ip": "198.51.100.88",
                },
                host="10.0.0.5",
            )
            self.assertEqual(get_trusted_client_ip(req_spoofed), "10.0.0.5")

            # 2. Legitimate reverse proxy with matching edge origin secret is trusted
            req_legit_cf = MockRequest(
                headers={
                    "x-edge-secret": "prod_secret_token",
                    "cf-connecting-ip": "203.0.113.42",
                },
                host="10.0.0.5",
            )
            self.assertEqual(get_trusted_client_ip(req_legit_cf), "203.0.113.42")

            req_legit_xff = MockRequest(
                headers={
                    "x-origin-secret": "prod_secret_token",
                    "x-forwarded-for": "203.0.113.99, 10.0.0.1",
                },
                host="10.0.0.5",
            )
            self.assertEqual(get_trusted_client_ip(req_legit_xff), "203.0.113.99")

            # 3. Corrupted or injection proxy header with matching secret falls back to client host
            req_corrupted = MockRequest(
                headers={
                    "x-edge-secret": "prod_secret_token",
                    "cf-connecting-ip": "corrupted_ip\r\nINJECT",
                },
                host="10.0.0.5",
            )
            self.assertEqual(get_trusted_client_ip(req_corrupted), "10.0.0.5")

    async def test_34_sql_injection_and_postgis_parameterization(self):
        """Verify strict SQL query parameterization, PostGIS placeholder binding, and column whitelisting."""
        from pydantic import ValidationError
        from app.routers.users import UpdateProfileBody, update_my_profile
        from app.services.messaging_service import broadcast_promotional_campaign
        from app.services.core_people_finder import fetch_recommended_feed

        # 1. Column injection blocked by Pydantic extra='forbid'
        with self.assertRaises(ValidationError):
            UpdateProfileBody(first_name="Aarav", injected_column="malicious_val")

        # 2. Whitelist enforcement in update_my_profile dynamic SET clause
        mock_conn = _create_mock_conn()
        mock_conn.execute.return_value = "UPDATE 1"
        mock_conn.fetchrow.return_value = {"id": uuid.uuid4(), "first_name": "Aarav"}
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        executed_queries = []
        async def mock_execute(sql, *args):
            executed_queries.append((sql, args))
            return "UPDATE 1"

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        user_id = uuid.uuid4()
        await update_my_profile(
            body=UpdateProfileBody(first_name="Aarav", bio="New bio"),
            current_user={"user_id": user_id},
            pool=mock_pool,
        )

        self.assertEqual(len(executed_queries), 1)
        sql, args = executed_queries[0]
        # Must be parameterized with $1, $2, $3 and no raw strings
        self.assertIn("first_name = $2", sql)
        self.assertIn("bio = $3", sql)
        self.assertIn("WHERE id = $1", sql)
        self.assertEqual(args[0], user_id)
        self.assertEqual(args[1], "Aarav")
        self.assertEqual(args[2], "New bio")

        # 3. Messaging campaign limit is parameterized as $N
        executed_campaign_queries = []
        async def mock_fetch(sql, *args):
            executed_campaign_queries.append((sql, args))
            return []

        mock_conn.fetch = AsyncMock(side_effect=mock_fetch)
        await broadcast_promotional_campaign(
            pool=mock_pool,
            campaign_name="Diwali Special",
            title="Celebrate",
            message="Join community",
            channels=["sms"],
            limit=250,
        )
        c_sql, c_args = executed_campaign_queries[0]
        self.assertIn("LIMIT $2", c_sql)
        self.assertEqual(c_args[-1], 250)

        # 4. PostGIS ST_Distance and ST_DWithin in candidate feed query execution
        executed_feed_queries = []
        async def mock_feed_fetch(sql, *args):
            executed_feed_queries.append((sql, args))
            return []

        mock_conn.fetch = AsyncMock(side_effect=mock_feed_fetch)
        user_data = {
            "id": user_id,
            "gender": "man",
            "show_me": "women",
            "date_of_birth": "1995-01-01",
            "location": "POINT(77.5946 12.9716)",
            "dietary_strictness": "pure_jain",
            "eats_root_vegetables": False,
            "eats_onion_garlic": False,
            "community_sect": "shwetambar",
            "open_to_relocation": True,
            "max_distance_km": 50,
            "behavior_vector": [0.088388] * 128,
        }
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss

        await fetch_recommended_feed(user_id=user_id, user_data=user_data, db=mock_pool, redis=mock_redis, limit=10)
        self.assertGreaterEqual(len(executed_feed_queries), 1)
        feed_sql, feed_args = executed_feed_queries[0]
        self.assertIn("ST_Distance(", feed_sql)
        self.assertIn("ST_DWithin(", feed_sql)
        self.assertIn("$1::geography", feed_sql)
        self.assertIn("$10 * 1000", feed_sql)
        self.assertEqual(feed_args[0], "POINT(77.5946 12.9716)")
        self.assertEqual(feed_args[9], 50)


    def test_35_malicious_media_payload_and_exif_stripping(self):
        """Verify media sanitizer rejects corrupt headers, prevents decompression bombs, and strips EXIF GPS."""
        import io
        from PIL import Image
        from app.services.media_processor import process_and_sanitize_image

        # 1. Corrupt magic bytes / non-image masquerade rejected
        with self.assertRaises(ValueError) as ctx:
            process_and_sanitize_image(b"PK\x03\x04zip_bomb_payload_not_image")
        self.assertIn("Corrupted image header", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            process_and_sanitize_image(b"<script>alert('xss')</script>")
        self.assertIn("Corrupted image header", str(ctx.exception))

        # 2. Corrupted WebP (valid RIFF header but broken/truncated payload)
        broken_webp = b"RIFF\x18\x00\x00\x00WEBPVP8 \x0c\x00\x00\x00\x30\x01\x00\x9d\x01\x2a"
        with self.assertRaises(ValueError):
            process_and_sanitize_image(broken_webp)

        # 3. Valid image with EXIF metadata is cleanly converted to WebP with 0 EXIF tags
        valid_img = Image.new("RGB", (100, 100), color="blue")
        exif = valid_img.getexif()
        exif[0x010e] = "Camera Description"  # ImageDescription
        exif[0x0132] = "2026:09:07 12:00:00"  # DateTime
        in_buf = io.BytesIO()
        valid_img.save(in_buf, format="JPEG", exif=exif)
        jpeg_bytes = in_buf.getvalue()

        clean_webp_bytes = process_and_sanitize_image(jpeg_bytes)
        self.assertTrue(clean_webp_bytes.startswith(b"RIFF"))
        self.assertEqual(clean_webp_bytes[8:12], b"WEBP")

        # Verify EXIF is completely stripped in the result
        with Image.open(io.BytesIO(clean_webp_bytes)) as sanitized_img:
            sanitized_exif = sanitized_img.getexif()
            self.assertEqual(len(sanitized_exif), 0)

        # 4. Decompression bomb protection triggers DecompressionBombError
        with patch("PIL.Image.open") as mock_open:
            mock_open.side_effect = Image.DecompressionBombError("Too large")
            fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00"
            with self.assertRaises(ValueError) as ctx:
                process_and_sanitize_image(fake_jpeg)
            self.assertIn("Decompression bomb detected", str(ctx.exception))

    async def test_36_ssrf_and_webhook_signature_forgery(self):
        """Verify SSRF blocklist on external URLs and HMAC-SHA256 webhook anti-tamper verification."""
        from app.core.security import is_safe_public_url
        from app.services.payment_service import verify_webhook_signature
        from app.services.messaging_service import broadcast_promotional_campaign
        from app.core.config import settings

        # 1. SSRF URL validation
        self.assertFalse(is_safe_public_url("http://127.0.0.1:8000/secret"))
        self.assertFalse(is_safe_public_url("http://localhost/admin"))
        self.assertFalse(is_safe_public_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(is_safe_public_url("http://10.0.0.1/internal"))
        self.assertFalse(is_safe_public_url("http://192.168.1.1/"))
        self.assertFalse(is_safe_public_url("ftp://example.com/file"))
        self.assertTrue(is_safe_public_url("https://jainune.com/invite"))
        self.assertTrue(is_safe_public_url("https://app.jainune.com/welcome"))

        # Campaign rejects internal SSRF cta_url
        mock_conn = _create_mock_conn()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        with self.assertRaises(ValueError) as ctx:
            await broadcast_promotional_campaign(
                pool=mock_pool,
                campaign_name="SSRF Attempt",
                title="Bad URL",
                message="Test",
                channels=["sms"],
                cta_url="http://169.254.169.254/secret",
            )
        self.assertIn("Invalid cta_url", str(ctx.exception))

        # 2. Webhook Signature Forgery
        import hmac
        import hashlib
        payload = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123","amount":29900}}}}'
        secret = "test_webhook_secret_key"

        with patch.object(settings, "razorpay_webhook_secret", secret):
            # Valid signature passes
            valid_sig = hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
            self.assertTrue(verify_webhook_signature(payload, valid_sig))

            # Tampered payload fails
            tampered_payload = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123","amount":1}}}}'
            self.assertFalse(verify_webhook_signature(tampered_payload, valid_sig))

            # Forged signature fails
            self.assertFalse(verify_webhook_signature(payload, "forged_signature_hex"))

            # Empty signature fails
            self.assertFalse(verify_webhook_signature(payload, ""))

    async def test_37_jwt_replay_token_revocation_and_security_headers(self):
        """Verify algorithm confusion rejection, token revocation blacklist, and strict security headers."""
        import jwt as pyjwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from app.core.security import validate_access_token
        from fastapi.security import HTTPAuthorizationCredentials
        from starlette.testclient import TestClient
        from app.main import app

        user_id = str(uuid.uuid4())
        jti = str(uuid.uuid4())

        priv_key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        test_priv_pem = priv_key_obj.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        test_pub_pem = priv_key_obj.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        with patch("app.core.security._RSA_PRIVATE_KEY", test_priv_pem), \
             patch("app.core.security._RSA_PUBLIC_KEY", test_pub_pem):

            # 1. Algorithm confusion attack: attacker passes token signed with HS256 (HMAC)
            confused_token = pyjwt.encode(
                {
                    "sub": user_id,
                    "jti": jti,
                    "iss": "jainune-api",
                    "aud": "jainune-client",
                    "exp": 9999999999,
                },
                "attacker_secret_key_32_bytes_long!",
                algorithm="HS256",
            )
            creds_confused = HTTPAuthorizationCredentials(scheme="Bearer", credentials=confused_token)
            with self.assertRaises(HTTPException) as ctx:
                await validate_access_token(creds_confused)
            self.assertEqual(ctx.exception.status_code, 401)

            # 2. Token replay after revocation via Redis blacklist
            valid_token = pyjwt.encode(
                {
                    "sub": user_id,
                    "jti": jti,
                    "iss": "jainune-api",
                    "aud": "jainune-client",
                    "exp": 9999999999,
                },
                test_priv_pem,
                algorithm="RS256",
            )
            creds_valid = HTTPAuthorizationCredentials(scheme="Bearer", credentials=valid_token)
            mock_redis = AsyncMock()

            # Active token: exists returns False -> success
            mock_redis.exists.return_value = False
            payload = await validate_access_token(creds_valid, redis=mock_redis)
            self.assertEqual(payload["sub"], user_id)

            # Blacklisted token: exists returns True -> 401 Revoked
            mock_redis.exists.return_value = True
            with self.assertRaises(HTTPException) as ctx:
                await validate_access_token(creds_valid, redis=mock_redis)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Token has been revoked.")

        # 3. Security response headers middleware
        from app.main import add_security_headers
        mock_req = MagicMock()
        mock_req.url.path = "/v1/users/me"
        mock_resp = MagicMock()
        mock_resp.headers = {}
        async def mock_call_next(req):
            return mock_resp

        res = await add_security_headers(mock_req, mock_call_next)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("max-age=31536000", res.headers.get("Strict-Transport-Security", ""))
        self.assertIn("default-src 'none'", res.headers.get("Content-Security-Policy", ""))
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=()", res.headers.get("Permissions-Policy", ""))

        # 3b. Legal page CSP allows inline styles for rendered markdown
        mock_legal_req = MagicMock()
        mock_legal_req.url.path = "/legal/privacy"
        mock_legal_resp = MagicMock()
        mock_legal_resp.headers = {}
        async def mock_legal_call(req):
            return mock_legal_resp
        res_legal = await add_security_headers(mock_legal_req, mock_legal_call)
        self.assertIn("default-src 'self'", res_legal.headers.get("Content-Security-Policy", ""))

        # 3c. DevOps liveness endpoint returns 200 alive
        from app.main import liveness
        live_resp = await liveness()
        self.assertEqual(live_resp.status_code, 200)
        self.assertIn(b'"status":"alive"', live_resp.body)

        # 4. CORS origin lock
        from app.core.config import settings
        self.assertNotIn("https://evil-hacker.com", settings.allowed_origins)
        self.assertIn("https://app.jainune.com", settings.allowed_origins)
        self.assertIn("https://jainune.com", settings.allowed_origins)

    async def test_38_websocket_lifecycle_and_background_disconnect(self):
        """Verify WebSocket connection cleanly handles background teardown (code 1000) and ticket verification."""
        from app.routers.websockets import websocket_chat
        from starlette.websockets import WebSocketDisconnect

        chat_id = uuid.uuid4()
        user_id = uuid.uuid4()

        mock_ws = AsyncMock()
        mock_ws.headers = {"origin": "https://app.jainune.com"}
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        # Simulate clean client background disconnect
        mock_ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect(code=1000))
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect(code=1000))

        mock_redis = AsyncMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zadd = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.get = AsyncMock(return_value=str(user_id))
        mock_redis.delete = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()
        async def mock_listen():
            if False:
                yield {}
        mock_pubsub.listen = mock_listen
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            {"account_status": "active", "suspend_until": None, "deleted_at": None},
            {"id": chat_id, "match_id": chat_id, "is_unmatched": False, "other_id": uuid.uuid4()},
            {"account_status": "active", "deleted_at": None},
        ])
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Connect and cleanly background-disconnect
        with patch("app.routers.websockets.get_pool", return_value=mock_pool), \
             patch("app.routers.websockets.get_redis", return_value=mock_redis):
            await websocket_chat(websocket=mock_ws, chat_id=chat_id, ticket="valid_ticket")

        mock_ws.accept.assert_awaited_once()

    async def test_39_checkout_background_sync_and_idempotent_order_resolution(self):
        """Verify checkout sync endpoint recovers order after client backgrounding/interruption and blocks IDOR."""
        from app.routers.subscriptions import sync_subscription, SyncSubscriptionBody

        user_id = uuid.uuid4()
        attacker_id = uuid.uuid4()
        order_id = "order_bg_sync_789"

        mock_conn = MagicMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # 1. Successful sync when user returns from UPI app (GPay / PhonePe)
        mock_conn.fetchrow = AsyncMock(return_value={"user_id": user_id, "status": "created"})
        with patch("app.services.payment_service.sync_order_with_razorpay", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = {
                "synced": True,
                "activated": True,
                "tier": "gold_monthly",
                "expires_at": "2026-10-07T00:00:00Z",
                "status": "captured",
            }
            body = SyncSubscriptionBody(razorpay_order_id=order_id)
            res = await sync_subscription(body=body, current_user={"user_id": user_id}, pool=mock_pool)
            self.assertTrue(res["activated"])
            self.assertEqual(res["tier"], "gold_monthly")

        # 2. Rejection if attacker attempts to sync another user's order
        mock_conn.fetchrow = AsyncMock(return_value={"user_id": user_id, "status": "created"})
        with self.assertRaises(HTTPException) as ctx:
            await sync_subscription(body=body, current_user={"user_id": attacker_id}, pool=mock_pool)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("does not belong to user", ctx.exception.detail)

    async def test_40_push_notification_cold_boot_routing_payload_integrity(self):
        """Verify push notification data payloads include required routing fields with stringified values for mobile cold-boot."""
        from app.services.push_notifications import send_push_notification

        match_id = str(uuid.uuid4())
        sender_id = str(uuid.uuid4())

        captured_messages = []

        async def mock_post(url, headers=None, json=None):
            captured_messages.append(json)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = '{"data": [{"status": "ok"}]}'
            return mock_resp

        mock_client = MagicMock()
        mock_client.post = mock_post

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            # 1. Chat push payload
            await send_push_notification(
                device_token="ExponentPushToken[cold_boot_test_token]",
                title="New Message",
                body="Hey, how are you?",
                data={
                    "type": "chat",
                    "match_id": match_id,
                    "chat_id": match_id,
                    "sender_id": sender_id,
                    "sender_name": "Aarav",
                },
            )

            # 2. Super Connect push payload
            await send_push_notification(
                device_token="ExponentPushToken[cold_boot_test_token]",
                title="Super Connect Received",
                body="Someone sent you a Super Connect!",
                data={
                    "type": "super_connect",
                    "sender_id": sender_id,
                },
            )

        self.assertEqual(len(captured_messages), 2)

        # Validate chat payload stringification & routing keys
        chat_data = captured_messages[0]["data"]
        self.assertEqual(chat_data["type"], "chat")
        self.assertEqual(chat_data["match_id"], match_id)
        self.assertEqual(chat_data["sender_id"], sender_id)
        for k, v in chat_data.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

        # Validate super connect payload
        sc_data = captured_messages[1]["data"]
        self.assertEqual(sc_data["type"], "super_connect")
        self.assertEqual(sc_data["sender_id"], sender_id)

    def test_41_production_environment_variables_audit(self):
        """Verify Settings model_validator rejects insecure default/test secrets in production mode."""
        from pydantic import ValidationError
        from app.core.config import Settings

        # 1. Production with defaults must fail
        with self.assertRaises((ValidationError, ValueError)) as ctx:
            Settings(
                environment="production",
                otp_pepper_secret="default_test_pepper_secret_32_bytes_len",
                database_url="postgresql://postgres:password@localhost:5432/jainune_dev",
            )
        err_str = str(ctx.exception)
        self.assertIn("Production environment variable audit failed", err_str)
        self.assertIn("otp_pepper_secret", err_str)
        self.assertIn("database_url", err_str)
        self.assertIn("razorpay_key_id", err_str)
        self.assertIn("smtp_host", err_str)
        self.assertIn("fcm_service_account_path", err_str)

        # 2. Production with full valid credentials passes
        prod_settings = Settings(
            environment="production",
            otp_pepper_secret="a_very_secure_prod_pepper_secret_min_32_bytes_long!",
            database_url="postgresql://app_prod:prod_pw_9921@db-cluster.internal.jainune.com:5432/jainune_production",
            razorpay_key_id="rzp_live_k8a92j1h829",
            razorpay_key_secret="live_rzp_secret_key_89218291",
            razorpay_webhook_secret="live_rzp_webhook_secret_prod_99182918",  # F-02/R-02
            aws_access_key_id="AKIA_PROD_LIVE_KEY_992",
            aws_secret_access_key="prod_live_aws_secret_value_39182918",
            msg91_auth_key="msg91_live_auth_token_88291",
            cloudflare_origin_secret="cf_live_origin_tunnel_secret_9918",
            turnstile_secret_key="0x4AAAAAA_live_turnstile_secret_8819",
            sentry_dsn="https://mock_sentry_key@o992.ingest.sentry.io/18291",
            metrics_secret_token="prod_metrics_secret_token_12345678",
            google_client_id="prod_google_client_id_live_99182.apps.googleusercontent.com",
            apple_bundle_id="com.jainune.app",
            smtp_host="smtp.sendgrid.net",
            fcm_service_account_path=__file__,
            jwt_secret_key="prod_jwt_hmac_secret_key_very_secure_min_32_bytes!",  # F-02
            store_webhook_secret="prod_store_webhook_secret_apple_google_99182",  # F-06
        )
        self.assertEqual(prod_settings.environment, "production")

        # 3. Development environment allows default test secrets
        dev_settings = Settings(environment="development")
        self.assertEqual(dev_settings.environment, "development")

    def test_42_dockerfile_security_and_non_root_specs(self):
        """Verify Dockerfile and docker-compose.prod.yml adhere to non-root UID 10001 and safe capabilities."""
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent.parent.parent

        dockerfile_path = backend_dir / "Dockerfile"
        self.assertTrue(dockerfile_path.exists())
        dockerfile_content = dockerfile_path.read_text(encoding="utf-8")

        # Check explicit non-root UID/GID 10001 and home dir
        self.assertIn("10001", dockerfile_content)
        self.assertIn("-m -d /home/appuser", dockerfile_content)
        self.assertIn("USER 10001:10001", dockerfile_content)
        self.assertIn("--chown=10001:10001", dockerfile_content)

        # Check absence of wildcard forwarded IPs
        self.assertNotIn('--forwarded-allow-ips "*"', dockerfile_content)

        # Check docker-compose.prod.yml security options
        compose_path = backend_dir / "docker-compose.prod.yml"
        self.assertTrue(compose_path.exists())
        compose_content = compose_path.read_text(encoding="utf-8")
        self.assertIn("no-new-privileges:true", compose_content)
        self.assertIn("cap_drop:", compose_content)
        self.assertIn("ALL", compose_content)
        self.assertIn('user: "10001:10001"', compose_content)
        self.assertIn("init: true", compose_content)

    def test_43_database_migration_rollbacks_0001_through_0010(self):
        """Verify reversible down-migration scripts exist for migrations 0001-0010 and parse valid SQL blocks."""
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent.parent.parent
        down_dir = backend_dir / "migrations" / "down"
        self.assertTrue(down_dir.exists(), "Down migrations directory must exist")

        expected_versions = [
            "0001_initial_schema",
            "0002_postgis_pgvector",
            "0003_rls_security_policies",
            "0004_location_geofence_and_waitlist",
            "0005_chat_safety_and_moderation",
            "0006_complete_monetization_and_schema_reconciliation",
            "0007_production_domain_reconciliation",
            "0008_multiprovider_auth_and_account_cleanup",
            "0009_performance_indexes",
            "0010_database_audit_reconciliation",
        ]

        for ver in expected_versions:
            down_file = down_dir / f"{ver}.down.sql"
            self.assertTrue(down_file.exists(), f"Missing down migration: {down_file.name}")
            sql = down_file.read_text(encoding="utf-8").strip()
            self.assertIn("BEGIN;", sql, f"{down_file.name} must include transactional BEGIN;")
            self.assertTrue(sql.endswith("COMMIT;"), f"{down_file.name} must end with transactional COMMIT;")

    def test_44_sentry_pii_scrubbing_and_prometheus_metrics(self):
        """Verify Sentry PII scrubbing, error fingerprinting, and Prometheus metric text exposition format."""
        from app.core.sentry import scrub_pii_from_dict, sentry_before_send
        from app.core.metrics import PrometheusRegistry

        # 1. PII Scrubbing
        sensitive_payload = {
            "headers": {
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.test",
                "Cookie": "session_id=secret_cookie_val",
                "User-Agent": "Jainune-App/1.0",
            },
            "data": {
                "phone_number": "+919876543210",
                "otp": "123456",
                "message": "Call me at +919876543210 or 9876543210",
                "normal_field": "Hello world",
            },
        }
        scrubbed = scrub_pii_from_dict(sensitive_payload)
        self.assertEqual(scrubbed["headers"]["Authorization"], "[SCRUBBED]")
        self.assertEqual(scrubbed["headers"]["Cookie"], "[SCRUBBED]")
        self.assertEqual(scrubbed["headers"]["User-Agent"], "Jainune-App/1.0")
        self.assertEqual(scrubbed["data"]["phone_number"], "[SCRUBBED]")
        self.assertEqual(scrubbed["data"]["otp"], "[SCRUBBED]")
        self.assertIn("[PHONE_SCRUBBED]", scrubbed["data"]["message"])
        self.assertEqual(scrubbed["data"]["normal_field"], "Hello world")

        # 2. Sentry Error Fingerprinting
        class MockPostgresError(Exception):
            pass
        MockPostgresError.__module__ = "asyncpg.exceptions"

        event = {"request": {"headers": {"Authorization": "Bearer secret_tok"}}}
        hint = {"exc_info": (MockPostgresError, MockPostgresError("connection closed"), None)}
        processed = sentry_before_send(event, hint)
        self.assertEqual(processed["fingerprint"], ["database-error", "MockPostgresError"])
        self.assertEqual(processed["request"]["headers"]["Authorization"], "[SCRUBBED]")

        # 3. Prometheus Metric Registry
        reg = PrometheusRegistry()
        reg.record_request_start()
        self.assertEqual(reg.in_progress, 1)

        reg.record_request_end(method="GET", endpoint="/v1/feed", status=200, duration_seconds=0.045)
        self.assertEqual(reg.in_progress, 0)
        self.assertEqual(reg.request_counts[("GET", "/v1/feed", "200")], 1)

        output = reg.generate_prometheus_output(version="1.0.0", environment="production")
        self.assertIn("# HELP http_requests_total", output)
        self.assertIn('# TYPE http_requests_total counter', output)
        self.assertIn('http_requests_total{endpoint="/v1/feed",method="GET",status="200"} 1', output)
        self.assertIn("# HELP http_request_duration_seconds", output)
        self.assertIn('# TYPE http_request_duration_seconds histogram', output)
        self.assertIn('http_request_duration_seconds_bucket{endpoint="/v1/feed",le="0.05",method="GET"} 1', output)
        self.assertIn('app_build_info{environment="production",version="1.0.0"} 1', output)


if __name__ == "__main__":
    unittest.main()



