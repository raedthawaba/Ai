"""API Key Manager — hashed key storage, validation, rotation, and revocation."""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "hj_"
API_KEY_LENGTH = 48
KEY_HASH_ALGO = "sha3_256"


@dataclass
class APIKey:
    key_id: str
    name: str
    tenant_id: str
    user_id: str
    scopes: List[str]
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None
    is_active: bool = True
    hash: str = ""


class APIKeyManager:
    """Manages API key lifecycle with hashed storage."""

    def __init__(self, db: Any, redis_client: Any) -> None:
        self.db = db
        self.redis = redis_client

    def generate_key(
        self,
        tenant_id: str,
        user_id: str,
        name: str,
        scopes: List[str],
        expires_in_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        raw_key = API_KEY_PREFIX + secrets.token_urlsafe(API_KEY_LENGTH)
        key_hash = self._hash_key(raw_key)
        key_id = secrets.token_hex(16)

        expires_at = None
        if expires_in_days:
            expires_at = time.time() + expires_in_days * 86400

        api_key = APIKey(
            key_id=key_id,
            name=name,
            tenant_id=tenant_id,
            user_id=user_id,
            scopes=scopes,
            expires_at=expires_at,
            hash=key_hash,
        )
        self._persist(api_key)

        return {
            "key_id": key_id,
            "key": raw_key,
            "name": name,
            "scopes": scopes,
            "expires_at": expires_at,
            "warning": "Store this key securely — it will not be shown again",
        }

    def validate_key(self, raw_key: str) -> Optional[APIKey]:
        if not raw_key.startswith(API_KEY_PREFIX):
            return None

        cache_key = f"apikey:validated:{self._hash_key(raw_key)}"
        cached = self.redis.get(cache_key)
        if cached:
            import json
            return APIKey(**json.loads(cached))

        key_hash = self._hash_key(raw_key)
        api_key = self._load_by_hash(key_hash)

        if not api_key or not api_key.is_active:
            return None

        if api_key.expires_at and time.time() > api_key.expires_at:
            return None

        self.redis.setex(cache_key, 300, self._serialize(api_key))
        self._update_last_used(api_key.key_id)
        return api_key

    def revoke_key(self, key_id: str, tenant_id: str) -> bool:
        result = self.db.execute(
            "UPDATE api_keys SET is_active = FALSE WHERE key_id = %s AND tenant_id = %s",
            (key_id, tenant_id),
        )
        self.redis.delete(f"apikey:id:{key_id}")
        return result.rowcount > 0

    def _hash_key(self, raw_key: str) -> str:
        return hashlib.new(KEY_HASH_ALGO, raw_key.encode()).hexdigest()

    def _persist(self, api_key: APIKey) -> None:
        self.db.execute(
            """INSERT INTO api_keys
               (key_id, name, tenant_id, user_id, scopes, hash,
                created_at, expires_at, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                api_key.key_id, api_key.name, api_key.tenant_id,
                api_key.user_id, api_key.scopes, api_key.hash,
                api_key.created_at, api_key.expires_at, api_key.is_active,
            ),
        )

    def _load_by_hash(self, key_hash: str) -> Optional[APIKey]:
        row = self.db.fetchone(
            "SELECT * FROM api_keys WHERE hash = %s", (key_hash,)
        )
        if row:
            return APIKey(**row)
        return None

    def _serialize(self, api_key: APIKey) -> str:
        import json
        return json.dumps(
            {k: v for k, v in api_key.__dict__.items() if k != "hash"}
        )

    def _update_last_used(self, key_id: str) -> None:
        self.redis.setex(f"apikey:last_used:{key_id}", 3600, str(time.time()))
