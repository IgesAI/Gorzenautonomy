"""Shared FastAPI dependencies (auth)."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from gorzen.config import settings

security_bearer = HTTPBearer(auto_error=False)


class AuthUser(BaseModel):
    """Authenticated principal (JWT or dev bypass)."""

    username: str
    role: str = "admin"


def _issue_token(username: str, role: str = "admin") -> str:
    from datetime import datetime, timedelta, timezone

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
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
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


def verify_admin_login(username: str, password: str) -> bool:
    """Constant-time-ish comparison for operator login."""
    u_ok = hmac.compare_digest(username.encode("utf-8"), settings.admin_username.encode("utf-8"))
    p_ok = hmac.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))
    return u_ok and p_ok


AuthUserDep = Annotated[AuthUser, Depends(get_current_user)]
