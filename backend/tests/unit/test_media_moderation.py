"""
Unit tests for Bug 7 (Content Moderation Gate & Admin Review) and Bug 8 (python-multipart CVE).
"""
import asyncio
import json
import re
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from app.services.moderation import (
    CloudflareVisionModerationClient,
    ModerationResult,
    run_photo_moderation,
    get_photo_lock,
)


class TestBug8PythonMultipartVersion(unittest.TestCase):
    @classmethod
    def _read_requirements(cls) -> str:
        from pathlib import Path
        cur = Path(__file__).resolve()
        candidates = [
            cur.parents[2] / "requirements.txt",
            cur.parents[1] / "requirements.txt",
            Path("requirements.txt"),
            Path("backend/requirements.txt"),
        ]
        for p in candidates:
            if p.exists() and p.is_file():
                return p.read_text(encoding="utf-8")
        raise FileNotFoundError("requirements.txt not found in candidate paths")

    def test_python_multipart_cve_fix_in_requirements(self):
        content = self._read_requirements()
        match = re.search(r"python-multipart\s*([>=<]+)\s*([\d\.]+)", content)
        self.assertIsNotNone(match, "python-multipart not found in requirements.txt")
        op, ver = match.groups()
        ver_tuple = tuple(map(int, ver.split(".")))
        self.assertGreaterEqual(
            ver_tuple,
            (0, 0, 18),
            f"python-multipart must be >=0.0.18 to fix CVE-2024-53981, found {op}{ver}",
        )

    def test_cve_dependency_bumps_in_requirements(self):
        content = self._read_requirements()

        # Item 9: Pillow intentionally REMOVED per OPTIMIZE.md §9.1
        # Server-side image loading (Pillow) causes 48 MB RAM spike per upload → OOM on 512 MB Render.
        # Client sends WebP directly; server does magic-byte validation only.
        # This assertion verifies Pillow has NOT been re-added.
        pillow_match = re.search(r"Pillow\s*([>=<]+)\s*([\d\.]+)", content)
        self.assertIsNone(pillow_match, (
            "Pillow must NOT be in requirements.txt (OPTIMIZE.md §9.1): "
            "server-side PIL causes OOM on 512 MB Render. Use client-side WebP compression."
        ))

        # Item 10: cryptography >= 43.0.0 (CVE-2024-12797)
        crypto_match = re.search(r"cryptography\s*([>=<]+)\s*([\d\.]+)", content)
        self.assertIsNotNone(crypto_match, "cryptography not found in requirements.txt")
        c_op, c_ver = crypto_match.groups()
        self.assertGreaterEqual(
            tuple(map(int, c_ver.split("."))),
            (43, 0, 0),
            f"cryptography must be >=43.0.0 to fix CVE-2024-12797, found {c_op}{c_ver}",
        )

        # Item 11: fastapi >= 0.115.0 (CVE-2024-47874 via Starlette >= 0.40.0)
        fastapi_match = re.search(r"fastapi\s*([>=<]+)\s*([\d\.]+)", content)
        self.assertIsNotNone(fastapi_match, "fastapi not found in requirements.txt")
        f_op, f_ver = fastapi_match.groups()
        self.assertGreaterEqual(
            tuple(map(int, f_ver.split("."))),
            (0, 115, 0),
            f"fastapi must be >=0.115.0 to fix CVE-2024-47874, found {f_op}{f_ver}",
        )


class TestCloudflareVisionModerationClient(unittest.IsolatedAsyncioTestCase):
    """Tests for Cloudflare Workers AI single-token hybrid output moderation."""

    def setUp(self):
        from app.core.config import settings
        self._orig_acc = settings.cloudflare_account_id
        self._orig_tok = settings.cloudflare_api_token
        settings.cloudflare_account_id = "test_cf_account_id"
        settings.cloudflare_api_token = "test_cf_api_token"
        self._sleep_patcher = patch("asyncio.sleep", AsyncMock())
        self._sleep_patcher.start()

    def tearDown(self):
        self._sleep_patcher.stop()
        from app.core.config import settings
        settings.cloudflare_account_id = self._orig_acc
        settings.cloudflare_api_token = self._orig_tok

    async def test_pass_token_returns_safe(self):
        """Single-token PASS → is_safe=True, reason='clean'."""
        client = CloudflareVisionModerationClient()

        def mock_handler(request: httpx.Request):
            return httpx.Response(200, json={"result": {"response": "PASS"}})

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            result = await client.moderate_image_bytes(b"swimwear_bytes", http_client=http)

        self.assertTrue(result.is_safe)
        self.assertEqual(result.reason, "clean")
        self.assertAlmostEqual(result.confidence, 0.95)

    async def test_nudity_token_returns_rejection(self):
        """Single-token 'nudity' → is_safe=False, reason='nudity'."""
        client = CloudflareVisionModerationClient()

        def mock_handler(request: httpx.Request):
            return httpx.Response(200, json={"result": {"response": "nudity"}})

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            result = await client.moderate_image_bytes(b"nsfw_bytes", http_client=http)

        self.assertFalse(result.is_safe)
        self.assertEqual(result.reason, "nudity")

    async def test_all_valid_reject_tags_produce_rejection(self):
        """All 8 reject tags are correctly classified as rejections."""
        tags = ["nudity", "csam", "weapon", "gore", "contact", "ad", "celebrity", "morph"]
        client = CloudflareVisionModerationClient()
        for tag in tags:
            def make_handler(t):
                def mock_handler(request: httpx.Request):
                    return httpx.Response(200, json={"result": {"response": t}})
                return mock_handler
            transport = httpx.MockTransport(make_handler(tag))
            async with httpx.AsyncClient(transport=transport) as http:
                result = await client.moderate_image_bytes(b"test_bytes", http_client=http)
            self.assertFalse(result.is_safe, f"Expected rejection for tag '{tag}'")
            self.assertEqual(result.reason, tag)

    async def test_rate_limit_429_returns_pending(self):
        """HTTP 429 from CF → is_safe=None (pending for admin review)."""
        client = CloudflareVisionModerationClient()

        def mock_handler(request: httpx.Request):
            return httpx.Response(429, json={"errors": [{"message": "rate limited"}]})

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            result = await client.moderate_image_bytes(b"dummy_bytes", http_client=http)

        self.assertIsNone(result.is_safe)
        self.assertEqual(result.reason, "Photo under review")

    async def test_dhash_cache_hit_instant_reject(self):
        """In-memory dHash cache hit → instant rejection with 0 HTTP calls."""
        import app.services.moderation as mod_module
        client = CloudflareVisionModerationClient()
        test_hash = "deadbeefcafe0001"
        mod_module._banned_hashes_cache.add(test_hash)

        called = []

        def mock_handler(request: httpx.Request):
            called.append(request)
            return httpx.Response(200, json={"result": {"response": "PASS"}})

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            result = await client.moderate_image_bytes(b"banned_bytes", dhash=test_hash, http_client=http)

        # No HTTP call made — cache short-circuit
        self.assertEqual(len(called), 0)
        self.assertFalse(result.is_safe)
        self.assertEqual(result.reason, "duplicate")

        # Cleanup
        mod_module._banned_hashes_cache.discard(test_hash)


class TestPhotoModerationPipeline(unittest.IsolatedAsyncioTestCase):
    def _create_mock_pool(self, conn):
        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()
        return pool

    async def test_run_photo_moderation_auto_approves_safe(self):
        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()

        db_state = {
            "photo_status": "pending",
            "photo_cdn": None,
            "user_avatar": None,
        }

        conn = MagicMock()
        async def mock_fetchrow(query, *args):
            if "SELECT id, user_id, status" in query:
                return {
                    "id": photo_id,
                    "user_id": user_id,
                    "status": db_state["photo_status"],
                    "cdn_url": db_state["photo_cdn"],
                }
            return None

        async def mock_execute(query, *args):
            if "UPDATE user_media" in query and "status = 'approved'" in query:
                db_state["photo_status"] = "approved"
                db_state["photo_cdn"] = args[0]
            elif "UPDATE users" in query and "avatar_url" in query:
                db_state["user_avatar"] = args[0]

        conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        conn.execute = AsyncMock(side_effect=mock_execute)
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = self._create_mock_pool(conn)

        def mock_img_handler(request: httpx.Request):
            return httpx.Response(200, content=b"image_data")

        transport = httpx.MockTransport(mock_img_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            moderator = MagicMock()
            moderator.moderate_image_bytes = AsyncMock(
                return_value=ModerationResult(is_safe=True, reason="clean", confidence=0.98)
            )

            result = await run_photo_moderation(
                photo_id=photo_id,
                user_id=user_id,
                pool=pool,
                moderator=moderator,
                http_client=http,
            )

        self.assertTrue(result.is_safe)
        self.assertEqual(db_state["photo_status"], "approved")
        self.assertIsNotNone(db_state["user_avatar"])

    async def test_run_photo_moderation_rejects_unsafe(self):
        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()

        db_state = {
            "photo_status": "pending",
            "photo_cdn": "https://cdn.example.com/old_avatar.webp",
            "user_avatar": "https://cdn.example.com/old_avatar.webp",
        }

        conn = MagicMock()
        async def mock_fetchrow(query, *args):
            return {
                "id": photo_id,
                "user_id": user_id,
                "status": db_state["photo_status"],
                "cdn_url": db_state["photo_cdn"],
            }

        async def mock_execute(query, *args):
            if "UPDATE user_media" in query and "status = 'rejected'" in query:
                db_state["photo_status"] = "rejected"
            elif "UPDATE users SET avatar_url = NULL" in query:
                db_state["user_avatar"] = None

        conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        conn.fetchval = AsyncMock(return_value=True)
        conn.execute = AsyncMock(side_effect=mock_execute)
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = self._create_mock_pool(conn)

        def mock_img_handler(request: httpx.Request):
            return httpx.Response(200, content=b"image_data")

        transport = httpx.MockTransport(mock_img_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            moderator = MagicMock()
            moderator.moderate_image_bytes = AsyncMock(
                return_value=ModerationResult(is_safe=False, reason="nudity", confidence=0.99)
            )

            result = await run_photo_moderation(
                photo_id=photo_id,
                user_id=user_id,
                pool=pool,
                moderator=moderator,
                http_client=http,
            )

        self.assertFalse(result.is_safe)
        self.assertEqual(db_state["photo_status"], "rejected")
        self.assertIsNone(db_state["user_avatar"])

    async def test_single_flight_deduplication_and_idempotency(self):
        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()

        db_state = {"status": "pending"}

        conn = MagicMock()
        async def mock_fetchrow(query, *args):
            return {
                "id": photo_id,
                "user_id": user_id,
                "status": db_state["status"],
                "cdn_url": "https://cdn.example.com/avatar.webp",
            }

        async def mock_execute(query, *args):
            if "UPDATE user_media" in query:
                db_state["status"] = "approved"

        conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        conn.execute = AsyncMock(side_effect=mock_execute)
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = self._create_mock_pool(conn)

        call_count = 0

        def mock_img_handler(request: httpx.Request):
            return httpx.Response(200, content=b"image_data")

        transport = httpx.MockTransport(mock_img_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            moderator = MagicMock()
            async def mock_moderate(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.05)
                return ModerationResult(is_safe=True, reason="clean", confidence=0.95)

            moderator.moderate_image_bytes = AsyncMock(side_effect=mock_moderate)

            t1 = asyncio.create_task(run_photo_moderation(photo_id, user_id, pool=pool, moderator=moderator, http_client=http))
            t2 = asyncio.create_task(run_photo_moderation(photo_id, user_id, pool=pool, moderator=moderator, http_client=http))
            res1, res2 = await asyncio.gather(t1, t2)

        self.assertTrue(res1.is_safe)
        self.assertTrue(res2.is_safe)
        self.assertEqual(call_count, 1)


class TestAdminMediaModerationEndpoints(unittest.IsolatedAsyncioTestCase):
    async def test_admin_approve_user_photo(self):
        from app.routers.admin import approve_media

        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()
        admin = {"user_id": uuid.uuid4(), "admin_role": "admin"}

        db_state = {"status": "pending", "avatar_url": None}

        conn = MagicMock()
        async def mock_fetchrow(query, *args):
            if "FROM user_media" in query:
                return {
                    "id": photo_id,
                    "user_id": user_id,
                    "cdn_url": "https://cdn.example.com/avatar.webp",
                    "s3_key": f"{user_id}/avatar.webp",
                    "media_type": "photo",
                    "position": 1,
                }
            return None

        async def mock_execute(query, *args):
            if "UPDATE user_media" in query and "status = 'approved'" in query:
                db_state["status"] = "approved"
            elif "UPDATE users" in query and "avatar_url" in query:
                db_state["avatar_url"] = args[0]

        conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        conn.execute = AsyncMock(side_effect=mock_execute)
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()

        with patch("app.routers.admin.recompute_trust_score", AsyncMock()):
            resp = await approve_media(media_id=photo_id, admin=admin, pool=pool)

        self.assertEqual(resp["status"], "approved")
        self.assertEqual(db_state["status"], "approved")
        self.assertEqual(db_state["avatar_url"], "https://cdn.example.com/avatar.webp")

    async def test_admin_reject_user_photo(self):
        from app.routers.admin import reject_media, RejectMediaBody

        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()
        admin = {"user_id": uuid.uuid4(), "admin_role": "admin"}

        body = RejectMediaBody(reason="nudity")

        db_state = {
            "status": "pending",
            "avatar_url": "https://cdn.example.com/avatar.webp",
        }

        conn = MagicMock()
        async def mock_fetchrow(query, *args):
            if "FROM user_media" in query:
                return {
                    "id": photo_id,
                    "user_id": user_id,
                    "cdn_url": "https://cdn.example.com/avatar.webp",
                    "media_type": "photo",
                    "position": 1,
                }
            return None

        async def mock_execute(query, *args):
            if "UPDATE user_media" in query and "status = 'rejected'" in query:
                db_state["status"] = "rejected"
            elif "UPDATE users" in query and "avatar_url = NULL" in query:
                db_state["avatar_url"] = None

        conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        conn.fetchval = AsyncMock(return_value=True)
        conn.execute = AsyncMock(side_effect=mock_execute)
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()

        with patch("app.routers.admin.recompute_trust_score", AsyncMock()):
            with patch("app.services.media_processor.delete_user_avatar", AsyncMock()) as mock_delete:
                resp = await reject_media(media_id=photo_id, body=body, admin=admin, pool=pool)
                mock_delete.assert_called_once_with(user_id)

        self.assertTrue(resp["rejected"])
        self.assertEqual(db_state["status"], "rejected")
        self.assertIsNone(db_state["avatar_url"])

    async def test_admin_approve_user_media_voice_note_does_not_set_avatar(self):
        from app.routers.admin import approve_media

        media_id = uuid.uuid4()
        user_id = uuid.uuid4()
        admin = {"user_id": uuid.uuid4(), "admin_role": "admin"}

        db_state = {"status": "pending", "avatar_url": None}

        conn = MagicMock()
        async def mock_fetchrow(query, *args):
            if "FROM user_media" in query:
                return {
                    "id": media_id,
                    "user_id": user_id,
                    "cdn_url": "https://cdn.example.com/voice.mp4",
                    "s3_key": f"{user_id}/voice.mp4",
                    "media_type": "voice",
                    "position": 1,
                }
            return None

        async def mock_execute(query, *args):
            if "UPDATE user_media" in query and "status = 'approved'" in query:
                db_state["status"] = "approved"
            elif "UPDATE users" in query and "avatar_url" in query:
                db_state["avatar_url"] = args[0]

        conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        conn.execute = AsyncMock(side_effect=mock_execute)
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()

        with patch("app.routers.admin.recompute_trust_score", AsyncMock()):
            resp = await approve_media(media_id=media_id, admin=admin, pool=pool)

        self.assertEqual(resp["status"], "approved")
        self.assertEqual(db_state["status"], "approved")
        # Voice note must NEVER become users.avatar_url
        self.assertIsNone(db_state["avatar_url"])

    async def test_confirm_upload_raises_404_when_intent_missing(self):
        from app.routers.media import confirm_upload, ConfirmUploadBody
        from fastapi import HTTPException

        media_id = uuid.uuid4()
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}
        body = ConfirmUploadBody(media_id=media_id)

        conn = MagicMock()
        conn.execute = AsyncMock(return_value="UPDATE 0")
        conn.fetchval = AsyncMock(return_value=False)
        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.media.sliding_window_rate_limit", AsyncMock()):
            with patch("app.routers.media.verify_avatar_uploaded", AsyncMock(return_value=True)):
                with self.assertRaises(HTTPException) as ctx:
                    await confirm_upload(body=body, current_user=current_user, db=pool, redis=MagicMock())
                self.assertEqual(ctx.exception.status_code, 404)


class TestAvatarSizeBounds(unittest.IsolatedAsyncioTestCase):
    def _storage_client_with_items(self, items):
        client = MagicMock()
        bucket = MagicMock()
        client.storage.from_ = MagicMock(return_value=bucket)
        bucket.list.return_value = items
        return client

    async def test_verify_avatar_accepts_storage_size_at_limit(self):
        from app.services.media_processor import MAX_AVATAR_BYTES, verify_avatar_uploaded

        client = self._storage_client_with_items([
            {"name": "avatar.webp", "metadata": {"size": str(MAX_AVATAR_BYTES)}}
        ])

        with patch("app.services.media_processor._get_supabase", return_value=client):
            self.assertTrue(await verify_avatar_uploaded(uuid.uuid4()))

    async def test_confirm_upload_rejects_and_cleans_over_limit_avatar(self):
        from fastapi import HTTPException
        from app.routers.media import ConfirmUploadBody, confirm_upload
        from app.services.media_processor import AvatarTooLargeError

        media_id = uuid.uuid4()
        user_id = uuid.uuid4()
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=True)
        conn.execute = AsyncMock(return_value="UPDATE 1")
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()
        redis = AsyncMock()

        with patch("app.routers.media.sliding_window_rate_limit", AsyncMock()):
            with patch("app.routers.media.verify_avatar_uploaded", AsyncMock(side_effect=AvatarTooLargeError)):
                with patch("app.routers.media.delete_user_avatar", AsyncMock()) as delete_avatar:
                    with self.assertRaises(HTTPException) as ctx:
                        await confirm_upload(
                            body=ConfirmUploadBody(media_id=media_id),
                            current_user={"user_id": str(user_id)},
                            db=pool,
                            redis=redis,
                        )

        self.assertEqual(ctx.exception.status_code, 413)
        self.assertEqual(conn.execute.await_count, 2)
        delete_avatar.assert_awaited_once_with(str(user_id))
        redis.delete.assert_awaited_once()

    async def test_verify_avatar_rejects_storage_size_over_limit(self):
        from app.services.media_processor import AvatarTooLargeError, MAX_AVATAR_BYTES, verify_avatar_uploaded

        client = self._storage_client_with_items([
            {"name": "avatar.webp", "metadata": {"size": str(MAX_AVATAR_BYTES + 1)}}
        ])

        with patch("app.services.media_processor._get_supabase", return_value=client):
            with self.assertRaises(AvatarTooLargeError):
                await verify_avatar_uploaded(uuid.uuid4())

    async def test_verify_avatar_fails_closed_when_storage_size_is_unavailable(self):
        from app.services.media_processor import verify_avatar_uploaded

        client = self._storage_client_with_items([{"name": "avatar.webp", "metadata": None}])
        with patch("app.services.media_processor._get_supabase", return_value=client):
            self.assertFalse(await verify_avatar_uploaded(uuid.uuid4()))

    async def test_moderation_stream_rejects_oversize_without_content_length(self):
        from app.services.media_processor import AvatarTooLargeError, MAX_AVATAR_BYTES, _read_bounded_image_response

        body = b"x" * (MAX_AVATAR_BYTES + 1)
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, stream=httpx.ByteStream(body))
        )
        async with httpx.AsyncClient(transport=transport) as http:
            with self.assertRaises(AvatarTooLargeError):
                await _read_bounded_image_response(http, "https://cdn.example.com/avatar.webp")

    async def test_moderation_authenticated_fallback_uses_same_byte_cap(self):
        from app.core.config import settings
        from app.services.media_processor import AvatarTooLargeError, MAX_AVATAR_BYTES, download_avatar_bytes

        requests = []

        def handler(request: httpx.Request):
            requests.append(request)
            if "/public/" in request.url.path:
                return httpx.Response(404)
            return httpx.Response(200, headers={"content-length": str(MAX_AVATAR_BYTES + 1)})

        original_url = settings.supabase_url
        original_key = settings.supabase_service_role_key
        settings.supabase_url = "https://storage.example.com"
        settings.supabase_service_role_key = "service-key-test"
        try:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http:
                with self.assertRaises(AvatarTooLargeError):
                    await download_avatar_bytes(uuid.uuid4(), http, cdn_url="https://cdn.example.com/public/avatar.webp")
        finally:
            settings.supabase_url = original_url
            settings.supabase_service_role_key = original_key

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1].headers["apikey"], "service-key-test")
        self.assertEqual(requests[1].headers["authorization"], "Bearer service-key-test")

    async def test_oversize_moderation_result_rejects_without_calling_vision_model(self):
        from app.services.media_processor import MAX_AVATAR_BYTES
        from app.services.moderation import run_photo_moderation

        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": photo_id,
            "user_id": user_id,
            "status": "pending",
            "cdn_url": "https://cdn.example.com/avatar.webp",
        })
        conn.fetchval = AsyncMock(return_value=True)
        conn.execute = AsyncMock()
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()

        moderator = MagicMock()
        moderator.moderate_image_bytes = AsyncMock()
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                stream=httpx.ByteStream(b"x" * (MAX_AVATAR_BYTES + 1)),
            )
        )
        async with httpx.AsyncClient(transport=transport) as http:
            with patch("app.services.media_processor.delete_user_avatar", AsyncMock()) as delete_avatar:
                result = await run_photo_moderation(
                    photo_id,
                    user_id,
                    pool=pool,
                    moderator=moderator,
                    http_client=http,
                )

        self.assertFalse(result.is_safe)
        self.assertIn("350 KB", result.reason)
        moderator.moderate_image_bytes.assert_not_awaited()
        self.assertTrue(any("status = 'rejected'" in call.args[0] for call in conn.execute.await_args_list))
        delete_avatar.assert_awaited_once_with(user_id)


class TestRateLimiterUpstashResilienceAndTOCTOU(unittest.IsolatedAsyncioTestCase):
    async def test_in_memory_rate_limiter_swipe_actions_zero_redis_calls(self):
        from app.core.security import sliding_window_rate_limit
        from fastapi import HTTPException

        actor_id = uuid.uuid4()
        key = f"ratelimit:interaction:{actor_id}"

        mock_redis = AsyncMock()

        # 10 swipes within limit
        for _ in range(10):
            await sliding_window_rate_limit(key=key, limit=10, window_seconds=60, redis=mock_redis)

        # 11th swipe must raise HTTP 429
        with self.assertRaises(HTTPException) as ctx:
            await sliding_window_rate_limit(key=key, limit=10, window_seconds=60, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # In-process swipe rate-limiting makes ZERO calls to Redis
        mock_redis.pipeline.assert_not_called()
        mock_redis.zadd.assert_not_called()

    async def test_rate_limiter_falls_back_to_in_memory_on_redis_exception(self):
        from app.core.security import sliding_window_rate_limit
        from fastapi import HTTPException

        user_id = uuid.uuid4()
        key = f"ratelimit:otp:request:{user_id}"

        failing_redis = MagicMock()
        failing_redis.pipeline.side_effect = Exception("Upstash Redis daily quota limit reached")

        # Must not raise 503; must seamlessly fall back to in-memory limiter
        for _ in range(3):
            await sliding_window_rate_limit(key=key, limit=3, window_seconds=60, redis=failing_redis)

        with self.assertRaises(HTTPException) as ctx:
            await sliding_window_rate_limit(key=key, limit=3, window_seconds=60, redis=failing_redis)
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_photo_moderation_purges_storage_on_rejection(self):
        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()

        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": photo_id,
            "user_id": user_id,
            "status": "pending",
            "cdn_url": "https://cdn.example.com/avatar.webp",
        })
        conn.fetchval = AsyncMock(return_value=True)
        conn.execute = AsyncMock()
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()

        moderator = MagicMock()
        moderator.moderate_image_bytes = AsyncMock(
            return_value=ModerationResult(is_safe=False, reason="nudity", confidence=0.99)
        )

        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"image_data"))
        async with httpx.AsyncClient(transport=transport) as http:
            with patch("app.services.media_processor.delete_user_avatar", AsyncMock()) as mock_delete:
                res = await run_photo_moderation(photo_id, user_id, pool=pool, moderator=moderator, http_client=http)
                mock_delete.assert_called_once_with(user_id)
        self.assertFalse(res.is_safe)

    async def test_photo_moderation_stale_rejection_does_not_purge_new_photo(self):
        """TOCTOU Defense: If user already uploaded Photo B, rejecting Photo A does NOT purge storage."""
        photo_id = uuid.uuid4()
        user_id = uuid.uuid4()

        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": photo_id,
            "user_id": user_id,
            "status": "pending",
            "cdn_url": "https://cdn.example.com/avatar.webp",
        })
        # Photo A is no longer position 1 (user uploaded a new photo)
        conn.fetchval = AsyncMock(return_value=False)
        conn.execute = AsyncMock()
        conn.transaction = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock()

        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__ = AsyncMock()

        moderator = MagicMock()
        moderator.moderate_image_bytes = AsyncMock(
            return_value=ModerationResult(is_safe=False, reason="nudity", confidence=0.99)
        )

        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"image_data"))
        async with httpx.AsyncClient(transport=transport) as http:
            with patch("app.services.media_processor.delete_user_avatar", AsyncMock()) as mock_delete:
                res = await run_photo_moderation(photo_id, user_id, pool=pool, moderator=moderator, http_client=http)
                mock_delete.assert_not_called()
        self.assertFalse(res.is_safe)

    async def test_cloudflare_moderation_unknown_word_maps_to_other(self):
        """Unknown model output word that isn't in valid tags → reason='other', is_safe=False."""
        from app.core.config import settings
        orig_acc = settings.cloudflare_account_id
        orig_tok = settings.cloudflare_api_token
        settings.cloudflare_account_id = "test_cf_account_id"
        settings.cloudflare_api_token = "test_cf_api_token"
        try:
            client = CloudflareVisionModerationClient()

            def mock_handler(request: httpx.Request):
                return httpx.Response(200, json={"result": {"response": "UNKNOWN_LABEL"}})

            transport = httpx.MockTransport(mock_handler)
            with patch("asyncio.sleep", AsyncMock()):
                async with httpx.AsyncClient(transport=transport) as http:
                    res = await client.moderate_image_bytes(b"test_image_bytes", http_client=http)

            self.assertFalse(res.is_safe)
            self.assertEqual(res.reason, "other")
        finally:
            settings.cloudflare_account_id = orig_acc
            settings.cloudflare_api_token = orig_tok


if __name__ == "__main__":
    unittest.main()
