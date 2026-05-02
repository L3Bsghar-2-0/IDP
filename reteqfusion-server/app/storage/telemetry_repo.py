"""Telemetry insert + query repository."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.storage.database import Database

logger = logging.getLogger(__name__)


_INSERT_SQL = """
INSERT INTO telemetry (
    time, tenant, site, device_id, sensor_id, sensor_type, reading_key,
    value, unit, quality, seq, fw_version,
    heat_index, absolute_humidity, dew_point, comfort_index,
    hazard_level, raw_json
) VALUES (
    $1, $2, $3, $4, $5, $6, $7,
    $8, $9, $10, $11, $12,
    $13, $14, $15, $16,
    $17, $18::jsonb
)
"""


_INSERT_ANOMALY_SQL = """
INSERT INTO anomalies (
    time, device_id, sensor_id, sensor_type, anomaly_type,
    confidence, description, reading_value
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""


_INSERT_GAS_ALERT_SQL = """
INSERT INTO gas_alerts (time, device_id, sensor_id, level, gas_ppm)
VALUES ($1, $2, $3, $4, $5)
"""


_INSERT_DIAGNOSTIC_SQL = """
INSERT INTO diagnostics (
    time, device_id, uptime_s, free_heap, wifi_rssi, mqtt_reconnects, dlq_buffered
) VALUES ($1, $2, $3, $4, $5, $6, $7)
"""


class TelemetryRepository:
    """All inserts and reads against telemetry-related hypertables."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------- inserts

    async def insert_reading(
        self,
        *,
        ts: datetime,
        tenant: str,
        site: str,
        device_id: str,
        sensor_id: str,
        sensor_type: str,
        reading_key: str,
        value: float,
        unit: str,
        quality: str,
        seq: int,
        fw_version: str,
        heat_index: float | None,
        absolute_humidity: float | None,
        dew_point: float | None,
        comfort_index: str | None,
        hazard_level: str | None,
        raw_json: dict[str, Any],
    ) -> None:
        """Insert a single reading_key row."""
        await self._db.execute(
            _INSERT_SQL,
            ts,
            tenant,
            site,
            device_id,
            sensor_id,
            sensor_type,
            reading_key,
            value,
            unit,
            quality,
            seq,
            fw_version,
            heat_index,
            absolute_humidity,
            dew_point,
            comfort_index,
            hazard_level,
            json.dumps(raw_json, default=str),
        )

    async def insert_anomaly(
        self,
        *,
        ts: datetime,
        device_id: str,
        sensor_id: str,
        sensor_type: str,
        anomaly_type: str,
        confidence: float,
        description: str,
        reading_value: float,
    ) -> None:
        await self._db.execute(
            _INSERT_ANOMALY_SQL,
            ts,
            device_id,
            sensor_id,
            sensor_type,
            anomaly_type,
            confidence,
            description,
            reading_value,
        )

    async def insert_gas_alert(
        self,
        *,
        ts: datetime,
        device_id: str,
        sensor_id: str,
        level: str,
        gas_ppm: float,
    ) -> None:
        await self._db.execute(
            _INSERT_GAS_ALERT_SQL,
            ts,
            device_id,
            sensor_id,
            level,
            gas_ppm,
        )

    async def insert_diagnostic(
        self,
        *,
        ts: datetime,
        device_id: str,
        uptime_s: int,
        free_heap: int,
        wifi_rssi: int,
        mqtt_reconnects: int,
        dlq_buffered: int,
    ) -> None:
        await self._db.execute(
            _INSERT_DIAGNOSTIC_SQL,
            ts,
            device_id,
            uptime_s,
            free_heap,
            wifi_rssi,
            mqtt_reconnects,
            dlq_buffered,
        )

    # ------------------------------------------------------------- queries

    async def latest_for_sensor(
        self, device_id: str, sensor_id: str
    ) -> list[dict[str, Any]]:
        """Return the most recent reading for each reading_key of a sensor."""
        rows = await self._db.fetch(
            """
            SELECT DISTINCT ON (reading_key)
                time, reading_key, value, unit, quality, sensor_type,
                heat_index, absolute_humidity, dew_point, comfort_index, hazard_level
            FROM telemetry
            WHERE device_id = $1 AND sensor_id = $2
            ORDER BY reading_key, time DESC
            """,
            device_id,
            sensor_id,
        )
        return [dict(r) for r in rows]

    async def history_raw(
        self,
        device_id: str,
        sensor_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        rows = await self._db.fetch(
            """
            SELECT time, reading_key, value, unit, quality
            FROM telemetry
            WHERE device_id = $1 AND sensor_id = $2 AND time >= $3 AND time <= $4
            ORDER BY time ASC
            """,
            device_id,
            sensor_id,
            start,
            end,
        )
        return [dict(r) for r in rows]

    async def history_aggregate(
        self,
        device_id: str,
        sensor_id: str,
        start: datetime,
        end: datetime,
        view: str,
    ) -> list[dict[str, Any]]:
        """Read from telemetry_1min / telemetry_1hour."""
        if view not in {"telemetry_1min", "telemetry_1hour"}:
            raise ValueError(f"invalid aggregate view: {view!r}")
        rows = await self._db.fetch(
            f"""
            SELECT bucket AS time, reading_key,
                   avg_value, min_value, max_value, sample_count
            FROM {view}
            WHERE device_id = $1 AND sensor_id = $2 AND bucket >= $3 AND bucket <= $4
            ORDER BY bucket ASC
            """,
            device_id,
            sensor_id,
            start,
            end,
        )
        return [dict(r) for r in rows]

    async def list_devices(self) -> list[dict[str, Any]]:
        """Return distinct devices with their sensor types and last-seen timestamp."""
        rows = await self._db.fetch(
            """
            SELECT device_id,
                   array_agg(DISTINCT sensor_type) AS sensor_types,
                   MAX(time) AS last_seen
            FROM telemetry
            GROUP BY device_id
            ORDER BY device_id
            """
        )
        return [dict(r) for r in rows]

    async def list_sensors_for_device(self, device_id: str) -> list[dict[str, Any]]:
        rows = await self._db.fetch(
            """
            SELECT sensor_id, sensor_type, MAX(time) AS last_seen
            FROM telemetry
            WHERE device_id = $1
            GROUP BY sensor_id, sensor_type
            ORDER BY sensor_id
            """,
            device_id,
        )
        return [dict(r) for r in rows]

    async def latest_anomalies(
        self,
        device_id: str | None,
        sensor_type: str | None,
        anomaly_type: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[object] = []
        if device_id:
            args.append(device_id)
            clauses.append(f"device_id = ${len(args)}")
        if sensor_type:
            args.append(sensor_type)
            clauses.append(f"sensor_type = ${len(args)}")
        if anomaly_type:
            args.append(anomaly_type)
            clauses.append(f"anomaly_type = ${len(args)}")
        if start:
            args.append(start)
            clauses.append(f"time >= ${len(args)}")
        if end:
            args.append(end)
            clauses.append(f"time <= ${len(args)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(limit)
        rows = await self._db.fetch(
            f"""
            SELECT time, device_id, sensor_id, sensor_type, anomaly_type,
                   confidence, description, reading_value
            FROM anomalies
            {where}
            ORDER BY time DESC
            LIMIT ${len(args)}
            """,
            *args,
        )
        return [dict(r) for r in rows]

    async def latest_gas_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self._db.fetch(
            """
            SELECT time, device_id, sensor_id, level, gas_ppm
            FROM gas_alerts
            ORDER BY time DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def stats(self, smoke_threshold_ppm: int) -> dict[str, Any]:
        row = await self._db.fetchrow(
            """
            WITH today AS (
              SELECT date_trunc('day', NOW()) AS d_start
            ),
            msg AS (
              SELECT COUNT(*) AS n FROM telemetry, today
              WHERE telemetry.time >= today.d_start
            ),
            an AS (
              SELECT COUNT(*) AS n FROM anomalies, today
              WHERE anomalies.time >= today.d_start
            ),
            gas AS (
              SELECT COUNT(*) AS n FROM gas_alerts, today
              WHERE gas_alerts.time >= today.d_start
            ),
            dlq_today AS (
              SELECT COUNT(*) AS n FROM dlq, today
              WHERE dlq.received_at >= today.d_start
            ),
            online AS (
              SELECT COUNT(*) AS n FROM device_status
              WHERE status = 'online' AND last_seen >= NOW() - INTERVAL '5 minutes'
            ),
            avg_t AS (
              SELECT AVG(value) AS v FROM telemetry
              WHERE sensor_type = 'dht22' AND reading_key = 'temperature'
                AND quality = 'good' AND time >= NOW() - INTERVAL '1 hour'
            ),
            avg_h AS (
              SELECT AVG(value) AS v FROM telemetry
              WHERE sensor_type = 'dht22' AND reading_key = 'humidity'
                AND quality = 'good' AND time >= NOW() - INTERVAL '1 hour'
            ),
            avg_g AS (
              SELECT AVG(value) AS v_avg, MAX(value) AS v_max FROM telemetry
              WHERE sensor_type = 'mq2' AND reading_key = 'gas_ppm'
                AND quality = 'good' AND time >= NOW() - INTERVAL '1 hour'
            )
            SELECT
              (SELECT n FROM msg)        AS total_messages_today,
              (SELECT n FROM an)         AS anomaly_count_today,
              (SELECT n FROM gas)        AS gas_alerts_today,
              (SELECT n FROM online)     AS devices_online,
              (SELECT n FROM dlq_today)  AS dlq_count_today,
              (SELECT v FROM avg_t)      AS avg_temperature_1h,
              (SELECT v FROM avg_h)      AS avg_humidity_1h,
              (SELECT v_avg FROM avg_g)  AS avg_gas_ppm_1h,
              (SELECT v_max FROM avg_g)  AS max_gas_ppm_1h
            """
        )
        result = dict(row) if row else {}
        result["smoke_threshold_ppm"] = smoke_threshold_ppm
        return result
