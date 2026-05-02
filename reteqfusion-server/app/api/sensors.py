"""Per-sensor latest + history endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.schemas import HistoryPoint, SensorReading

router = APIRouter(prefix="/api/v1/devices", tags=["sensors"])


@router.get(
    "/{device_id}/sensors/{sensor_id}/latest",
    response_model=list[SensorReading],
)
async def latest(device_id: str, sensor_id: str, request: Request) -> list[SensorReading]:
    """Most recent reading for each reading_key of a sensor."""
    repo = request.app.state.telemetry_repo
    rows = await repo.latest_for_sensor(device_id, sensor_id)
    if not rows:
        raise HTTPException(status_code=404, detail="no readings for sensor")
    return [
        SensorReading(
            time=r["time"],
            reading_key=r["reading_key"],
            value=r.get("value"),
            unit=r.get("unit"),
            quality=r.get("quality"),
        )
        for r in rows
    ]


@router.get(
    "/{device_id}/sensors/{sensor_id}/history",
    response_model=list[HistoryPoint],
)
async def history(
    device_id: str,
    sensor_id: str,
    request: Request,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    resolution: Literal["raw", "1min", "1hour"] = "raw",
) -> list[HistoryPoint]:
    """Time-bucketed history. Use resolution=1min|1hour for downsampled data."""
    repo = request.app.state.telemetry_repo
    end = to or datetime.now(tz=timezone.utc)
    start = from_ or (end - timedelta(hours=1))

    if resolution == "raw":
        rows = await repo.history_raw(device_id, sensor_id, start, end)
        return [
            HistoryPoint(
                time=r["time"],
                reading_key=r["reading_key"],
                value=r.get("value"),
                unit=r.get("unit"),
                quality=r.get("quality"),
            )
            for r in rows
        ]

    view = "telemetry_1min" if resolution == "1min" else "telemetry_1hour"
    rows = await repo.history_aggregate(device_id, sensor_id, start, end, view)
    return [
        HistoryPoint(
            time=r["time"],
            reading_key=r["reading_key"],
            avg_value=r.get("avg_value"),
            min_value=r.get("min_value"),
            max_value=r.get("max_value"),
            sample_count=r.get("sample_count"),
        )
        for r in rows
    ]
