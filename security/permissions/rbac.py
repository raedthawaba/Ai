"""RBAC — Role-Based Access Control with hierarchical permissions."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    INFERENCE_READ = "inference:read"
    INFERENCE_WRITE = "inference:write"
    TRAINING_READ = "training:read"
    TRAINING_WRITE = "training:write"
    TRAINING_ADMIN = "training:admin"
    MODEL_READ = "model:read"
    MODEL_WRITE = "model:write"
    MODEL_ADMIN = "model:admin"
    DATA_READ = "data:read"
    DATA_WRITE = "data:write"
    DATA_ADMIN = "data:admin"
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_ADMIN = "user:admin"
    TENANT_ADMIN = "tenant:admin"
    SYSTEM_ADMIN = "system:admin"
    API_KEY_READ = "apikey:read"
    API_KEY_WRITE = "apikey:write"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS: Dict[str, Set[Permission]] = {
    "viewer": {
        Permission.INFERENCE_READ,
        Permission.MODEL_READ,
        Permission.DATA_READ,
    },
    "user": {
        Permission.INFERENCE_READ,
        Permission.INFERENCE_WRITE,
        Permission.MODEL_READ,
        Permission.DATA_READ,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
    },
    "developer": {
        Permission.INFERENCE_READ,
        Permission.INFERENCE_WRITE,
        Permission.MODEL_READ,
        Permission.MODEL_WRITE,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.TRAINING_READ,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
    },
    "admin": {
        Permission.INFERENCE_READ,
        Permission.INFERENCE_WRITE,
        Permission.MODEL_READ,
        Permission.MODEL_WRITE,
        Permission.MODEL_ADMIN,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.DATA_ADMIN,
        Permission.TRAINING_READ,
        Permission.TRAINING_WRITE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
        Permission.AUDIT_READ,
        Permission.TENANT_ADMIN,
    },
    "superadmin": {p for p in Permission},
}


@dataclass
class RBACContext:
    user_id: str
    tenant_id: str
    roles: List[str]
    _permissions: Set[Permission] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        for role in self.roles:
            self._permissions.update(ROLE_PERMISSIONS.get(role, set()))

    def has_permission(self, permission: Permission) -> bool:
        return permission in self._permissions

    def require_permission(self, permission: Permission) -> None:
        if not self.has_permission(permission):
            logger.warning(
                "Permission denied: user=%s tenant=%s required=%s roles=%s",
                self.user_id, self.tenant_id, permission, self.roles,
            )
            raise PermissionError(
                f"Permission '{permission.value}' required — your roles: {self.roles}"
            )

    def get_permissions(self) -> List[str]:
        return [p.value for p in self._permissions]
