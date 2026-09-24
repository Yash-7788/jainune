"""
Redis Client Manager:
- Connection retry logic with backoff.
- Multi-server / Sentinel / cluster fallback support.
- Built-in InMemoryRedis fallback for network disconnection and Upstash 10k daily limit protection.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import redis.asyncio as aioredis
from app.core.config import settings

log = logging.getLogger(__name__)


class InMemoryPipeline:
    def __init__(self, backend: InMemoryRedis):
        self._backend = backend
        self._cmds: list[tuple[str, tuple, dict]] = []

    def zremrangebyscore(self, name: str, min_val: Any, max_val: Any) -> InMemoryPipeline:
        self._cmds.append(("zremrangebyscore", (name, min_val, max_val), {}))
        return self

    def zadd(self, name: str, mapping: dict[str, float]) -> InMemoryPipeline:
        self._cmds.append(("zadd", (name, mapping), {}))
        return self

    def zcard(self, name: str) -> InMemoryPipeline:
        self._cmds.append(("zcard", (name,), {}))
        return self

    def expire(self, name: str, time_sec: int) -> InMemoryPipeline:
        self._cmds.append(("expire", (name, time_sec), {}))
        return self

    def get(self, name: str) -> InMemoryPipeline:
        self._cmds.append(("get", (name,), {}))
        return self

    def set(self, name: str, value: Any, **kwargs: Any) -> InMemoryPipeline:
        self._cmds.append(("set", (name, value), kwargs))
        return self

    def delete(self, *names: str) -> InMemoryPipeline:
        self._cmds.append(("delete", names, {}))
        return self

    def incr(self, name: str, amount: int = 1) -> InMemoryPipeline:
        self._cmds.append(("incr", (name, amount), {}))
        return self

    def decr(self, name: str, amount: int = 1) -> InMemoryPipeline:
        self._cmds.append(("decr", (name, amount), {}))
        return self

    async def execute(self) -> list[Any]:
        results = []
        for cmd, args, kwargs in self._cmds:
            fn = getattr(self._backend, cmd)
            res = await fn(*args, **kwargs)
            results.append(res)
        self._cmds.clear()
        return results


class InMemoryRedis:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._expires: dict[str, float] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._hashes: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, key: str) -> bool:
        if key in self._expires and time.time() > self._expires[key]:
            self._data.pop(key, None)
            self._zsets.pop(key, None)
            self._hashes.pop(key, None)
            self._expires.pop(key, None)
            return True
        return False

    async def ping(self) -> bool:
        return True

    async def get(self, name: str) -> Any:
        async with self._lock:
            if self._is_expired(name):
                return None
            val = self._data.get(name)
            if val is not None and isinstance(val, str):
                return val.encode("utf-8")
            return val

    async def getdel(self, name: str) -> Any:
        """Atomically return and remove a string value, matching Redis GETDEL."""
        async with self._lock:
            if self._is_expired(name):
                return None
            value = self._data.pop(name, None)
            self._expires.pop(name, None)
            if isinstance(value, str):
                return value.encode("utf-8")
            return value

    async def set(
        self,
        name: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool | None:
        async with self._lock:
            self._is_expired(name)
            exists = name in self._data
            if nx and exists:
                return None
            if xx and not exists:
                return None
            self._data[name] = value
            if ex:
                self._expires[name] = time.time() + ex
            elif px:
                self._expires[name] = time.time() + (px / 1000.0)
            else:
                self._expires.pop(name, None)
            return True

    async def setex(self, name: str, time_sec: int, value: Any) -> bool:
        return bool(await self.set(name, value, ex=time_sec))

    async def delete(self, *names: str) -> int:
        count = 0
        async with self._lock:
            for n in names:
                self._expires.pop(n, None)
                if n in self._data:
                    del self._data[n]
                    count += 1
                if n in self._zsets:
                    del self._zsets[n]
                    count += 1
                if n in self._hashes:
                    del self._hashes[n]
                    count += 1
        return count

    async def exists(self, *names: str) -> int:
        count = 0
        async with self._lock:
            for n in names:
                if not self._is_expired(n) and (n in self._data or n in self._zsets or n in self._hashes):
                    count += 1
        return count

    async def expire(self, name: str, time_sec: int) -> bool:
        async with self._lock:
            if not self._is_expired(name) and (name in self._data or name in self._zsets or name in self._hashes):
                self._expires[name] = time.time() + time_sec
                return True
        return False

    async def ttl(self, name: str) -> int:
        async with self._lock:
            if self._is_expired(name):
                return -2
            if name not in self._expires:
                return -1 if (name in self._data or name in self._zsets or name in self._hashes) else -2
            rem = int(self._expires[name] - time.time())
            return max(rem, 0)

    async def incr(self, name: str, amount: int = 1) -> int:
        async with self._lock:
            self._is_expired(name)
            current = self._data.get(name, 0)
            try:
                val = int(current) + amount
            except (ValueError, TypeError):
                val = amount
            self._data[name] = val
            return val

    async def decr(self, name: str, amount: int = 1) -> int:
        return await self.incr(name, -amount)

    async def hget(self, name: str, key: str) -> Any:
        async with self._lock:
            if self._is_expired(name):
                return None
            return self._hashes.get(name, {}).get(key)

    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
        async with self._lock:
            self._is_expired(name)
            h = self._hashes.setdefault(name, {})
            added = 0
            if mapping:
                for k, v in mapping.items():
                    if k not in h:
                        added += 1
                    h[k] = v
            if key is not None:
                if key not in h:
                    added += 1
                h[key] = value
            return added

    async def hdel(self, name: str, *keys: str) -> int:
        async with self._lock:
            if self._is_expired(name) or name not in self._hashes:
                return 0
            count = 0
            for k in keys:
                if k in self._hashes[name]:
                    del self._hashes[name][k]
                    count += 1
            return count

    async def hgetall(self, name: str) -> dict:
        async with self._lock:
            if self._is_expired(name):
                return {}
            return dict(self._hashes.get(name, {}))

    async def zadd(self, name: str, mapping: dict[str, float]) -> int:
        async with self._lock:
            self._is_expired(name)
            z = self._zsets.setdefault(name, {})
            added = 0
            for k, score in mapping.items():
                if k not in z:
                    added += 1
                z[k] = float(score)
            return added

    async def zcard(self, name: str) -> int:
        async with self._lock:
            if self._is_expired(name):
                return 0
            return len(self._zsets.get(name, {}))

    async def zrem(self, name: str, *values: str) -> int:
        async with self._lock:
            if self._is_expired(name) or name not in self._zsets:
                return 0
            count = 0
            for v in values:
                if v in self._zsets[name]:
                    del self._zsets[name][v]
                    count += 1
            return count

    async def zremrangebyscore(self, name: str, min_val: float | int | str, max_val: float | int | str) -> int:
        async with self._lock:
            if self._is_expired(name) or name not in self._zsets:
                return 0
            min_f = float("-inf") if str(min_val) == "-inf" else float(min_val)
            max_f = float("inf") if str(max_val) in ("+inf", "inf") else float(max_val)
            to_remove = [k for k, score in self._zsets[name].items() if min_f <= score <= max_f]
            for k in to_remove:
                del self._zsets[name][k]
            return len(to_remove)

    async def zrangebyscore(self, name: str, min_val: float | int | str, max_val: float | int | str) -> list:
        async with self._lock:
            if self._is_expired(name) or name not in self._zsets:
                return []
            min_f = float("-inf") if str(min_val) == "-inf" else float(min_val)
            max_f = float("inf") if str(max_val) in ("+inf", "inf") else float(max_val)
            items = [(k, score) for k, score in self._zsets[name].items() if min_f <= score <= max_f]
            items.sort(key=lambda x: x[1])
            return [k.encode("utf-8") if isinstance(k, str) else k for k, _ in items]

    async def publish(self, channel: str, message: Any) -> int:
        return 0

    def pipeline(self, transaction: bool = True) -> InMemoryPipeline:
        return InMemoryPipeline(self)

    async def aclose(self) -> None:
        pass


class ResilientPipeline:
    def __init__(self, real_pipe: Any, fallback: InMemoryRedis):
        self._real_pipe = real_pipe
        self._fallback = fallback
        self._buffered_cmds: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str) -> Any:
        real_attr = getattr(self._real_pipe, name)

        def buffer_and_call(*args: Any, **kwargs: Any) -> Any:
            self._buffered_cmds.append((name, args, kwargs))
            res = real_attr(*args, **kwargs)
            return self if res is self._real_pipe else res

        return buffer_and_call

    async def execute(self) -> list[Any]:
        try:
            res = self._real_pipe.execute()
            return await res if hasattr(res, "__await__") else res
        except Exception as exc:
            msg = str(exc).lower()
            if "max daily request limit" in msg or "quota" in msg or isinstance(exc, (aioredis.ConnectionError, aioredis.TimeoutError, aioredis.ResponseError, OSError)):
                log.warning("Redis pipeline execute failed (%s). Replaying on in-memory fallback.", exc)
                fb_pipe = self._fallback.pipeline()
                for cmd, args, kwargs in self._buffered_cmds:
                    fn = getattr(fb_pipe, cmd)
                    fn(*args, **kwargs)
                return await fb_pipe.execute()
            raise


class ResilientRedisClient:
    def __init__(self, real_client: Any = None):
        self._real = real_client
        self._fallback = InMemoryRedis()
        self._degraded = (real_client is None)

    def _should_fallback(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        if "max daily request limit" in msg or "quota" in msg:
            return True
        if isinstance(exc, (aioredis.ConnectionError, aioredis.TimeoutError, aioredis.ResponseError, OSError)):
            return True
        return False

    def pipeline(self, transaction: bool = True) -> Any:
        if self._degraded or self._real is None:
            return self._fallback.pipeline(transaction=transaction)
        try:
            return ResilientPipeline(self._real.pipeline(transaction=transaction), self._fallback)
        except Exception as exc:
            if self._should_fallback(exc):
                self._degraded = True
                log.warning("Redis pipeline creation failed (%s). Falling back to in-memory.", exc)
                return self._fallback.pipeline(transaction=transaction)
            raise

    async def aclose(self) -> None:
        if self._real:
            try:
                await self._real.aclose()
            except Exception:
                pass
        await self._fallback.aclose()

    def __getattr__(self, name: str) -> Any:
        if self._degraded or self._real is None:
            return getattr(self._fallback, name)

        attr = getattr(self._real, name)
        if not callable(attr):
            return attr

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if self._degraded:
                return await getattr(self._fallback, name)(*args, **kwargs)
            try:
                return await attr(*args, **kwargs)
            except Exception as exc:
                if self._should_fallback(exc):
                    self._degraded = True
                    log.warning("Redis command %s failed (%s). Degrading to in-memory fallback.", name, exc)
                    fallback_fn = getattr(self._fallback, name)
                    return await fallback_fn(*args, **kwargs)
                raise

        return wrapper


_redis: ResilientRedisClient | None = None


async def create_redis(max_retries: int = 3) -> ResilientRedisClient:
    """Initializes Redis connection pool with retry and fallback resilience."""
    global _redis
    primary_url = settings.redis_url

    for attempt in range(1, max_retries + 1):
        try:
            client = await aioredis.from_url(
                primary_url,
                max_connections=settings.redis_pool_max_connections,
                decode_responses=False,
            )
            await client.ping()
            _redis = ResilientRedisClient(client)
            log.info("Redis connection established successfully.")
            return _redis
        except Exception as exc:
            log.warning("Redis connection attempt %s/%s failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                await asyncio.sleep(attempt * 1.0)

    fallback_url = getattr(settings, "redis_fallback_url", None)
    if fallback_url:
        log.warning("Attempting connection to secondary fallback Redis...")
        try:
            client = await aioredis.from_url(
                fallback_url,
                max_connections=settings.redis_pool_max_connections,
                decode_responses=False,
            )
            await client.ping()
            _redis = ResilientRedisClient(client)
            log.info("Fallback Redis connection established.")
            return _redis
        except Exception as exc:
            log.critical("Fallback Redis connection failed: %s", exc)

    log.warning("Redis unreachable. Initializing zero-cost InMemoryRedis fallback.")
    _redis = ResilientRedisClient(None)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def get_redis() -> ResilientRedisClient:
    global _redis
    if _redis is None:
        _redis = ResilientRedisClient(None)
    return _redis
