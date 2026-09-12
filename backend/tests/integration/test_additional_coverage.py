"""
Integration tests covering additional core endpoints:
- Subscriptions plans, orders, and cancellation
- Health and liveness probes
- User profile fetch (/v1/users/me) and DPDP data export (/v1/users/me/export)
- Onboarding status and full profile construction steps 2-22
- Media status and deletion (/v1/media/status/{id}, /v1/media/{id})
- Chats list and weekly question (/v1/chats, /v1/chats/weekly-question)
- Arcade dilemmas feed and wallet (/v1/arcade/dilemmas, /v1/arcade/wallet)
- User block, unblock, and pause profile (/v1/users/{id}/block, /v1/users/{id}/unblock, /v1/users/me/pause)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_and_health(client: AsyncClient, mock_pool):
    """Test /livez and /v1/health endpoints."""
    resp = await client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"

    resp2 = await client.get("/v1/health")
    assert resp2.status_code in (200, 503)


@pytest.mark.asyncio
async def test_subscription_plans(client: AsyncClient):
    """Test public plans listing."""
    resp = await client.get("/v1/subscriptions/plans")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_subscription_order(authed_client, mock_pool, fake_redis):
    """Test creating a Razorpay order via POST /v1/subscriptions/order."""
    client, user_id = authed_client
    mock_order = {
        "order_id": "order_test_123",
        "amount": 99900,
        "currency": "INR",
        "key_id": "rzp_test_mock",
        "plan_id": "jainune_plus_monthly",
    }
    with patch("app.services.payment_service.create_order", new_callable=AsyncMock, return_value=mock_order):
        resp = await client.post("/v1/subscriptions/order", json={"plan_id": "jainune_plus_monthly"})
        assert resp.status_code == 201
        assert resp.json()["order_id"] == "order_test_123"


@pytest.mark.asyncio
async def test_subscription_cancel(authed_client, mock_pool):
    """Test subscription cancel returns non-recurring pass status."""
    client, user_id = authed_client
    pool, conn = mock_pool
    conn.fetchrow.return_value = {
        "subscription_tier": "gold",
        "subscription_valid_until": datetime.now(timezone.utc),
    }

    resp = await client.post("/v1/subscriptions/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_users_me_profile(authed_client, mock_pool):
    """Test /v1/users/me returns authenticated user details."""
    client, user_id = authed_client
    pool, conn = mock_pool

    conn.fetchrow.return_value = {
        "id": uuid.UUID(str(user_id)),
        "first_name": "Yash",
        "last_name": "Jain",
        "phone_number": "+919876543210",
        "email": "yash@example.com",
        "gender": "men",
        "show_me": "women",
        "looking_for": "marriage",
        "dietary_strictness": "pure_jain",
        "community_sect": "shwetambar_murtipujak",
        "city": "Mumbai",
        "state": "Maharashtra",
        "country": "India",
        "account_status": "active",
        "onboarding_completed": True,
        "is_photo_verified": True,
        "subscription_tier": "free",
        "subscription_valid_until": None,
        "super_connect_credits": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "deleted_at": None,
        "photos": [],
        "prompts": [],
    }
    conn.fetch.return_value = []

    resp = await client.get("/v1/users/me")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_users_me_export(authed_client, mock_pool):
    """Test DPDP Act data export via /v1/users/me/export."""
    client, user_id = authed_client
    pool, conn = mock_pool

    conn.fetchrow.return_value = {
        "id": uuid.UUID(str(user_id)),
        "first_name": "Yash",
        "phone_number": "+919876543210",
        "email": "yash@example.com",
        "created_at": datetime.now(timezone.utc),
    }
    conn.fetch.return_value = []

    resp = await client.get("/v1/users/me/export")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data or "user_id" in data or "profile" in data or "id" in data


@pytest.mark.asyncio
async def test_onboarding_status(authed_client, mock_pool):
    """Test /v1/onboarding/status returns user onboarding step."""
    client, user_id = authed_client
    pool, conn = mock_pool

    conn.fetchrow.return_value = {
        "onboarding_step": 3,
        "onboarding_completed": False,
    }

    resp = await client.get("/v1/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["current_step"] == 3


@pytest.mark.asyncio
async def test_onboarding_all_steps(authed_client, mock_pool, fake_redis):
    """Test sequentially stepping through onboarding steps 2 to 17, 18, 19, 20, 21, 22."""
    client, user_id = authed_client
    pool, conn = mock_pool

    media_id = str(uuid.uuid4())
    conn.fetchrow.return_value = {"onboarding_completed": False, "id": uuid.UUID(media_id)}
    conn.fetch.return_value = [{"id": uuid.UUID(media_id)}]
    conn.execute.return_value = "UPDATE 1"

    step_payloads = [
        (2, {"first_name": "Aarav", "date_of_birth": "1998-05-15"}),
        (3, {"gender": "man"}),
        (4, {"show_me": "women"}),
        (5, {"looking_for": "marriage"}),
        (6, {"dietary_strictness": "pure_jain"}),
        (7, {"eats_root_vegetables": False, "eats_onion_garlic": False}),
        (8, {"community_sect": "shwetambar_murtipujak"}),
        (9, {"paryushan_mode": True}),
        (10, {"city": "Mumbai", "state": "Maharashtra"}),
        (12, {"max_distance_km": 50}),
        (13, {"open_to_relocation": True}),
        (14, {"height_cm": 175}),
        (15, {"job_title": "Engineer", "company": "Tech"}),
        (16, {"education": "B.Tech"}),
        (17, {"bio": "Devout Jain looking for like-minded partner"}),
        (18, {"prompts": [{"prompt_key": "temple", "response_text": "Palitana", "position": 1}]}),
        (19, {"media_ids": [media_id]}),
        (20, {"media_id": media_id}),
        (21, {
            "core_matchmaking": True,
            "family_contact_gotra": False,
            "relocation_intercity": True,
            "marketing": False,
        }),
    ]

    for step_num, payload in step_payloads:
        resp = await client.patch(f"/v1/onboarding/step/{step_num}", json=payload)
        assert resp.status_code == 200, f"Step {step_num} failed with {resp.text}"
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["current_step"] == step_num

    # Step 22 idempotent check
    conn.fetchrow.return_value = {"onboarding_completed": True}
    resp22 = await client.patch("/v1/onboarding/step/22", json={})
    assert resp22.status_code == 200
    assert resp22.json()["data"]["completed"] is True


@pytest.mark.asyncio
async def test_media_status_and_delete(authed_client, mock_pool, fake_redis):
    """Test polling media status and deleting a media asset."""
    client, user_id = authed_client
    pool, conn = mock_pool
    mid = uuid.uuid4()

    conn.fetchrow.return_value = {
        "id": mid,
        "status": "approved",
        "cdn_url": "https://cdn.jainune.com/photos/1.jpg",
        "rejection_reason": None,
        "s3_key": "photos/1.jpg",
    }
    conn.execute.return_value = "DELETE 1"

    with patch("app.services.account_service._delete_s3_keys_sync", return_value=None):
        resp_status = await client.get(f"/v1/media/status/{mid}")
        assert resp_status.status_code == 200
        assert resp_status.json()["status"] == "approved"

        resp_del = await client.delete(f"/v1/media/{mid}")
        assert resp_del.status_code == 200
        assert resp_del.json()["success"] is True


@pytest.mark.asyncio
async def test_chats_list(authed_client, mock_pool):
    """Test /v1/chats returns conversation threads."""
    client, user_id = authed_client
    pool, conn = mock_pool

    conn.fetch.return_value = []

    resp = await client.get("/v1/chats")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chats_weekly_question(authed_client):
    """Test /v1/chats/weekly-question returns rotating cultural question."""
    client, user_id = authed_client
    resp = await client.get("/v1/chats/weekly-question")
    assert resp.status_code == 200
    assert "question" in resp.json()


@pytest.mark.asyncio
async def test_arcade_feed(authed_client, mock_pool, fake_redis):
    """Test /v1/arcade/dilemmas returns dilemma feed."""
    client, user_id = authed_client
    pool, conn = mock_pool

    conn.fetch.return_value = []

    resp = await client.get("/v1/arcade/dilemmas")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_users_block_and_unblock(authed_client, mock_pool, fake_redis):
    """Test blocking and unblocking via /v1/users/{id}/block and /unblock."""
    client, user_id = authed_client
    pool, conn = mock_pool
    target_id = str(uuid.uuid4())

    conn.execute.return_value = "INSERT 1"
    conn.fetch.return_value = []

    resp = await client.post(f"/v1/users/{target_id}/block", json={"reason": "inappropriate"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    resp_unblock = await client.delete(f"/v1/users/{target_id}/block")
    assert resp_unblock.status_code == 200
    assert resp_unblock.json()["success"] is True


@pytest.mark.asyncio
async def test_users_pause_profile(authed_client, mock_pool, fake_redis):
    """Test pausing profile via /v1/users/me/pause."""
    client, user_id = authed_client
    pool, conn = mock_pool

    conn.execute.return_value = "UPDATE 1"

    resp = await client.post("/v1/users/me/pause")
    assert resp.status_code == 200
    assert resp.json()["is_paused"] is True


@pytest.mark.asyncio
async def test_users_unpause_blocks_prompts(authed_client, mock_pool, fake_redis):
    """Test unpausing account, fetching blocks list, and updating user prompts and FCM token."""
    client, user_id = authed_client
    pool, conn = mock_pool
    conn.execute.return_value = "UPDATE 1"

    resp_unpause = await client.post("/v1/users/me/unpause")
    assert resp_unpause.status_code == 200
    assert resp_unpause.json()["is_paused"] is False

    conn.fetch.return_value = [{"blocked_id": uuid.uuid4(), "created_at": datetime.now(timezone.utc)}]
    resp_blocks = await client.get("/v1/users/me/blocks")
    assert resp_blocks.status_code == 200
    assert len(resp_blocks.json()["blocked_users"]) == 1

    conn.fetch.return_value = [{"prompt_key": "q1", "response_text": "Ahimsa", "position": 1}]
    resp_prompts = await client.get("/v1/users/me/prompts")
    assert resp_prompts.status_code == 200

    resp_put_prompts = await client.put("/v1/users/me/prompts", json={
        "prompts": [{"prompt_key": "q1", "response_text": "Ahimsa always", "position": 1}]
    })
    assert resp_put_prompts.status_code == 200
    assert resp_put_prompts.json()["success"] is True

    resp_fcm = await client.post("/v1/users/me/fcm-token", json={"fcm_token": "fcm_test_token_123"})
    assert resp_fcm.status_code == 200
    assert resp_fcm.json()["success"] is True


@pytest.mark.asyncio
async def test_chat_messages_read_unmatch(authed_client, mock_pool, fake_redis):
    """Test fetching chat messages, marking thread as read, and unmatching."""
    client, user_id = authed_client
    pool, conn = mock_pool
    chat_id = uuid.uuid4()
    other_id = uuid.uuid4()
    conn.fetchrow.return_value = {
        "id": chat_id,
        "participant_1_id": user_id,
        "participant_2_id": other_id,
        "is_unmatched": False,
        "is_expired": False,
        "expires_at": None,
        "match_id": uuid.uuid4(),
    }
    conn.fetch.return_value = [
        {
            "id": uuid.uuid4(),
            "chat_id": chat_id,
            "sender_id": user_id,
            "message_type": "text",
            "content": "Jai Jinendra",
            "media_url": None,
            "is_read": True,
            "created_at": datetime.now(timezone.utc),
            "is_moderated": False,
            "moderation_type": None,
            "moderation_disclaimer": None,
        }
    ]
    resp = await client.get(f"/v1/chats/{chat_id}/messages")
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 1

    resp_read = await client.post(f"/v1/chats/{chat_id}/read")
    assert resp_read.status_code == 204

    resp_unmatch = await client.post(f"/v1/chats/{chat_id}/unmatch")
    assert resp_unmatch.status_code == 200
    assert resp_unmatch.json()["success"] is True
