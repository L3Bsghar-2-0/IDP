"""Last-Will-and-Testament + status messages from devices."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StatusMessage(BaseModel):
    """Device online/offline status."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    device_id: str
    status: Literal["online", "offline"]
    ts: datetime
    ip: str | None = None
    rssi: int | None = None
    fw_version: str | None = None

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
