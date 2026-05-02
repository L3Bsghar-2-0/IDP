"""asyncpg connection pool wrapper."""
from __future__ import annotations

import asyncio
import logging

import asyncpg

logger = logging.getLogger(__name__)


class Database:
    """Lazy asyncpg pool with connect/close + execute helpers."""

    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 10) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self, retries: int = 30, delay: float = 2.0) -> None:
        """Create the pool, retrying while TimescaleDB is still booting."""
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                self._pool = await asyncpg.create_pool(
                    dsn=self._dsn,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    command_timeout=30.0,
                )
                logger.info("db_pool_created", extra={"attempt": attempt})
                return
            except (OSError, asyncpg.PostgresError) as exc:
                last_err = exc
                logger.warning(
                    "db_connect_retry",
                    extra={"attempt": attempt, "err": str(exc)},
                )
                await asyncio.sleep(delay)
        raise RuntimeError(f"could not connect to database after {retries} attempts: {last_err}")

    async def close(self) -> None:
        """Close the pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("database pool not initialised")
        return self._pool

    # Convenience wrappers ---------------------------------------------------

    async def execute(self, query: str, *args: object) -> str:
        return await self.pool.execute(query, *args)

    async def fetch(self, query: str, *args: object) -> list[asyncpg.Record]:
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: object):
        return await self.pool.fetchval(query, *args)
