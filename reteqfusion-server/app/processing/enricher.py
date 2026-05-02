"""Derived metrics for DHT22 (heat index, dew point, …) and MQ-2 (hazard level)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.telemetry import Reading


@dataclass
class Dht22Enrichment:
    heat_index: float | None
    absolute_humidity: float | None
    dew_point: float | None
    comfort_index: str


@dataclass
class Mq2Enrichment:
    hazard_level: str
    sensor_voltage_ratio: float | None


# ---------------------------------------------------------------------- DHT22


def heat_index(temp_c: float, humidity: float) -> float | None:
    """Steadman formula approximation. Defined when T > 27 °C and RH > 40 %."""
    if temp_c <= 27.0 or humidity <= 40.0:
        return None
    t = temp_c
    rh = humidity
    return (
        -8.78469
        + 1.61139 * t
        + 2.33854 * rh
        - 0.14611 * t * rh
        - 0.01230 * t * t
        - 0.01643 * rh * rh
        + 0.00221 * t * t * rh
        + 0.00072 * t * rh * rh
        - 0.00000357 * t * t * rh * rh
    )


def absolute_humidity(temp_c: float, humidity: float) -> float | None:
    """Return absolute humidity in g/m³.

    AH = (6.112 * e^(17.67*T/(T+243.5)) * RH * 2.1674) / (273.15 + T)
    """
    try:
        sat = 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))
        return (sat * humidity * 2.1674) / (273.15 + temp_c)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def dew_point(temp_c: float, humidity: float) -> float | None:
    """Magnus formula dew point in °C."""
    if humidity <= 0:
        return None
    try:
        a = 17.625
        b = 243.04
        ln_rh = math.log(humidity / 100.0)
        gamma = ln_rh + (a * temp_c) / (b + temp_c)
        return (b * gamma) / (a - gamma)
    except (ValueError, ZeroDivisionError):
        return None


def comfort_index(temp_c: float, humidity: float) -> str:
    if 20.0 <= temp_c <= 26.0 and 30.0 <= humidity <= 60.0:
        return "comfortable"
    if temp_c > 26.0:
        return "hot"
    if temp_c < 20.0:
        return "cold"
    if humidity > 60.0:
        return "humid"
    if humidity < 30.0:
        return "dry"
    return "comfortable"


def enrich_dht22(readings: dict[str, Reading]) -> Dht22Enrichment:
    """Compute derived DHT22 metrics from validated readings."""
    t_reading = readings.get("temperature")
    h_reading = readings.get("humidity")
    if (
        t_reading is None
        or h_reading is None
        or t_reading.quality == "bad"
        or h_reading.quality == "bad"
    ):
        return Dht22Enrichment(None, None, None, "comfortable")

    t = t_reading.value
    rh = h_reading.value
    return Dht22Enrichment(
        heat_index=heat_index(t, rh),
        absolute_humidity=absolute_humidity(t, rh),
        dew_point=dew_point(t, rh),
        comfort_index=comfort_index(t, rh),
    )


# ----------------------------------------------------------------------- MQ-2


def hazard_level_from_ppm(gas_ppm: float, smoke_threshold: int, hazard_threshold: int) -> str:
    if gas_ppm < 300.0:
        return "safe"
    if gas_ppm < smoke_threshold:
        return "low"
    if gas_ppm < hazard_threshold:
        return "alarm"
    return "hazard"


def enrich_mq2(
    readings: dict[str, Reading],
    smoke_threshold: int,
    hazard_threshold: int,
) -> Mq2Enrichment:
    """Compute derived MQ-2 metrics."""
    gas = readings.get("gas_ppm")
    voltage = readings.get("voltage")

    hazard = "safe"
    if gas is not None and gas.quality != "bad":
        hazard = hazard_level_from_ppm(gas.value, smoke_threshold, hazard_threshold)

    voltage_ratio: float | None = None
    if voltage is not None and voltage.quality != "bad":
        voltage_ratio = max(0.0, min(1.0, voltage.value / 3.3))

    return Mq2Enrichment(hazard_level=hazard, sensor_voltage_ratio=voltage_ratio)
