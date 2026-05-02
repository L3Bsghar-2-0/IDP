"""Health endpoint for Docker healthcheck."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Return liveness + dependency status."""
    db_ok = False
    try:
        await request.app.state.database.fetchval("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    mqtt_ok = False
    try:
        mqtt_ok = bool(request.app.state.mqtt_client.is_connected())
    except Exception:  # noqa: BLE001
        mqtt_ok = False
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok, mqtt=mqtt_ok)
