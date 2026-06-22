"""Tenant Config — manages per-tenant feature flags and configuration overrides."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import redis

logger = logging.getLogger(__name__)


class TenantConfig:
    """Per-tenant configuration with Redis caching and DB persistence."""

    CACHE_TTL = 300

    def __init__(self, db: Any, redis_client: redis.Redis) -> None:
        self.db = db
        self.redis = redis_client

    def get(self, tenant_id: str, key: str, default: Any = None) -> Any:
        config = self._load(tenant_id)
        return config.get(key, default)

    def set(self, tenant_id: str, key: str, value: Any) -> None:
        config = self._load(tenant_id)
        config[key] = value
        self._save(tenant_id, config)
        self.redis.delete(f"tenant:config:{tenant_id}")
        logger.info("Tenant %s config updated: %s", tenant_id, key)

    def get_all(self, tenant_id: str) -> Dict[str, Any]:
        return self._load(tenant_id)

    def is_feature_enabled(self, tenant_id: str, feature: str) -> bool:
        config = self._load(tenant_id)
        features = config.get("features", [])
        return feature in features or "*" in features

    def _load(self, tenant_id: str) -> Dict[str, Any]:
        cache_key = f"tenant:config:{tenant_id}"
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        row = self.db.fetchone(
            "SELECT settings FROM tenants WHERE tenant_id = %s", (tenant_id,)
        )
        config = json.loads(row["settings"]) if row else {}
        self.redis.setex(cache_key, self.CACHE_TTL, json.dumps(config))
        return config

    def _save(self, tenant_id: str, config: Dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE tenants SET settings = %s WHERE tenant_id = %s",
            (json.dumps(config), tenant_id),
        )
