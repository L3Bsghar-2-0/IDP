from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

from .base import BaseSensor, FailureEvent, FailureScheduler
from .device import FilePublisher, MQTTPublisher, QueuePublisher, StdoutPublisher, VirtualDevice, run_devices
from .sensors import build_sensor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


class FailureCfg(BaseModel):
    sensor_id: str
    type: Literal["spike", "stuck", "dropout", "drift", "noise_increase", "disconnect"]
    start_offset_s: float = 0.0
    duration_s: float = 60.0
    intensity: float = 1.0
    params: Dict[str, Any] = Field(default_factory=dict)


class SensorCfg(BaseModel):
    type: str
    sensor_id: str
    sample_rate_hz: float = 1.0
    noise_factor: float = 1.0
    enabled: bool = True


class DeviceCfg(BaseModel):
    device_id: str
    site: str
    tenant: str = "default_tenant"
    sensors: List[SensorCfg] = Field(default_factory=list)
    failures: List[FailureCfg] = Field(default_factory=list)


class MQTTCfg(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    use_tls: bool = True


class SimulationCfg(BaseModel):
    speed_multiplier: float = 1.0
    random_failures: bool = False
    aggregate_window_s: float = 1.0


class RootCfg(BaseModel):
    devices: List[DeviceCfg]
    simulation: SimulationCfg = Field(default_factory=SimulationCfg)
    mqtt: MQTTCfg = Field(default_factory=MQTTCfg)


def load_config(path: str) -> RootCfg:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    try:
        return RootCfg.model_validate(raw)
    except ValidationError as exc:
        raise SystemExit(f"Invalid config: {exc}") from exc


def build_failure_scheduler(failures: List[FailureCfg], now_ms: int, random_mode: bool) -> FailureScheduler:
    events = [
        FailureEvent(
            sensor_id=f.sensor_id,
            failure_type=f.type,
            start_ts=now_ms + int(f.start_offset_s * 1000),
            duration_s=f.duration_s,
            intensity=f.intensity,
            params=f.params,
        )
        for f in failures
    ]
    return FailureScheduler(events=events, random_mode=random_mode)


def build_sensors(device_cfg: DeviceCfg) -> List[BaseSensor]:
    sensors: List[BaseSensor] = []
    for sc in device_cfg.sensors:
        if not sc.enabled:
            continue
        sensor = build_sensor(
            sensor_type=sc.type,
            device_id=device_cfg.device_id,
            sensor_id=sc.sensor_id,
            sample_rate_hz=sc.sample_rate_hz,
            noise_factor=sc.noise_factor,
        )
        sensors.append(sensor)
    return sensors


async def make_devices(cfg: RootCfg, mode: str, file_output: str) -> List[VirtualDevice]:
    now_ms = BaseSensor.now_ms()
    devices: List[VirtualDevice] = []

    shared_queue: Optional[asyncio.Queue[Dict[str, Any]]] = None
    if mode == "queue":
        shared_queue = asyncio.Queue(maxsize=10000)

    for device_cfg in cfg.devices:
        sensors = build_sensors(device_cfg)
        scheduler = build_failure_scheduler(device_cfg.failures, now_ms, cfg.simulation.random_failures)

        if mode == "stdout":
            publisher = StdoutPublisher()
        elif mode == "file":
            # Each device writes to its own NDJSON for easy ingestion and replay.
            out_path = str(Path(file_output).with_name(f"{device_cfg.device_id}.ndjson"))
            publisher = FilePublisher(out_path)
        elif mode == "mqtt":
            publisher = MQTTPublisher(
                tenant=device_cfg.tenant,
                site=device_cfg.site,
                device_id=device_cfg.device_id,
                host=cfg.mqtt.host,
                port=cfg.mqtt.port,
                use_tls=cfg.mqtt.use_tls,
                sqlite_path=f"offline_buffer_{device_cfg.device_id}.db",
            )
        elif mode == "queue":
            if shared_queue is None:
                raise RuntimeError("Queue was not initialized")
            publisher = QueuePublisher(shared_queue)
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        devices.append(
            VirtualDevice(
                device_id=device_cfg.device_id,
                site=device_cfg.site,
                tenant=device_cfg.tenant,
                sensors=sensors,
                publisher=publisher,
                failure_scheduler=scheduler,
                simulation_speed=cfg.simulation.speed_multiplier,
                aggregate_window_s=cfg.simulation.aggregate_window_s,
            )
        )
    return devices


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Industrial IoT sensor simulator")
    parser.add_argument("--mode", choices=["mqtt", "stdout", "file"], default="stdout")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output-file", default="telemetry.ndjson")
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    if args.mode == "mqtt":
        for key in ["MQTT_HOST", "MQTT_PORT", "MQTT_USER", "MQTT_PASS"]:
            if key not in os.environ:
                logger.warning("%s is not set; MQTT mode may fail depending on broker config.", key)

    devices = await make_devices(cfg, args.mode, args.output_file)
    logger.info("Starting %d virtual devices in %s mode", len(devices), args.mode)
    await run_devices(devices)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
