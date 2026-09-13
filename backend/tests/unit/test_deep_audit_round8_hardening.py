"""
Unit tests for Deep Audit Round 8 Hardening (R8-1 to R8-4).

Covers:
R8-1: Reciprocal candidate orientation filter in live feed query (_run_pipeline).
R8-2: Media moderation race condition protection with atomic status = 'processing' guards.
R8-3: Account soft-delete user_devices push notification token purging.
R8-4: Case-insensitive and alias normalization for settings.environment.
"""

import sys
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

if "botocore.config" not in sys.modules:
    sys.modules["botocore.config"] = MagicMock()

from app.core.config import Settings


class TestDeepAuditRound8Hardening(unittest.IsolatedAsyncioTestCase):

    # -----------------------------------------------------------------------
    # R8-4: Case-insensitive and alias normalization for settings.environment
    # -----------------------------------------------------------------------
    def test_01_environment_normalization(self):
        """Settings.environment should normalize casing, whitespace, and prod aliases."""
        s1 = Settings(environment="Development")
        self.assertEqual(s1.environment, "development")

        s2 = Settings(environment="  DEV  ")
        self.assertEqual(s2.environment, "development")

        s3 = Settings(environment="TESTING")
        self.assertEqual(s3.environment, "testing")

        # In production mode without prod env vars, validator should trigger
        # confirming that "Production" / "PROD" was normalized to "production".
        with self.assertRaises(ValueError) as ctx1:
            Settings(environment="Production")
        self.assertIn("Production environment variable audit failed", str(ctx1.exception))

        with self.assertRaises(ValueError) as ctx2:
            Settings(environment="  PROD  ")
        self.assertIn("Production environment variable audit failed", str(ctx2.exception))

        with self.assertRaises(ValueError) as ctx3:
            Settings(environment="PRODUCTION")
        self.assertIn("Production environment variable audit failed", str(ctx3.exception))

    # -----------------------------------------------------------------------
    # R8-2: Media moderation race condition protection
    # -----------------------------------------------------------------------
    @patch("app.services.media_processor._check_s3_size", return_value=(True, None))
    @patch("app.services.media_processor.get_pool")
    @patch("app.services.media_processor._rekognition_check")
    @patch("app.services.media_processor._delete_from_quarantine")
    async def test_02_media_moderation_guard_prevents_overwrite(
        self, mock_del_quarantine, mock_rekog, mock_get_pool, mock_s3_size
    ):
        """If media status was already changed, rejection should not downgrade user status."""
        from app.services.media_processor import _run_moderation

        mock_rekog.return_value = ("rejected", "EXPLICIT_CONTENT")

        executed_queries = []
        mock_conn = AsyncMock()

        async def track_execute(query, *args):
            executed_queries.append((query, args))
            # Simulate race: row is already approved, so 0 rows updated
            if "UPDATE user_media" in query:
                return "UPDATE 0"
            return "UPDATE 1"

        mock_conn.execute.side_effect = track_execute
        mock_conn.fetchval.return_value = 0

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx
        mock_get_pool.return_value = mock_db

        media_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await _run_moderation(media_id, "uploads/pic.jpg", "photo", user_id)

        # Confirm UPDATE query included AND status = 'processing'
        media_updates = [q for q, args in executed_queries if "UPDATE user_media" in q and "status = 'rejected'" in q]
        self.assertTrue(len(media_updates) >= 1)
        self.assertIn("status = 'processing'", media_updates[0])

        # Confirm users table was NOT downgraded to pending_media because UPDATE returned "UPDATE 0"
        downgrade_updates = [q for q, args in executed_queries if "pending_media" in q]
        self.assertEqual(len(downgrade_updates), 0)

    @patch("app.services.media_processor._check_s3_size", return_value=(False, "File too large"))
    @patch("app.services.media_processor.get_pool")
    @patch("app.services.media_processor._delete_from_quarantine")
    async def test_02b_s3_size_failure_guard(
        self, mock_del_quarantine, mock_get_pool, mock_s3_size
    ):
        """S3 size failure rejection query must also include status = 'processing' guard."""
        from app.services.media_processor import _run_moderation

        executed_queries = []
        mock_conn = AsyncMock()

        async def track_execute(query, *args):
            executed_queries.append((query, args))
            return "UPDATE 1"

        mock_conn.execute.side_effect = track_execute
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx
        mock_get_pool.return_value = mock_db

        media_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await _run_moderation(media_id, "uploads/pic.jpg", "photo", user_id)

        media_updates = [q for q, args in executed_queries if "UPDATE user_media" in q and "status = 'rejected'" in q]
        self.assertTrue(len(media_updates) >= 1)
        self.assertIn("status = 'processing'", media_updates[0])

    # -----------------------------------------------------------------------
    # R8-3: Account soft-delete user_devices push notification token purging
    # -----------------------------------------------------------------------
    async def test_03_account_soft_delete_purges_user_devices(self):
        """Soft delete must delete both refresh_tokens and user_devices."""
        from app.services.account_service import soft_delete_user_account

        executed_queries = []
        mock_conn = AsyncMock()

        async def track_execute(query, *args):
            executed_queries.append((query, args))
            return "DELETE 1"

        mock_conn.execute.side_effect = track_execute
        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        user_id = uuid.uuid4()
        mock_redis = AsyncMock()
        mock_conn.fetch.return_value = []
        res = await soft_delete_user_account(user_id, mock_conn, mock_redis, "Closing account")
        self.assertEqual(res["status"], "soft_deleted")

        deleted_tables = [
            q for q, args in executed_queries
            if "DELETE FROM" in q
        ]
        self.assertTrue(any("user_devices" in q for q in deleted_tables))
        self.assertTrue(any("refresh_tokens" in q for q in deleted_tables))

    # -----------------------------------------------------------------------
    # R8-1: Reciprocal candidate orientation filter in live feed query
    # -----------------------------------------------------------------------
    async def test_04_reciprocal_gender_filter_in_pipeline(self):
        """_run_pipeline must pass caller's gender and filter candidate's show_me reciprocally."""
        from app.services.core_people_finder import _run_pipeline

        mock_conn = AsyncMock()
        executed_query = None
        query_args = None

        async def track_fetch(query, *args):
            nonlocal executed_query, query_args
            executed_query = query
            query_args = args
            return []

        mock_conn.fetch.side_effect = track_fetch
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        user_id = uuid.uuid4()
        user_data = {
            "gender": "man",
            "show_me": "women",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "is_incognito": False,
            "max_distance_km": 50,
            "age_min": 20,
            "age_max": 35,
            "interested_in": ["women"],
        }

        await _run_pipeline(user_id, user_data, mock_db, internal_limit=10)

        self.assertIsNotNone(executed_query)
        self.assertIn("u.show_me", executed_query)
        # Reciprocal clause checking candidate's show_me against caller gender ($14)
        self.assertIn("$14::text IS NULL", executed_query)
        self.assertIn("u.show_me = 'everyone'", executed_query)
        # Verify caller gender passed as $14 argument
        self.assertIn("man", query_args)

    # -----------------------------------------------------------------------
    # FINDING-01: Auto-assign free slot & prevent slot 1 overwrite
    # -----------------------------------------------------------------------
    @patch("boto3.client")
    async def test_05_upload_request_auto_assigns_free_slot(self, mock_boto):
        """When position is None, request_upload auto-assigns next free slot (e.g. 2 when 1 is occupied)."""
        from app.routers.media import request_upload, UploadRequestBody

        mock_s3 = MagicMock()
        mock_s3.generate_presigned_post.return_value = {"url": "https://s3.example.com", "fields": {}}
        mock_boto.return_value = mock_s3

        executed_inserts = []
        mock_conn = AsyncMock()

        async def track_fetch(query, *args):
            if "SELECT position, status" in query:
                return [{"position": 1, "status": "approved", "s3_key": "uploads/u1/photo/m1.jpg"}]
            return []

        async def track_execute(query, *args):
            if "INSERT INTO user_media" in query:
                executed_inserts.append(args)
            return "INSERT 1"

        mock_conn.fetch.side_effect = track_fetch
        mock_conn.execute.side_effect = track_execute
        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        current_user = {"id": uuid.uuid4(), "role": "user"}
        mock_redis = AsyncMock()

        body = UploadRequestBody(
            media_type="photo",
            content_type="image/jpeg",
            file_size_bytes=1024 * 500,
            position=None,
        )

        res = await request_upload(body, current_user, mock_db, mock_redis)
        self.assertIsNotNone(res.media_id)
        self.assertEqual(len(executed_inserts), 1)
        # Position is argument $5 in INSERT query
        target_pos = executed_inserts[0][4]
        self.assertEqual(target_pos, 2)

    @patch("app.services.media_processor._delete_from_quarantine")
    @patch("boto3.client")
    async def test_06_upload_request_cleans_up_replaced_s3_key(self, mock_boto, mock_del_quarantine):
        """Explicit slot replacement deletes old quarantined S3 object to prevent orphaning."""
        from app.routers.media import request_upload, UploadRequestBody

        mock_s3 = MagicMock()
        mock_s3.generate_presigned_post.return_value = {"url": "https://s3.example.com", "fields": {}}
        mock_boto.return_value = mock_s3

        mock_conn = AsyncMock()

        async def track_fetch(query, *args):
            if "SELECT position, status" in query:
                return [{"position": 1, "status": "pending", "s3_key": "uploads/u1/photo/old_pic.jpg"}]
            return []

        mock_conn.fetch.side_effect = track_fetch
        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        current_user = {"id": uuid.uuid4(), "role": "user"}
        mock_redis = AsyncMock()

        body = UploadRequestBody(
            media_type="photo",
            content_type="image/jpeg",
            file_size_bytes=1024 * 500,
            position=1,
        )

        res = await request_upload(body, current_user, mock_db, mock_redis)
        self.assertIsNotNone(res.media_id)
        mock_del_quarantine.assert_called_once_with("uploads/u1/photo/old_pic.jpg")

    # -----------------------------------------------------------------------
    # FINDING-03: Proactive session replacement notification
    # -----------------------------------------------------------------------
    @patch("app.routers.auth.get_redis")
    async def test_07_login_replaces_session_and_publishes_force_disconnect(self, mock_get_redis):
        """When user logs in with an existing active session, force_disconnect is published to user commands."""
        import json
        from app.routers.auth import _issue_token_response

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = "old_token_hash_value"
        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        user_id = uuid.uuid4()
        res = await _issue_token_response(user_id, False, True, mock_conn)
        self.assertIn("access_token", res["data"])
        mock_redis.set.assert_called()
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args[0]
        self.assertEqual(call_args[0], f"user:{user_id}:commands")
        payload = json.loads(call_args[1])
        self.assertEqual(payload["type"], "force_disconnect")
        self.assertIn("another device", payload["reason"])

    @patch("app.routers.auth.validate_access_token")
    @patch("app.routers.auth.sliding_window_rate_limit")
    @patch("app.routers.auth.revoke_token")
    async def test_08_logout_all_devices_publishes_force_disconnect(self, mock_revoke, mock_rate, mock_val):
        """When user logs out with all_devices=True, force_disconnect is published to kick all active sessions."""
        import json
        from app.routers.auth import logout_endpoint
        from app.models.schemas.auth import LogoutBody

        mock_val.return_value = {"jti": "test-jti", "exp": 9999999999}
        user_id = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        mock_redis = AsyncMock()
        credentials = MagicMock()
        body = LogoutBody(all_devices=True)

        res = await logout_endpoint(
            current_user={"id": str(user_id)},
            db=mock_db,
            redis=mock_redis,
            body=body,
            credentials=credentials,
        )
        self.assertTrue(res["success"])
        self.assertIn("message", res["data"])
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args[0]
        self.assertEqual(call_args[0], f"user:{user_id}:commands")
        payload = json.loads(call_args[1])
        self.assertEqual(payload["type"], "force_disconnect")


if __name__ == "__main__":
    unittest.main()
