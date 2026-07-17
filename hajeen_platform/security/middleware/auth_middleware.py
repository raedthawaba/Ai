"""Production Auth Middleware — JWT + API Key + RBAC + Rate Limiting.

يحمي جميع routes تلقائياً ما عدا القائمة البيضاء.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from hajeen_platform.security.rbac.rbac import ROUTE_PERMISSIONS, Permission, has_permission
from hajeen_platform.security.audit.audit_logger import AuditAction, get_audit_logger

logger = logging.getLogger(__name__)

# ── المسارات المسموحة بدون مصادقة ──────────────────────────────────────────
PUBLIC_PATHS: frozenset[str] = frozenset({
    "/health",
    "/ping",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/health",
    "/api/v1/ping",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/ws/chat",
})

# ── استخراج التوكن من الطلب ────────────────────────────────────────────────

def _extract_token(request: Request) -> Tuple[Optional[str], str]:
    """Returns (token, token_type): token_type is 'bearer' or 'apikey'."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip(), "bearer"
    api_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("x-api-key")
        or request.query_params.get("api_key")
    )
    if api_key:
        return api_key, "apikey"
    return None, "none"


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware شامل: JWT/APIKey auth + RBAC + Rate Limiting + Audit."""

    def __init__(self, app, enable_rate_limiting: bool = True) -> None:
        super().__init__(app)
        self._rate_limiting = enable_rate_limiting
        self._jwt_auth = None
        self._api_key_manager = None
        self._rate_limiter = None
        self._audit = get_audit_logger()

    def _lazy_init(self) -> None:
        if self._jwt_auth is None:
            try:
                from hajeen_platform.security.auth.jwt_auth import JWTAuthenticator
                self._jwt_auth = JWTAuthenticator()
            except Exception as e:
                logger.warning("JWT auth init failed: %s", e)

        if self._api_key_manager is None:
            try:
                from hajeen_platform.security.auth.api_key_manager import get_api_key_manager
                self._api_key_manager = get_api_key_manager()
            except Exception as e:
                logger.warning("JWT auth init failed: %s", e)

        if self._rate_limiter is None and self._rate_limiting:
            try:
                import redis as redis_lib
                import os
                r = redis_lib.from_url(
                    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                r.ping()
                from hajeen_platform.security.rate_limit.rate_limiter import RateLimiter
                self._rate_limiter = RateLimiter(r)
            except Exception as e:
                logger.warning("Rate limiter Redis unavailable: %s — skipping", e)

    async def dispatch(self, request: Request, call_next: Callable):
        self._lazy_init()
        start = time.monotonic()
        path = request.url.path
        method = request.method
        ip = _get_client_ip(request)

        # ── 1. المسارات العامة ────────────────────────────────────────────
        if path in PUBLIC_PATHS or method == "OPTIONS":
            response = await call_next(request)
            return response

        # ── 2. استخراج التوكن ─────────────────────────────────────────────
        token, token_type = _extract_token(request)
        user_id = "anonymous"
        tenant_id = "default"
        roles: list[str] = []

        if token:
            if token_type == "bearer" and self._jwt_auth:
                try:
                    claims = self._jwt_auth.validate_token(token)
                    user_id = claims.sub
                    tenant_id = claims.tenant_id
                    roles = claims.roles
                    request.state.user_id = user_id
                    request.state.tenant_id = tenant_id
                    request.state.roles = roles
                    request.state.claims = claims
                except PermissionError as e:
                    self._audit.log(
                        AuditAction.LOGIN_FAILED, "auth", "jwt_validation", tenant_id, user_id, ip_address=ip,
                        status="denied", error=str(e),
                    )
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"error": "unauthorized", "message": str(e)},
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            elif token_type == "apikey" and self._api_key_manager:
                api_key = self._api_key_manager.validate_key(token)
                if not api_key:
                    self._audit.log(
                        AuditAction.LOGIN_FAILED, "auth", "api_key_validation", tenant_id, user_id, ip_address=ip,
                        status="denied", error="API key invalid or expired",
                    )
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"error": "unauthorized", "message": "API key invalid or expired"},
                    )
                user_id = api_key.user_id
                tenant_id = api_key.tenant_id
                roles = api_key.roles # Use roles from APIKey object
                request.state.user_id = user_id
                request.state.tenant_id = tenant_id
                request.state.roles = roles
                request.state.api_key = api_key
        else:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "unauthorized",
                    "message": "يجب تقديم Authorization header أو X-API-Key",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # ── 3. Rate Limiting ──────────────────────────────────────────────
        if self._rate_limiter:
            endpoint_key = "inference" if "/ai/" in path else "default"
            allowed, meta = self._rate_limiter.check(
                identifier=user_id, endpoint=endpoint_key, tenant_id=tenant_id
            )
            if not allowed:
                self._audit.log(
                    AuditAction.RATE_LIMITED, "system", "rate_limiter", tenant_id, user_id, ip_address=ip,
                    status="denied", metadata=meta
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": "تجاوزت الحد المسموح به من الطلبات",
                        "retry_after": meta["reset"],
                        "limit": meta["limit"],
                    },
                    headers={
                        "X-RateLimit-Limit": str(meta["limit"]),
                        "X-RateLimit-Remaining": str(meta["remaining"]),
                        "X-RateLimit-Reset": str(meta["reset"]),
                        "Retry-After": str(meta["reset"] - int(time.time())),
                    },
                )

        # ── 4. RBAC Permission Check ───────────────────────────────────────
        route_key = f"{method}:{path}"
        base_path = "/" + "/".join(path.split("/")[:5])
        base_key = f"{method}:{base_path}"

        required_permission = (
            ROUTE_PERMISSIONS.get(route_key)
            or ROUTE_PERMISSIONS.get(base_key)
        )

        if required_permission and not has_permission(roles, required_permission):
            self._audit.log(
                AuditAction.PERMISSION_DENIED, "auth", "rbac_check", tenant_id, user_id, ip_address=ip,
                status="denied", details={"permission": required_permission.value, "path": path}
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "forbidden",
                    "message": f"لا تملك صلاحية: {required_permission.value}",
                    "required_permission": required_permission.value,
                    "your_roles": roles,
                },
            )

        # ── 5. تنفيذ الطلب ────────────────────────────────────────────────
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        response.headers["X-User-ID"] = user_id
        response.headers["X-Tenant-ID"] = tenant_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)

        return response
