"""Top-level router that mounts all sub-routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api import devices, events, health, sensors

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(devices.router)
api_router.include_router(sensors.router)
api_router.include_router(events.router)
