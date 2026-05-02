from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import random
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import aiosqlite
import numpy as np
import paho.mqtt.client as mqtt

from .base import BaseSensor, FailureScheduler

logger = logging.getLogger(__name__)


class Publisher(Protocol):
    async def start(self) -> None:
        ...

    async def publish(self, sensor_id: str, payload: Dict[str, Any]) -> None:
        ...

    async def stop(self) -> None:
        ...


class StdoutPublisher:
    async def start(self) -> None:
        return None

    async def publish(self, sensor_id: str, payload: Dict[str, Any]) -> None:
        _ = sensor_id
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=True))

    async def stop(self) -> None:
        return None


class QueuePublisher:
    def __init__(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        self.queue = queue

    async def start(self) -> None:
        return None

    async def publish(self, sensor_id: str, payload: Dict[str, Any]) -> None:
        _ = sensor_id
        await self.queue.put(payload)

    async def stop(self) -> None:
        return None


class FilePublisher:
    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self._fh: Optional[Any] = None

    async def start(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.file_path.open("a", encoding="utf-8")

    async def publish(self, sensor_id: str, payload: Dict[str, Any]) -> None:
        _ = sensor_id
        if self._fh is None:
            raise RuntimeError("FilePublisher is not started")
        self._fh.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n")
        self._fh.flush()

    async def stop(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class MQTTPublisher:
    """MQTT publisher with QoS1, TLS, LWT, reconnect backoff, and SQLite offline buffer."""

    def __init__(
        self,
        tenant: str,
        site: str,
        device_id: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        use_tls: bool = True,
        sqlite_path: str = "offline_buffer.db",
        client_id: Optional[str] = None,
    ) -> None:
        self.tenant = tenant
        self.site = site
        self.device_id = device_id

        self.host = host or os.getenv("MQTT_HOST", "localhost")
        self.port = int(port or int(os.getenv("MQTT_PORT", "8883")))
        self.user = os.getenv("MQTT_USER", "")
        self.password = os.getenv("MQTT_PASS", "")
        self.use_tls = use_tls

        self.sqlite_path = sqlite_path
        self.client = mqtt.Client(client_id=client_id or f"sim-{device_id}-{int(time.time())}")
        self.connected = False
        self._running = False
        self._db_lock = asyncio.Lock()
        self._reconnect_task: Optional[asyncio.Task[None]] = None
        self._drain_task: Optional[asyncio.Task[None]] = None
        self._backoff_s = 1.0

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _status_topic(self) -> str:
        return f"tenants/{self.tenant}/sites/{self.site}/devices/{self.device_id}/status"

    def _telemetry_topic(self, sensor_id: str) -> str:
        return (
            f"tenants/{self.tenant}/sites/{self.site}/devices/{self.device_id}/"
            f"sensors/{sensor_id}/telemetry"
        )

    async def _init_db(self) -> None:
        async with aiosqlite.connect(self.sqlite_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS mqtt_buffer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    qos INTEGER NOT NULL,
                    created_ts INTEGER NOT NULL
                )
                """
            )
            await db.commit()

    async def start(self) -> None:
        await self._init_db()
        self._running = True

        self.client.will_set(self._status_topic(), payload="offline", qos=1, retain=True)
        if self.user:
            self.client.username_pw_set(self.user, self.password)

        if self.use_tls:
            context = ssl.create_default_context()
            self.client.tls_set_context(context)

        await self._try_connect()
        self.client.loop_start()
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        self._drain_task = asyncio.create_task(self._drain_loop())

    async def _try_connect(self) -> None:
        try:
            self.client.connect(self.host, self.port, keepalive=30)
        except Exception as exc:  # pragma: no cover - runtime network path
            logger.warning("MQTT initial connect failed for %s: %s", self.device_id, exc)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: int) -> None:
        _ = userdata, flags
        if rc == 0:
            self.connected = True
            self._backoff_s = 1.0
            client.publish(self._status_topic(), payload="online", qos=1, retain=True)
        else:
            self.connected = False

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        _ = client, userdata, rc
        self.connected = False

    async def _reconnect_loop(self) -> None:
        while self._running:
            if not self.connected:
                try:
                    self.client.reconnect()
                except Exception:
                    jitter = random.uniform(0, 0.25 * self._backoff_s)
                    await asyncio.sleep(self._backoff_s + jitter)
                    self._backoff_s = min(self._backoff_s * 2.0, 60.0)
                    continue
            await asyncio.sleep(1.0)

    async def _insert_buffer(self, topic: str, payload: str, qos: int = 1) -> None:
        async with self._db_lock:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute(
                    "INSERT INTO mqtt_buffer(topic, payload, qos, created_ts) VALUES(?, ?, ?, ?)",
                    (topic, payload, qos, int(time.time() * 1000)),
                )
                # Keep only the newest 10k messages and drop oldest overflow.
                await db.execute(
                    """
                    DELETE FROM mqtt_buffer
                    WHERE id IN (
                        SELECT id FROM mqtt_buffer
                        ORDER BY id ASC
                        LIMIT MAX((SELECT COUNT(*) FROM mqtt_buffer) - 10000, 0)
                    )
                    """
                )
                await db.commit()

    async def _drain_loop(self) -> None:
        while self._running:
            if not self.connected:
                await asyncio.sleep(1.0)
                continue
            await self._drain_once(limit=200)
            await asyncio.sleep(0.5)

    async def _drain_once(self, limit: int = 100) -> None:
        async with self._db_lock:
            async with aiosqlite.connect(self.sqlite_path) as db:
                cursor = await db.execute(
                    "SELECT id, topic, payload, qos FROM mqtt_buffer ORDER BY id ASC LIMIT ?", (limit,)
                )
                rows = await cursor.fetchall()
                if not rows:
                    return
                delivered_ids: List[int] = []
                for row_id, topic, payload, qos in rows:
                    msg_info = self.client.publish(topic, payload=payload, qos=qos, retain=False)
                    if msg_info.rc == mqtt.MQTT_ERR_SUCCESS:
                        delivered_ids.append(int(row_id))
                    else:
                        break
                if delivered_ids:
                    placeholders = ",".join("?" for _ in delivered_ids)
                    await db.execute(f"DELETE FROM mqtt_buffer WHERE id IN ({placeholders})", delivered_ids)
                    await db.commit()

    async def publish(self, sensor_id: str, payload: Dict[str, Any]) -> None:
        topic = self._telemetry_topic(sensor_id)
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)

        if self.connected:
            info = self.client.publish(topic, payload=encoded, qos=1, retain=False)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                return

        await self._insert_buffer(topic, encoded, qos=1)

    async def stop(self) -> None:
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
        if self._drain_task:
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain_task
        if self.connected:
            self.client.publish(self._status_topic(), payload="offline", qos=1, retain=True)
        self.client.loop_stop()
        self.client.disconnect()


@dataclass
class VirtualDevice:
    device_id: str
    site: str
    tenant: str
    sensors: List[BaseSensor]
    publisher: Publisher
    failure_scheduler: Optional[FailureScheduler] = None
    simulation_speed: float = 1.0
    aggregate_window_s: float = 1.0

    def __post_init__(self) -> None:
        self._running = False
        self._tasks: List[asyncio.Task[None]] = []
        self._sensor_map: Dict[str, BaseSensor] = {s.sensor_id: s for s in self.sensors}
        self._hf_buffers: Dict[str, List[Dict[str, Any]]] = {
            s.sensor_id: [] for s in self.sensors if s.sample_rate_hz > 10.0
        }
        self._hf_last_flush: Dict[str, float] = {k: time.monotonic() for k in self._hf_buffers}

    async def start(self) -> None:
        self._running = True
        await self.publisher.start()

        for sensor in self.sensors:
            self._tasks.append(asyncio.create_task(self._sensor_loop(sensor)))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.publisher.stop()

    def _aggregate_values(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        first = readings[0]["value"]
        if isinstance(first, dict):
            out: Dict[str, Any] = {}
            for key in first:
                vals = np.array([float(r["value"][key]) for r in readings], dtype=float)
                out[key] = {
                    "min": float(np.min(vals)),
                    "max": float(np.max(vals)),
                    "mean": float(np.mean(vals)),
                    "std": float(np.std(vals)),
                    "count": int(vals.size),
                }
            return out

        vals = np.array([float(r["value"]) for r in readings], dtype=float)
        return {
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals)),
            "count": int(vals.size),
        }

    async def _sensor_loop(self, sensor: BaseSensor) -> None:
        interval_s = 1.0 / sensor.sample_rate_hz
        speed = max(0.01, self.simulation_speed)

        while self._running:
            now_ms = BaseSensor.now_ms()
            if self.failure_scheduler:
                self.failure_scheduler.tick(self._sensor_map, now_ms)

            reading = sensor.read()
            if reading is not None:
                if sensor.sample_rate_hz > 10.0:
                    buf = self._hf_buffers[sensor.sensor_id]
                    buf.append(reading)
                    now_mono = time.monotonic()
                    if (now_mono - self._hf_last_flush[sensor.sensor_id]) >= self.aggregate_window_s:
                        agg = self._aggregate_values(buf)
                        out = {
                            "v": reading["v"],
                            "device_id": reading["device_id"],
                            "sensor_id": reading["sensor_id"],
                            "sensor_type": reading["sensor_type"],
                            "ts": reading["ts"],
                            "seq": reading["seq"],
                            "value": agg,
                            "unit": reading["unit"],
                            "quality": reading["quality"],
                            "meta": {"aggregated": True, "window_s": self.aggregate_window_s},
                        }
                        await self.publisher.publish(sensor.sensor_id, out)
                        buf.clear()
                        self._hf_last_flush[sensor.sensor_id] = now_mono
                else:
                    await self.publisher.publish(sensor.sensor_id, reading)

            await asyncio.sleep(interval_s / speed)


async def run_devices(devices: List[VirtualDevice]) -> None:
    await asyncio.gather(*(d.start() for d in devices))
    try:
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Stopping devices")
    finally:
        await asyncio.gather(*(d.stop() for d in devices))
