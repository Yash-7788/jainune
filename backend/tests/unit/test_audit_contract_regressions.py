"""Payment recovery and retention/delta-sync boundary regressions."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.redis import InMemoryRedis
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
        "order_id": "order_new", "id": "pay_new", "amount": 39900,
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
