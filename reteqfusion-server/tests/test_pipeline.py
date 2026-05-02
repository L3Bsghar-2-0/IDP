"""Tests for validator, enricher, and anomaly detection."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.telemetry import Reading, TelemetryMessage
from app.processing.anomaly import AnomalyDetector
from app.processing.enricher import (
    comfort_index,
    dew_point,
    enrich_dht22,
    enrich_mq2,
    hazard_level_from_ppm,
    heat_index,
)
from app.processing.validator import validate_telemetry


def _make(sensor_type: str, readings: dict[str, dict]) -> TelemetryMessage:
    return TelemetryMessage.model_validate(
        {
            "schema_version": "1.0",
            "ts": "2025-01-01T12:00:00.000Z",
            "device_id": "esp32_test",
            "tenant": "demo",
            "site": "lab",
            "sensor_id": f"{sensor_type}_01",
            "sensor_type": sensor_type,
            "seq": 1,
            "readings": readings,
            "fw_version": "1.0.0",
        }
    )


# ----------------------------------------------------------------- validator


def test_dht22_in_range_passes() -> None:
    msg = _make(
        "dht22",
        {
            "temperature": {"value": 22.5, "unit": "C", "quality": "good"},
            "humidity":    {"value": 50.0, "unit": "%", "quality": "good"},
        },
    )
    res = validate_telemetry(msg)
    assert res.passed is True
    assert res.cleaned_readings["temperature"].quality == "good"


def test_dht22_out_of_range_marked_bad() -> None:
    msg = _make(
        "dht22",
        {
            "temperature": {"value": 200.0, "unit": "C", "quality": "good"},
            "humidity":    {"value": 50.0,  "unit": "%", "quality": "good"},
        },
    )
    res = validate_telemetry(msg)
    assert res.passed is False
    assert res.cleaned_readings["temperature"].quality == "bad"
    assert any(f.startswith("range:temperature") for f in res.flags)


def test_mq2_smoke_detected_must_be_boolean() -> None:
    msg = _make(
        "mq2",
        {
            "raw_adc":        {"value": 890,  "unit": "adc",  "quality": "good"},
            "voltage":        {"value": 0.72, "unit": "V",    "quality": "good"},
            "rs_r0_ratio":    {"value": 3.21, "unit": "",     "quality": "good"},
            "gas_ppm":        {"value": 412,  "unit": "ppm",  "quality": "good"},
            "smoke_detected": {"value": 7,    "unit": "bool", "quality": "good"},
        },
    )
    res = validate_telemetry(msg)
    assert res.passed is False
    assert res.cleaned_readings["smoke_detected"].quality == "bad"


def test_mq2_gas_ppm_below_min_marked_bad() -> None:
    msg = _make(
        "mq2",
        {
            "raw_adc":        {"value": 100,  "unit": "adc",  "quality": "good"},
            "voltage":        {"value": 0.1,  "unit": "V",    "quality": "good"},
            "rs_r0_ratio":    {"value": 5.0,  "unit": "",     "quality": "good"},
            "gas_ppm":        {"value": 100,  "unit": "ppm",  "quality": "good"},
            "smoke_detected": {"value": 0,    "unit": "bool", "quality": "good"},
        },
    )
    res = validate_telemetry(msg)
    assert res.passed is False
    assert res.cleaned_readings["gas_ppm"].quality == "bad"


def test_dht22_nan_marked_bad() -> None:
    msg = _make(
        "dht22",
        {
            "temperature": {"value": float("nan"), "unit": "C", "quality": "good"},
            "humidity":    {"value": 50.0,         "unit": "%", "quality": "good"},
        },
    )
    res = validate_telemetry(msg)
    assert res.passed is False
    assert res.cleaned_readings["temperature"].quality == "bad"


# ------------------------------------------------------------------ enricher


def test_heat_index_below_threshold_returns_none() -> None:
    assert heat_index(20.0, 60.0) is None


def test_heat_index_above_threshold_returns_value() -> None:
    val = heat_index(32.0, 70.0)
    assert val is not None and val > 32.0


def test_dew_point_known_case() -> None:
    val = dew_point(25.0, 60.0)
    assert val is not None
    assert 16.0 < val < 18.0  # ~16.7 °C


def test_comfort_index_categories() -> None:
    assert comfort_index(22.0, 50.0) == "comfortable"
    assert comfort_index(35.0, 50.0) == "hot"
    assert comfort_index(10.0, 50.0) == "cold"
    assert comfort_index(22.0, 80.0) == "humid"
    assert comfort_index(22.0, 20.0) == "dry"


def test_hazard_level_thresholds() -> None:
    assert hazard_level_from_ppm(50, 1000, 3000) == "safe"
    assert hazard_level_from_ppm(500, 1000, 3000) == "low"
    assert hazard_level_from_ppm(1500, 1000, 3000) == "alarm"
    assert hazard_level_from_ppm(5000, 1000, 3000) == "hazard"


def test_enrich_mq2_voltage_ratio_clamped() -> None:
    readings = {
        "voltage":        Reading(value=1.65, unit="V", quality="good"),
        "gas_ppm":        Reading(value=200, unit="ppm", quality="good"),
        "rs_r0_ratio":    Reading(value=4.0, unit="",   quality="good"),
        "raw_adc":        Reading(value=2048, unit="adc", quality="good"),
        "smoke_detected": Reading(value=0,   unit="bool", quality="good"),
    }
    enrich = enrich_mq2(readings, smoke_threshold=1000, hazard_threshold=3000)
    assert enrich.hazard_level == "safe"
    assert 0.49 < (enrich.sensor_voltage_ratio or 0) < 0.51


def test_enrich_dht22_skips_when_bad() -> None:
    readings = {
        "temperature": Reading(value=0.0, unit="C", quality="bad"),
        "humidity":    Reading(value=50.0, unit="%", quality="good"),
    }
    enrich = enrich_dht22(readings)
    assert enrich.heat_index is None
    assert enrich.dew_point is None


# ------------------------------------------------------------------ anomaly


def test_smoke_alarm_rises_then_clears() -> None:
    detector = AnomalyDetector(smoke_threshold_ppm=1000, hazard_threshold_ppm=3000)
    safe_msg = _make(
        "mq2",
        {
            "raw_adc":        {"value": 800,  "unit": "adc",  "quality": "good"},
            "voltage":        {"value": 0.5,  "unit": "V",    "quality": "good"},
            "rs_r0_ratio":    {"value": 5.0,  "unit": "",     "quality": "good"},
            "gas_ppm":        {"value": 500,  "unit": "ppm",  "quality": "good"},
            "smoke_detected": {"value": 0,    "unit": "bool", "quality": "good"},
        },
    )
    detector.detect(safe_msg, safe_msg.readings)

    smoke_msg = _make(
        "mq2",
        {
            "raw_adc":        {"value": 900,  "unit": "adc",  "quality": "good"},
            "voltage":        {"value": 1.0,  "unit": "V",    "quality": "good"},
            "rs_r0_ratio":    {"value": 4.0,  "unit": "",     "quality": "good"},
            "gas_ppm":        {"value": 1500, "unit": "ppm",  "quality": "good"},
            "smoke_detected": {"value": 1,    "unit": "bool", "quality": "good"},
        },
    )
    out = detector.detect(smoke_msg, smoke_msg.readings)
    types = [a.type for a in out]
    assert "SMOKE_ALARM" in types

    # Subsequent reading still above does NOT re-emit alarm (rising edge only)
    out2 = detector.detect(smoke_msg, smoke_msg.readings)
    assert "SMOKE_ALARM" not in [a.type for a in out2]


def test_hazard_alarm_emitted() -> None:
    detector = AnomalyDetector(smoke_threshold_ppm=1000, hazard_threshold_ppm=3000)
    safe_msg = _make(
        "mq2",
        {
            "raw_adc":        {"value": 800,  "unit": "adc",  "quality": "good"},
            "voltage":        {"value": 0.5,  "unit": "V",    "quality": "good"},
            "rs_r0_ratio":    {"value": 5.0,  "unit": "",     "quality": "good"},
            "gas_ppm":        {"value": 500,  "unit": "ppm",  "quality": "good"},
            "smoke_detected": {"value": 0,    "unit": "bool", "quality": "good"},
        },
    )
    detector.detect(safe_msg, safe_msg.readings)

    hazard_msg = _make(
        "mq2",
        {
            "raw_adc":        {"value": 3500, "unit": "adc",  "quality": "good"},
            "voltage":        {"value": 2.8,  "unit": "V",    "quality": "good"},
            "rs_r0_ratio":    {"value": 0.8,  "unit": "",     "quality": "good"},
            "gas_ppm":        {"value": 5000, "unit": "ppm",  "quality": "good"},
            "smoke_detected": {"value": 1,    "unit": "bool", "quality": "good"},
        },
    )
    out = detector.detect(hazard_msg, hazard_msg.readings)
    types = [a.type for a in out]
    assert "HAZARD_ALARM" in types
    assert "SMOKE_ALARM" in types


def test_heat_alert_above_60c() -> None:
    detector = AnomalyDetector(smoke_threshold_ppm=1000, hazard_threshold_ppm=3000)
    msg = _make(
        "dht22",
        {
            "temperature": {"value": 75.0, "unit": "C", "quality": "good"},
            "humidity":    {"value": 50.0, "unit": "%", "quality": "good"},
        },
    )
    out = detector.detect(msg, msg.readings)
    assert any(a.type == "HEAT_ALERT" for a in out)


def test_dropout_after_three_bad_dht22() -> None:
    detector = AnomalyDetector(smoke_threshold_ppm=1000, hazard_threshold_ppm=3000)
    bad = {
        "temperature": Reading(value=0.0, unit="C", quality="bad"),
        "humidity":    Reading(value=0.0, unit="%", quality="bad"),
    }
    msg = _make(
        "dht22",
        {
            "temperature": {"value": 0.0, "unit": "C", "quality": "bad"},
            "humidity":    {"value": 0.0, "unit": "%", "quality": "bad"},
        },
    )
    types: list[str] = []
    for _ in range(3):
        types.extend(a.type for a in detector.detect(msg, bad))
    assert "DROPOUT" in types
