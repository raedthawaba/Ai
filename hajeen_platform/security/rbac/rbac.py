"""RBAC — Role-Based Access Control (Production-grade).

Roles hierarchy:
    superadmin > admin > developer > user > readonly > guest

Permissions are additive — a role inherits all permissions of lower roles.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Dict, FrozenSet, List, Optional, Set


class Role(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN      = "admin"
    DEVELOPER  = "developer"
    USER       = "user"
    READONLY   = "readonly"
    GUEST      = "guest"


class Permission(str, Enum):
    # AI Inference
    CHAT              = "chat"
    CHAT_STREAM       = "chat:stream"
    COMPLETION        = "completion"
    EMBEDDINGS        = "embeddings"
    RAG_QUERY         = "rag:query"
    MODELS_READ       = "models:read"
    EVALUATE          = "evaluate"

    # Data & Channels
    CHANNELS_READ     = "channels:read"
    CHANNELS_WRITE    = "channels:write"
    CHANNELS_DELETE   = "channels:delete"
    SEARCH            = "search"
    INDEX_WRITE       = "index:write"

    # Tasks & Jobs
    TASKS_READ        = "tasks:read"
    TASKS_WRITE       = "tasks:write"
    TASKS_DELETE      = "tasks:delete"
    JOBS_READ         = "jobs:read"
    JOBS_MANAGE       = "jobs:manage"

    # System
    STORAGE_READ      = "storage:read"
    STORAGE_WRITE     = "storage:write"
    HEALTH_READ       = "health:read"
    METRICS_READ      = "metrics:read"

    # Admin
    USERS_READ        = "users:read"
    USERS_WRITE       = "users:write"
    USERS_DELETE      = "users:delete"
    APIKEYS_MANAGE    = "apikeys:manage"
    APIKEYS_READ      = "apikeys:read"
    APIKEYS_CREATE    = "apikeys:create"
    APIKEYS_REVOKE    = "apikeys:revoke"
    AUDIT_READ        = "audit:read"
    CONFIG_WRITE      = "config:write"
    TRAINING_RUN      = "training:run"


_ROLE_PERMISSIONS: Dict[Role, FrozenSet[Permission]] = {
    Role.GUEST: frozenset({
        Permission.HEALTH_READ,
    }),
    Role.READONLY: frozenset({
        Permission.HEALTH_READ,
        Permission.MODELS_READ,
        Permission.CHANNELS_READ,
        Permission.SEARCH,
        Permission.TASKS_READ,
        Permission.JOBS_READ,
        Permission.STORAGE_READ,
        Permission.METRICS_READ,
    }),
    Role.USER: frozenset({
        Permission.HEALTH_READ,
        Permission.MODELS_READ,
        Permission.CHANNELS_READ,
        Permission.SEARCH,
        Permission.TASKS_READ,
        Permission.JOBS_READ,
        Permission.STORAGE_READ,
        Permission.CHAT,
        Permission.CHAT_STREAM,
        Permission.COMPLETION,
        Permission.EMBEDDINGS,
        Permission.RAG_QUERY,
        Permission.INDEX_WRITE,
    }),
    Role.DEVELOPER: frozenset({
        Permission.HEALTH_READ,
        Permission.MODELS_READ,
        Permission.CHANNELS_READ,
        Permission.CHANNELS_WRITE,
        Permission.SEARCH,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.JOBS_READ,
        Permission.JOBS_MANAGE,
        Permission.STORAGE_READ,
        Permission.STORAGE_WRITE,
        Permission.METRICS_READ,
        Permission.CHAT,
        Permission.CHAT_STREAM,
        Permission.COMPLETION,
        Permission.EMBEDDINGS,
        Permission.RAG_QUERY,
        Permission.INDEX_WRITE,
        Permission.EVALUATE,
        Permission.APIKEYS_MANAGE,
        Permission.APIKEYS_READ,
        Permission.APIKEYS_CREATE,
        Permission.APIKEYS_REVOKE,
    }),
    Role.ADMIN: frozenset({
        Permission.HEALTH_READ,
        Permission.MODELS_READ,
        Permission.CHANNELS_READ,
        Permission.CHANNELS_WRITE,
        Permission.CHANNELS_DELETE,
        Permission.SEARCH,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.TASKS_DELETE,
        Permission.JOBS_READ,
        Permission.JOBS_MANAGE,
        Permission.STORAGE_READ,
        Permission.STORAGE_WRITE,
        Permission.METRICS_READ,
        Permission.CHAT,
        Permission.CHAT_STREAM,
        Permission.COMPLETION,
        Permission.EMBEDDINGS,
        Permission.RAG_QUERY,
        Permission.INDEX_WRITE,
        Permission.EVALUATE,
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.APIKEYS_MANAGE,
        Permission.APIKEYS_READ,
        Permission.APIKEYS_CREATE,
        Permission.APIKEYS_REVOKE,
        Permission.AUDIT_READ,
        Permission.TRAINING_RUN,
    }),
    Role.SUPERADMIN: frozenset(Permission),
}


@lru_cache(maxsize=None)
def get_permissions(role: Role) -> FrozenSet[Permission]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(roles: List[str], permission: Permission) -> bool:
    for r in roles:
        try:
            role = Role(r)
            if permission in get_permissions(role):
                return True
        except ValueError:
            continue
    return False


def get_all_permissions(roles: List[str]) -> Set[Permission]:
    perms: Set[Permission] = set()
    for r in roles:
        try:
            perms |= get_permissions(Role(r))
        except ValueError:
            continue
    return perms


ROUTE_PERMISSIONS: Dict[str, Permission] = {
    "POST:/api/v1/ai/chat":                   Permission.CHAT,
    "POST:/api/v1/ai/chat/stream":             Permission.CHAT_STREAM,
    "POST:/api/v1/ai/completion":              Permission.COMPLETION,
    "POST:/api/v1/ai/completions":             Permission.COMPLETION,
    "POST:/api/v1/ai/embeddings":              Permission.EMBEDDINGS,
    "POST:/api/v1/ai/rag/query":               Permission.RAG_QUERY,
    "GET:/api/v1/ai/models":                   Permission.MODELS_READ,
    "GET:/api/v1/ai/stats":                    Permission.METRICS_READ,
    "POST:/api/v1/ai/evaluate":                Permission.EVALUATE,
    "POST:/api/v1/index/articles":             Permission.INDEX_WRITE,
    "GET:/api/v1/channels":                    Permission.CHANNELS_READ,
    "POST:/api/v1/channels":                   Permission.CHANNELS_WRITE,
    "PUT:/api/v1/channels":                    Permission.CHANNELS_WRITE,
    "DELETE:/api/v1/channels":                 Permission.CHANNELS_DELETE,
    "POST:/api/v1/search":                     Permission.SEARCH,
    "GET:/api/v1/tasks":                       Permission.TASKS_READ,
    "POST:/api/v1/tasks":                      Permission.TASKS_WRITE,
    "GET:/api/v1/storage/stats":               Permission.STORAGE_READ,
    "GET:/api/v1/auth/users":                  Permission.USERS_READ,
    "POST:/api/v1/auth/users":                 Permission.USERS_WRITE,
    "GET:/api/v1/auth/apikeys":                Permission.APIKEYS_READ,
    "POST:/api/v1/auth/apikeys":               Permission.APIKEYS_CREATE,
    "GET:/api/v1/auth/apikeys/{key_id}":       Permission.APIKEYS_READ,
    "DELETE:/api/v1/auth/apikeys/{key_id}":    Permission.APIKEYS_REVOKE,
    "GET:/api/v1/auth/audit":                  Permission.AUDIT_READ,
    "POST:/api/v1/auth/training/start":        Permission.TRAINING_RUN,
}
