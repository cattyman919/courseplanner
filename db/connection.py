"""SQLite connection management and idempotent schema setup."""

import sqlite3
from pathlib import Path

from db import seed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "courseplanner.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 1


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with row access by name and foreign keys enforced."""
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> None:
    """Create schema if missing, seed if empty. Idempotent."""
    conn = get_connection(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise RuntimeError(
                f"Database schema version {version} does not match expected "
                f"{SCHEMA_VERSION}. Delete {path or DB_PATH} and restart to recreate it."
            )
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        seed.seed_if_empty(conn)
    finally:
        conn.close()
