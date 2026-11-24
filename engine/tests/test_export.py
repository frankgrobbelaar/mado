"""Export: everything Mado knows, in one zip that opens without Mado."""

import csv
import io
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from mado import __version__, db, history, own_looks, own_styles, recipes, watching
from mado.config import DataPaths
from mado.core.cube import read
from mado.core.grids import blended
from mado.core.looks import mado_look
from mado.core.touches import Touches
from mado.export import export_data
from mado.library import add_folder, find_pictures, folders, save_facts, save_waiting
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
            "duplicates.json",
            "favourites.json",
            "folders.json",
            "history.csv",
            "looks.json",
            "mado.db",
            "manifest.json",
            "pictures.csv",
            "recipes.json",
            "settings.json",
            "styles.json",
            "wallpaper.json",
            "watch-folders.json",
            "words.csv",
        ]
        assert json.loads(zipped.read("looks.json")) == []
        assert json.loads(zipped.read("styles.json")) == []
        assert json.loads(zipped.read("favourites.json")) == []
        studio = json.loads(zipped.read("wallpaper.json"))
        assert (studio["layout"], studio["daily"]["on"], studio["pictures"]) == ("each", False, [])
        assert json.loads(zipped.read("recipes.json")) == []
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
        [raw] = [row["id"] for row in conn.execute("SELECT id FROM pictures WHERE raw = 1")]
        save_waiting(conn, raw, now=NOW)  # Mado's RAW reader is on its way

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
    assert rows[1]["state"] == "camera RAW, waiting for Mado's RAW reader"
    assert [row["hdr"] for row in rows] == ["no", ""]  # a RAW waiting isn't looked at yet


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


def test_historys_columns_line_up_with_their_names(paths: DataPaths, tmp_path: Path):
    _records_with_one_setting(paths)
    with closing(db.connect(paths.database)) as conn:
        line = history.made(
            conn,
            now=NOW,
            job_id=None,
            name="Harbour at dusk.heic",
            made_for=None,
            look="Warm film at 60%",
            original=tmp_path / "Harbour at dusk.heic",
            result=tmp_path / "Harbour at dusk (Warm film).jpg",
            edit="erased a part",
        )
        with conn:
            conn.execute(
                "UPDATE history SET undone_at = ?, cleared_at = ?, cleared_by = 'days'"
                " WHERE id = ?",
                ("2026-11-22T15:00:00+00:00", "2026-12-22T03:00:00+00:00", line),
            )

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        [row] = list(csv.DictReader(io.StringIO(zipped.read("history.csv").decode("utf-8"))))
    assert row["madeFor"] == ""
    assert row["look"] == "Warm film at 60%"
    assert row["edit"] == "erased a part"
    assert row["clearedAt"] == "2026-12-22T03:00:00+00:00"
    assert row["clearedBy"] == "days"
    assert row["undoneAt"] == "2026-11-22T15:00:00+00:00"
    assert None not in row  # no value without its column's name


def test_your_looks_are_in_the_export_as_files_any_app_opens(paths: DataPaths, tmp_path: Path):
    _records_with_one_setting(paths)
    warm = mado_look("warm-film")
    assert warm is not None
    assert warm.grid is not None
    with closing(db.connect(paths.database)) as conn:
        own_looks.kept(conn, "Holiday: warm", warm, 0.6, Touches(grain=20), NOW)

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        listed = json.loads(zipped.read("looks.json"))
        cube = read(zipped.read("looks/Holiday- warm.cube").decode("utf-8"))
    assert listed == [
        {
            "name": "Holiday: warm",
            "kind": "mix",
            "source": "Warm film at 60%, grain 20",
            "touches": {"grain": 20},
            "points": 33,
            "addedAt": NOW.isoformat(timespec="seconds"),
            "file": "looks/Holiday- warm.cube",
        }
    ]
    assert cube.title == "Holiday: warm"
    assert np.allclose(cube.grid, blended(warm.grid, 0.6), atol=1e-4)


def test_your_styles_are_in_the_export_as_their_numbers_and_small_copies(
    paths: DataPaths, tmp_path: Path
):
    _records_with_one_setting(paths)
    code = np.linspace(-1, 1, 512, dtype=np.float32)
    small = b"RIFF\x10\x00\x00\x00WEBPVP8 tiny"
    with closing(db.connect(paths.database)) as conn:
        own_styles.kept(conn, "Lantern: glow", code, small, "Night market.jpg", NOW)

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        listed = json.loads(zipped.read("styles.json"))
        kept_small = zipped.read("styles/Lantern- glow.webp")
    assert listed == [
        {
            "name": "Lantern: glow",
            "source": "Night market.jpg",
            "addedAt": NOW.isoformat(timespec="seconds"),
            "code": listed[0]["code"],
            "thumbnail": "styles/Lantern- glow.webp",
        }
    ]
    assert np.array_equal(np.array(listed[0]["code"], np.float32), code)  # exactly
    assert kept_small == small  # the small copy only: never the picture itself


def test_recipes_and_watch_folders_are_in_the_export(paths: DataPaths, tmp_path: Path):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        kept = recipes.kept(
            conn,
            "Holiday prints",
            [{"step": "size", "size": "tv-8k"}],
            {"how": "new", "format": "JPEG", "quality": 95, "folder": "Edited"},
            NOW,
        )
        watching.added(conn, inbox, kept.id, Path("Done"), NOW)

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        listed = json.loads(zipped.read("recipes.json"))
        watched = json.loads(zipped.read("watch-folders.json"))
    assert listed == [
        {
            "name": "Holiday prints",
            "steps": [{"step": "size", "size": "tv-8k"}],
            "saving": {"how": "new", "format": "JPEG", "quality": 95, "folder": "Edited"},
            "used": 0,
            "usedAt": None,
        }
    ]
    assert watched == [
        {
            "folder": str(inbox),
            "recipe": "Holiday prints",
            "results": str(inbox / "Done"),
            "watching": True,
        }
    ]


def test_what_looking_after_the_library_keeps_is_in_the_export(paths: DataPaths, tmp_path: Path):
    _records_with_one_setting(paths)
    folder = tmp_path / "Phone"
    for name in ("Pier.jpg", "Pier (2).jpg", "Old pier.jpg"):
        draw(folder / name)
    with closing(db.connect(paths.database)) as conn:
        add_folder(conn, folder, now=NOW)
        find_pictures(conn, folders(conn)[0], stamp="2026-11-22T14:00:00")
        ids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM pictures")}
        pair = sorted((ids["Pier.jpg"], ids["Pier (2).jpg"]))
        with conn:
            conn.execute(
                "UPDATE pictures SET read_at = 'x', problem = 'The file is damaged.', damaged = 1"
                " WHERE id = ?",
                (ids["Old pier.jpg"],),
            )
            conn.execute(
                "INSERT INTO not_same (first, second, versions, at) VALUES (?, ?, 'v', 'x')",
                pair,
            )
            conn.execute(
                "INSERT INTO reviews (at, duplicates, bursts) VALUES ('2026-11-22T14:00', 1, 0)"
            )
        history.aside(
            conn,
            now=NOW,
            name="Pier (3).jpg",
            original=folder / "Pier (3).jpg",
            kept=folder / "Pier.jpg",
            aside=tmp_path / "Mado quarantine" / "2026-11-22" / "Pier (3).jpg",
            size=1234,
            review_id=1,
        )

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        rows = list(csv.DictReader(io.StringIO(zipped.read("history.csv").decode("utf-8"))))
        kept = json.loads(zipped.read("duplicates.json"))
        listed = list(csv.DictReader(io.StringIO(zipped.read("pictures.csv").decode("utf-8"))))
    [line] = rows
    assert (line["kind"], line["kept"], line["review"]) == ("aside", str(folder / "Pier.jpg"), "1")
    assert kept["notTheSame"] == [sorted([str(folder / "Pier.jpg"), str(folder / "Pier (2).jpg")])]
    assert kept["reviews"] == [{"at": "2026-11-22T14:00", "duplicates": 1, "bursts": 0}]
    states = {row["path"]: row["state"] for row in listed}
    assert states[str(folder / "Old pier.jpg")] == (
        "won't open, marked as damaged: The file is damaged."
    )
