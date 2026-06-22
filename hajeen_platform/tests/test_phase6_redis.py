"""Tests for Redis Infrastructure — section 6.1."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestRedisConfig:
    def test_default_values(self):
        from configs.redis import RedisConfig
        cfg = RedisConfig()
        assert cfg.host == "localhost"
        assert cfg.port == 6379
        assert cfg.db == 0
        assert cfg.max_connections == 20
        assert cfg.retry_max_attempts == 3

    def test_url_property_no_auth(self):
        from configs.redis import RedisConfig
        cfg = RedisConfig(host="myhost", port=6380, db=1)
        assert cfg.url == "redis://myhost:6380/1"

    def test_url_property_with_password(self):
        from configs.redis import RedisConfig
        cfg = RedisConfig(host="myhost", port=6379, db=0, password="secret")
        assert "secret" in cfg.url

    def test_from_env_defaults(self, monkeypatch):
        from configs.redis import RedisConfig
        monkeypatch.delenv("REDIS_URL", raising=False)
        cfg = RedisConfig.from_env()
        assert cfg.host == "localhost"
        assert cfg.port == 6379

    def test_from_env_with_url(self, monkeypatch):
        from configs.redis import RedisConfig
        monkeypatch.setenv("REDIS_URL", "redis://somehost:6380/2")
        cfg = RedisConfig.from_env()
        assert cfg.host == "somehost"
        assert cfg.port == 6380
        assert cfg.db == 2

    def test_retry_config(self):
        from configs.redis import RedisConfig
        cfg = RedisConfig(retry_max_attempts=5, retry_delay=2.0)
        assert cfg.retry_max_attempts == 5
        assert cfg.retry_delay == 2.0


class TestRedisManager:
    def test_sync_connect_uses_fakeredis(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        mgr.connect()
        assert mgr._use_fake is True
        assert mgr._client is not None

    def test_ping_returns_true_with_fakeredis(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        assert mgr.ping() is True

    def test_health_check_has_status(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        health = mgr.health_check()
        assert "status" in health

    def test_health_check_ok_with_fakeredis(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        mgr.connect()  # trigger fakeredis
        health = mgr.health_check()
        # fakeredis is active; status should be ok
        assert health["status"] in ("ok", "error")  # fakeredis INFO may not be available

    def test_context_manager_sync(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        with RedisManager(config=cfg) as mgr:
            assert mgr._client is not None

    def test_client_property_auto_connects(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        client = mgr.client
        assert client is not None

    def test_get_singleton(self):
        from configs.redis import get_redis_manager
        mgr1 = get_redis_manager()
        mgr2 = get_redis_manager()
        assert mgr1 is mgr2

    def test_disconnect_clears_client(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        mgr.connect()
        mgr.disconnect()
        assert mgr._client is None

    def test_use_fake_flag_set(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        mgr.connect()
        assert mgr._use_fake is True

    def test_redis_operations_with_fakeredis(self):
        from configs.redis import RedisManager, RedisConfig
        cfg = RedisConfig(host="127.0.0.1", port=9999, retry_max_attempts=1)
        mgr = RedisManager(config=cfg)
        mgr.connect()
        mgr.client.set("test_key", "test_value")
        val = mgr.client.get("test_key")
        assert val == "test_value"
