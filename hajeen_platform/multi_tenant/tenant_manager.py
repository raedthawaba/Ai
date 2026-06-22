"""Tenant Manager — manages tenant lifecycle, configuration, and isolation."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Tenant:
    tenant_id: str
    name: str
    plan: str
    status: str = "active"
    created_at: float = field(default_factory=time.time)
    settings: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


PLAN_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "free": {
        "max_requests_per_day": 100,
        "max_tokens_per_request": 1024,
        "max_models": 1,
        "max_users": 3,
        "storage_gb": 1,
        "gpu_minutes_per_month": 0,
        "features": ["inference", "rag_basic"],
    },
    "starter": {
        "max_requests_per_day": 1000,
        "max_tokens_per_request": 4096,
        "max_models": 5,
        "max_users": 10,
        "storage_gb": 10,
        "gpu_minutes_per_month": 100,
        "features": ["inference", "rag", "fine_tuning_basic"],
    },
    "professional": {
        "max_requests_per_day": 10000,
        "max_tokens_per_request": 8192,
        "max_models": 20,
        "max_users": 50,
        "storage_gb": 100,
        "gpu_minutes_per_month": 1000,
        "features": ["inference", "rag", "fine_tuning", "agents", "api_access"],
    },
    "enterprise": {
        "max_requests_per_day": -1,
        "max_tokens_per_request": 32768,
        "max_models": -1,
        "max_users": -1,
        "storage_gb": -1,
        "gpu_minutes_per_month": -1,
        "features": ["*"],
    },
}


class TenantManager:
    """Manages tenant lifecycle and configuration."""

    def __init__(self, db: Any, redis_client: Any) -> None:
        self.db = db
        self.redis = redis_client

    def create_tenant(
        self,
        name: str,
        plan: str,
        admin_user_id: str,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Tenant:
        if plan not in PLAN_DEFAULTS:
            raise ValueError(f"Invalid plan: {plan}. Valid: {list(PLAN_DEFAULTS.keys())}")

        tenant_id = f"t_{uuid.uuid4().hex[:12]}"
        tenant_settings = {**PLAN_DEFAULTS[plan], **(settings or {})}

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            plan=plan,
            settings=tenant_settings,
        )
        self._persist(tenant)
        self._init_tenant_resources(tenant)
        logger.info("Created tenant %s (%s) on plan %s", name, tenant_id, plan)
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        cache_key = f"tenant:{tenant_id}"
        cached = self.redis.get(cache_key)
        if cached:
            import json
            data = json.loads(cached)
            return Tenant(**data)

        row = self.db.fetchone("SELECT * FROM tenants WHERE tenant_id = %s", (tenant_id,))
        if not row:
            return None

        tenant = Tenant(**row)
        import json
        self.redis.setex(cache_key, 300, json.dumps(row))
        return tenant

    def upgrade_plan(self, tenant_id: str, new_plan: str) -> Tenant:
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        tenant.plan = new_plan
        tenant.settings.update(PLAN_DEFAULTS[new_plan])
        self._update(tenant)
        self.redis.delete(f"tenant:{tenant_id}")
        logger.info("Upgraded tenant %s to plan %s", tenant_id, new_plan)
        return tenant

    def suspend_tenant(self, tenant_id: str, reason: str) -> None:
        self.db.execute(
            "UPDATE tenants SET status = 'suspended', metadata = jsonb_set(metadata, '{suspension_reason}', %s) WHERE tenant_id = %s",
            (f'"{reason}"', tenant_id),
        )
        self.redis.delete(f"tenant:{tenant_id}")
        logger.warning("Suspended tenant %s: %s", tenant_id, reason)

    def _persist(self, tenant: Tenant) -> None:
        import json
        self.db.execute(
            "INSERT INTO tenants (tenant_id, name, plan, status, created_at, settings, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (tenant.tenant_id, tenant.name, tenant.plan, tenant.status,
             tenant.created_at, json.dumps(tenant.settings), json.dumps(tenant.metadata)),
        )

    def _update(self, tenant: Tenant) -> None:
        import json
        self.db.execute(
            "UPDATE tenants SET plan = %s, settings = %s WHERE tenant_id = %s",
            (tenant.plan, json.dumps(tenant.settings), tenant.tenant_id),
        )

    def _init_tenant_resources(self, tenant: Tenant) -> None:
        self.redis.hset(f"tenant:quota:{tenant.tenant_id}", mapping={
            "requests_today": 0,
            "tokens_today": 0,
            "gpu_minutes_used": 0,
        })
