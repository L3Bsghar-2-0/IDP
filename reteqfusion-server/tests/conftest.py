"""Pytest fixtures: in-memory pipeline scaffolding (no DB / MQTT required)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    """A test Settings instance with in-process defaults."""
    return Settings(
        MQTT_HOST="localhost",
        MQTT_PORT=1883,
        MQTT_USERNAME="test",
        MQTT_PASSWORD="test",
        MQTT_CLIENT_ID="test-client",
        MQTT_TLS=False,
        MQTT_KEEPALIVE=60,
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="reteqfusion",
        POSTGRES_USER="reteq",
        POSTGRES_PASSWORD="x",
        DATABASE_URL="postgresql://reteq:x@localhost:5432/reteqfusion",
        GRAFANA_ADMIN_PASSWORD="x",
        LOG_LEVEL="WARNING",
        API_PORT=8000,
        MQ2_SMOKE_ALARM_PPM=1000,
        MQ2_HAZARD_PPM=3000,
    )


@dataclass
class FakeTelemetryRepo:
    """In-memory replacement for TelemetryRepository."""

    rows: list[dict] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    gas_alerts: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)

    async def insert_reading(self, **kwargs):
        self.rows.append(kwargs)

    async def insert_anomaly(self, **kwargs):
        self.anomalies.append(kwargs)

    async def insert_gas_alert(self, **kwargs):
        self.gas_alerts.append(kwargs)

    async def insert_diagnostic(self, **kwargs):
        self.diagnostics.append(kwargs)


@dataclass
class FakeDeviceRepo:
    upserts: list[dict] = field(default_factory=list)
    touches: list[dict] = field(default_factory=list)

    async def upsert_status(self, **kwargs):
        self.upserts.append(kwargs)

    async def touch_last_seen(self, device_id, ts, fw_version=None):
        self.touches.append({"device_id": device_id, "ts": ts, "fw": fw_version})


@dataclass
class FakeDlqRepo:
    entries: list[dict] = field(default_factory=list)

    async def insert(self, topic, error_type, error_message, raw_payload):
        self.entries.append(
            {
                "topic": topic,
                "error_type": error_type,
                "error_message": error_message,
                "raw_payload": raw_payload,
            }
        )


@dataclass
class FakeMqtt:
    published: list[tuple[str, dict | str]] = field(default_factory=list)

    def publish(self, topic, payload, qos=1, retain=False):
        self.published.append((topic, payload))

    def is_connected(self) -> bool:
        return True


@pytest.fixture
def fake_repos():
    return {
        "telemetry": FakeTelemetryRepo(),
        "device": FakeDeviceRepo(),
        "dlq": FakeDlqRepo(),
        "mqtt": FakeMqtt(),
    }


@pytest.fixture
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for asyncio tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
