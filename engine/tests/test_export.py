"""Export: everything Mado knows, in one zip that opens without Mado."""

import csv
import io
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from mado import __version__, db, history
from mado.config import DataPaths
from mado.export import export_data
from mado.library import add_folder, find_pictures, save_facts
from mado.migrations import MIGRATIONS
from mado.pictures import read_facts
from tests.drawn import draw, exif

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
        assert sorted(zipped.namelist()) == [
            "folders.json",
            "history.csv",
            "mado.db",
            "manifest.json",
            "pictures.csv",
            "settings.json",
        ]
        assert json.loads(zipped.read("settings.json")) == {"set_up": True}
        assert json.loads(zipped.read("manifest.json")) == {
            "app": "Mado",
            "version": __version__,
            "exportedAt": "2026-11-22T14:20:00+00:00",
            "schemaVersion": len(MIGRATIONS),
        }


def test_the_library_is_in_the_export_readable_without_mado(paths: DataPaths, tmp_path: Path):
    phone = tmp_path / "Phone"
    draw(phone / "2026" / "IMG_2041.jpg", described=exif(taken="2026:11:12 18:42:07", where=True))
    (phone / "_MG_0042.CR3").write_bytes(b"raw")
    _records_with_one_setting(paths)
    with closing(db.connect(paths.database)) as conn:
        folder = add_folder(conn, phone, now=NOW)
        find_pictures(conn, folder, stamp=NOW.isoformat())
        [jpeg] = [row["id"] for row in conn.execute("SELECT id FROM pictures WHERE raw = 0")]
        save_facts(conn, jpeg, read_facts(phone / "2026" / "IMG_2041.jpg", "picture"), now=NOW)

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        assert json.loads(zipped.read("folders.json")) == [
            {"path": str(phone), "addedAt": NOW.isoformat()}
        ]
        rows = list(csv.DictReader(io.StringIO(zipped.read("pictures.csv").decode("utf-8"))))
    assert [(row["path"], row["format"], row["takenAt"], row["located"]) for row in rows] == [
        (str(phone / "2026" / "IMG_2041.jpg"), "JPEG", "2026-11-12T18:42:07", "yes"),
        (str(phone / "_MG_0042.CR3"), "CR3", rows[1]["takenAt"], "no"),
    ]
    assert rows[1]["state"] == "camera RAW, not read yet"


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


def test_history_is_in_the_export_readable_without_mado(paths: DataPaths, tmp_path: Path):
    _records_with_one_setting(paths)
    with closing(db.connect(paths.database)) as conn:
        history.made(
            conn,
            now=NOW,
            job_id=None,
            name="Harbour at dusk.heic",
            made_for="TV 8K",
            original=tmp_path / "Harbour at dusk.heic",
            result=tmp_path / "Harbour at dusk (TV 8K).jpg",
        )

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        rows = list(csv.DictReader(io.StringIO(zipped.read("history.csv").decode("utf-8"))))
    assert [(row["kind"], row["name"], row["madeFor"]) for row in rows] == [
        ("made", "Harbour at dusk.heic", "TV 8K")
    ]
