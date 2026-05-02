"""Sliding-window anomaly detection per (device_id, sensor_id, reading_key)."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque

import numpy as np

from app.models.telemetry import Reading, TelemetryMessage


WINDOW = 20
DROPOUT_RUN = 3
STUCK_WINDOW = 10
HIGH_HUMIDITY_RUN = 5


@dataclass
class AnomalyResult:
    """Detected anomaly event."""

    type: str
    sensor_type: str
    sensor_id: str
    device_id: str
    ts: datetime
    confidence: float
    description: str
    reading_value: float


@dataclass
class _SensorState:
    values: Deque[float] = field(default_factory=lambda: deque(maxlen=WINDOW))
    qualities: Deque[str] = field(default_factory=lambda: deque(maxlen=DROPOUT_RUN))
    high_humidity_run: int = 0
    last_smoke_above: bool = False
    last_hazard_above: bool = False
    last_dropout_emitted: bool = False
    last_stuck_emitted: bool = False
    last_drift_emitted: bool = False


class AnomalyDetector:
    """Maintains per-sensor sliding windows and emits anomaly events."""

    def __init__(self, smoke_threshold_ppm: int, hazard_threshold_ppm: int) -> None:
        self._smoke = smoke_threshold_ppm
        self._hazard = hazard_threshold_ppm
        self._states: dict[tuple[str, str, str], _SensorState] = defaultdict(_SensorState)

    # -------------------------------------------------------------- helpers

    def _state(self, device_id: str, sensor_id: str, key: str) -> _SensorState:
        return self._states[(device_id, sensor_id, key)]

    @staticmethod
    def _stats(values: Deque[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        arr = np.array(values, dtype=float)
        return float(arr.mean()), float(arr.std(ddof=0))

    # --------------------------------------------------------------- public

    def detect(self, msg: TelemetryMessage, readings: dict[str, Reading]) -> list[AnomalyResult]:
        """Run the appropriate detection rules for the message's sensor type."""
        if msg.sensor_type == "dht22":
            return self._detect_dht22(msg, readings)
        if msg.sensor_type == "mq2":
            return self._detect_mq2(msg, readings)
        return []

    # ---------------------------------------------------------------- DHT22

    def _detect_dht22(
        self, msg: TelemetryMessage, readings: dict[str, Reading]
    ) -> list[AnomalyResult]:
        out: list[AnomalyResult] = []

        for key in ("temperature", "humidity"):
            if key not in readings:
                continue
            reading = readings[key]
            state = self._state(msg.device_id, msg.sensor_id, key)
            state.qualities.append(reading.quality)

            # Dropout — 3+ consecutive bad
            if (
                len(state.qualities) >= DROPOUT_RUN
                and all(q == "bad" for q in list(state.qualities)[-DROPOUT_RUN:])
            ):
                if not state.last_dropout_emitted:
                    out.append(
                        AnomalyResult(
                            type="DROPOUT",
                            sensor_type="dht22",
                            sensor_id=msg.sensor_id,
                            device_id=msg.device_id,
                            ts=msg.ts,
                            confidence=0.9,
                            description=f"3+ consecutive bad reads on {key}",
                            reading_value=reading.value,
                        )
                    )
                    state.last_dropout_emitted = True
            else:
                state.last_dropout_emitted = False

            # Skip metric-based detection on bad samples
            if reading.quality == "bad" or not math.isfinite(reading.value):
                continue

            # SPIKE
            if len(state.values) >= 5:
                mean, std = self._stats(state.values)
                if std > 0 and abs(reading.value - mean) > 3.0 * std:
                    out.append(
                        AnomalyResult(
                            type="SPIKE",
                            sensor_type="dht22",
                            sensor_id=msg.sensor_id,
                            device_id=msg.device_id,
                            ts=msg.ts,
                            confidence=min(1.0, abs(reading.value - mean) / (3.0 * std + 1e-6) / 2.0),
                            description=f"{key} {reading.value:.2f} > 3σ from mean {mean:.2f}",
                            reading_value=reading.value,
                        )
                    )

            # STUCK_SENSOR — std of last 10 < 0.05
            if len(state.values) >= STUCK_WINDOW:
                last = np.array(list(state.values)[-STUCK_WINDOW:], dtype=float)
                if float(last.std(ddof=0)) < 0.05:
                    if not state.last_stuck_emitted:
                        out.append(
                            AnomalyResult(
                                type="STUCK_SENSOR",
                                sensor_type="dht22",
                                sensor_id=msg.sensor_id,
                                device_id=msg.device_id,
                                ts=msg.ts,
                                confidence=0.85,
                                description=f"{key} std<0.05 over last {STUCK_WINDOW} samples",
                                reading_value=reading.value,
                            )
                        )
                        state.last_stuck_emitted = True
                else:
                    state.last_stuck_emitted = False

            # HEAT_ALERT (industrial)
            if key == "temperature" and reading.value > 60.0:
                out.append(
                    AnomalyResult(
                        type="HEAT_ALERT",
                        sensor_type="dht22",
                        sensor_id=msg.sensor_id,
                        device_id=msg.device_id,
                        ts=msg.ts,
                        confidence=1.0,
                        description=f"temperature {reading.value:.1f}°C exceeds 60°C",
                        reading_value=reading.value,
                    )
                )

            # HIGH_HUMIDITY — sustained 5 readings > 95
            if key == "humidity":
                if reading.value > 95.0:
                    state.high_humidity_run += 1
                    if state.high_humidity_run >= HIGH_HUMIDITY_RUN:
                        out.append(
                            AnomalyResult(
                                type="HIGH_HUMIDITY",
                                sensor_type="dht22",
                                sensor_id=msg.sensor_id,
                                device_id=msg.device_id,
                                ts=msg.ts,
                                confidence=0.9,
                                description=f"humidity > 95% for {state.high_humidity_run} samples",
                                reading_value=reading.value,
                            )
                        )
                        state.high_humidity_run = HIGH_HUMIDITY_RUN  # cap
                else:
                    state.high_humidity_run = 0

            state.values.append(reading.value)

        return out

    # ----------------------------------------------------------------- MQ-2

    def _detect_mq2(
        self, msg: TelemetryMessage, readings: dict[str, Reading]
    ) -> list[AnomalyResult]:
        out: list[AnomalyResult] = []

        # DROPOUT on raw_adc — 3+ consecutive zero
        adc = readings.get("raw_adc")
        if adc is not None:
            adc_state = self._state(msg.device_id, msg.sensor_id, "raw_adc")
            adc_state.qualities.append("bad" if adc.value == 0 else "good")
            if (
                len(adc_state.qualities) >= DROPOUT_RUN
                and all(q == "bad" for q in list(adc_state.qualities)[-DROPOUT_RUN:])
            ):
                if not adc_state.last_dropout_emitted:
                    out.append(
                        AnomalyResult(
                            type="DROPOUT",
                            sensor_type="mq2",
                            sensor_id=msg.sensor_id,
                            device_id=msg.device_id,
                            ts=msg.ts,
                            confidence=0.95,
                            description="raw_adc=0 for 3+ consecutive samples (sensor disconnected?)",
                            reading_value=adc.value,
                        )
                    )
                    adc_state.last_dropout_emitted = True
            else:
                adc_state.last_dropout_emitted = False

        # Gas-related rules
        gas = readings.get("gas_ppm")
        if gas is not None and gas.quality != "bad" and math.isfinite(gas.value):
            gas_state = self._state(msg.device_id, msg.sensor_id, "gas_ppm")

            # SPIKE
            if len(gas_state.values) >= 5:
                mean, std = self._stats(gas_state.values)
                if std > 0 and abs(gas.value - mean) > 3.0 * std:
                    out.append(
                        AnomalyResult(
                            type="SPIKE",
                            sensor_type="mq2",
                            sensor_id=msg.sensor_id,
                            device_id=msg.device_id,
                            ts=msg.ts,
                            confidence=min(1.0, abs(gas.value - mean) / (3.0 * std + 1e-6) / 2.0),
                            description=f"gas_ppm {gas.value:.0f} > 3σ from mean {mean:.0f}",
                            reading_value=gas.value,
                        )
                    )

            # STUCK_SENSOR — std of last 10 gas_ppm < 1.0
            if len(gas_state.values) >= STUCK_WINDOW:
                last = np.array(list(gas_state.values)[-STUCK_WINDOW:], dtype=float)
                if float(last.std(ddof=0)) < 1.0:
                    if not gas_state.last_stuck_emitted:
                        out.append(
                            AnomalyResult(
                                type="STUCK_SENSOR",
                                sensor_type="mq2",
                                sensor_id=msg.sensor_id,
                                device_id=msg.device_id,
                                ts=msg.ts,
                                confidence=0.8,
                                description=f"gas_ppm std<1.0 over last {STUCK_WINDOW} samples",
                                reading_value=gas.value,
                            )
                        )
                        gas_state.last_stuck_emitted = True
                else:
                    gas_state.last_stuck_emitted = False

            # SMOKE_ALARM — rising edge across smoke threshold
            currently_smoke = gas.value >= self._smoke
            if currently_smoke and not gas_state.last_smoke_above:
                out.append(
                    AnomalyResult(
                        type="SMOKE_ALARM",
                        sensor_type="mq2",
                        sensor_id=msg.sensor_id,
                        device_id=msg.device_id,
                        ts=msg.ts,
                        confidence=1.0,
                        description=f"gas_ppm crossed SMOKE threshold {self._smoke}: now {gas.value:.0f}",
                        reading_value=gas.value,
                    )
                )
            gas_state.last_smoke_above = currently_smoke

            # HAZARD_ALARM — rising edge across hazard threshold
            currently_hazard = gas.value >= self._hazard
            if currently_hazard and not gas_state.last_hazard_above:
                out.append(
                    AnomalyResult(
                        type="HAZARD_ALARM",
                        sensor_type="mq2",
                        sensor_id=msg.sensor_id,
                        device_id=msg.device_id,
                        ts=msg.ts,
                        confidence=1.0,
                        description=f"gas_ppm crossed HAZARD threshold {self._hazard}: now {gas.value:.0f}",
                        reading_value=gas.value,
                    )
                )
            gas_state.last_hazard_above = currently_hazard

            gas_state.values.append(gas.value)

        # DRIFT on rs_r0_ratio — slope > 0.05/sample over WINDOW
        rs = readings.get("rs_r0_ratio")
        if rs is not None and rs.quality != "bad" and math.isfinite(rs.value):
            rs_state = self._state(msg.device_id, msg.sensor_id, "rs_r0_ratio")
            rs_state.values.append(rs.value)
            if len(rs_state.values) >= WINDOW:
                xs = np.arange(len(rs_state.values), dtype=float)
                ys = np.array(list(rs_state.values), dtype=float)
                slope = float(np.polyfit(xs, ys, 1)[0])
                if abs(slope) > 0.05:
                    if not rs_state.last_drift_emitted:
                        out.append(
                            AnomalyResult(
                                type="DRIFT",
                                sensor_type="mq2",
                                sensor_id=msg.sensor_id,
                                device_id=msg.device_id,
                                ts=msg.ts,
                                confidence=min(1.0, abs(slope) / 0.5),
                                description=f"rs_r0_ratio slope {slope:+.3f} per sample",
                                reading_value=rs.value,
                            )
                        )
                        rs_state.last_drift_emitted = True
                else:
                    rs_state.last_drift_emitted = False

        return out
