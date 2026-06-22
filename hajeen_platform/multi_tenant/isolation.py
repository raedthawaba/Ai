"""
Tenant Isolation — ensures data and resource isolation between tenants.
Provides context-aware database filtering and namespace separation.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)
_current_user: ContextVar[Optional[str]] = ContextVar("current_user", default=None)


@contextmanager
def tenant_context(tenant_id: str, user_id: str) -> Generator[None, None, None]:
    t = _current_tenant.set(tenant_id)
    u = _current_user.set(user_id)
    try:
        yield
    finally:
        _current_tenant.reset(t)
        _current_user.reset(u)


def get_current_tenant() -> Optional[str]:
    return _current_tenant.get()


def get_current_user() -> Optional[str]:
    return _current_user.get()


def require_tenant() -> str:
    tenant_id = get_current_tenant()
    if not tenant_id:
        raise RuntimeError("No tenant context set — call tenant_context first")
    return tenant_id


class TenantAwareQuery:
    """Adds automatic tenant_id filtering to database queries."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def fetchone(self, sql: str, params: tuple = (), enforce: bool = True) -> Optional[Any]:
        tenant_id = require_tenant() if enforce else get_current_tenant()
        if tenant_id and "tenant_id" in sql:
            return self.db.fetchone(sql, params + (tenant_id,))
        return self.db.fetchone(sql, params)

    def fetchall(self, sql: str, params: tuple = (), enforce: bool = True) -> list:
        tenant_id = require_tenant() if enforce else get_current_tenant()
        if tenant_id:
            augmented = f"{sql} AND tenant_id = %s" if "WHERE" in sql.upper() else f"{sql} WHERE tenant_id = %s"
            return self.db.fetchall(augmented, params + (tenant_id,))
        return self.db.fetchall(sql, params)

    def execute(self, sql: str, params: tuple = (), enforce: bool = True) -> Any:
        tenant_id = require_tenant() if enforce else get_current_tenant()
        if tenant_id and "tenant_id" not in sql:
            logger.warning(
                "Write query without tenant_id filter may affect multiple tenants: %s", sql[:100]
            )
        return self.db.execute(sql, params)
