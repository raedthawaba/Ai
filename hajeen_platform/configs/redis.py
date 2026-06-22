"""Redis Infrastructure — section 6.1.

Provides a unified Redis connection manager with:
- Async and sync connection pools
- Health checks
- Retry connection logic with exponential backoff
- Graceful degradation when Redis is unavailable (fakeredis fallback)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class RedisConfig:
    """Redis connection settings."""

    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    max_connections: int = 20
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 3.0
    retry_on_timeout: bool = True
    retry_max_attempts: int = 3
    retry_delay: float = 1.0         # initial delay in seconds
    retry_backoff_factor: float = 2.0

    @property
    def url(self) -> str:
        """Build a redis:// URL from settings."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"

    @classmethod
    def from_env(cls) -> "RedisConfig":
        """Create config from environment variables."""
        url = os.getenv("REDIS_URL", "")
        if url:
            # Parse redis://[:password@]host[:port][/db]
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                return cls(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or 6379,
                    db=int(parsed.path.lstrip("/") or 0),
                    password=parsed.password,
                )
            except Exception:
                pass
        return cls()


# ---------------------------------------------------------------------------
# Redis Manager
# ---------------------------------------------------------------------------

class RedisManager:
    """Async-capable Redis connection manager.

    Falls back to ``fakeredis`` when the real Redis server is unavailable,
    so the platform runs correctly in local development without a running Redis.

    Parameters
    ----------
    config:
        :class:`RedisConfig` — defaults to loading from environment.
    """

    def __init__(self, config: Optional[RedisConfig] = None) -> None:
        self.config = config or RedisConfig.from_env()
        self._client: Any = None
        self._async_client: Any = None
        self._use_fake: bool = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a synchronous Redis connection."""
        if self._client is not None:
            return
        self._client = self._connect_with_retry()

    async def async_connect(self) -> None:
        """Open an asynchronous Redis connection."""
        if self._async_client is not None:
            return
        self._async_client = await self._async_connect_with_retry()

    def disconnect(self) -> None:
        """Close the synchronous connection."""
        if self._client and not self._use_fake:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None

    async def async_disconnect(self) -> None:
        """Close the asynchronous connection."""
        if self._async_client and not self._use_fake:
            try:
                await self._async_client.aclose()
            except Exception:
                pass
        self._async_client = None

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return True if the synchronous connection is alive."""
        try:
            if self._client is None:
                self.connect()
            return self._client.ping()
        except Exception as exc:
            logger.warning("RedisManager.ping failed: %s", exc)
            return False

    async def async_ping(self) -> bool:
        """Return True if the asynchronous connection is alive."""
        try:
            if self._async_client is None:
                await self.async_connect()
            return await self._async_client.ping()
        except Exception as exc:
            logger.warning("RedisManager.async_ping failed: %s", exc)
            return False

    def health_check(self) -> dict:
        """Return a health report dict."""
        try:
            alive = self.ping()
            info = {}
            if alive and self._client:
                raw = self._client.info("server")
                info = {
                    "version": raw.get("redis_version", "?"),
                    "uptime_seconds": raw.get("uptime_in_seconds", 0),
                    "used_memory_human": raw.get("used_memory_human", "?"),
                }
            return {
                "status": "ok" if alive else "error",
                "backend": "fakeredis" if self._use_fake else "redis",
                "host": self.config.host,
                "port": self.config.port,
                "db": self.config.db,
                **info,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Client accessors
    # ------------------------------------------------------------------

    @property
    def client(self):
        """Synchronous Redis client (auto-connects)."""
        if self._client is None:
            self.connect()
        return self._client

    @property
    def async_client(self):
        """Async Redis client — must call ``async_connect`` first."""
        return self._async_client

    # ------------------------------------------------------------------
    # Context managers
    # ------------------------------------------------------------------

    def __enter__(self) -> "RedisManager":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()

    async def __aenter__(self) -> "RedisManager":
        await self.async_connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.async_disconnect()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect_with_retry(self):
        """Attempt Redis connection with exponential backoff."""
        cfg = self.config
        delay = cfg.retry_delay

        for attempt in range(1, cfg.retry_max_attempts + 1):
            try:
                return self._make_sync_client()
            except Exception as exc:
                logger.warning(
                    "Redis sync connect attempt %d/%d failed: %s",
                    attempt, cfg.retry_max_attempts, exc,
                )
                if attempt < cfg.retry_max_attempts:
                    time.sleep(delay)
                    delay *= cfg.retry_backoff_factor

        logger.info("Redis unavailable — falling back to fakeredis (in-memory)")
        return self._make_fake_client()

    async def _async_connect_with_retry(self):
        """Attempt async Redis connection with exponential backoff."""
        cfg = self.config
        delay = cfg.retry_delay

        for attempt in range(1, cfg.retry_max_attempts + 1):
            try:
                client = await self._make_async_client()
                await client.ping()
                return client
            except Exception as exc:
                logger.warning(
                    "Redis async connect attempt %d/%d failed: %s",
                    attempt, cfg.retry_max_attempts, exc,
                )
                if attempt < cfg.retry_max_attempts:
                    await asyncio.sleep(delay)
                    delay *= cfg.retry_backoff_factor

        logger.info("Redis unavailable — falling back to async fakeredis")
        return self._make_async_fake_client()

    def _make_sync_client(self):
        import redis
        client = redis.Redis(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            retry_on_timeout=self.config.retry_on_timeout,
            max_connections=self.config.max_connections,
            decode_responses=True,
        )
        client.ping()  # fail fast
        logger.info("Connected to Redis at %s:%d/%d", self.config.host, self.config.port, self.config.db)
        return client

    async def _make_async_client(self):
        import redis.asyncio as aioredis
        client = aioredis.Redis(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            max_connections=self.config.max_connections,
            decode_responses=True,
        )
        return client

    def _make_fake_client(self):
        try:
            import fakeredis
            self._use_fake = True
            logger.info("Using fakeredis for in-memory Redis simulation")
            return fakeredis.FakeRedis(decode_responses=True)
        except ImportError:
            raise RuntimeError(
                "Neither Redis nor fakeredis is available. "
                "Install: pip install fakeredis"
            )

    def _make_async_fake_client(self):
        try:
            import fakeredis
            self._use_fake = True
            logger.info("Using async fakeredis for in-memory Redis simulation")
            return fakeredis.aioredis.FakeRedis(decode_responses=True)
        except (ImportError, AttributeError):
            try:
                import fakeredis.aioredis as fakeredis_aio
                self._use_fake = True
                return fakeredis_aio.FakeRedis(decode_responses=True)
            except ImportError:
                raise RuntimeError("fakeredis with asyncio support not available. pip install fakeredis")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_manager: Optional[RedisManager] = None


def get_redis_manager(config: Optional[RedisConfig] = None) -> RedisManager:
    """Return the module-level RedisManager singleton."""
    global _default_manager
    if _default_manager is None:
        _default_manager = RedisManager(config)
    return _default_manager
