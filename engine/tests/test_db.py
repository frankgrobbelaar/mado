import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from mado import db
from mado.migrations import MIGRATIONS


def test_a_file_that_isnt_a_database_is_refused_and_let_go(tmp_path: Path):
    path = tmp_path / "damaged.db"
    path.write_bytes(b"not a database at all, just bytes" * 64)

    with pytest.raises(sqlite3.DatabaseError):
        db.connect(path)

    path.unlink()  # Windows lets go of a file only once nothing has it open


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


def test_records_from_mado_0_5_keep_every_picture_and_what_refers_to_it_and_learn_outside_ones(
    tmp_path: Path,
):
    pier = r"D:\Pictures\Pier.jpg"
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        for number, sql in enumerate(MIGRATIONS[:7], start=1):
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        conn.execute("INSERT INTO folders (path, added_at) VALUES (?, 'x')", (r"D:\Pictures",))
        for name in ("Pier.jpg", "Pier (2).jpg"):
            conn.execute(
                """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at,
                                         seen_at, read_at, format, width, height, taken_at,
                                         taken_from, damaged)
                   VALUES (1, ?, '', ?, 10, 1, 'x', 'x', 'x', 'JPEG', 40, 30, 'x', 'file', 1)""",
                (rf"D:\Pictures\{name}", name),
            )
        conn.execute("INSERT INTO prints (picture_id, size, modified, at) VALUES (1, 10, 1, 'x')")
        conn.execute(
            "INSERT INTO choices (picture_id, keep, size, modified, at) VALUES (2, 1, 10, 1, 'x')"
        )
        conn.execute("INSERT INTO not_same (first, second, versions, at) VALUES (1, 2, '', 'x')")
        conn.execute(
            """INSERT INTO jobs (kind, picture_id, source, recipe, state, queued_at)
               VALUES ('make', 1, ?, '{}', 'done', 'x')""",
            (pier,),
        )
        conn.commit()

        assert db.migrate(conn) == len(MIGRATIONS)

        pictures = conn.execute("SELECT * FROM pictures ORDER BY id").fetchall()
        assert [(row["id"], row["name"], row["damaged"]) for row in pictures] == [
            (1, "Pier.jpg", 1),
            (2, "Pier (2).jpg", 1),
        ]
        assert [(row["opened_at"], row["pasted"]) for row in pictures] == [(None, 0), (None, 0)]
        assert conn.execute("SELECT picture_id FROM prints").fetchone()[0] == 1
        assert conn.execute("SELECT picture_id FROM choices").fetchone()[0] == 2
        assert conn.execute("SELECT first, second FROM not_same").fetchone()[:] == (1, 2)
        assert conn.execute("SELECT picture_id FROM jobs").fetchone()[0] == 1
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert {"pictures_by_taken", "pictures_by_folder"} <= names
        # A picture outside the library has no library folder, and the rules still hold.
        conn.execute(
            """INSERT INTO pictures (path, dir, name, size, modified, found_at, seen_at,
                                     taken_at, taken_from, opened_at)
               VALUES (?, '', 'Sail.png', 10, 1, 'x', 'x', 'x', 'file', 'x')""",
            (r"E:\Elsewhere\Sail.png",),
        )
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO prints (picture_id, size, modified, at) VALUES (9, 1, 1, '')")
        conn.execute("DELETE FROM folders")  # its pictures go with it, and only its
        assert [row["name"] for row in conn.execute("SELECT name FROM pictures")] == ["Sail.png"]
        assert conn.execute("SELECT picture_id FROM jobs").fetchone()[0] is None


def test_records_brought_up_to_date_with_a_change_still_unsaved_keep_what_refers_to_a_picture(
    tmp_path: Path,
):
    # Foreign keys can't be turned off inside a transaction: one left open by whoever asked
    # would have had making the pictures table again empty the tables that refer to it.
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        for number, sql in enumerate(MIGRATIONS[:7], start=1):
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        conn.execute("INSERT INTO folders (path, added_at) VALUES (?, 'x')", (r"D:\Pictures",))
        conn.execute(
            """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at,
                                     seen_at, taken_at, taken_from)
               VALUES (1, ?, '', 'Pier.jpg', 10, 1, 'x', 'x', 'x', 'file')""",
            (r"D:\Pictures\Pier.jpg",),
        )
        conn.execute("INSERT INTO prints (picture_id, size, modified, at) VALUES (1, 10, 1, 'x')")
        conn.execute(
            "INSERT INTO choices (picture_id, keep, size, modified, at) VALUES (1, 1, 10, 1, 'x')"
        )
        assert conn.in_transaction  # nothing saved yet

        assert db.migrate(conn) == len(MIGRATIONS)

        assert conn.execute("SELECT picture_id FROM prints").fetchall()[0][0] == 1
        assert conn.execute("SELECT picture_id FROM choices").fetchall()[0][0] == 1
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_a_migration_that_breaks_a_reference_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    breaking = "DELETE FROM folders;"  # foreign keys are off while it runs: its pictures dangle
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        db.migrate(conn)
        conn.execute("INSERT INTO folders (path, added_at) VALUES (?, 'x')", (r"D:\Pictures",))
        conn.execute(
            """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at,
                                     seen_at, taken_at, taken_from)
               VALUES (1, ?, '', 'Pier.jpg', 10, 1, 'x', 'x', 'x', 'file')""",
            (r"D:\Pictures\Pier.jpg",),
        )
        conn.commit()
        monkeypatch.setattr(db, "MIGRATIONS", (*MIGRATIONS, breaking))

        with pytest.raises(sqlite3.IntegrityError):
            db.migrate(conn)

        assert db.schema_version(conn) == len(MIGRATIONS)
        assert conn.execute("SELECT COUNT(*) FROM folders").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_records_from_mado_0_6_keep_every_picture_and_learn_favourites_and_the_wallpaper_studio(
    tmp_path: Path,
):
    with closing(db.connect(tmp_path / "mado.db")) as conn:
        for number, sql in enumerate(MIGRATIONS[:8], start=1):
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        conn.execute("INSERT INTO folders (path, added_at) VALUES (?, 'x')", (r"D:\Pictures",))
        conn.execute(
            """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at,
                                     seen_at, taken_at, taken_from)
               VALUES (1, ?, '', 'Pier.jpg', 10, 1, 'x', 'x', 'x', 'file')""",
            (r"D:\Pictures\Pier.jpg",),
        )
        conn.commit()

        assert db.migrate(conn) == len(MIGRATIONS)

        assert conn.execute("SELECT name FROM pictures").fetchone()[0] == "Pier.jpg"
        studio = conn.execute("SELECT * FROM studio").fetchall()
        assert [(row["layout"], row["gap"], row["daily"], row["daily_at"]) for row in studio] == [
            ("each", 0, 0, "07:00")
        ]
        conn.execute("INSERT INTO favourites (picture_id, at) VALUES (1, 'x')")
        conn.execute(
            "INSERT INTO studio_pictures (monitor, picture_id, at) VALUES (?, 1, 'x')",
            (r"\?\DISPLAY#MADE0001#1",),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO favourites (picture_id, at) VALUES (9, 'x')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO studio (id) VALUES (2)")  # one row, always
        conn.execute("DELETE FROM folders")  # a picture forgotten takes its heart with it
        assert conn.execute("SELECT COUNT(*) FROM favourites").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM studio_pictures").fetchone()[0] == 0
