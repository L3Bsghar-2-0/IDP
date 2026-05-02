"""Telemetry message envelope and per-reading models."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Reading keys expected per sensor type. Used by validators downstream.
DHT22_READING_KEYS: tuple[str, ...] = ("temperature", "humidity")
MQ2_READING_KEYS: tuple[str, ...] = (
    "raw_adc",
    "voltage",
    "rs_r0_ratio",
    "gas_ppm",
    "smoke_detected",
)


class Reading(BaseModel):
    """A single sensor reading: value + unit + quality flag."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    value: float
    unit: str = ""
    quality: Literal["good", "uncertain", "bad"] = "good"

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v: object) -> float:
        """Allow ints/booleans through and convert NaN to 0.0 with quality downgrade."""
        if isinstance(v, bool):
            return float(int(v))
        if v is None:
            return float("nan")
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return float("nan")

    @field_validator("value", mode="after")
    @classmethod
    def _check_finite(cls, v: float) -> float:
        # NaN is allowed at this layer; downstream validator marks it bad.
        return v


class TelemetryMessage(BaseModel):
    """Full telemetry envelope from an ESP32 device."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    schema_version: str
    ts: datetime
    device_id: str
    tenant: str
    site: str
    sensor_id: str
    sensor_type: Literal["dht22", "mq2"]
    seq: int
    readings: dict[str, Reading]
    fw_version: str = ""

    @field_validator("ts", mode="before")
    @classmethod
    def _parse_ts(cls, value: object) -> datetime:
        """Parse ISO-8601 string (with trailing Z) into a UTC-aware datetime."""
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError as exc:
                raise ValueError(f"invalid ISO-8601 timestamp: {value!r}") from exc
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        raise ValueError(f"unsupported ts type: {type(value).__name__}")

    @field_validator("ts")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    def expected_keys(self) -> tuple[str, ...]:
        """Return the reading keys expected for this message's sensor type."""
        if self.sensor_type == "dht22":
            return DHT22_READING_KEYS
        return MQ2_READING_KEYS

    def has_nan_reading(self) -> bool:
        """Return True if any reading carries a NaN value (bad DHT22 read)."""
        return any(math.isnan(r.value) for r in self.readings.values())
