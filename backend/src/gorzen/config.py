from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Gorzen Digital-Twin Platform"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://gorzen:gorzen@localhost:5432/gorzen"
    object_store_path: str = "./storage/logs"
    event_store_path: str = "./storage/events"

    cors_origins: list[str] = ["http://localhost:5173"]

    uq_default_mc_samples: int = 1000
    uq_default_method: str = "monte_carlo"

    model_config = {"env_prefix": "GORZEN_"}


settings = Settings()
