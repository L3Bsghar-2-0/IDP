"""Parse hierarchical MQTT topics into structured info."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicInfo:
    """Decoded topic components."""

    raw: str
    tenant: str | None
    site: str | None
    device_id: str | None
    sensor_type: str | None       # 'dht22' or 'mq2' for telemetry
    kind: str                     # 'telemetry' | 'status' | 'diagnostics' | 'other'


def parse_topic(topic: str) -> TopicInfo:
    """Parse topics of the form:
        tenants/<tenant>/sites/<site>/devices/<device>/sensors/<sensor>/telemetry
        tenants/<tenant>/sites/<site>/devices/<device>/status
        tenants/<tenant>/sites/<site>/devices/<device>/diagnostics
    """
    parts = topic.strip("/").split("/")

    tenant = site = device_id = sensor_type = None
    kind = "other"

    if len(parts) >= 6 and parts[0] == "tenants" and parts[2] == "sites" and parts[4] == "devices":
        tenant = parts[1]
        site = parts[3]
        device_id = parts[5]

        # tenants/T/sites/S/devices/D/status                               (7 parts)
        # tenants/T/sites/S/devices/D/diagnostics                          (7 parts)
        # tenants/T/sites/S/devices/D/sensors/<X>/telemetry                (9 parts)
        if len(parts) == 7:
            tail = parts[6]
            if tail == "status":
                kind = "status"
            elif tail == "diagnostics":
                kind = "diagnostics"
        elif len(parts) >= 9 and parts[6] == "sensors":
            sensor_type = parts[7]
            tail = parts[8]
            if tail == "telemetry":
                kind = "telemetry"

    return TopicInfo(
        raw=topic,
        tenant=tenant,
        site=site,
        device_id=device_id,
        sensor_type=sensor_type,
        kind=kind,
    )
