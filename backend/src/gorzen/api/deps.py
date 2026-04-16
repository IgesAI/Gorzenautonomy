"""Shared FastAPI dependencies (auth).

Authentication is JWT (HS256 by default). The admin password is verified
against a bcrypt hash stored in ``settings.admin_password_hash``; the legacy
plaintext ``settings.admin_password`` is accepted only as a fallback and logs
a warning at startup.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from gorzen.config import settings

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)

# Bcrypt context for admin password verification. ``passlib`` handles the
# work-factor and constant-time comparison internally.
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthUser(BaseModel):
    """Authenticated principal (JWT or dev bypass)."""

    username: str
    role: str = "admin"


def _issue_token(username: str, role: str = "admin") -> str:
    from datetime import datetime, timedelta, timezone

    if not settings.jwt_secret.strip():
        raise RuntimeError("JWT secret not configured")
    if len(settings.jwt_secret) < 32:
        # Still proceed — app startup already logs the warning — but never
        # silently issue a token with a short secret in production.
        logger.warning("Issuing JWT with a short secret (< 32 chars).")
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": username,
        "role": role,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(username: str, role: str = "admin") -> str:
    if not settings.auth_enabled:
        raise RuntimeError("JWT secret not configured")
    return _issue_token(username, role)


def decode_token(token: str) -> AuthUser:
    if not settings.auth_enabled:
        return AuthUser(username="dev", role="admin")
    allowed = [a for a in settings.jwt_allowed_algorithms if a.strip()]
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT algorithm allowlist is empty",
        )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=allowed)
        sub = payload.get("sub")
        if not sub or not isinstance(sub, str):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        role = payload.get("role", "operator")
        if not isinstance(role, str):
            role = "operator"
        return AuthUser(username=sub, role=role)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security_bearer)],
) -> AuthUser:
    if not settings.auth_enabled:
        return AuthUser(username="dev", role="admin")
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(creds.credentials)


def require_role(*roles: str):
    """Dependency factory — restrict a route to one of the named roles."""

    async def _checker(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
        if roles and user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return user

    return _checker


def hash_password(plaintext: str) -> str:
    """Produce a bcrypt hash suitable for ``settings.admin_password_hash``."""
    return _pwd_ctx.hash(plaintext)


def verify_admin_login(username: str, password: str) -> bool:
    """Verify operator login against the configured bcrypt hash.

    Falls back to a constant-time plaintext comparison against
    ``settings.admin_password`` only when no hash is configured — this is the
    legacy dev path and logs a warning every time it is used.
    """
    u_ok = hmac.compare_digest(username.encode("utf-8"), settings.admin_username.encode("utf-8"))
    if not u_ok:
        return False

    hashed = settings.admin_password_hash.strip()
    if hashed:
        try:
            return _pwd_ctx.verify(password, hashed)
        except (ValueError, TypeError) as exc:
            logger.error("Malformed GORZEN_ADMIN_PASSWORD_HASH: %s", exc)
            return False

    logger.warning(
        "verify_admin_login using plaintext GORZEN_ADMIN_PASSWORD. "
        "Set GORZEN_ADMIN_PASSWORD_HASH to a bcrypt hash in production."
    )
    return hmac.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))


AuthUserDep = Annotated[AuthUser, Depends(get_current_user)]
