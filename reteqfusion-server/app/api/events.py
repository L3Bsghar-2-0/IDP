"""Anomaly, gas alert, DLQ, and stats endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Request

from app.api.schemas import AnomalyEvent, DlqEntry, GasAlertEvent, StatsResponse
from app.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.get("/anomalies", response_model=list[AnomalyEvent])
async def list_anomalies(
    request: Request,
    device_id: str | None = None,
    sensor_type: Literal["dht22", "mq2"] | None = None,
    type: str | None = Query(default=None, alias="type"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[AnomalyEvent]:
    rows = await request.app.state.telemetry_repo.latest_anomalies(
        device_id=device_id,
        sensor_type=sensor_type,
        anomaly_type=type,
        start=from_,
        end=to,
        limit=limit,
    )
    return [AnomalyEvent(**r) for r in rows]


@router.get("/gas-alerts", response_model=list[GasAlertEvent])
async def gas_alerts(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[GasAlertEvent]:
    rows = await request.app.state.telemetry_repo.latest_gas_alerts(limit=limit)
    return [GasAlertEvent(**r) for r in rows]


@router.get("/dlq", response_model=list[DlqEntry])
async def dlq(request: Request, limit: int = Query(default=50, ge=1, le=500)) -> list[DlqEntry]:
    rows = await request.app.state.dlq_repo.latest(limit=limit)
    return [DlqEntry(**r) for r in rows]


@router.get("/stats", response_model=StatsResponse)
async def stats(request: Request) -> StatsResponse:
    settings = get_settings()
    row = await request.app.state.telemetry_repo.stats(
        smoke_threshold_ppm=settings.mq2_smoke_alarm_ppm
    )
    return StatsResponse(
        total_messages_today=int(row.get("total_messages_today") or 0),
        anomaly_count_today=int(row.get("anomaly_count_today") or 0),
        gas_alerts_today=int(row.get("gas_alerts_today") or 0),
        devices_online=int(row.get("devices_online") or 0),
        dlq_count_today=int(row.get("dlq_count_today") or 0),
        avg_temperature_1h=row.get("avg_temperature_1h"),
        avg_humidity_1h=row.get("avg_humidity_1h"),
        avg_gas_ppm_1h=row.get("avg_gas_ppm_1h"),
        max_gas_ppm_1h=row.get("max_gas_ppm_1h"),
        smoke_threshold_ppm=settings.mq2_smoke_alarm_ppm,
    )
