"""Dead-letter queue repository."""
from __future__ import annotations

import logging
from typing import Any

from app.storage.database import Database

logger = logging.getLogger(__name__)


class DlqRepository:
    """Stores messages that failed to parse / validate."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def insert(
        self,
        topic: str,
        error_type: str,
        error_message: str,
        raw_payload: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO dlq (topic, error_type, error_message, raw_payload)
            VALUES ($1, $2, $3, $4)
            """,
            topic,
            error_type,
            error_message,
            raw_payload[:64_000],
        )

    async def latest(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self._db.fetch(
            """
            SELECT id, received_at, topic, error_type, error_message, raw_payload
            FROM dlq
            ORDER BY received_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def count_recent(self, minutes: int) -> tuple[int, str | None]:
        """Return (count, latest error_type) within the window."""
        row = await self._db.fetchrow(
            """
            SELECT COUNT(*) AS n,
                   (SELECT error_type FROM dlq ORDER BY received_at DESC LIMIT 1) AS latest_err
            FROM dlq
            WHERE received_at >= NOW() - ($1 || ' minutes')::INTERVAL
            """,
            str(minutes),
        )
        if not row:
            return 0, None
        return int(row["n"] or 0), row["latest_err"]
