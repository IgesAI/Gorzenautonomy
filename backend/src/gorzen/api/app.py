from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gorzen.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from gorzen.api.routers import calibration, catalog, envelope, mission, twin

    app.include_router(twin.router, prefix="/twins", tags=["twins"])
    app.include_router(envelope.router, prefix="/twins", tags=["envelope"])
    app.include_router(mission.router, prefix="/twins", tags=["mission"])
    app.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
    app.include_router(calibration.router, prefix="/calibration", tags=["calibration"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
