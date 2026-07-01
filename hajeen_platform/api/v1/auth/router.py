"""Auth API Routes — تسجيل الدخول والتسجيل وإدارة التوكنات."""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

JWT_SECRET = os.getenv("JWT_SECRET", "hajeen-change-me-in-production-secret-key")


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)
    tenant_id: str = Field(default="default")
    roles: List[str] = Field(default=["user"])


class LoginRequest(BaseModel):
    username: str
    password: str
    tenant_id: str = "default"


class RefreshRequest(BaseModel):
    refresh_token: str


class RevokeRequest(BaseModel):
    token: str


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: List[str] = Field(default=["chat", "search"])
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    roles: List[str]
    tenant_id: str


# ── In-memory user store (يُستبدل بـ PostgreSQL في الإنتاج) ──────────────────

_USERS: Dict[str, Dict[str, Any]] = {
    "admin": {
        "user_id": "usr_admin",
        "username": "admin",
        "email": "admin@hajeen.ai",
        "password_hash": "__admin_placeholder__",
        "roles": ["superadmin"],
        "tenant_id": "default",
        "active": True,
    }
}


def _hash_password(password: str) -> str:
    import hashlib
    salt = os.getenv("PASSWORD_SALT", "hajeen-salt-change-me")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def _verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash == "__admin_placeholder__":
        return password == os.getenv("ADMIN_PASSWORD", "HajeenAdmin2024!")
    return _hash_password(password) == stored_hash


def _get_jwt_auth():
    from security.auth.jwt_auth import JWTAuthenticator
    import os
    return JWTAuthenticator(secret=os.getenv("JWT_SECRET", JWT_SECRET))


# ── POST /auth/register ───────────────────────────────────────────────────────

@router.post("/register", summary="تسجيل مستخدم جديد", status_code=201)
async def register(body: RegisterRequest) -> Dict[str, Any]:
    if body.username in _USERS:
        raise HTTPException(status_code=400, detail="اسم المستخدم موجود بالفعل")

    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    _USERS[body.username] = {
        "user_id": user_id,
        "username": body.username,
        "email": body.email,
        "password_hash": _hash_password(body.password),
        "roles": body.roles,
        "tenant_id": body.tenant_id,
        "active": True,
        "created_at": time.time(),
    }
    logger.info("New user registered: %s (tenant=%s)", body.username, body.tenant_id)
    return {
        "success": True,
        "user_id": user_id,
        "username": body.username,
        "roles": body.roles,
        "message": "تم تسجيل المستخدم بنجاح",
    }


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse, summary="تسجيل الدخول")
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    user = _USERS.get(body.username)
    if not user or not user.get("active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اسم المستخدم أو كلمة المرور غير صحيحة",
        )

    if not _verify_password(body.password, user["password_hash"]):
        logger.warning("Failed login attempt for user: %s", body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اسم المستخدم أو كلمة المرور غير صحيحة",
        )

    jwt = _get_jwt_auth()
    access_token = jwt.issue_token(
        user_id=user["user_id"],
        tenant_id=user["tenant_id"],
        roles=user["roles"],
        token_type="access",
    )
    refresh_token = jwt.issue_token(
        user_id=user["user_id"],
        tenant_id=user["tenant_id"],
        roles=user["roles"],
        token_type="refresh",
    )

    logger.info("User logged in: %s", body.username)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
        user_id=user["user_id"],
        roles=user["roles"],
        tenant_id=user["tenant_id"],
    )


# ── POST /auth/refresh ────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse, summary="تجديد التوكن")
async def refresh_token(body: RefreshRequest) -> TokenResponse:
    try:
        jwt = _get_jwt_auth()
        new_access = jwt.refresh_access_token(body.refresh_token)
        claims = jwt.validate_token(new_access)
        new_refresh = jwt.issue_token(
            claims.sub, claims.tenant_id, claims.roles, "refresh"
        )
        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=3600,
            user_id=claims.sub,
            roles=claims.roles,
            tenant_id=claims.tenant_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# ── POST /auth/revoke ─────────────────────────────────────────────────────────

@router.post("/revoke", summary="إلغاء صلاحية التوكن")
async def revoke_token(body: RevokeRequest) -> Dict[str, Any]:
    jwt = _get_jwt_auth()
    jwt.revoke_token(body.token)
    return {"success": True, "message": "تم إلغاء صلاحية التوكن"}


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get("/me", summary="معلومات المستخدم الحالي")
async def get_current_user(request: Request) -> Dict[str, Any]:
    user_id = getattr(request.state, "user_id", None)
    roles = getattr(request.state, "roles", [])
    tenant_id = getattr(request.state, "tenant_id", "default")
    if not user_id:
        raise HTTPException(status_code=401, detail="غير مصادق")
    return {
        "user_id": user_id,
        "roles": roles,
        "tenant_id": tenant_id,
        "permissions": [p.value for p in __import__(
            "security.rbac.rbac", fromlist=["get_all_permissions"]
        ).get_all_permissions(roles)],
    }


# ── POST /auth/apikeys ────────────────────────────────────────────────────────

@router.post("/apikeys", summary="إنشاء API Key جديد")
async def create_api_key(body: CreateAPIKeyRequest, request: Request) -> Dict[str, Any]:
    user_id = getattr(request.state, "user_id", "anonymous")
    tenant_id = getattr(request.state, "tenant_id", "default")

    import secrets
    raw_key = f"hj_{secrets.token_urlsafe(32)}"
    key_id = uuid.uuid4().hex[:16]

    logger.info("API key created: %s for user %s", key_id, user_id)
    return {
        "key_id": key_id,
        "key": raw_key,
        "name": body.name,
        "scopes": body.scopes,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "expires_in_days": body.expires_in_days,
        "warning": "احفظ هذا المفتاح بأمان — لن يُعرض مرة أخرى",
    }


# ── GET /auth/users ───────────────────────────────────────────────────────────

@router.get("/users", summary="قائمة المستخدمين (admin فقط)")
async def list_users(request: Request) -> Dict[str, Any]:
    roles = getattr(request.state, "roles", [])
    if "admin" not in roles and "superadmin" not in roles:
        raise HTTPException(status_code=403, detail="يجب أن تكون admin")
    safe_users = [
        {k: v for k, v in u.items() if k not in ("password_hash",)}
        for u in _USERS.values()
    ]
    return {"users": safe_users, "total": len(safe_users)}
