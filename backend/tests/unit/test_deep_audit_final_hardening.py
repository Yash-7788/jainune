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
            self.assertTrue(any("super_connect_credits    = GREATEST(0, COALESCE(super_connect_credits, 0) - 5)" in s for s in executed_sqls))

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


if __name__ == "__main__":
    unittest.main()

