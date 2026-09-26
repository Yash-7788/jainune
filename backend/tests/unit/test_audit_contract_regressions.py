"""Payment recovery and retention/delta-sync boundary regressions."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.redis import InMemoryRedis, ResilientRedisClient
from app.core.security import hash_otp, verify_otp
from app.routers.chats import get_messages
from app.services.payment_service import process_payment_captured, get_effective_user_tier


def pool_for(conn):
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock()
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
async def test_otp_is_consumed_atomically_by_in_memory_redis_fallback():
    phone = "+919876543219"
    otp = "654321"
    redis = ResilientRedisClient(None)
    await redis.set(f"auth:otp:{phone}", hash_otp(phone, otp), ex=180)

    async def verify_once():
        try:
            return await verify_otp(phone, otp, redis)
        except HTTPException as exc:
            return exc.status_code

    results = await asyncio.gather(verify_once(), verify_once())
    assert results.count(True) == 1
    assert results.count(400) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_status", ["expired", "revoked", "account_hold"])
@pytest.mark.parametrize("cache_failure", [False, True])
async def test_new_subscription_restores_access(prior_status, cache_failure):
    uid = uuid.uuid4()
    state = dict(subscription_tier="free", subscription_valid_until=None,
                 billing_status=prior_status)
    conn = AsyncMock()
    pool = pool_for(conn)
    intent = dict(user_id=uid, plan_id="jainune_base_399", status="created", amount=39900)

    async def fetchrow(sql, *args):
        return intent.copy() if "FROM payment_intents" in sql else state.copy()

    async def execute(sql, *args):
        if "UPDATE users" in sql and "subscription_tier" in sql:
            state.update(subscription_tier=args[0], subscription_valid_until=args[1])
            if "billing_status" in sql and "'active'" in sql:
                state["billing_status"] = "active"
        if "UPDATE payment_intents" in sql:
            intent["status"] = "captured"

    conn.fetchrow.side_effect = fetchrow
    conn.execute.side_effect = execute
    redis = InMemoryRedis()
    await redis.set(f"user:{uid}:billing_status", prior_status)
    if cache_failure:
        redis.delete = AsyncMock(side_effect=ConnectionError("cache unavailable"))
    event = {"payload": {"payment": {"entity": {
        "order_id": "order_new", "id": "pay_new", "amount": 39900, "status": "captured",
    }}}}
    with patch("app.core.redis.get_redis", return_value=redis):
        await process_payment_captured(event, pool)
        assert await get_effective_user_tier(uid, conn) == "base_399"
        assert state["billing_status"] == "active"
        writes = conn.execute.await_count
        await process_payment_captured(event, pool)
        assert conn.execute.await_count == writes  # duplicate does not grant again


@pytest.mark.asyncio
@pytest.mark.parametrize("db_status", ["account_hold", "expired", "revoked"])
async def test_database_restriction_wins_over_active_cache(db_status):
    conn = AsyncMock()
    conn.fetchrow.return_value = dict(subscription_tier="base_399", billing_status=db_status,
                                     subscription_valid_until=datetime.now(timezone.utc) + timedelta(days=30))
    redis = InMemoryRedis()
    uid = uuid.uuid4()
    await redis.set(f"user:{uid}:billing_status", "active")
    with patch("app.core.redis.get_redis", return_value=redis):
        assert await get_effective_user_tier(uid, conn) == "free"


@pytest.mark.asyncio
@pytest.mark.parametrize("anchor_exists", [False, True])
async def test_forward_sync_recovers_retained_history(anchor_exists):
    uid, chat_id, old_cursor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    start = datetime.now(timezone.utc)
    retained = [dict(id=uuid.uuid4(), chat_id=chat_id, sender_id=uid,
                     message_type="text", content=str(i), media_url=None,
                     is_read=False, created_at=start + timedelta(seconds=i)) for i in range(51)]
    conn = AsyncMock()
    pool = pool_for(conn)
    conn.fetchrow.return_value = {"id": old_cursor, "created_at": start} if anchor_exists else None
    conn.fetch.return_value = retained
    with patch("app.routers.chats._assert_participant", new=AsyncMock(return_value={"id": chat_id})):
        result = await get_messages(chat_id, {"user_id": uid}, pool,
                                    limit=50, since_id=str(old_cursor), redis=None)
    assert len(result.messages) == 50
    assert result.has_more is True
    assert result.next_cursor == str(retained[49]["id"])
    sql = conn.fetch.call_args.args[0]
    assert "chat_id = $1" in sql
    assert "ORDER BY created_at ASC, id ASC" in sql


@pytest.mark.asyncio
async def test_bug001_wrong_otp_does_not_consume_valid_code():
    phone = "+919876543210"
    otp = "123456"
    redis = ResilientRedisClient(None)
    await redis.set(f"auth:otp:{phone}", hash_otp(phone, otp), ex=180)

    # 1. Wrong OTP attempt fails with 401
    with pytest.raises(HTTPException) as exc_info:
        await verify_otp(phone, "000000", redis)
    assert exc_info.value.status_code == 401

    # 2. Correct OTP attempt still succeeds (not consumed by wrong attempt)
    assert await verify_otp(phone, otp, redis) is True

    # 3. Subsequent attempt fails with 400 (consumed on successful verification)
    with pytest.raises(HTTPException) as exc_info:
        await verify_otp(phone, otp, redis)
    assert exc_info.value.status_code == 400


def test_bug002_browser_headers_spoofer_requires_turnstile():
    from app.core.bot_defense import verify_bot_integrity

    # User-agent or browser headers claiming to be mobile client without turnstile token
    browser_spoof_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "X-Client-Platform": "android",
        "Sec-Ch-Ua": '"Chromium";v="120"',
    }
    is_bot, reason = verify_bot_integrity(browser_spoof_headers, is_production=True)
    assert is_bot is True
    assert "Security verification challenge failed" in reason

    # Genuine mobile client without browser markers
    mobile_headers = {
        "User-Agent": "JainuneMobile/1.0 (Android)",
        "X-Client-Platform": "android",
    }
    is_bot, _ = verify_bot_integrity(mobile_headers, is_production=True)
    assert is_bot is False


@pytest.mark.asyncio
async def test_bug003_refresh_token_grace_period_and_theft_detection():
    from app.routers.auth import refresh_token_endpoint, TokenRefreshBody
    import hashlib
    import json

    user_id = uuid.uuid4()
    raw_token = "valid_refresh_token_sample"
    redis = ResilientRedisClient(None)

    conn = AsyncMock()
    pool = pool_for(conn)

    # Test 1: Recent grace entry within 15 seconds returns grace payload
    now_utc = datetime.now(timezone.utc)
    mock_payload = {"access_token": "grace_access_jwt", "token_type": "bearer", "expires_in": 900}
    conn.fetchrow.return_value = {
        "revocation_type": "grace",
        "user_id": user_id,
        "payload": json.dumps(mock_payload),
        "expires_at": now_utc + timedelta(days=30),
        "created_at": now_utc - timedelta(seconds=5),
    }

    req = MagicMock()
    req.headers = {}
    req.client.host = "127.0.0.1"

    body = TokenRefreshBody(refresh_token=raw_token)
    res = await refresh_token_endpoint(body=body, request=req, db=pool, redis=redis)
    res_data = json.loads(res.body.decode()) if hasattr(res, "body") else res
    payload_data = res_data.get("data", res_data)
    assert payload_data.get("access_token") == "grace_access_jwt"

    # Test 2: Expired grace entry (> 15 seconds) triggers theft detection (HTTP 401)
    conn.fetchrow.return_value = {
        "revocation_type": "revoked",
        "user_id": user_id,
        "payload": json.dumps(mock_payload),
        "expires_at": now_utc + timedelta(days=30),
        "created_at": now_utc - timedelta(seconds=20),
    }
    with pytest.raises(HTTPException) as exc_info:
        await refresh_token_endpoint(body=body, request=req, db=pool, redis=redis)
    assert exc_info.value.status_code == 401
    assert "Refresh token reuse detected" in exc_info.value.detail


@pytest.mark.asyncio
async def test_bug004_onboarding_incomplete_feed_and_interactions_denied():
    from app.routers.feed import get_feed
    from app.routers.interactions import record_interaction_action, InteractionActionRequest

    # Incomplete user blocked from feed
    incomplete_user = {"user_id": str(uuid.uuid4()), "onboarding_completed": False}
    with pytest.raises(HTTPException) as exc_info:
        await get_feed(current_user=incomplete_user, db=MagicMock(), redis=None)
    assert exc_info.value.status_code == 403
    assert "Onboarding must be completed" in exc_info.value.detail

    # Incomplete user blocked from swiping/interacting
    with pytest.raises(HTTPException) as exc_info:
        await record_interaction_action(
            body=InteractionActionRequest(target_id=uuid.uuid4(), action="like"),
            current_user=incomplete_user,
            db=MagicMock(),
            redis=None,
        )
    assert exc_info.value.status_code == 403
    assert "Onboarding must be completed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_bug005_admin_approve_unprocessed_media_rejected():
    from app.routers.admin import approve_media

    media_id = uuid.uuid4()
    admin_user = {"user_id": uuid.uuid4(), "admin_role": "admin"}
    conn = AsyncMock()
    pool = pool_for(conn)

    # Unprocessed media returns is_processed=False
    conn.fetchrow.return_value = {
        "id": media_id,
        "user_id": uuid.uuid4(),
        "s3_key": "raw/media.jpg",
        "cdn_url": None,
        "media_type": "photo",
        "position": 0,
        "is_processed": False,
    }

    with pytest.raises(HTTPException) as exc_info:
        await approve_media(media_id=media_id, admin=admin_user, pool=pool)
    assert exc_info.value.status_code == 400
    assert "Cannot approve media before file is uploaded and processed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_bug006_google_play_consumable_dice_credits_wallet():
    from app.routers.subscriptions import verify_google_play, GooglePlayVerifyBody

    user_id = uuid.uuid4()
    current_user = {"user_id": str(user_id)}
    conn = AsyncMock()
    pool = pool_for(conn)

    # Mock no existing token found in store_subscriptions
    conn.fetch.return_value = []
    # Mock user exists
    conn.fetchrow.return_value = {"id": user_id}

    body = GooglePlayVerifyBody(
        orderId="GPA.1234-5678-9012-34567",
        productId="arcade_3_pack",
        purchaseToken="valid_google_purchase_token_sample",
        purchaseTime=int(datetime.now(timezone.utc).timestamp() * 1000),
    )

    with patch("app.services.google_play_verifier.verify_google_play_purchase", return_value={"purchaseState": 0, "consumptionState": 0}):
        res = await verify_google_play(body=body, current_user=current_user, pool=pool, redis=None)

    assert res.get("success") is True
    assert res.get("dice_rolls_granted") == 3

    executed_sqls = [call.args[0] for call in conn.execute.call_args_list]
    wallet_updates = [sql for sql in executed_sqls if "user_arcade_wallet" in sql and "available_dice_rolls" in sql]
    assert len(wallet_updates) >= 1
