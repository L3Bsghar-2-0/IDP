"""Backward-compat translator: ESP32 firmware v1 schema → server schema.

The original ESP32 firmware (esp32-edge/) publishes a flatter, older payload:

    DHT22:  {"v":"1","fw":"1.0.0","ts":<int>,"value":{"temp_c":..,"hum":..}, ...}
    MQ-2:   {"v":"1","fw":"1.0.0","ts":<int>,"unit":"raw_adc","gas_level":..,
             "stats":{"raw_min":..,"raw_max":..,"raw_mean":..,"raw_stddev":..,"count":..}, ...}
    Status: {"status":"online|offline","ts":<int>}        (no device_id)

The server's models expect the v1.0 envelope with `schema_version`, ISO-8601 `ts`,
nested `readings`, and explicit `tenant`/`site`. This module converts in place
so legacy publishers continue to work without server-model changes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.mqtt.topic_parser import TopicInfo


def _epoch_to_iso(value: Any) -> Any:
    """Convert int/float Unix epoch (seconds) to ISO-8601 UTC string."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return value
    return value


def _is_legacy_telemetry(data: dict) -> bool:
    """Legacy DHT22/MQ-2 payloads carry `v` instead of `schema_version`,
    or use `value`/`gas_level` instead of `readings`."""
    if "schema_version" in data and "readings" in data:
        return False
    return "v" in data or "value" in data or "gas_level" in data


def _is_legacy_status(data: dict) -> bool:
    """Legacy status payload omits device_id and uses int ts."""
    if "device_id" in data and isinstance(data.get("ts"), str):
        return False
    return True


def _translate_dht22_readings(legacy: dict) -> dict:
    """Map flat `value:{temp_c,hum}` → nested `readings:{temperature,humidity}`."""
    value = legacy.get("value") or {}
    quality = legacy.get("quality", "good")
    readings: dict[str, dict] = {}
    if "temp_c" in value:
        readings["temperature"] = {
            "value": value["temp_c"],
            "unit": "C",
            "quality": quality,
        }
    if "hum" in value:
        readings["humidity"] = {
            "value": value["hum"],
            "unit": "%",
            "quality": quality,
        }
    return readings


def _translate_mq2_readings(legacy: dict) -> dict:
    """Map `gas_level` (raw ADC mean) and `stats` → minimal MQ-2 readings.

    The legacy firmware only publishes raw ADC; voltage/ppm/smoke aren't
    derivable without R0 calibration, so we expose what we have.
    """
    quality = legacy.get("quality", "good")
    unit = legacy.get("unit", "adc")
    readings: dict[str, dict] = {}
    if "gas_level" in legacy:
        readings["raw_adc"] = {
            "value": legacy["gas_level"],
            "unit": unit,
            "quality": quality,
        }
    return readings


def translate_telemetry(info: TopicInfo, data: dict) -> dict:
    """Return a v1.0 envelope built from a legacy DHT22 or MQ-2 payload.

    Pass-through if data already matches the v1.0 schema.
    """
    if not _is_legacy_telemetry(data):
        return data

    out: dict[str, Any] = dict(data)

    out["schema_version"] = out.pop("v", "1.0-legacy")
    if "fw" in out and "fw_version" not in out:
        out["fw_version"] = out.pop("fw")
    if "ts" in out:
        out["ts"] = _epoch_to_iso(out["ts"])

    if info.tenant and "tenant" not in out:
        out["tenant"] = info.tenant
    if info.site and "site" not in out:
        out["site"] = info.site
    if info.device_id and "device_id" not in out:
        out["device_id"] = info.device_id

    sensor_type = out.get("sensor_type") or info.sensor_type or ""
    if sensor_type == "dht22":
        out["readings"] = _translate_dht22_readings(out)
        out.pop("value", None)
    elif sensor_type == "mq2":
        out["readings"] = _translate_mq2_readings(out)
        out.pop("gas_level", None)
        out.pop("unit", None)
        out.pop("stats", None)
    else:
        out.setdefault("readings", {})

    out.pop("quality", None)  # already pushed into per-reading qualities
    out.pop("rssi", None)     # not part of telemetry envelope (lives in status)

    return out


def translate_status(info: TopicInfo, data: dict) -> dict:
    """Fill in missing device_id from topic and convert int ts → ISO."""
    if not _is_legacy_status(data):
        return data

    out: dict[str, Any] = dict(data)
    if "ts" in out:
        out["ts"] = _epoch_to_iso(out["ts"])
    if "device_id" not in out and info.device_id:
        out["device_id"] = info.device_id
    return out


def translate_diagnostics(info: TopicInfo, data: dict) -> dict:
    """Diagnostics share the same int-ts / missing-device_id concerns."""
    out: dict[str, Any] = dict(data)
    if isinstance(out.get("ts"), (int, float)):
        out["ts"] = _epoch_to_iso(out["ts"])
    if "device_id" not in out and info.device_id:
        out["device_id"] = info.device_id
    return out
