"""Device diagnostics envelope (heap, uptime, rssi)."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator


class DiagnosticsMessage(BaseModel):
    """Periodic device health metrics."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    device_id: str
    ts: datetime
    uptime_s: int = 0
    free_heap: int = 0
    wifi_rssi: int = 0
    mqtt_reconnects: int = 0
    dlq_buffered: int = 0

    @field_validator("ts", mode="before")
    @classmethod
    def _parse_ts(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        raise ValueError("invalid ts")

    @field_validator("ts")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)
