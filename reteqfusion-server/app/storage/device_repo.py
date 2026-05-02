"""Device status repository: upsert online/offline + last-seen."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.storage.database import Database

logger = logging.getLogger(__name__)


class DeviceRepository:
    """Stores per-device current status."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert_status(
        self,
        device_id: str,
        status: str,
        ts: datetime,
        ip: str | None,
        rssi: int | None,
        fw_version: str | None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO device_status (device_id, last_seen, status, ip, rssi, fw_version)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (device_id) DO UPDATE SET
                last_seen  = EXCLUDED.last_seen,
                status     = EXCLUDED.status,
                ip         = COALESCE(EXCLUDED.ip,         device_status.ip),
                rssi       = COALESCE(EXCLUDED.rssi,       device_status.rssi),
                fw_version = COALESCE(EXCLUDED.fw_version, device_status.fw_version)
            """,
            device_id,
            ts,
            status,
            ip,
            rssi,
            fw_version,
        )

    async def touch_last_seen(
        self,
        device_id: str,
        ts: datetime,
        fw_version: str | None = None,
    ) -> None:
        """Mark device online by virtue of receiving a message from it."""
        await self._db.execute(
            """
            INSERT INTO device_status (device_id, last_seen, status, fw_version)
            VALUES ($1, $2, 'online', $3)
            ON CONFLICT (device_id) DO UPDATE SET
                last_seen  = EXCLUDED.last_seen,
                status     = 'online',
                fw_version = COALESCE(EXCLUDED.fw_version, device_status.fw_version)
            """,
            device_id,
            ts,
            fw_version,
        )

    async def list_all(self) -> list[dict[str, Any]]:
        rows = await self._db.fetch(
            """
            SELECT device_id, last_seen, status, ip, rssi, fw_version
            FROM device_status
            ORDER BY device_id
            """
        )
        return [dict(r) for r in rows]

    async def get(self, device_id: str) -> dict[str, Any] | None:
        row = await self._db.fetchrow(
            """
            SELECT device_id, last_seen, status, ip, rssi, fw_version
            FROM device_status
            WHERE device_id = $1
            """,
            device_id,
        )
        return dict(row) if row else None

    async def stale_devices(self, threshold_minutes: int) -> list[dict[str, Any]]:
        """Return devices whose last_seen is older than threshold and still marked online."""
        rows = await self._db.fetch(
            """
            SELECT device_id, last_seen, status
            FROM device_status
            WHERE status = 'online'
              AND last_seen < NOW() - ($1 || ' minutes')::INTERVAL
            """,
            str(threshold_minutes),
        )
        return [dict(r) for r in rows]
