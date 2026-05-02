from __future__ import annotations

import math
import random
from typing import Any, Dict, List

import numpy as np

from .base import BaseSensor, FailureConfig, cyclic_phase

G_TO_MPS2 = 9.80665


class TemperatureSensor(BaseSensor):
    """Indoor process temperature with diurnal occupancy heat gains."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="temperature",
            unit="C",
            sample_rate_hz=sample_rate_hz,
            min_value=-10.0,
            max_value=60.0,
            noise_factor=noise_factor,
            base_noise_std=0.3,
        )

    def _simulate_value(self, ts_ms: int) -> float:
        # Daily thermal swing: coolest pre-dawn, warmest during staffed daytime operation.
        day_phase = cyclic_phase(ts_ms, 24 * 3600)
        occupancy_bump = 2.0 * max(0.0, math.sin(day_phase - math.pi / 2.2))
        base = 24.0 + 4.5 * math.sin(day_phase - math.pi / 2) + occupancy_bump
        noise = self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return self._clip(base + noise)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        x = float(value)
        for f in active_failures:
            if f.failure_type == "stuck" and self._last_value is not None:
                x = float(self._last_value)
            elif f.failure_type == "spike":
                # Shorted thermistor often rails high near hardcoded firmware sentinel values.
                x = 99.0
        return x


class HumiditySensor(BaseSensor):
    """Relative humidity inversely coupled with temperature."""

    def __init__(
        self,
        device_id: str,
        sensor_id: str,
        sample_rate_hz: float,
        linked_temperature: TemperatureSensor | None = None,
        noise_factor: float = 1.0,
    ) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="humidity",
            unit="%RH",
            sample_rate_hz=sample_rate_hz,
            min_value=20.0,
            max_value=90.0,
            noise_factor=noise_factor,
            base_noise_std=1.0,
        )
        self.linked_temperature = linked_temperature

    def _simulate_value(self, ts_ms: int) -> float:
        # Relative humidity falls as air warms (constant absolute moisture approximation).
        day_phase = cyclic_phase(ts_ms, 24 * 3600)
        temp_proxy = 24.0 + 4.5 * math.sin(day_phase - math.pi / 2)
        if self.linked_temperature and self.linked_temperature._last_value is not None:
            temp_proxy = float(self.linked_temperature._last_value)
        baseline = 55.0 - 0.8 * (temp_proxy - 24.0)
        weather_wave = 6.0 * math.sin(day_phase + math.pi / 3)
        noise = self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return self._clip(baseline + weather_wave + noise)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        x = float(value)
        for f in active_failures:
            if f.failure_type == "spike":
                x = 100.0
            elif f.failure_type == "dropout":
                x = 0.0
        return x


class CO2Sensor(BaseSensor):
    """NDIR CO2 in occupied industrial spaces."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="co2",
            unit="ppm",
            sample_rate_hz=sample_rate_hz,
            min_value=400.0,
            max_value=5000.0,
            noise_factor=noise_factor,
            base_noise_std=15.0,
        )

    def _simulate_value(self, ts_ms: int) -> float:
        # Occupancy and combustion load elevate CO2 through shifts, then ventilation clears at night.
        day_phase = cyclic_phase(ts_ms, 24 * 3600)
        occupied = max(0.0, math.sin(day_phase - math.pi / 2.1))
        base = 450.0 + 1100.0 * occupied + 250.0 * max(0.0, math.sin(2 * day_phase - 0.7))
        noise = self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return self._clip(base + noise)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        x = float(value)
        for f in active_failures:
            if f.failure_type == "drift":
                # NDIR optical contamination can bias readings upward gradually.
                elapsed_h = max(0.0, (ts_ms - f.start_ts) / 3_600_000.0)
                x += elapsed_h * 20.0 * f.intensity
            elif f.failure_type == "stuck":
                x = 400.0
        return self._clip(x)


class PowerMeterSensor(BaseSensor):
    """Industrial active power following shift peaks and machine cycles."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="power",
            unit="W",
            sample_rate_hz=sample_rate_hz,
            min_value=0.0,
            max_value=50000.0,
            noise_factor=noise_factor,
            base_noise_std=20.0,
        )

    def _simulate_value(self, ts_ms: int) -> float:
        # Two Gaussian-like shift peaks around 08:00 and 14:00 model startup and second shift ramps.
        day_s = (ts_ms / 1000.0) % (24 * 3600)
        hour = day_s / 3600.0
        peak1 = 17000.0 * math.exp(-((hour - 8.0) ** 2) / 3.0)
        peak2 = 14000.0 * math.exp(-((hour - 14.0) ** 2) / 4.0)
        baseline = 6000.0 + peak1 + peak2
        machine_cycle = 1800.0 * max(0.0, math.sin(cyclic_phase(ts_ms, 900)))
        noise = self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return self._clip(baseline + machine_cycle + noise)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        x = float(value)
        for f in active_failures:
            if f.failure_type == "dropout":
                x = 0.0
            elif f.failure_type == "spike":
                x = -abs(x) * max(1.0, f.intensity)
        return x


class PressureSensor(BaseSensor):
    """Pneumatic/HVAC pressure with mostly stable operation and sparse events."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="pressure",
            unit="bar",
            sample_rate_hz=sample_rate_hz,
            min_value=0.5,
            max_value=10.0,
            noise_factor=noise_factor,
            base_noise_std=0.05,
        )
        self._event_until_ms = 0
        self._event_amp = 0.0

    def _simulate_value(self, ts_ms: int) -> float:
        # Line pressure remains near setpoint with occasional compressor actuation bumps.
        baseline = 6.2
        if ts_ms > self._event_until_ms and self._rng.random() < 0.01:
            self._event_until_ms = ts_ms + int(self._rng.uniform(5.0, 20.0) * 1000)
            self._event_amp = self._rng.uniform(0.2, 0.8)
        event_term = 0.0
        if ts_ms < self._event_until_ms:
            event_term = self._event_amp * math.sin(cyclic_phase(ts_ms, 30.0))
        noise = self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return self._clip(baseline + event_term + noise)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        x = float(value)
        for f in active_failures:
            if f.failure_type == "dropout":
                # Leak event: abrupt pressure collapse toward near-atmospheric gauge pressure.
                x = max(0.5, x - 4.0 * f.intensity)
            elif f.failure_type == "noise_increase":
                # Pump cavitation introduces oscillatory pressure ripple.
                cavitation = 0.4 * f.intensity * math.sin(cyclic_phase(ts_ms, 1.2))
                x += cavitation
        return self._clip(x)


class VibrationSensor(BaseSensor):
    """Tri-axial vibration in m/s^2 for rotating machinery."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        full_scale = 16.0 * G_TO_MPS2
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="vibration",
            unit="m/s2",
            sample_rate_hz=sample_rate_hz,
            min_value=-full_scale,
            max_value=full_scale,
            noise_factor=noise_factor,
            base_noise_std=0.15,
        )
        self._full_scale = full_scale

    def _simulate_value(self, ts_ms: int) -> Dict[str, float]:
        # Baseline machine vibration is low with periodic impulse packets from rotating elements.
        pulse = max(0.0, math.sin(cyclic_phase(ts_ms, 2.0))) ** 3
        x = 0.8 * pulse + self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        y = 0.6 * pulse + self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        z = 9.81 + 0.4 * pulse + self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return {
            "x": float(np.clip(x, -self._full_scale, self._full_scale)),
            "y": float(np.clip(y, -self._full_scale, self._full_scale)),
            "z": float(np.clip(z, -self._full_scale, self._full_scale)),
        }

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        vec = dict(value)
        for f in active_failures:
            if f.failure_type == "stuck":
                # Single-axis ADC lock-up; default to X unless configured.
                axis = str(f.params.get("axis", "x"))
                if axis in vec and self._last_value and isinstance(self._last_value, dict):
                    vec[axis] = float(self._last_value.get(axis, vec[axis]))
            elif f.failure_type == "spike":
                # Mechanical shock appears as simultaneous burst on all axes.
                shock = self._full_scale * min(1.0, 0.7 * f.intensity)
                vec = {k: float(np.clip(v + shock, -self._full_scale, self._full_scale)) for k, v in vec.items()}
        return vec


class FlowMeter(BaseSensor):
    """Process fluid flowmeter in liters/minute."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="flow",
            unit="L/min",
            sample_rate_hz=sample_rate_hz,
            min_value=0.0,
            max_value=500.0,
            noise_factor=noise_factor,
            base_noise_std=2.0,
        )

    def _simulate_value(self, ts_ms: int) -> float:
        # Flow tracks staffing shifts and washdown/transfer cycles.
        day_phase = cyclic_phase(ts_ms, 24 * 3600)
        shift_load = 180.0 + 140.0 * max(0.0, math.sin(day_phase - math.pi / 2.3))
        cycle_term = 60.0 * max(0.0, math.sin(cyclic_phase(ts_ms, 1800)))
        noise = self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return self._clip(shift_load + cycle_term + noise)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        x = float(value)
        for f in active_failures:
            if f.failure_type == "spike":
                x = -abs(x)
            elif f.failure_type == "stuck":
                x = 500.0
        return x


class GasSensor(BaseSensor):
    """Methane/VOC detector reporting %LEL."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="gas",
            unit="%LEL",
            sample_rate_hz=sample_rate_hz,
            min_value=0.0,
            max_value=100.0,
            noise_factor=noise_factor,
            base_noise_std=0.5,
        )
        self._event_until_ms = 0
        self._event_amp = 0.0

    def _simulate_value(self, ts_ms: int) -> float:
        # Normal baseline is low, with rare short-lived release plumes.
        baseline = 2.0 + self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        if ts_ms > self._event_until_ms and self._rng.random() < 0.006:
            self._event_until_ms = ts_ms + int(self._rng.uniform(8, 40) * 1000)
            self._event_amp = self._rng.uniform(8.0, 35.0)
        event = 0.0
        if ts_ms < self._event_until_ms:
            event = self._event_amp * math.exp(-((self._event_until_ms - ts_ms) / 7000.0))
        return self._clip(baseline + event)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        x = float(value)
        for f in active_failures:
            if f.failure_type == "drift":
                # Catalyst poisoning often biases sensor permanently high.
                x = max(x, 25.0 * f.intensity)
            elif f.failure_type == "dropout":
                x = 0.0
        return self._clip(x)


class EnergyMeter(BaseSensor):
    """Invoice-like cumulative kWh plus instantaneous kW channel."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="energy",
            unit="kWh",
            sample_rate_hz=sample_rate_hz,
            min_value=0.0,
            max_value=None,
            noise_factor=noise_factor,
            base_noise_std=0.03,
        )
        self._kwh_total = 0.0
        self._last_ts_ms: int | None = None

    def _simulate_value(self, ts_ms: int) -> Dict[str, float]:
        # Instantaneous demand follows power profile; cumulative register integrates over time.
        day_s = (ts_ms / 1000.0) % (24 * 3600)
        hour = day_s / 3600.0
        kw = 12.0 + 18.0 * math.exp(-((hour - 8.0) ** 2) / 4.0) + 15.0 * math.exp(-((hour - 14.0) ** 2) / 4.5)
        kw += max(0.0, math.sin(cyclic_phase(ts_ms, 1200))) * 4.0
        kw += self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        kw = max(0.0, kw)

        if self._last_ts_ms is None:
            self._last_ts_ms = ts_ms
        dt_h = max(0.0, (ts_ms - self._last_ts_ms) / 3_600_000.0)
        self._kwh_total += kw * dt_h
        self._last_ts_ms = ts_ms

        return {"kwh_total": round(self._kwh_total, 6), "kw": round(kw, 6)}

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        out = dict(value)
        for f in active_failures:
            if f.failure_type == "dropout":
                # Power loss can reset volatile meter state in low-end devices.
                self._kwh_total = 0.0
                out["kwh_total"] = 0.0
                out["kw"] = 0.0
            elif f.failure_type == "stuck":
                if self._last_value and isinstance(self._last_value, dict):
                    out["kwh_total"] = float(self._last_value.get("kwh_total", out["kwh_total"]))
                    out["kw"] = float(self._last_value.get("kw", out["kw"]))
        return out


class AmbientLightSensor(BaseSensor):
    """Ambient illuminance modeled by daytime solar cycle."""

    def __init__(self, device_id: str, sensor_id: str, sample_rate_hz: float, noise_factor: float = 1.0) -> None:
        super().__init__(
            device_id=device_id,
            sensor_id=sensor_id,
            sensor_type="ambient_light",
            unit="lux",
            sample_rate_hz=sample_rate_hz,
            min_value=0.0,
            max_value=100000.0,
            noise_factor=noise_factor,
            base_noise_std=150.0,
        )

    def _simulate_value(self, ts_ms: int) -> float:
        # Sunrise-to-sunset half-sine approximates daylight intensity envelope.
        day_s = (ts_ms / 1000.0) % (24 * 3600)
        hour = day_s / 3600.0
        sunrise = 6.0
        sunset = 18.5
        if hour < sunrise or hour > sunset:
            base = 20.0  # Nighttime spill light.
        else:
            frac = (hour - sunrise) / (sunset - sunrise)
            base = 85000.0 * math.sin(math.pi * frac)
        cloud_mod = 7000.0 * max(0.0, math.sin(cyclic_phase(ts_ms, 5400) + 1.2))
        noise = self._rng.gauss(0.0, self.base_noise_std * self.noise_factor)
        return self._clip(base - cloud_mod + noise)

    def _apply_sensor_specific_failures(self, value: Any, active_failures: List[FailureConfig], ts_ms: int) -> Any:
        _ = ts_ms
        x = float(value)
        for f in active_failures:
            if f.failure_type == "dropout":
                x = 0.0
            elif f.failure_type == "stuck":
                x = 100000.0
        return self._clip(x)


SENSOR_TYPES = {
    "TemperatureSensor": TemperatureSensor,
    "HumiditySensor": HumiditySensor,
    "CO2Sensor": CO2Sensor,
    "PowerMeterSensor": PowerMeterSensor,
    "PressureSensor": PressureSensor,
    "VibrationSensor": VibrationSensor,
    "FlowMeter": FlowMeter,
    "GasSensor": GasSensor,
    "EnergyMeter": EnergyMeter,
    "AmbientLightSensor": AmbientLightSensor,
}


def build_sensor(
    sensor_type: str,
    device_id: str,
    sensor_id: str,
    sample_rate_hz: float,
    noise_factor: float = 1.0,
) -> BaseSensor:
    cls = SENSOR_TYPES.get(sensor_type)
    if cls is None:
        raise ValueError(f"Unknown sensor type: {sensor_type}")
    return cls(device_id=device_id, sensor_id=sensor_id, sample_rate_hz=sample_rate_hz, noise_factor=noise_factor)
