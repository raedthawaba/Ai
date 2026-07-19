import time
from typing import Dict

class RevokedTokenStore:
    """A simple in-memory store for revoked JWT tokens."""
    def __init__(self):
        self._revoked_tokens: Dict[str, float] = {}

    def revoke(self, jti: str, expires_at: float):
        """Revokes a token by its JTI (JWT ID) until its expiration time."""
        self._revoked_tokens[jti] = expires_at

    def is_revoked(self, jti: str) -> bool:
        """Checks if a token is revoked and not yet expired."""
        expires_at = self._revoked_tokens.get(jti)
        if expires_at and expires_at > time.time():
            return True
        # Clean up expired revoked tokens
        if expires_at and expires_at <= time.time():
            del self._revoked_tokens[jti]
        return False

    def cleanup_expired_tokens(self):
        """Removes all expired revoked tokens from the store."""
        current_time = time.time()
        self._revoked_tokens = {jti: exp for jti, exp in self._revoked_tokens.items() if exp > current_time}

# Singleton instance
_revoked_store: RevokedTokenStore | None = None

def get_revoked_token_store() -> RevokedTokenStore:
    global _revoked_store
    if _revoked_store is None:
        _revoked_store = RevokedTokenStore()
    return _revoked_store
