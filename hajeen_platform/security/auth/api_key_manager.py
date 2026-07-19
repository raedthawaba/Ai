import os
import secrets
import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hajeen_platform.security.rbac.rbac import Permission, Role

@dataclass
class APIKey:
    key_id: str
    hashed_key: str
    user_id: str
    tenant_id: str
    roles: List[str]
    created_at: float
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None
    is_active: bool = True
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, any]:
        return {
            "key_id": self.key_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "roles": self.roles,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

class APIKeyManager:
    """Manages API key generation, storage, validation, and revocation."""

    def __init__(self):
        # In a real application, this would be a persistent store (database)
        self._api_keys: Dict[str, APIKey] = {}

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def generate_key(self, user_id: str, tenant_id: str, roles: List[str], expires_in_seconds: Optional[int] = None, metadata: Optional[Dict[str, str]] = None) -> Tuple[str, APIKey]:
        raw_key = secrets.token_urlsafe(32)  # Generate a random URL-safe string
        hashed_key = self._hash_key(raw_key)
        key_id = secrets.token_hex(16) # Unique ID for the key
        created_at = time.time()
        expires_at = created_at + expires_in_seconds if expires_in_seconds else None

        api_key = APIKey(
            key_id=key_id,
            hashed_key=hashed_key,
            user_id=user_id,
            tenant_id=tenant_id,
            roles=roles,
            created_at=created_at,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        self._api_keys[key_id] = api_key
        return raw_key, api_key

    def validate_key(self, raw_key: str) -> Optional[APIKey]:
        hashed_key = self._hash_key(raw_key)
        for key_id, api_key in self._api_keys.items():
            if api_key.hashed_key == hashed_key and api_key.is_active:
                if api_key.expires_at and api_key.expires_at < time.time():
                    api_key.is_active = False # Mark as expired
                    return None
                api_key.last_used_at = time.time()
                return api_key
        return None

    def revoke_key(self, key_id: str) -> bool:
        if key_id in self._api_keys:
            self._api_keys[key_id].is_active = False
            return True
        return False

    def get_key_by_id(self, key_id: str) -> Optional[APIKey]:
        return self._api_keys.get(key_id)

    def get_all_keys_for_user(self, user_id: str) -> List[APIKey]:
        return [key for key in self._api_keys.values() if key.user_id == user_id]

# Singleton instance
_api_key_manager: Optional[APIKeyManager] = None

def get_api_key_manager() -> APIKeyManager:
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager
