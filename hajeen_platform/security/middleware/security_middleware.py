"""Security Middleware — Phase 7 — JWT, RBAC, Rate Limiting, Headers."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# JWT Authentication
# ──────────────────────────────────────────────────────────────────────────────

_SECRET = os.getenv("JWT_SECRET", "hajeen-change-me-in-production")
_ALGORITHM = "HS256"
_TOKEN_TTL = int(os.getenv("JWT_TTL_SECONDS", "3600"))


def create_token(
    user_id: str,
    roles: List[str],
    extra: Optional[Dict] = None,
    ttl: int = _TOKEN_TTL,
) -> str:
    """يُنشئ JWT token حقيقي (PyJWT إذا متاح، وإلا HMAC بسيط)."""
    payload = {
        "sub": user_id,
        "roles": roles,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
        **(extra or {}),
    }
    try:
        import jwt
        return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    except ImportError:
        # HMAC fallback
        import base64
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        body = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b"=")
        sig = hmac.new(
            _SECRET.encode(), f"{header.decode()}.{body.decode()}".encode(),
            hashlib.sha256,
        ).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
        return f"{header.decode()}.{body.decode()}.{sig_b64.decode()}"


def verify_token(token: str) -> Dict:
    """يتحقق من صحة الـ token ويُعيد الـ payload."""
    try:
        import jwt
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
        return payload
    except ImportError:
        return _verify_hmac(token)
    except Exception as exc:
        raise ValueError(f"Token غير صالح: {exc}") from exc


def _verify_hmac(token: str) -> Dict:
    import base64
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("تنسيق Token خاطئ")
    header, body, sig = parts
    expected_sig = hmac.new(
        _SECRET.encode(),
        f"{header}.{body}".encode(),
        hashlib.sha256,
    ).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()
    if not hmac.compare_digest(sig, expected_b64):
        raise ValueError("توقيع Token خاطئ")
    payload = json.loads(base64.urlsafe_b64decode(body + "=="))
    if payload.get("exp", 0) < time.time():
        raise ValueError("Token منتهي الصلاحية")
    return payload


# ──────────────────────────────────────────────────────────────────────────────
# RBAC Authorization
# ──────────────────────────────────────────────────────────────────────────────

_ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {
        "read", "write", "delete", "manage_users",
        "manage_channels", "manage_models", "view_metrics",
    },
    "editor": {"read", "write", "manage_channels"},
    "viewer": {"read", "view_metrics"},
    "api_client": {"read", "write"},
}


def has_permission(roles: List[str], required: str) -> bool:
    for role in roles:
        if required in _ROLE_PERMISSIONS.get(role, set()):
            return True
    return False


def require_permission(permission: str) -> Callable:
    """Decorator للتحقق من الصلاحية."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, token: str, **kwargs: Any) -> Any:
            payload = verify_token(token)
            roles = payload.get("roles", [])
            if not has_permission(roles, permission):
                raise PermissionError(
                    f"المستخدم لا يملك صلاحية '{permission}'"
                )
            return fn(*args, **kwargs, token=token)
        return wrapper
    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ──────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Token bucket rate limiter — async-safe.

    max_requests: الحد الأقصى للطلبات
    window_seconds: نافذة الوقت
    """

    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: Dict[str, list] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """يُعيد True إذا كان الطلب مسموحاً، False إذا تجاوز الحد."""
        now = time.time()
        cutoff = now - self._window
        bucket = self._buckets[key]
        # إزالة الطلبات القديمة
        self._buckets[key] = [t for t in bucket if t > cutoff]
        if len(self._buckets[key]) >= self._max:
            logger.warning("Rate limit exceeded for key: %s", key[:50])
            return False
        self._buckets[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        now = time.time()
        cutoff = now - self._window
        used = len([t for t in self._buckets.get(key, []) if t > cutoff])
        return max(0, self._max - used)

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)

    def cleanup_expired(self) -> int:
        """إزالة البيانات المنتهية من الذاكرة."""
        now = time.time()
        cutoff = now - self._window
        removed = 0
        keys_to_delete = []
        for key, times in self._buckets.items():
            fresh = [t for t in times if t > cutoff]
            if not fresh:
                keys_to_delete.append(key)
            else:
                self._buckets[key] = fresh
            removed += len(times) - len(fresh)
        for k in keys_to_delete:
            del self._buckets[k]
        return removed


# ──────────────────────────────────────────────────────────────────────────────
# Input Sanitization
# ──────────────────────────────────────────────────────────────────────────────

_DANGEROUS_PATTERNS = [
    "<script", "javascript:", "data:", "onerror=",
    "onload=", "onclick=", "eval(", "document.cookie",
    "../", "..\\", "/etc/passwd", "cmd.exe",
]


def sanitize_input(value: str, max_length: int = 10_000) -> str:
    """تنظيف المدخلات من الأنماط الخطرة."""
    if not isinstance(value, str):
        return str(value)[:max_length]
    value = value[:max_length]
    lower = value.lower()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in lower:
            logger.warning("خطر محتمل في المدخلات: %s", pattern)
            value = value.replace(pattern, "")
    return value.strip()


def validate_api_key(api_key: str, valid_keys: Set[str]) -> bool:
    """التحقق من API key باستخدام constant-time comparison."""
    for valid in valid_keys:
        if hmac.compare_digest(
            hashlib.sha256(api_key.encode()).hexdigest(),
            hashlib.sha256(valid.encode()).hexdigest(),
        ):
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Secure Headers
# ──────────────────────────────────────────────────────────────────────────────

SECURE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store",
}


# ──────────────────────────────────────────────────────────────────────────────
# Singletons
# ──────────────────────────────────────────────────────────────────────────────

_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(max_requests: int = 100, window: int = 60) -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(max_requests=max_requests, window_seconds=window)
    return _rate_limiter
