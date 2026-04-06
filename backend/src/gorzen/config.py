from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GORZEN_", env_file=".env", extra="ignore")

    app_name: str = "Gorzen Digital-Twin Platform"
    debug: bool = False

    database_url: str = Field(
        default="postgresql+asyncpg://gorzen:gorzen@localhost:5432/gorzen",
        description="Async SQLAlchemy URL; default matches docker-compose `db` service after `alembic upgrade head`.",
    )
    object_store_path: str = "./storage/logs"
    event_store_path: str = "./storage/events"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    uq_default_mc_samples: int = 1000
    uq_default_method: str = "monte_carlo"
    #: If Monte Carlo model failure rate exceeds this fraction, mission_completion_probability is forced to 0.
    uq_mc_failure_rate_mcp_zero: float = 0.05

    # JWT: leave empty to disable auth (local dev only).
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    admin_username: str = "admin"
    admin_password: str = "change-me"

    security_headers: bool = True
    rate_limit_per_minute: int = 120

    # Run ``alembic upgrade head`` on startup (docker-compose sets this true).
    run_migrations_on_startup: bool = False

    @property
    def auth_enabled(self) -> bool:
        return bool(self.jwt_secret.strip())


settings = Settings()
