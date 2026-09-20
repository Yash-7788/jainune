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

if "supabase" not in sys.modules:
    sys.modules["supabase"] = MagicMock()

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
    async def test_02_media_moderation_guard_prevents_overwrite(self):
        """If media status was already resolved, moderation guard prevents overwrite."""
        from app.services.moderation import run_photo_moderation

        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "id": photo_id,
            "user_id": user_id,
            "status": "approved",
            "cdn_url": "https://cdn.jainune.com/avatar.webp",
        }
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_ctx

        res = await run_photo_moderation(photo_id, user_id, pool=mock_pool)
        self.assertTrue(res.is_safe)
        self.assertEqual(res.reason, "Already approved")
        mock_conn.execute.assert_not_called()

    async def test_02b_s3_size_failure_guard(self):
        """If photo record does not exist, moderation gracefully returns failure."""
        from app.services.moderation import run_photo_moderation

        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_ctx

        res = await run_photo_moderation(photo_id, user_id, pool=mock_pool)
        self.assertIsNone(res.is_safe)
        self.assertEqual(res.reason, "Photo not found")

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
    # FINDING-01: Supabase avatar signed upload URL and overwrite
    # -----------------------------------------------------------------------
    @patch("app.routers.media.generate_supabase_upload_signed_url")
    @patch("app.routers.media.sliding_window_rate_limit", AsyncMock())
    async def test_05_upload_request_auto_assigns_free_slot(self, mock_gen_url):
        """request_upload assigns avatar slot 1 and returns Supabase signed URL."""
        from app.routers.media import request_upload, UploadRequestBody

        mock_gen_url.return_value = {
            "signed_url": "https://supabase.co/signed/avatar.webp",
            "path": "user1/avatar.webp",
            "cdn_url": "https://cdn.jainune.com/avatar.webp",
        }

        executed_inserts = []
        mock_conn = AsyncMock()

        async def track_execute(query, *args):
            if "INSERT INTO user_photos" in query:
                executed_inserts.append(args)
            return "INSERT 1"

        mock_conn.execute.side_effect = track_execute
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}
        mock_redis = AsyncMock()

        body = UploadRequestBody(
            media_type="photo",
            content_type="image/webp",
            file_size_bytes=1024 * 10,
        )

        res = await request_upload(body, current_user, mock_db, mock_redis)
        self.assertIsNotNone(res.media_id)
        self.assertEqual(res.signed_url, "https://supabase.co/signed/avatar.webp")
        self.assertEqual(len(executed_inserts), 1)
        self.assertEqual(executed_inserts[0][2], f"{user_id}/avatar.webp")

    @patch("app.routers.media.generate_supabase_upload_signed_url")
    @patch("app.routers.media.sliding_window_rate_limit", AsyncMock())
    async def test_06_upload_request_cleans_up_replaced_s3_key(self, mock_gen_url):
        """request_upload upserts avatar slot to overwrite previous upload intent."""
        from app.routers.media import request_upload, UploadRequestBody

        mock_gen_url.return_value = {
            "signed_url": "https://supabase.co/signed/new.webp",
            "path": "user1/avatar.webp",
            "cdn_url": "https://cdn.jainune.com/avatar.webp",
        }

        executed_queries = []
        mock_conn = AsyncMock()

        async def track_execute(query, *args):
            executed_queries.append(query)
            return "INSERT 1"

        mock_conn.execute.side_effect = track_execute
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}
        mock_redis = AsyncMock()

        body = UploadRequestBody(
            media_type="photo",
            content_type="image/webp",
            file_size_bytes=1024 * 10,
        )

        res = await request_upload(body, current_user, mock_db, mock_redis)
        self.assertIsNotNone(res.media_id)
        self.assertTrue(any("ON CONFLICT (user_id, position) DO UPDATE" in q for q in executed_queries))

    # -----------------------------------------------------------------------
    # FINDING-03: Proactive session replacement notification
    # -----------------------------------------------------------------------
    @patch("app.routers.auth.ws_manager.disconnect_user", new_callable=AsyncMock)
    async def test_07_login_replaces_session_and_publishes_force_disconnect(self, mock_disconnect):
        """When user logs in with an existing active session, force_disconnect is triggered via ws_manager."""
        from app.routers.auth import _issue_token_response

        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = "old_token_hash_value"
        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        user_id = uuid.uuid4()
        res = await _issue_token_response(user_id, False, True, mock_conn)
        self.assertIn("access_token", res["data"])
        mock_disconnect.assert_called_once()
        self.assertEqual(mock_disconnect.call_args[0][0], str(user_id))
        self.assertIn("another device", mock_disconnect.call_args[1]["reason"])

    @patch("app.routers.auth.ws_manager.disconnect_user", new_callable=AsyncMock)
    @patch("app.routers.auth.validate_access_token")
    @patch("app.routers.auth.sliding_window_rate_limit")
    @patch("app.routers.auth.revoke_token")
    async def test_08_logout_all_devices_publishes_force_disconnect(self, mock_revoke, mock_rate, mock_val, mock_disconnect):
        """When user logs out with all_devices=True, disconnect is triggered on ws_manager."""
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
        mock_disconnect.assert_called_once()
        self.assertEqual(mock_disconnect.call_args[0][0], str(user_id))
        self.assertIn("all devices", mock_disconnect.call_args[1]["reason"])

    # -----------------------------------------------------------------------
    # FINDING-04: Chat message idempotency key & deduplication
    # -----------------------------------------------------------------------
    @patch("app.routers.chats._assert_participant")
    @patch("app.routers.chats.sliding_window_rate_limit")
    async def test_09_send_message_deduplicates_by_idempotency_key(self, mock_rate, mock_assert):
        """When sending a message with existing idempotency_key, existing row is returned without duplicate insert or pub/sub."""
        from datetime import datetime, timezone
        from app.routers.chats import send_message
        from app.models.schemas.chat import SendMessageRequest

        chat_id = uuid.uuid4()
        user_id = uuid.uuid4()
        existing_msg_id = uuid.uuid4()
        mock_assert.return_value = {
            "id": chat_id,
            "match_id": uuid.uuid4(),
            "participant_1_id": user_id,
            "participant_2_id": uuid.uuid4(),
            "is_unmatched": False,
            "is_expired": False,
        }

        mock_conn = AsyncMock()
        existing_row = {
            "id": existing_msg_id,
            "chat_id": chat_id,
            "sender_id": user_id,
            "message_type": "text",
            "content": "Jai Jinendra",
            "media_url": None,
            "is_read": False,
            "created_at": datetime.now(timezone.utc),
            "is_moderated": False,
            "moderation_type": None,
            "moderation_disclaimer": None,
            "idempotency_key": "idemp-key-123",
        }
        mock_conn.fetchrow.return_value = existing_row

        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        mock_redis = AsyncMock()
        body = SendMessageRequest(
            content="Jai Jinendra",
            idempotency_key="idemp-key-123",
        )

        res = await send_message(
            chat_id=chat_id,
            body=body,
            current_user={"id": str(user_id)},
            db=mock_db,
            redis=mock_redis,
            x_idempotency_key=None,
        )

        self.assertEqual(res.id, existing_msg_id)
        self.assertEqual(res.content, "Jai Jinendra")
        self.assertEqual(res.idempotency_key, "idemp-key-123")
        # Ensure no second pub/sub broadcast fired
        mock_redis.publish.assert_not_called()

    @patch("app.routers.chats._assert_participant")
    @patch("app.routers.chats.sliding_window_rate_limit")
    @patch("app.routers.chats.get_effective_user_tier", return_value="free")
    async def test_10_send_message_without_idempotency_key_inserts_normally(self, mock_tier, mock_rate, mock_assert):
        """Older clients without idempotency key insert and publish normally."""
        from datetime import datetime, timezone
        from app.routers.chats import send_message
        from app.models.schemas.chat import SendMessageRequest

        chat_id = uuid.uuid4()
        user_id = uuid.uuid4()
        other_id = uuid.uuid4()
        msg_id = uuid.uuid4()
        mock_assert.return_value = {
            "id": chat_id,
            "match_id": uuid.uuid4(),
            "participant_1_id": user_id,
            "participant_2_id": other_id,
            "is_unmatched": False,
            "is_expired": False,
        }

        mock_conn = AsyncMock()
        new_row = {
            "id": msg_id,
            "chat_id": chat_id,
            "sender_id": user_id,
            "message_type": "text",
            "content": "Hello",
            "media_url": None,
            "is_read": False,
            "created_at": datetime.now(timezone.utc),
            "is_moderated": False,
            "moderation_type": None,
            "moderation_disclaimer": None,
            "idempotency_key": None,
        }

        async def track_fetchrow(query, *args):
            if "INSERT INTO messages" in query:
                return new_row
            return None

        mock_conn.fetchrow.side_effect = track_fetchrow
        mock_conn.fetchval.return_value = None  # not blocked, recipient active

        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = None
        mock_db = MagicMock()
        mock_db.acquire.return_value = mock_ctx

        mock_redis = AsyncMock()
        body = SendMessageRequest(content="Hello")

        with patch("app.routers.chats.ws_manager.broadcast_chat", new_callable=AsyncMock) as mock_broadcast:
            res = await send_message(
                chat_id=chat_id,
                body=body,
                current_user={"user_id": str(user_id)},
                db=mock_db,
                redis=mock_redis,
            )

            self.assertEqual(res.id, msg_id)
            self.assertEqual(res.content, "Hello")
            mock_broadcast.assert_called_once()

    def test_11_all_migration_files_have_down_migrations(self):
        """All backend/migrations/*.sql files must have matching down/*.down.sql."""
        from pathlib import Path
        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        down_dir = migrations_dir / "down"

        up_files = {p.stem for p in migrations_dir.glob("*.sql")}
        down_files = {p.stem.replace(".down", "") for p in down_dir.glob("*.down.sql")}

        missing = up_files - down_files
        self.assertEqual(missing, set(), f"Missing down migrations for: {missing}")

    async def test_12_run_migrations_get_current_version(self):
        """get_current_version prints the latest applied version or NONE."""
        import io
        import sys
        from pathlib import Path
        from unittest.mock import patch

        backend_root = str(Path(__file__).resolve().parents[2])
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)
        import run_migrations

        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = "schema_migrations"
        mock_conn.fetchrow.return_value = {"version": "0025_messages_idempotency_key.sql"}
        mock_conn.close.return_value = None

        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            await run_migrations.get_current_version()
            self.assertEqual(mock_out.getvalue().strip(), "0025_messages_idempotency_key.sql")

        # When table does not exist
        mock_conn.fetchval.return_value = None
        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            await run_migrations.get_current_version()
            self.assertEqual(mock_out.getvalue().strip(), "NONE")

    async def test_13_run_migrations_rollback_target_version(self):
        """rollback_migrations stops at target_version and deletes schema_migrations entries."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        backend_root = str(Path(__file__).resolve().parents[2])
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)
        import run_migrations

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"version": "0025_messages_idempotency_key.sql"},
            {"version": "0024_matches_status_check_and_liked_me_pagination.sql"},
            {"version": "0023_user_devices.sql"},
        ]
        mock_conn.execute.return_value = None
        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_conn.close.return_value = None

        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
            await run_migrations.rollback_migrations(steps=None, target_version="0024_matches_status_check_and_liked_me_pagination.sql")

        # 0025 was rolled back, but 0024 was target, so stopped at 0024.
        delete_calls = [call for call in mock_conn.execute.call_args_list if "DELETE FROM schema_migrations" in str(call)]
        self.assertEqual(len(delete_calls), 1)
        self.assertIn("0025_messages_idempotency_key.sql", str(delete_calls[0]))

    def test_14_deploy_prod_workflow_has_automated_rollback(self):
        """deploy-prod.yml must capture PREV_IMAGE / PREV_MIGRATION and execute rollback."""
        from pathlib import Path
        import yaml

        workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "deploy-prod.yml"
        self.assertTrue(workflow_path.exists())

        content = workflow_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        self.assertIn("jobs", parsed)

        # Ensure rollback and state capture logic exist in script
        self.assertIn("PREV_IMAGE=$(docker inspect", content)
        self.assertIn("PREV_MIGRATION=$(docker compose", content)
        self.assertIn("Preflight sanity check", content)
        self.assertIn("=== INITIATING AUTOMATIC ROLLBACK ===", content)
        self.assertIn("run_migrations.py --to-version", content)
        self.assertIn('export BACKEND_IMAGE="$PREV_IMAGE"', content)
        self.assertIn(".current_backend_image", content)

    async def test_15_envelope_and_legal_coverage(self):
        """Verify response envelopes and legal routes."""
        from app.core.responses import ok, err
        from app.routers.legal import robots_txt, privacy_policy

        # Responses ok and err branches
        ok_res = ok({"data": 1}, meta={"test": True})
        self.assertTrue(ok_res["success"])
        self.assertTrue(ok_res["meta"]["test"])

        err_res = err("TEST_ERROR", "Error msg", details=["some_detail"])
        self.assertFalse(err_res["success"])
        self.assertEqual(err_res["error"]["code"], "TEST_ERROR")
        self.assertEqual(err_res["error"]["details"], ["some_detail"])

        # Legal routes
        rob = robots_txt()
        self.assertIn("User-agent", rob.body.decode())
        priv = await privacy_policy()
        self.assertIn("Introduction", priv)
        from app.routers.legal import terms_of_service, child_safety_standards, community_guidelines
        terms = await terms_of_service()
        self.assertIn("Eligibility", terms)
        child = await child_safety_standards()
        self.assertIn("Child Safety", child)
        guidelines = await community_guidelines()
        self.assertIn("Ahimsa", guidelines)

    async def test_16_upload_validation_errors(self):
        """Verify request_upload validates content-type and rejects retired media types."""
        from pydantic import ValidationError
        from fastapi import HTTPException
        from app.routers.media import request_upload, UploadRequestBody

        mock_user = {"user_id": str(uuid.uuid4())}
        mock_db = MagicMock()
        mock_redis = AsyncMock()

        # Invalid photo content type
        b1 = UploadRequestBody(media_type="photo", content_type="application/pdf", file_size_bytes=1000)
        with self.assertRaises(HTTPException) as ctx:
            await request_upload(b1, mock_user, mock_db, mock_redis)
        self.assertEqual(ctx.exception.status_code, 400)

        # Voice media_type rejected at schema level
        with self.assertRaises(ValidationError):
            UploadRequestBody(media_type="voice", content_type="audio/m4a", file_size_bytes=1000)


if __name__ == "__main__":
    unittest.main()
