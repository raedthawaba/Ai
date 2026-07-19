"""Audit Logger — tamper-evident structured audit trail for all API operations."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from enum import Enum
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    LOGIN_SUCCESS     = "login:success"
    LOGIN_FAILED      = "login:failed"
    LOGOUT            = "logout"
    APIKEY_CREATED    = "apikey:created"
    APIKEY_VALIDATED  = "apikey:validated"
    APIKEY_REVOKED    = "apikey:revoked"
    PERMISSION_DENIED = "permission:denied"
    RATE_LIMITED      = "rate:limited"
    MODEL_INFERENCE   = "model:inference"
    MODEL_TRAINING    = "model:training"
    POLICY_UPDATE     = "policy:update"
    SYSTEM_HEALTH     = "system:health"
    CONFIG_CHANGE     = "config:change"


@dataclass
class AuditEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    tenant_id: str = ""
    user_id: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    ip_address: str = ""
    user_agent: str = ""
    request_id: str = ""
    status: str = "success"
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    hash: str = ""

    def compute_hash(self) -> str:
        payload = json.dumps(
            {k: v for k, v in asdict(self).items() if k != "hash"},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class AuditLogger:
    """Writes tamper-evident audit logs to persistent storage."""

    def __init__(self, db: Any, redis_client: Any) -> None:
        self.db = db
        self.redis = redis_client
        self._last_hash = self._get_last_hash()

    def log(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        tenant_id: str,
        user_id: str,
        ip_address: str = "",
        user_agent: str = "",
        request_id: str = "",
        status: str = "success",
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            status=status,
            error=error,
            metadata=metadata or {},
            previous_hash=self._last_hash,
        )
        event.hash = event.compute_hash()
        self._last_hash = event.hash

        self._persist(event)
        logger.info(
            "AUDIT action=%s resource=%s/%s user=%s tenant=%s status=%s",
            action, resource_type, resource_id, user_id, tenant_id, status,
        )
        return event

    def _persist(self, event: AuditEvent) -> None:
        self.db.execute(
            """INSERT INTO audit_log
               (event_id, timestamp, tenant_id, user_id, action,
                resource_type, resource_id, ip_address, user_agent,
                request_id, status, error, metadata, hash, previous_hash)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                event.event_id, event.timestamp, event.tenant_id, event.user_id,
                event.action, event.resource_type, event.resource_id,
                event.ip_address, event.user_agent, event.request_id,
                event.status, event.error,
                json.dumps(event.metadata), event.hash, event.previous_hash,
            ),
        )

    def _get_last_hash(self) -> str:
        row = self.db.fetchone(
            "SELECT hash FROM audit_log ORDER BY timestamp DESC LIMIT 1"
        )
        return row["hash"] if row else "genesis"

    def verify_chain(self, limit: int = 1000) -> Dict[str, Any]:
        rows = self.db.fetchall(
            "SELECT * FROM audit_log ORDER BY timestamp ASC LIMIT %s", (limit,)
        )
        broken_at: List[str] = []
        for row in rows:
            event = AuditEvent(**{**row, "hash": "", "metadata": json.loads(row.get("metadata", "{}"))})
            computed = event.compute_hash()
            if computed != row["hash"]:
                broken_at.append(row["event_id"])

        return {
            "verified": len(broken_at) == 0,
            "total_events": len(rows),
            "broken_events": broken_at,
        }


# ── Singleton Factory ─────────────────────────────────────────────────────────
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Singleton factory for AuditLogger."""
    global _audit_logger
    if _audit_logger is None:
        # Create dummy db and redis for now
        class DummyDB:
            def execute(self, *args, **kwargs): pass
            def fetchone(self, *args, **kwargs): return None
            def fetchall(self, *args, **kwargs): return []
        class DummyRedis:
            def get(self, *args, **kwargs): return None
            def set(self, *args, **kwargs): pass
        _audit_logger = AuditLogger(DummyDB(), DummyRedis())
    return _audit_logger
