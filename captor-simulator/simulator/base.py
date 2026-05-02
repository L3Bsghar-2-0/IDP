from __future__ import annotations

import math
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

QualityFlag = Literal["good", "suspect", "bad"]


@dataclass
class FailureConfig:
    """Active failure state carried by each sensor and applied in read()."""

    failure_type: str
    start_ts: int
    duration_s: float
    intensity: float = 1.0
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def end_ts(self) -> int:
        return int(self.start_ts + self.duration_s * 1000)

    def is_active(self, now_ms: int) -> bool:
        return self.start_ts <= now_ms < self.end_ts


class BaseSensor(ABC):
    """Abstract sensor with standardized output schema and failure injection hooks."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        device_id: str,
        sensor_id: str,
        sensor_type: str,
        unit: str,
        sample_rate_hz: float,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        noise_factor: float = 1.0,
        base_noise_std: float = 0.0,
    ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be > 0")
        self.device_id = device_id
        self.sensor_id = sensor_id
        self.sensor_type = sensor_type
        self.unit = unit
        self.sample_rate_hz = sample_rate_hz
        self.min_value = min_value
        self.max_value = max_value
        self.noise_factor = noise_factor
        self.base_noise_std = base_noise_std

        self._seq = 0
        self._last_value: Optional[Any] = None
        self._active_failures: List[FailureConfig] = []
        self._disconnect_probability = 0.0
        self._rng = random.Random(f"{device_id}:{sensor_id}")

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    @property
    def seq(self) -> int:
        return self._seq

    def inject_failure(self, config: FailureConfig) -> None:
        self._active_failures.append(config)

    def clear_expired_failures(self, now_ms: int) -> None:
        self._active_failures = [f for f in self._active_failures if f.is_active(now_ms)]

    def set_disconnect_probability(self, probability: float) -> None:
        self._disconnect_probability = max(0.0, min(1.0, probability))

    def _quality_for_failures(self, active: List[FailureConfig]) -> QualityFlag:
        if not active:
            return "good"
        severe_types = {"disconnect", "dropout"}
        if any(f.failure_type in severe_types for f in active):
            return "bad"
        return "suspect"

    def _clip(self, value: float) -> float:
        if self.min_value is not None:
            value = max(self.min_value, value)
        if self.max_value is not None:
            value = min(self.max_value, value)
        return value

    @abstractmethod
    def _simulate_value(self, ts_ms: int) -> Any:
        """Return the ideal simulated value before generic failure transforms."""

    def _simulate_meta(self, ts_ms: int) -> Dict[str, Any]:
        """Optional extra metadata for subclasses."""
        _ = ts_ms
        return {}

    def _apply_sensor_specific_failures(
        self,
        value: Any,
        active_failures: List[FailureConfig],
        ts_ms: int,
    ) -> Any:
        """Subclass extension point for sensor-specific physics failures."""
        _ = ts_ms
        return value

    def _apply_common_failures(
        self,
        value: Any,
        active_failures: List[FailureConfig],
        ts_ms: int,
    ) -> Any:
        """Apply framework-level failure injection for scalar and dict outputs."""

        def mutate_scalar(x: float) -> float:
            drift_component = 0.0
            for f in active_failures:
                if f.failure_type == "spike":
                    spike = f.params.get("spike_value")
                    if spike is None:
                        span = (self.max_value or 1.0) - (self.min_value or 0.0)
                        spike = x + span * 0.3 * f.intensity
                    x = float(spike)
                elif f.failure_type == "stuck":
                    if self._last_value is not None:
                        x = float(self._last_value)
                elif f.failure_type == "dropout":
                    dropout_value = f.params.get("dropout_value", 0.0)
                    x = float(dropout_value)
                elif f.failure_type == "drift":
                    # Drift accumulates with elapsed failure time to mimic calibration drift.
                    elapsed_s = max(0.0, (ts_ms - f.start_ts) / 1000.0)
                    drift_rate = f.params.get("drift_per_sec", 0.01) * f.intensity
                    drift_component += elapsed_s * drift_rate
                elif f.failure_type == "noise_increase":
                    std = self.base_noise_std * max(1.0, f.intensity)
                    x += self._rng.gauss(0.0, std)
            x += drift_component
            if self.min_value is not None or self.max_value is not None:
                x = self._clip(x)
            return x

        if isinstance(value, dict):
            return {k: mutate_scalar(float(v)) for k, v in value.items()}
        return mutate_scalar(float(value))

    def read(self) -> Optional[Dict[str, Any]]:
        ts_ms = self.now_ms()
        self.clear_expired_failures(ts_ms)
        active = [f for f in self._active_failures if f.is_active(ts_ms)]

        if self._rng.random() < self._disconnect_probability:
            return None

        if any(f.failure_type == "disconnect" for f in active):
            return None

        value = self._simulate_value(ts_ms)
        value = self._apply_sensor_specific_failures(value, active, ts_ms)
        value = self._apply_common_failures(value, active, ts_ms)

        reading = {
            "v": self.SCHEMA_VERSION,
            "device_id": self.device_id,
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "ts": ts_ms,
            "seq": self._seq,
            "value": value,
            "unit": self.unit,
            "quality": self._quality_for_failures(active),
            "meta": self._simulate_meta(ts_ms),
        }

        self._seq += 1
        self._last_value = value
        return reading


@dataclass
class FailureEvent:
    sensor_id: str
    failure_type: Literal[
        "spike",
        "stuck",
        "dropout",
        "drift",
        "noise_increase",
        "disconnect",
    ]
    start_ts: int
    duration_s: float
    intensity: float = 1.0
    params: Dict[str, Any] = field(default_factory=dict)


class FailureScheduler:
    """Schedules deterministic or random failures and injects them into sensors."""

    SUPPORTED = {
        "spike",
        "stuck",
        "dropout",
        "drift",
        "noise_increase",
        "disconnect",
    }

    def __init__(self, events: Optional[List[FailureEvent]] = None, random_mode: bool = False) -> None:
        self.events = events or []
        self.random_mode = random_mode
        self._applied_keys: set[str] = set()
        self._rng = random.Random("failure-scheduler")

    def add_event(self, event: FailureEvent) -> None:
        if event.failure_type not in self.SUPPORTED:
            raise ValueError(f"Unsupported failure type: {event.failure_type}")
        self.events.append(event)

    def _event_key(self, ev: FailureEvent) -> str:
        return f"{ev.sensor_id}:{ev.failure_type}:{ev.start_ts}:{ev.duration_s}:{ev.intensity}"

    def _build_random_event(self, sensor_id: str, now_ms: int) -> FailureEvent:
        failure_type = self._rng.choice(sorted(self.SUPPORTED))
        duration_s = self._rng.uniform(10, 120)
        intensity = self._rng.uniform(0.5, 2.5)
        return FailureEvent(
            sensor_id=sensor_id,
            failure_type=failure_type,  # type: ignore[arg-type]
            start_ts=now_ms,
            duration_s=duration_s,
            intensity=intensity,
            params={},
        )

    def tick(self, sensors: Dict[str, BaseSensor], now_ms: Optional[int] = None) -> None:
        now_ms = now_ms or BaseSensor.now_ms()

        if self.random_mode and sensors:
            # Small per-tick probability creates sporadic faults for stress tests.
            for sensor_id in sensors:
                if self._rng.random() < 0.003:
                    event = self._build_random_event(sensor_id, now_ms)
                    self.add_event(event)

        for ev in self.events:
            if ev.failure_type not in self.SUPPORTED:
                continue
            key = self._event_key(ev)
            if key in self._applied_keys:
                continue
            if now_ms >= ev.start_ts:
                sensor = sensors.get(ev.sensor_id)
                if sensor is not None:
                    sensor.inject_failure(
                        FailureConfig(
                            failure_type=ev.failure_type,
                            start_ts=ev.start_ts,
                            duration_s=ev.duration_s,
                            intensity=ev.intensity,
                            params=ev.params,
                        )
                    )
                    self._applied_keys.add(key)


def cyclic_phase(ts_ms: int, period_s: float) -> float:
    t_s = ts_ms / 1000.0
    return (2.0 * math.pi * (t_s % period_s)) / period_s
