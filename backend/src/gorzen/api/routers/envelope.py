"""Envelope computation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gorzen.api.routers.twin import _twins
from gorzen.schemas.envelope import EnvelopeRequest, EnvelopeResponse
from gorzen.solver.envelope_solver import compute_envelope

router = APIRouter()


@router.post("/{twin_id}/envelope", response_model=EnvelopeResponse)
async def compute_twin_envelope(twin_id: str, request: EnvelopeRequest) -> EnvelopeResponse:
    if twin_id not in _twins:
        raise HTTPException(status_code=404, detail="Twin not found")

    twin = _twins[twin_id]
    response = compute_envelope(
        twin,
        speed_range=request.speed_range_ms,
        altitude_range=request.altitude_range_m,
        grid_resolution=request.grid_resolution,
        uq_method=request.uq_method,
        mc_samples=request.mc_samples,
    )
    return response
