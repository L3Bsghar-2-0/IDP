"""Pydantic model parsing tests."""
from __future__ import annotations

from datetime import timezone

import pytest

from app.models.diagnostics import DiagnosticsMessage
from app.models.status import StatusMessage
from app.models.telemetry import TelemetryMessage


def _dht22_payload() -> dict:
    return {
        "schema_version": "1.0",
        "ts": "2025-01-01T12:00:00.000Z",
        "device_id": "esp32_abc123",
        "tenant": "demo",
        "site": "lab",
        "sensor_id": "dht22_01",
        "sensor_type": "dht22",
        "seq": 1042,
        "readings": {
            "temperature": {"value": 23.4, "unit": "C", "quality": "good"},
            "humidity":    {"value": 58.1, "unit": "%", "quality": "good"},
        },
        "fw_version": "1.0.0",
    }


def _mq2_payload() -> dict:
    return {
        "schema_version": "1.0",
        "ts": "2025-01-01T12:00:00.000Z",
        "device_id": "esp32_abc123",
        "tenant": "demo",
        "site": "lab",
        "sensor_id": "mq2_01",
        "sensor_type": "mq2",
        "seq": 1043,
        "readings": {
            "raw_adc":        {"value": 890,  "unit": "adc",  "quality": "good"},
            "voltage":        {"value": 0.72, "unit": "V",    "quality": "good"},
            "rs_r0_ratio":    {"value": 3.21, "unit": "",     "quality": "good"},
            "gas_ppm":        {"value": 412,  "unit": "ppm",  "quality": "good"},
            "smoke_detected": {"value": 0,    "unit": "bool", "quality": "good"},
        },
        "fw_version": "1.0.0",
    }


def test_dht22_parses_and_normalises_ts() -> None:
    msg = TelemetryMessage.model_validate(_dht22_payload())
    assert msg.sensor_type == "dht22"
    assert msg.ts.tzinfo == timezone.utc
    assert set(msg.readings.keys()) == {"temperature", "humidity"}
    assert msg.expected_keys() == ("temperature", "humidity")


def test_mq2_parses() -> None:
    msg = TelemetryMessage.model_validate(_mq2_payload())
    assert msg.sensor_type == "mq2"
    assert "gas_ppm" in msg.readings
    assert msg.readings["smoke_detected"].value == 0.0
    assert "smoke_detected" in msg.expected_keys()


def test_invalid_sensor_type_rejected() -> None:
    payload = _dht22_payload()
    payload["sensor_type"] = "not_a_sensor"
    with pytest.raises(Exception):
        TelemetryMessage.model_validate(payload)


def test_status_message_parses() -> None:
    msg = StatusMessage.model_validate(
        {
            "device_id": "esp32_abc123",
            "status": "online",
            "ts": "2025-01-01T12:00:00.000Z",
            "ip": "192.168.1.42",
            "rssi": -65,
        }
    )
    assert msg.status == "online"
    assert msg.ts.tzinfo == timezone.utc


def test_diagnostics_parses() -> None:
    msg = DiagnosticsMessage.model_validate(
        {
            "device_id": "esp32_abc123",
            "ts": "2025-01-01T12:00:00.000Z",
            "uptime_s": 3600,
            "free_heap": 180000,
            "wifi_rssi": -65,
            "mqtt_reconnects": 0,
            "dlq_buffered": 0,
        }
    )
    assert msg.uptime_s == 3600
    assert msg.free_heap == 180000


def test_nan_value_in_reading_marked_via_helper() -> None:
    payload = _dht22_payload()
    payload["readings"]["temperature"]["value"] = float("nan")
    msg = TelemetryMessage.model_validate(payload)
    assert msg.has_nan_reading() is True


def test_topic_parser_telemetry() -> None:
    from app.mqtt.topic_parser import parse_topic

    info = parse_topic(
        "tenants/demo/sites/lab/devices/esp32_abc123/sensors/dht22/telemetry"
    )
    assert info.kind == "telemetry"
    assert info.tenant == "demo"
    assert info.site == "lab"
    assert info.device_id == "esp32_abc123"
    assert info.sensor_type == "dht22"


def test_topic_parser_status() -> None:
    from app.mqtt.topic_parser import parse_topic

    info = parse_topic("tenants/demo/sites/lab/devices/esp32_abc123/status")
    assert info.kind == "status"
    assert info.device_id == "esp32_abc123"


def test_topic_parser_diagnostics() -> None:
    from app.mqtt.topic_parser import parse_topic

    info = parse_topic("tenants/demo/sites/lab/devices/esp32_abc123/diagnostics")
    assert info.kind == "diagnostics"


def test_topic_parser_unknown() -> None:
    from app.mqtt.topic_parser import parse_topic

    info = parse_topic("garbage/topic")
    assert info.kind == "other"
