"""Periodic background task: device-offline, sustained gas, DLQ + anomaly bursts."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.config import Settings

if TYPE_CHECKING:
    from app.mqtt.client import MqttClient
    from app.storage.database import Database

logger = logging.getLogger(__name__)

OFFLINE_THRESHOLD_MINUTES = 5
ALERTING_INTERVAL_SECONDS = 60


class AlertingService:
    """Cyclic alerting checks against the database."""

    def __init__(
        self,
        *,
        database: "Database",
        mqtt_client: "MqttClient",
        settings: Settings,
    ) -> None:
        self._db = database
        self._mqtt = mqtt_client
        self._settings = settings
        # Track which devices have already been notified offline this cycle
        self._notified_offline: set[str] = set()

    async def run_forever(self) -> None:
        """Main loop. Each iteration is wrapped so a single failure doesn't kill it."""
        logger.info("alerting_service_started")
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("alerting_tick_failed")
            try:
                await asyncio.sleep(ALERTING_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise

    async def _tick(self) -> None:
        await self._check_offline_devices()
        await self._check_high_temperature()
        await self._check_sustained_gas()
        await self._check_dlq_growth()
        await self._check_anomaly_burst()

    # ----------------------------------------------- 1. device offline check

    async def _check_offline_devices(self) -> None:
        rows = await self._db.fetch(
            """
            SELECT device_id, last_seen, status
            FROM device_status
            WHERE last_seen < NOW() - ($1 || ' minutes')::INTERVAL
              AND status = 'online'
            """,
            str(OFFLINE_THRESHOLD_MINUTES),
        )
        currently_stale = {row["device_id"] for row in rows}

        for row in rows:
            device_id = row["device_id"]
            if device_id in self._notified_offline:
                continue
            topic = f"tenants/{self._settings.alert_tenant}/sites/{self._settings.alert_site}/alerts/{device_id}"
            payload = {
                "type": "DEVICE_OFFLINE",
                "device_id": device_id,
                "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
            }
            self._mqtt.publish(topic, payload, qos=1, retain=False)
            await self._db.execute(
                "UPDATE device_status SET status = 'offline' WHERE device_id = $1",
                device_id,
            )
            logger.warning("device_offline", extra=payload)
            self._notified_offline.add(device_id)

        # Forget devices that are no longer stale (so we'll re-notify if they go offline again)
        self._notified_offline &= currently_stale

    # ---------------------------------------- 2. DHT22 high temperature alert

    async def _check_high_temperature(self) -> None:
        rows = await self._db.fetch(
            """
            SELECT DISTINCT ON (device_id, sensor_id)
                device_id, sensor_id, time, value
            FROM telemetry
            WHERE sensor_type = 'dht22' AND reading_key = 'temperature'
              AND quality = 'good' AND time >= NOW() - INTERVAL '2 minutes'
            ORDER BY device_id, sensor_id, time DESC
            """
        )
        for row in rows:
            if row["value"] is None:
                continue
            if row["value"] > 60.0:
                topic = (
                    f"tenants/{self._settings.alert_tenant}/sites/{self._settings.alert_site}"
                    f"/alerts/{row['device_id']}/temperature"
                )
                payload = {
                    "type": "HIGH_TEMP",
                    "device_id": row["device_id"],
                    "sensor_id": row["sensor_id"],
                    "value": float(row["value"]),
                    "unit": "C",
                    "ts": row["time"].isoformat(),
                }
                self._mqtt.publish(topic, payload, qos=1, retain=False)
                logger.warning("high_temp_alert", extra=payload)

    # ---------------------------------------- 3. MQ-2 sustained gas average

    async def _check_sustained_gas(self) -> None:
        rows = await self._db.fetch(
            """
            SELECT device_id, sensor_id, AVG(value) AS avg_ppm
            FROM telemetry
            WHERE sensor_type = 'mq2' AND reading_key = 'gas_ppm'
              AND quality = 'good' AND time >= NOW() - INTERVAL '5 minutes'
            GROUP BY device_id, sensor_id
            HAVING AVG(value) > $1
            """,
            float(self._settings.mq2_smoke_alarm_ppm),
        )
        for row in rows:
            topic = (
                f"tenants/{self._settings.alert_tenant}/sites/{self._settings.alert_site}"
                f"/alerts/{row['device_id']}/gas_alarm"
            )
            payload = {
                "type": "SUSTAINED_GAS",
                "device_id": row["device_id"],
                "sensor_id": row["sensor_id"],
                "avg_ppm": float(row["avg_ppm"]),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            self._mqtt.publish(topic, payload, qos=1, retain=False)
            logger.critical("sustained_gas_alert", extra=payload)

    # ----------------------------------------------------- 4. DLQ growth

    async def _check_dlq_growth(self) -> None:
        row = await self._db.fetchrow(
            """
            SELECT COUNT(*) AS n,
                   (SELECT error_type FROM dlq ORDER BY received_at DESC LIMIT 1) AS latest_err
            FROM dlq
            WHERE received_at >= NOW() - INTERVAL '5 minutes'
            """
        )
        if row and (row["n"] or 0) > 0:
            logger.warning(
                "dlq_growth",
                extra={"count_5m": int(row["n"]), "latest_err": row["latest_err"]},
            )

    # ----------------------------------------------------- 5. anomaly burst

    async def _check_anomaly_burst(self) -> None:
        rows = await self._db.fetch(
            """
            SELECT anomaly_type, COUNT(*) AS n
            FROM anomalies
            WHERE time >= NOW() - INTERVAL '5 minutes'
            GROUP BY anomaly_type
            """
        )
        total = sum(int(r["n"]) for r in rows)
        if total > 10:
            breakdown = {r["anomaly_type"]: int(r["n"]) for r in rows}
            logger.critical(
                "anomaly_burst",
                extra={"total_5m": total, "breakdown": breakdown},
            )
