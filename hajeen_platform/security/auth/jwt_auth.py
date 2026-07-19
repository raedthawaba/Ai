"""JWT Authentication — token issuance, validation, and refresh."""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import jwt
from hajeen_platform.security.auth.revoked_tokens import get_revoked_token_store

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "hajeen-jwt-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = 3600
REFRESH_TOKEN_TTL = 86400 * 30


@dataclass
class TokenClaims:
    sub: str
    tenant_id: str
    roles: List[str]
    jti: str
    iat: float
    exp: float
    type: str = "access"


class JWTAuthenticator:
    """Issues and validates JWT tokens."""

    def __init__(
        self,
        secret: str = JWT_SECRET,
        algorithm: str = JWT_ALGORITHM,
        revoked_store: Optional[Any] = None,
    ) -> None:
        self.secret = secret
        self.algorithm = algorithm
        self.revoked_store = revoked_store or get_revoked_token_store()

    def issue_token(
        self,
        user_id: str,
        tenant_id: str,
        roles: List[str],
        token_type: str = "access",
    ) -> str:
        now = time.time()
        ttl = ACCESS_TOKEN_TTL if token_type == "access" else REFRESH_TOKEN_TTL
        payload: Dict[str, Any] = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "roles": roles,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + ttl,
            "type": token_type,
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def validate_token(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise PermissionError("Token expired")
        except jwt.InvalidTokenError as exc:
            raise PermissionError(f"Invalid token: {exc}")

        if self.revoked_store and self.revoked_store.is_revoked(payload["jti"]):
            raise PermissionError("Token revoked")

        return TokenClaims(
            sub=payload["sub"],
            tenant_id=payload["tenant_id"],
            roles=payload.get("roles", []),
            jti=payload["jti"],
            iat=payload["iat"],
            exp=payload["exp"],
            type=payload.get("type", "access"),
        )

    def revoke_token(self, token: str) -> None:
        try:
            payload = jwt.decode(
                token, self.secret, algorithms=[self.algorithm],
                options={"verify_exp": False},
            )
            if self.revoked_store:
                ttl = max(0, int(payload["exp"] - time.time()))
                self.revoked_store.revoke(payload["jti"], ttl)
        except jwt.InvalidTokenError:
            pass

    def refresh_access_token(self, refresh_token: str) -> str:
        claims = self.validate_token(refresh_token)
        if claims.type != "refresh":
            raise PermissionError("Not a refresh token")
        return self.issue_token(claims.sub, claims.tenant_id, claims.roles)
