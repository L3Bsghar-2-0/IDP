"""Physical-range validator for DHT22 and MQ-2 readings."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from app.models.telemetry import (
    DHT22_READING_KEYS,
    MQ2_READING_KEYS,
    Reading,
    TelemetryMessage,
)


# Physical valid ranges per (sensor_type, reading_key)
RANGES: dict[tuple[str, str], tuple[float, float]] = {
    ("dht22", "temperature"): (-40.0, 80.0),
    ("dht22", "humidity"):    (0.0, 100.0),
    ("mq2", "raw_adc"):       (0.0, 4095.0),
    ("mq2", "voltage"):       (0.0, 3.3),
    ("mq2", "rs_r0_ratio"):   (0.1, 10.0),
    ("mq2", "gas_ppm"):       (300.0, 10000.0),
}


@dataclass
class ValidationResult:
    """Outcome of validating one telemetry message."""

    passed: bool
    flags: list[str] = field(default_factory=list)
    cleaned_readings: dict[str, Reading] = field(default_factory=dict)


def _clone(reading: Reading, *, value: float | None = None, quality: str | None = None) -> Reading:
    return Reading(
        value=reading.value if value is None else value,
        unit=reading.unit,
        quality=reading.quality if quality is None else quality,  # type: ignore[arg-type]
    )


def _expected_keys(sensor_type: str) -> Iterable[str]:
    return DHT22_READING_KEYS if sensor_type == "dht22" else MQ2_READING_KEYS


def validate_telemetry(msg: TelemetryMessage) -> ValidationResult:
    """Range-check every reading; mark out-of-range as quality='bad' and flag.

    Out-of-range values are not discarded — they are still stored for traceability.
    """
    flags: list[str] = []
    cleaned: dict[str, Reading] = {}

    expected = set(_expected_keys(msg.sensor_type))
    incoming = set(msg.readings.keys())

    missing = expected - incoming
    if missing:
        flags.append(f"missing_keys:{','.join(sorted(missing))}")

    extra = incoming - expected
    if extra:
        flags.append(f"unexpected_keys:{','.join(sorted(extra))}")

    for key, reading in msg.readings.items():
        # NaN / non-finite ⇒ bad (DHT22 NaN read condition)
        if not math.isfinite(reading.value):
            flags.append(f"nonfinite:{key}")
            cleaned[key] = _clone(reading, value=0.0, quality="bad")
            continue

        if key == "smoke_detected":
            v = reading.value
            if v not in (0.0, 1.0):
                flags.append(f"smoke_not_boolean:{v}")
                cleaned[key] = _clone(reading, value=0.0, quality="bad")
            else:
                cleaned[key] = _clone(reading, value=float(int(v)))
            continue

        rng = RANGES.get((msg.sensor_type, key))
        if rng is None:
            # Unknown reading_key for this sensor type — keep but flag
            cleaned[key] = reading
            continue

        lo, hi = rng
        if reading.value < lo or reading.value > hi:
            flags.append(f"range:{key}:{reading.value}")
            cleaned[key] = _clone(reading, quality="bad")
        else:
            cleaned[key] = reading

    failure_prefixes = ("range:", "nonfinite:", "smoke_not_boolean:")
    passed = not any(f.startswith(failure_prefixes) for f in flags)
    return ValidationResult(passed=passed, flags=flags, cleaned_readings=cleaned)
