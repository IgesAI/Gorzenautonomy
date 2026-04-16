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
    #: Algorithms accepted by token verification. Pinned to prevent ``alg``
    #: confusion attacks (e.g. HS256 downgrade to ``none``).
    jwt_allowed_algorithms: list[str] = Field(
        default_factory=lambda: ["HS256", "HS384", "HS512"]
    )
    jwt_expire_minutes: int = 60
    admin_username: str = "admin"
    #: Bcrypt hash of the admin password. When set, ``admin_password`` is
    #: ignored and login verifies against this hash via ``passlib.bcrypt``.
    admin_password_hash: str = ""
    #: Legacy plaintext admin password — emits a warning at startup. Only
    #: used when ``admin_password_hash`` is empty.
    admin_password: str = "change-me"

    #: Shared secret for the ROS 2 bridge -> ``/telemetry/ingest`` endpoint.
    #: Empty disables the route (returns 503) so it can never silently accept
    #: anonymous telemetry.
    bridge_token: str = ""
    #: Token required on the telemetry WebSocket when JWT auth is disabled
    #: (dev mode). Empty blocks all WS connections in dev.
    dev_ws_token: str = ""

    security_headers: bool = True
    rate_limit_per_minute: int = 120

    #: When ``True``, the app refuses to start if auth is disabled. Set this
    #: in any non-dev environment to fail-fast instead of silently running
    #: wide open.
    require_auth: bool = False

    # Run ``alembic upgrade head`` on startup (docker-compose sets this true).
    run_migrations_on_startup: bool = False

    @property
    def auth_enabled(self) -> bool:
        return bool(self.jwt_secret.strip())


settings = Settings()
