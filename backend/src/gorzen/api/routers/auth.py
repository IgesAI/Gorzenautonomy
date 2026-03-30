"""OAuth2-style token endpoint (JWT) when ``GORZEN_JWT_SECRET`` is set."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from starlette.requests import Request

from gorzen.api.deps import create_access_token, verify_admin_login
from gorzen.api.limiter import limiter
from gorzen.config import settings

router = APIRouter()


@router.post("/token")
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request, form: OAuth2PasswordRequestForm = Depends()
) -> dict[str, str]:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled (empty GORZEN_JWT_SECRET)",
        )
    if not verify_admin_login(form.username, form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(form.username, role="admin")
    return {"access_token": token, "token_type": "bearer"}
