"""Response models for the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    db: bool
    mqtt: bool


class DeviceSummary(BaseModel):
    device_id: str
    status: str | None = None
    last_seen: datetime | None = None
    sensor_types: list[str] = []
    rssi: int | None = None
    fw_version: str | None = None


class DeviceDetail(DeviceSummary):
    sensors: list[dict[str, Any]] = []
    latest: dict[str, list[dict[str, Any]]] = {}


class SensorReading(BaseModel):
    time: datetime
    reading_key: str
    value: float | None = None
    unit: str | None = None
    quality: str | None = None


class HistoryPoint(BaseModel):
    time: datetime
    reading_key: str
    value: float | None = None
    unit: str | None = None
    quality: str | None = None
    avg_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    sample_count: int | None = None


class AnomalyEvent(BaseModel):
    time: datetime
    device_id: str
    sensor_id: str
    sensor_type: str
    anomaly_type: str
    confidence: float
    description: str
    reading_value: float


class GasAlertEvent(BaseModel):
    time: datetime
    device_id: str
    sensor_id: str
    level: str
    gas_ppm: float


class DlqEntry(BaseModel):
    id: int
    received_at: datetime
    topic: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    raw_payload: str | None = None


class StatsResponse(BaseModel):
    total_messages_today: int = 0
    anomaly_count_today: int = 0
    gas_alerts_today: int = 0
    devices_online: int = 0
    dlq_count_today: int = 0
    avg_temperature_1h: float | None = None
    avg_humidity_1h: float | None = None
    avg_gas_ppm_1h: float | None = None
    max_gas_ppm_1h: float | None = None
    smoke_threshold_ppm: int = 1000
