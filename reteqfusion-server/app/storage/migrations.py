"""Run the SQL migration files on startup.

Each statement is sent in its own simple-query, so TimescaleDB extension
quirks (e.g. continuous aggregates needing a separate transaction) work.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from app.storage.database import Database

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "sql"


_STATEMENT_SPLITTER = re.compile(r";\s*(?:\n|$)")


def _split_statements(sql: str) -> list[str]:
    """Naive splitter: comments stripped, then on `;`."""
    cleaned_lines: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    parts = [p.strip() for p in _STATEMENT_SPLITTER.split(cleaned)]
    return [p for p in parts if p]


async def run_migrations(db: Database) -> None:
    """Apply all .sql files in numerical order, idempotently."""
    if not MIGRATIONS_DIR.exists():
        logger.warning("migrations_dir_missing", extra={"path": str(MIGRATIONS_DIR)})
        return

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    logger.info("migrations_starting", extra={"count": len(files)})

    for sql_file in files:
        statements = _split_statements(sql_file.read_text(encoding="utf-8"))
        logger.info(
            "migration_applying",
            extra={"file": sql_file.name, "statements": len(statements)},
        )
        for stmt in statements:
            try:
                await db.execute(stmt)
            except Exception as exc:  # noqa: BLE001
                # Continuous aggregate / retention policies are idempotent in spirit
                # but Timescale sometimes raises when re-applied; log & continue.
                logger.warning(
                    "migration_statement_failed",
                    extra={
                        "file": sql_file.name,
                        "err": str(exc),
                        "stmt_preview": stmt[:120],
                    },
                )
    logger.info("migrations_done")
