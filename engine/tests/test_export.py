"""Export: everything Mado knows, in one zip that opens without Mado."""

import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from mado import __version__, db
from mado.config import DataPaths
from mado.export import export_data
from mado.migrations import MIGRATIONS

NOW = datetime(2026, 11, 22, 14, 20, tzinfo=UTC)


def _records_with_one_setting(paths: DataPaths) -> None:
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        with conn:
            conn.execute("INSERT INTO settings VALUES ('set_up', ?)", [json.dumps(True)])


def test_export_writes_one_zip_with_the_database_settings_and_manifest(
    paths: DataPaths, tmp_path: Path
):
    _records_with_one_setting(paths)

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    expected = tmp_path / "exports" / "Mado export 2026-11-22.zip"
    assert archive == expected
    with zipfile.ZipFile(expected) as zipped:
        assert sorted(zipped.namelist()) == ["mado.db", "manifest.json", "settings.json"]
        assert json.loads(zipped.read("settings.json")) == {"set_up": True}
        assert json.loads(zipped.read("manifest.json")) == {
            "app": "Mado",
            "version": __version__,
            "exportedAt": "2026-11-22T14:20:00+00:00",
            "schemaVersion": len(MIGRATIONS),
        }


def test_the_exported_database_opens_on_its_own(paths: DataPaths, tmp_path: Path):
    _records_with_one_setting(paths)
    archive = export_data(paths, tmp_path / "exports", now=NOW)
    assert archive is not None

    with zipfile.ZipFile(archive) as zipped:
        zipped.extract("mado.db", tmp_path / "unzipped")
    with closing(sqlite3.connect(tmp_path / "unzipped" / "mado.db")) as conn:
        assert conn.execute("SELECT key FROM settings").fetchall() == [("set_up",)]


def test_a_second_export_on_the_same_day_keeps_both(paths: DataPaths, tmp_path: Path):
    _records_with_one_setting(paths)

    first = export_data(paths, tmp_path, now=NOW)
    second = export_data(paths, tmp_path, now=NOW)

    assert first == tmp_path / "Mado export 2026-11-22.zip"
    assert second == tmp_path / "Mado export 2026-11-22 (2).zip"


def test_there_is_nothing_to_export_before_mado_has_data(paths: DataPaths, tmp_path: Path):
    assert export_data(paths, tmp_path, now=NOW) is None
    assert list(tmp_path.iterdir()) == []
