import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from mado import db
from mado.migrations import MIGRATIONS


def test_migrate_brings_a_new_database_to_the_latest_version(tmp_path: Path):
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        assert db.migrate(conn) == len(MIGRATIONS)
        assert db.schema_version(conn) == len(MIGRATIONS)


def test_migrate_is_safe_to_run_again(tmp_path: Path):
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        db.migrate(conn)
        assert db.migrate(conn) == len(MIGRATIONS)


def test_a_database_from_a_newer_mado_is_left_alone(tmp_path: Path):
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")

        with pytest.raises(db.NewerDatabaseError):
            db.migrate(conn)

        assert db.schema_version(conn) == len(MIGRATIONS) + 1


def test_a_failing_migration_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    broken = "CREATE TABLE half_done (id INTEGER); THIS IS NOT SQL;"
    monkeypatch.setattr(db, "MIGRATIONS", (*MIGRATIONS, broken))

    with closing(db.connect(tmp_path / "mado.db")) as conn:
        with pytest.raises(sqlite3.OperationalError):
            db.migrate(conn)

        assert db.schema_version(conn) == len(MIGRATIONS)
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert "settings" in tables
        assert "half_done" not in tables


def test_records_from_before_the_library_gain_it_and_keep_their_settings(tmp_path: Path):
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        conn.executescript(f"BEGIN;\n{MIGRATIONS[0]}\nPRAGMA user_version = 1;\nCOMMIT;")
        conn.execute("INSERT INTO settings VALUES ('set_up', 'true')")
        conn.commit()

        db.migrate(conn)

        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert {"folders", "pictures", "scans"} <= tables
        assert conn.execute("SELECT value FROM settings").fetchone()["value"] == "true"


def test_records_from_mado_0_1_gain_looks_and_keep_their_history(tmp_path: Path):
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        for number, sql in enumerate(MIGRATIONS[:3], start=1):
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        conn.execute(
            "INSERT INTO history (at, kind, name, made_for) VALUES (?, 'made', ?, ?)",
            ("2026-11-22T14:02:00+02:00", "Harbour at dusk.heic", "TV 8K"),
        )
        conn.commit()

        assert db.migrate(conn) == len(MIGRATIONS)

        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert "looks" in tables
        line = conn.execute("SELECT made_for, look FROM history").fetchone()
        assert (line["made_for"], line["look"]) == ("TV 8K", None)


def test_records_from_mado_0_2_gain_batches_and_keep_their_jobs_in_line(tmp_path: Path):
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        for number, sql in enumerate(MIGRATIONS[:4], start=1):
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        for source in ("Pier.jpg", "Sail.jpg"):
            conn.execute(
                """INSERT INTO jobs (kind, source, recipe, state, queued_at)
                   VALUES ('make', ?, '{}', 'queued', '2026-11-22T14:02:00+02:00')""",
                (source,),
            )
        conn.commit()

        assert db.migrate(conn) == len(MIGRATIONS)

        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert {"batches", "recipes", "watch_folders", "watched"} <= tables
        jobs = conn.execute("SELECT id, position, batch_id FROM jobs ORDER BY id").fetchall()
        assert [(job["position"], job["batch_id"]) for job in jobs] == [(1, None), (2, None)]


def test_records_from_mado_0_3_keep_every_line_of_history_and_learn_to_set_pictures_aside(
    tmp_path: Path,
):
    pier, aside = r"D:\Pier.jpg", r"D:\Mado quarantine\2026-11-22\Pier.jpg"
    replaced = (
        "2026-11-22T14:02:00+02:00", "replaced", 1, "Pier.jpg", "TV 8K", pier, pier, aside,
        "2026-11-22T14:02:00+02:00", "2026-12-22T03:00:00+02:00", "days", None, None,
        "Warm film at 60%",
    )  # fmt: skip
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        for number, sql in enumerate(MIGRATIONS[:5], start=1):
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        conn.execute(
            """INSERT INTO jobs (kind, source, recipe, state, queued_at)
               VALUES ('make', ?, '{}', 'done', '2026-11-22T14:02:00+02:00')""",
            (pier,),
        )
        conn.execute(
            """INSERT INTO history (at, kind, job_id, name, made_for, original, result, aside,
                                    aside_at, cleared_at, cleared_by, undone_at, bytes, look)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            replaced,
        )
        conn.execute(
            "INSERT INTO history (at, kind, name, bytes) VALUES (?, 'emptied', 'D:', 1400)",
            ("2026-11-22T15:00:00+02:00",),
        )
        conn.commit()

        assert db.migrate(conn) == len(MIGRATIONS)

        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert {"prints", "choices", "not_same", "reviews"} <= tables
        lines = conn.execute("SELECT * FROM history ORDER BY id").fetchall()
        columns = (
            "at", "kind", "job_id", "name", "made_for", "original", "result", "aside", "aside_at",
            "cleared_at", "cleared_by", "undone_at", "bytes", "look",
        )  # fmt: skip
        assert tuple(lines[0][column] for column in columns) == replaced
        assert (lines[0]["kept"], lines[0]["review_id"]) == (None, None)
        assert (lines[1]["kind"], lines[1]["name"], lines[1]["bytes"]) == ("emptied", "D:", 1400)
        conn.execute(
            "INSERT INTO history (at, kind, name, original, kept) VALUES (?, 'aside', ?, ?, ?)",
            ("2026-11-23T10:00:00+02:00", "Pier (2).jpg", r"D:\Pier (2).jpg", pier),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO history (at, kind, name) VALUES ('x', 'deleted', 'x')")
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert {"history_by_time", "history_by_review"} <= names
        conn.execute(
            """INSERT INTO folders (path, added_at) VALUES ('D:\\', '2026-11-22T09:00:00');"""
        )
        conn.execute(
            """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at,
                                     seen_at, taken_at, taken_from)
               VALUES (1, ?, '', 'Pier.jpg', 10, 1, 'x', 'x', 'x', 'file')""",
            (pier,),
        )
        assert conn.execute("SELECT damaged FROM pictures").fetchone()["damaged"] == 0
