"""JSON parsing + message type detection for ReTeqFusion subscriber.

All functions are designed to be lenient: malformed input never raises.
Returns a tuple (message_type, parsed_dict_or_none).
"""

import json
from typing import Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, ValidationError


# ───────────────────────── Pydantic models ─────────────────────────


class Reading(BaseModel):
    model_config = ConfigDict(extra="allow")
    value: Union[float, int]
    unit: str = ""
    quality: str = "unknown"


class TelemetryMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: str = "unknown"
    ts: str = ""
    device_id: str = "unknown"
    tenant: str = "unknown"
    site: str = "unknown"
    sensor_id: str = "unknown"
    sensor_type: str = "unknown"
    seq: int = -1
    readings: dict[str, Reading] = {}
    fw_version: str = "unknown"


class StatusMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    device_id: str = "unknown"
    status: str = "unknown"
    ts: str = ""
    ip: str = "unknown"
    rssi: int = 0


class DiagnosticsMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    device_id: str = "unknown"
    ts: str = ""
    uptime_s: int = 0
    free_heap: int = 0
    wifi_rssi: int = 0
    mqtt_reconnects: int = 0
    dlq_buffered: int = 0


# ─────────────────────────── detection ─────────────────────────────


def _topic_type(topic: str) -> str:
    if topic.endswith("/sensors/dht22/telemetry"):
        return "dht22_telemetry"
    if topic.endswith("/sensors/mq2/telemetry"):
        return "mq2_telemetry"
    if topic.endswith("/status"):
        return "status"
    if topic.endswith("/diagnostics"):
        return "diagnostics"
    if "/alerts/" in topic:
        return "alert"
    return "unknown"


def detect_message_type(
    topic: str, payload: bytes
) -> Tuple[str, Optional[dict]]:
    """Detect message type and return (type, parsed_dict).

    type ∈ {dht22_telemetry, mq2_telemetry, status, diagnostics, alert, unknown}.
    Never raises. On failure returns ('unknown', {'_error': ...}) — the dict
    always carries a hint about what went wrong.
    """
    if not payload:
        return "unknown", {"_error": "empty payload"}

    try:
        text = payload.decode("utf-8", errors="replace")
    except Exception as e:
        return "unknown", {"_error": f"decode error: {e}"}

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        return "unknown", {"_error": f"JSON parse error: {e}"}

    if not isinstance(raw, dict):
        return "unknown", {
            "_error": f"expected JSON object, got {type(raw).__name__}",
            "_raw": raw,
        }

    msg_type = _topic_type(topic)

    try:
        if msg_type in ("dht22_telemetry", "mq2_telemetry"):
            return msg_type, TelemetryMessage(**raw).model_dump()
        if msg_type == "status":
            return msg_type, StatusMessage(**raw).model_dump()
        if msg_type == "diagnostics":
            return msg_type, DiagnosticsMessage(**raw).model_dump()
        if msg_type == "alert":
            return "alert", raw
        return "unknown", raw
    except ValidationError as e:
        merged = dict(raw)
        merged["_validation_error"] = str(e)
        return msg_type, merged
