"""Tenant Router — FastAPI middleware that resolves tenant context from requests."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from multi_tenant.isolation import tenant_context
from multi_tenant.tenant_manager import TenantManager

logger = logging.getLogger(__name__)

TENANT_HEADER = "X-Tenant-ID"
PUBLIC_PATHS = {"/health", "/ready", "/metrics", "/api/v1/auth/login", "/api/v1/auth/register"}


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolves and validates tenant context for each request."""

    def __init__(self, app: ASGIApp, tenant_manager: TenantManager) -> None:
        super().__init__(app)
        self.tenant_manager = tenant_manager

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        tenant_id = self._resolve_tenant(request)
        user_id = request.state.user_id if hasattr(request.state, "user_id") else "anonymous"

        if not tenant_id:
            return JSONResponse(
                {"error": "Missing tenant context", "code": "TENANT_REQUIRED"},
                status_code=400,
            )

        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return JSONResponse(
                {"error": f"Tenant {tenant_id} not found", "code": "TENANT_NOT_FOUND"},
                status_code=404,
            )

        if tenant.status != "active":
            return JSONResponse(
                {"error": f"Tenant account is {tenant.status}", "code": "TENANT_INACTIVE"},
                status_code=403,
            )

        request.state.tenant_id = tenant_id
        request.state.tenant = tenant

        with tenant_context(tenant_id, user_id):
            response = await call_next(request)

        response.headers["X-Tenant-ID"] = tenant_id
        return response

    def _resolve_tenant(self, request: Request) -> Optional[str]:
        tenant_id = request.headers.get(TENANT_HEADER)
        if tenant_id:
            return tenant_id

        if hasattr(request.state, "claims"):
            return getattr(request.state.claims, "tenant_id", None)

        host = request.headers.get("host", "")
        if host and "." in host:
            subdomain = host.split(".")[0]
            if subdomain not in ("api", "www", "app"):
                return subdomain

        return None
