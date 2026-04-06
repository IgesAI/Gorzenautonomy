from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import alembic.command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from gorzen.api.deps import get_current_user
from gorzen.api.limiter import limiter
from gorzen.config import settings
from gorzen.db.session import engine
from gorzen.services.mavlink_telemetry import telemetry_service

log = structlog.get_logger("gorzen.app")

BACKEND_ROOT = Path(__file__).resolve().parents[3]

_DATABASE_SETUP_HINT = (
    "PostgreSQL must be reachable and match GORZEN_DATABASE_URL (default user/db: gorzen). "
    "Options: (1) Start Docker Desktop, then from the repo root run `docker compose up -d db`, "
    "then `cd backend && alembic upgrade head`. "
    "(2) On an existing local Postgres, run: "
    "CREATE USER gorzen WITH PASSWORD 'gorzen'; CREATE DATABASE gorzen OWNER gorzen; "
    "then `alembic upgrade head`. "
    "(3) Or set GORZEN_DATABASE_URL to your own connection string."
)


def _find_sqlalchemy_db_error(exc: BaseException) -> BaseException | None:
    if isinstance(exc, (OperationalError, DBAPIError)):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_sqlalchemy_db_error(sub)
            if found is not None:
                return found
    return None


async def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        cache_logger_on_first_use=True,
    )


def _run_alembic_upgrade() -> None:
    ini = BACKEND_ROOT / "alembic.ini"
    if not ini.is_file():
        log.warning("alembic.ini not found — skipping migrations", path=str(ini))
        return
    cfg = Config(str(ini))
    alembic.command.upgrade(cfg, "head")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        if settings.security_headers:
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


class DatabaseUnavailableMiddleware(BaseHTTPMiddleware):
    """Turn DB connection/query failures into 503 + setup hint (avoids opaque 500 + ExceptionGroup logs)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        try:
            return await call_next(request)
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            db_err = _find_sqlalchemy_db_error(e)
            if db_err is not None:
                log.warning("database_request_failed", error=str(db_err))
                return JSONResponse(
                    status_code=503,
                    content={"detail": "database_unavailable", "hint": _DATABASE_SETUP_HINT},
                )
            raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    log.info("startup", app=settings.app_name)

    if settings.run_migrations_on_startup:
        try:
            await asyncio.to_thread(_run_alembic_upgrade)
            log.info("migrations_applied")
        except Exception as e:
            log.exception("migration_failed", error=str(e))
            raise

    if settings.auth_enabled and settings.admin_password == "change-me":
        log.warning(
            "SECURITY: Default admin credentials in use. Set GORZEN_ADMIN_PASSWORD in production."
        )
    if settings.auth_enabled and len(settings.jwt_secret) < 32:
        log.warning(
            "SECURITY: JWT secret is too short. Set GORZEN_JWT_SECRET to a random 32+ char string."
        )

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("database_ok")
    except Exception as e:
        log.error("database_unreachable", error=str(e), hint=_DATABASE_SETUP_HINT)

    yield

    await telemetry_service.disconnect()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Digital-Twin Platform for VTOL Fleet Configuration "
            "and Perception-Constrained Autonomous Mission Planning"
        ),
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    app.add_middleware(DatabaseUnavailableMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept"],
    )

    auth_dep = [Depends(get_current_user)]

    from gorzen.api.routers import (
        audit,
        auth,
        calibration,
        catalog,
        envelope,
        environment,
        execution,
        mission,
        mission_plan,
        predictions,
        telemetry,
        telemetry_logs,
        twin,
        validation,
    )

    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(twin.router, prefix="/twins", tags=["twins"], dependencies=auth_dep)
    app.include_router(envelope.router, prefix="/twins", tags=["envelope"], dependencies=auth_dep)
    app.include_router(mission.router, prefix="/twins", tags=["mission"], dependencies=auth_dep)
    app.include_router(
        execution.router, prefix="/execution", tags=["execution"], dependencies=auth_dep
    )
    app.include_router(catalog.router, prefix="/catalog", tags=["catalog"], dependencies=auth_dep)
    app.include_router(
        calibration.router, prefix="/calibration", tags=["calibration"], dependencies=auth_dep
    )
    app.include_router(
        validation.router, prefix="/validation", tags=["validation"], dependencies=auth_dep
    )
    app.include_router(
        environment.router, prefix="/environment", tags=["environment"], dependencies=auth_dep
    )
    app.include_router(telemetry.ws_router, prefix="/telemetry", tags=["telemetry"])
    app.include_router(telemetry.internal_router, prefix="/telemetry", tags=["telemetry"])
    app.include_router(
        telemetry.router, prefix="/telemetry", tags=["telemetry"], dependencies=auth_dep
    )
    app.include_router(
        telemetry_logs.router,
        prefix="/telemetry-logs",
        tags=["telemetry-logs"],
        dependencies=auth_dep,
    )
    app.include_router(
        mission_plan.router, prefix="/mission-plan", tags=["mission-plan"], dependencies=auth_dep
    )
    app.include_router(
        predictions.router, prefix="/predictions", tags=["predictions"], dependencies=auth_dep
    )
    app.include_router(
        predictions.validations_router,
        prefix="/validations",
        tags=["validations"],
        dependencies=auth_dep,
    )
    app.include_router(audit.router, prefix="/audit", tags=["audit"], dependencies=auth_dep)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            log.warning("readiness_failed", error=str(e))
            raise HTTPException(
                status_code=503,
                detail={"status": "database_unavailable", "hint": _DATABASE_SETUP_HINT},
            ) from e
        return {"status": "ready"}

    return app
