"""Export: everything Mado knows, in one zip you can open without Mado."""

import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from mado import __version__, db
from mado.config import DataPaths


def export_data(paths: DataPaths, folder: Path, now: datetime | None = None) -> Path | None:
    """Write `Mado export <date>.zip` into `folder` and return its path: the database, its
    settings as JSON and a manifest saying which Mado wrote it.

    Returns None when Mado has no data yet. Never overwrites a file: a second
    export on the same day becomes `Mado export <date> (2).zip`.
    """
    if not paths.database.exists():
        return None
    now = now or datetime.now().astimezone()
    folder.mkdir(parents=True, exist_ok=True)
    target = _unused_name(folder / f"Mado export {now:%Y-%m-%d}.zip")

    with tempfile.TemporaryDirectory() as scratch:
        snapshot = Path(scratch) / "mado.db"
        with (
            closing(db.connect(paths.database)) as source,
            closing(sqlite3.connect(snapshot)) as copy,
        ):
            source.backup(copy)
            copy.execute("PRAGMA journal_mode = DELETE")  # one self-contained file
            settings = _settings(source)
            schema_version = db.schema_version(source)

        manifest = {
            "app": "Mado",
            "version": __version__,
            "exportedAt": now.isoformat(timespec="seconds"),
            "schemaVersion": schema_version,
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "mado.db")
            archive.writestr("settings.json", json.dumps(settings, indent=2))
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return target


def _settings(conn: sqlite3.Connection) -> dict[str, object]:
    if not _has_table(conn, "settings"):
        return {}
    rows = conn.execute("SELECT key, value FROM settings ORDER BY key")
    return {row["key"]: json.loads(row["value"]) for row in rows}


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"
    return conn.execute(query, (name,)).fetchone() is not None


def _unused_name(path: Path) -> Path:
    candidate, number = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate
