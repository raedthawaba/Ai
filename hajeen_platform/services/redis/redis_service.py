"""Redis Full Integration Service — Cache + Sessions + Queue + Streaming.

سياسات TTL:
  session_cache:   24 ساعة
  embedding_cache: 7 أيام
  response_cache:  1 ساعة
  token_cache:     طول عمر التوكن
  rate_limit:      ديناميكي حسب الـ window
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL     = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE   = os.getenv("REDIS_CACHE_URL", "redis://localhost:6379/1")
REDIS_QUEUE   = os.getenv("REDIS_QUEUE_URL", "redis://localhost:6379/2")

TTL = {
    "session":    86400,        # 24 ساعة
    "token":      3600,         # 1 ساعة
    "embedding":  86400 * 7,    # 7 أيام
    "response":   3600,         # 1 ساعة
    "model":      86400,        # 24 ساعة
    "ratelimit":  60,           # 1 دقيقة
    "stream":     300,          # 5 دقائق
}


class RedisService:
    """خدمة Redis موحّدة — 3 قواعد بيانات منفصلة."""

    def __init__(self) -> None:
        self._main: Optional[aioredis.Redis] = None
        self._cache: Optional[aioredis.Redis] = None
        self._queue: Optional[aioredis.Redis] = None
        self._connected = False

    async def connect(self) -> None:
        try:
            self._main  = await aioredis.from_url(REDIS_URL,  encoding="utf-8", decode_responses=True)
            self._cache = await aioredis.from_url(REDIS_CACHE, encoding="utf-8", decode_responses=True)
            self._queue = await aioredis.from_url(REDIS_QUEUE, encoding="utf-8", decode_responses=True)
            await self._main.ping()
            self._connected = True
            logger.info("Redis connected: main=%s cache=%s queue=%s", REDIS_URL, REDIS_CACHE, REDIS_QUEUE)
        except Exception as e:
            logger.warning("Redis connection failed: %s — running without cache", e)
            self._connected = False

    async def disconnect(self) -> None:
        for client in [self._main, self._cache, self._queue]:
            if client:
                await client.aclose()
        self._connected = False

    # ── Session Cache ─────────────────────────────────────────────────────────

    async def set_session(self, session_id: str, data: Dict[str, Any], ttl: int = TTL["session"]) -> None:
        if not self._connected or not self._cache:
            return
        await self._cache.setex(f"session:{session_id}", ttl, json.dumps(data, ensure_ascii=False))

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self._connected or not self._cache:
            return None
        raw = await self._cache.get(f"session:{session_id}")
        return json.loads(raw) if raw else None

    async def delete_session(self, session_id: str) -> None:
        if self._cache:
            await self._cache.delete(f"session:{session_id}")

    async def extend_session(self, session_id: str, ttl: int = TTL["session"]) -> None:
        if self._cache:
            await self._cache.expire(f"session:{session_id}", ttl)

    # ── Embedding Cache ───────────────────────────────────────────────────────

    async def get_embedding(self, text_hash: str) -> Optional[List[float]]:
        if not self._connected or not self._cache:
            return None
        raw = await self._cache.get(f"emb:{text_hash}")
        return json.loads(raw) if raw else None

    async def set_embedding(self, text_hash: str, vector: List[float], ttl: int = TTL["embedding"]) -> None:
        if not self._connected or not self._cache:
            return
        await self._cache.setex(f"emb:{text_hash}", ttl, json.dumps(vector))

    # ── Response Cache ────────────────────────────────────────────────────────

    async def get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        if not self._connected or not self._cache:
            return None
        raw = await self._cache.get(f"resp:{cache_key}")
        return json.loads(raw) if raw else None

    async def set_cached_response(self, cache_key: str, response: Dict[str, Any], ttl: int = TTL["response"]) -> None:
        if not self._connected or not self._cache:
            return
        await self._cache.setex(f"resp:{cache_key}", ttl, json.dumps(response, ensure_ascii=False))

    # ── Token Blacklist ───────────────────────────────────────────────────────

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        if self._main:
            await self._main.setex(f"blacklist:{jti}", ttl, "1")

    async def is_token_blacklisted(self, jti: str) -> bool:
        if not self._main:
            return False
        return await self._main.exists(f"blacklist:{jti}") > 0

    # ── Pub/Sub Streaming ─────────────────────────────────────────────────────

    async def publish_stream_chunk(self, stream_id: str, chunk: str) -> None:
        if self._main:
            await self._main.publish(f"stream:{stream_id}", chunk)

    async def subscribe_stream(self, stream_id: str) -> AsyncGenerator[str, None]:
        if not self._main:
            return
        pubsub = self._main.pubsub()
        await pubsub.subscribe(f"stream:{stream_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield message["data"]
                    if message["data"] == "[DONE]":
                        break
        finally:
            await pubsub.unsubscribe(f"stream:{stream_id}")
            await pubsub.aclose()

    # ── Task Queue ────────────────────────────────────────────────────────────

    async def enqueue_task(self, queue_name: str, task: Dict[str, Any], priority: int = 0) -> str:
        if not self._queue:
            return ""
        task_id = f"task_{int(time.time() * 1000)}_{id(task)}"
        task["task_id"] = task_id
        task["enqueued_at"] = time.time()
        await self._queue.zadd(f"queue:{queue_name}", {json.dumps(task, ensure_ascii=False): priority})
        return task_id

    async def dequeue_task(self, queue_name: str) -> Optional[Dict[str, Any]]:
        if not self._queue:
            return None
        results = await self._queue.zpopmin(f"queue:{queue_name}", 1)
        if results:
            task_str, _ = results[0]
            return json.loads(task_str)
        return None

    async def queue_length(self, queue_name: str) -> int:
        if not self._queue:
            return 0
        return await self._queue.zcard(f"queue:{queue_name}")

    # ── Distributed Lock ──────────────────────────────────────────────────────

    async def acquire_lock(self, resource: str, ttl: int = 30) -> bool:
        if not self._main:
            return True
        result = await self._main.set(f"lock:{resource}", "1", nx=True, ex=ttl)
        return result is True

    async def release_lock(self, resource: str) -> None:
        if self._main:
            await self._main.delete(f"lock:{resource}")

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        if not self._connected or not self._main:
            return {"connected": False}
        try:
            info = await self._main.info()
            return {
                "connected": True,
                "version": info.get("redis_version"),
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "connected_clients": info.get("connected_clients"),
                "total_commands": info.get("total_commands_processed"),
                "keyspace": info.get("keyspace_hits", 0),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


_redis_service: Optional[RedisService] = None


def get_redis_service() -> RedisService:
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service
