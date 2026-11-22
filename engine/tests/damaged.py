"""Mado's records, and damage to them, as the tests of rescuing them need."""

import json
import sqlite3
from contextlib import closing

from mado import db
from mado.config import DataPaths


def records(paths: DataPaths, marker: str) -> None:
    """Mado's records, with one ("marker": "before" or "after", say) that tells one moment's
    from another's."""
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        with conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('marker', ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (json.dumps(marker),),
            )


def marker_of(paths: DataPaths) -> str:
    with closing(db.connect(paths.database)) as conn:
        return json.loads(
            conn.execute("SELECT value FROM settings WHERE key = 'marker'").fetchone()[0]
        )


def scribble(paths: DataPaths) -> bytes:
    """mado.db's header scribbled over (a disk fault): SQLite can't tell it's a database."""
    with closing(sqlite3.connect(paths.database)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    damaged = b"\x00" * 100 + paths.database.read_bytes()[100:]
    paths.database.write_bytes(damaged)
    return damaged
