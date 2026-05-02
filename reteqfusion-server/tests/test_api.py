"""Lightweight API import smoke tests (no live DB needed)."""
from __future__ import annotations

from app.api import devices, events, health, sensors


def test_routers_import_cleanly() -> None:
    assert health.router.routes
    assert any(r.path == "/health" for r in health.router.routes)


def test_device_router_paths() -> None:
    paths = {r.path for r in devices.router.routes}
    assert "/api/v1/devices" in paths
    assert "/api/v1/devices/{device_id}" in paths


def test_sensor_router_paths() -> None:
    paths = {r.path for r in sensors.router.routes}
    assert "/api/v1/devices/{device_id}/sensors/{sensor_id}/latest" in paths
    assert "/api/v1/devices/{device_id}/sensors/{sensor_id}/history" in paths


def test_events_router_paths() -> None:
    paths = {r.path for r in events.router.routes}
    assert "/api/v1/anomalies" in paths
    assert "/api/v1/gas-alerts" in paths
    assert "/api/v1/dlq" in paths
    assert "/api/v1/stats" in paths
