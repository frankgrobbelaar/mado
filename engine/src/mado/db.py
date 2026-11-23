"""Mado's database: one SQLite file, upgraded in place by numbered migrations."""

import sqlite3
from pathlib import Path

from mado.migrations import MIGRATIONS


class NewerDatabaseError(Exception):
    """The database was written by a newer Mado than this one."""


def connect(path: Path) -> sqlite3.Connection:
    """Open the database the way Mado always uses it.

    WAL lets readers work while a write is in progress, and foreign keys are on.
    The connection may be handed between threads, but never used by two at once.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    return version


def migrate(conn: sqlite3.Connection) -> int:
    """Bring the schema up to date and return its version.

    Each migration runs once, in order, inside its own transaction, so a failure
    leaves the database exactly as it was before that migration.

    Foreign keys are off while they run: SQLite changes a column by making its table again,
    and dropping the old table would otherwise empty the tables that refer to it. Before each
    one commits, nothing may refer to a row that isn't there any more, unless it did before.
    """
    current = schema_version(conn)
    if current > len(MIGRATIONS):
        raise NewerDatabaseError(
            f"This database is at version {current}, but this Mado only knows up to "
            f"{len(MIGRATIONS)}. Update Mado to open it."
        )
    if current == len(MIGRATIONS):
        return current
    if conn.in_transaction:  # turning foreign keys off does nothing inside one
        conn.commit()  # what was asked before is kept, as executescript would have
    conn.execute("PRAGMA foreign_keys = OFF")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise sqlite3.OperationalError(
            "Mado couldn't turn foreign keys off to bring its records up to date, so it left "
            "them as they were."
        )
    try:
        for number, sql in enumerate(MIGRATIONS[current:], start=current + 1):
            before = _dangling(conn)
            try:
                conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};")
                broken = _dangling(conn) - before
                if broken:
                    raise sqlite3.IntegrityError(
                        f"Migration {number} left {len(broken)} rows referring to rows that "
                        "aren't there, so it was taken back."
                    )
                conn.commit()
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.rollback()
                raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    return schema_version(conn)


def _dangling(conn: sqlite3.Connection) -> set[tuple[object, ...]]:
    """The rows referring to a row that isn't there: each one's table, row and what it refers
    to."""
    return {tuple(row) for row in conn.execute("PRAGMA foreign_key_check")}
