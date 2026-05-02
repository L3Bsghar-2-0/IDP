"""Device REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import DeviceDetail, DeviceSummary

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.get("", response_model=list[DeviceSummary])
async def list_devices(request: Request) -> list[DeviceSummary]:
    """Return all known devices with their status and sensor types."""
    device_repo = request.app.state.device_repo
    telemetry_repo = request.app.state.telemetry_repo
    statuses = {row["device_id"]: row for row in await device_repo.list_all()}
    telemetry_devices = await telemetry_repo.list_devices()

    summaries: dict[str, DeviceSummary] = {}
    for row in telemetry_devices:
        s = statuses.get(row["device_id"], {})
        summaries[row["device_id"]] = DeviceSummary(
            device_id=row["device_id"],
            status=s.get("status"),
            last_seen=s.get("last_seen") or row.get("last_seen"),
            sensor_types=list(row.get("sensor_types") or []),
            rssi=s.get("rssi"),
            fw_version=s.get("fw_version"),
        )
    # also include devices known only via status
    for did, s in statuses.items():
        if did not in summaries:
            summaries[did] = DeviceSummary(
                device_id=did,
                status=s.get("status"),
                last_seen=s.get("last_seen"),
                sensor_types=[],
                rssi=s.get("rssi"),
                fw_version=s.get("fw_version"),
            )
    return sorted(summaries.values(), key=lambda d: d.device_id)


@router.get("/{device_id}", response_model=DeviceDetail)
async def get_device(device_id: str, request: Request) -> DeviceDetail:
    """Return device detail + the latest reading per sensor."""
    device_repo = request.app.state.device_repo
    telemetry_repo = request.app.state.telemetry_repo

    status = await device_repo.get(device_id)
    sensors = await telemetry_repo.list_sensors_for_device(device_id)
    if not status and not sensors:
        raise HTTPException(status_code=404, detail="device not found")

    latest: dict[str, list] = {}
    sensor_types: set[str] = set()
    for s in sensors:
        sensor_types.add(s["sensor_type"])
        rows = await telemetry_repo.latest_for_sensor(device_id, s["sensor_id"])
        latest[s["sensor_id"]] = [dict(r) for r in rows]

    return DeviceDetail(
        device_id=device_id,
        status=(status or {}).get("status"),
        last_seen=(status or {}).get("last_seen"),
        sensor_types=sorted(sensor_types),
        rssi=(status or {}).get("rssi"),
        fw_version=(status or {}).get("fw_version"),
        sensors=sensors,
        latest=latest,
    )
