"""
Unit tests for Profile & Media Management:
- UserProfileResponse compatibility with Google/Apple accounts (nullable phone/name).
- Own photos & prompts retrieval.
- Prompts updating (PUT /v1/users/me/prompts).
- Individual photo deletion from S3 and DB (DELETE /v1/media/{media_id}).
- Photo reordering (PATCH /v1/media/reorder).
"""

from __future__ import annotations

import sys
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()
if "redis" not in sys.modules:
    sys.modules["redis"] = MagicMock()
if "redis.asyncio" not in sys.modules:
    sys.modules["redis.asyncio"] = MagicMock()

from app.models.schemas.user import (
    MediaPositionItem,
    PromptItem,
    ReorderMediaBody,
    UpdatePromptsBody,
    UserProfileResponse,
)
from app.routers.media import delete_media, reorder_media
from app.routers.users import get_my_prompts, update_my_prompts


class TestProfileAndMediaManagement(unittest.IsolatedAsyncioTestCase):

    def test_user_profile_response_supports_nullable_oauth_fields(self):
        """Profile schema must allow None for phone_number and first_name during onboarding."""
        user_id = uuid.uuid4()
        profile = UserProfileResponse(
            id=user_id,
            phone_number=None,
            email="oauth.user@gmail.com",
            auth_provider="google",
            first_name=None,
            date_of_birth=None,
            gender=None,
            show_me=None,
            looking_for=None,
            city=None,
            state=None,
            dietary_strictness=None,
            community_sect=None,
            subscription_tier="free",
            is_photo_verified=False,
            account_status="active",
            onboarding_completed=False,
            super_connect_credits=0,
            photos=[],
            prompts=[],
        )
        self.assertIsNone(profile.phone_number)
        self.assertIsNone(profile.first_name)
        self.assertEqual(profile.email, "oauth.user@gmail.com")
        self.assertEqual(profile.auth_provider, "google")

    async def test_update_my_prompts(self):
        """Updating prompts must replace previous user prompts in transaction."""
        db = MagicMock()
        conn = AsyncMock()
        tx_mock = MagicMock()
        tx_mock.__aenter__ = AsyncMock(return_value=None)
        tx_mock.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=tx_mock)
        db.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        db.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}
        body = UpdatePromptsBody(prompts=[
            PromptItem(prompt_key="sunday_routine", response_text="Temple followed by family brunch", position=1),
            PromptItem(prompt_key="ideal_match", response_text="Someone grounded in core values", position=2),
        ])

        result = await update_my_prompts(body, current_user, db)
        self.assertTrue(result["success"])

        executed_queries = [call[0][0] for call in conn.execute.call_args_list]
        self.assertTrue(any("DELETE FROM user_prompts" in q for q in executed_queries))
        self.assertTrue(any("INSERT INTO user_prompts" in q for q in executed_queries))

    async def test_delete_single_media(self):
        """Deleting media must delete S3 object and DB row."""
        db = MagicMock()
        conn = AsyncMock()
        db.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        db.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        user_id = uuid.uuid4()
        media_id = uuid.uuid4()
        current_user = {"user_id": user_id}

        conn.fetchrow.return_value = {
            "id": media_id,
            "s3_key": "media/user_1/photo_1.jpg",
            "status": "approved",
        }

        with patch("app.services.account_service._delete_s3_keys_sync") as mock_s3_del:
            result = await delete_media(media_id, current_user, db)
            self.assertTrue(result["success"])
            mock_s3_del.assert_called_once_with(["media/user_1/photo_1.jpg"])

            executed_queries = [call[0][0] for call in conn.execute.call_args_list]
            self.assertTrue(any("DELETE FROM user_media" in q for q in executed_queries))

    async def test_reorder_media(self):
        """Reordering media updates position for all specified media IDs."""
        db = MagicMock()
        conn = AsyncMock()
        tx_mock = MagicMock()
        tx_mock.__aenter__ = AsyncMock(return_value=None)
        tx_mock.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=tx_mock)
        db.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        db.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}
        m1 = uuid.uuid4()
        m2 = uuid.uuid4()

        body = ReorderMediaBody(positions=[
            MediaPositionItem(media_id=m1, position=1),
            MediaPositionItem(media_id=m2, position=2),
        ])

        result = await reorder_media(body, current_user, db)
        self.assertTrue(result["success"])
        executed_queries = [call[0][0] for call in conn.execute.call_args_list]
        self.assertTrue(any("UPDATE user_media SET position" in q for q in executed_queries))


if __name__ == "__main__":
    unittest.main()
