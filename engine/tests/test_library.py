"""The library's folders and the pictures found in them, as the database keeps them."""

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mado.library import (
    FolderError,
    add_folder,
    file_time,
    find_pictures,
    folders,
    record,
    remove_folder,
    save_facts,
    save_problem,
    save_waiting,
    unread,
)
from mado.pictures import Facts
from tests.drawn import draw

NOW = datetime(2026, 11, 22, 9, 14, tzinfo=UTC)
STAMP = NOW.isoformat()
LATER = datetime(2026, 11, 22, 10, 0, tzinfo=UTC).isoformat()


def rows(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {row["name"]: row for row in conn.execute("SELECT * FROM pictures")}


def test_a_folder_joins_the_library_by_its_full_path(conn: sqlite3.Connection, tmp_path: Path):
    phone = tmp_path / "Pictures" / "Phone"
    phone.mkdir(parents=True)

    added = add_folder(conn, phone, now=NOW)

    assert added.path == phone
    assert [folder.path for folder in folders(conn)] == [phone]
    assert added.walked_at is None  # no scan has looked through it yet


def test_a_folder_that_isnt_there_is_refused(conn: sqlite3.Connection, tmp_path: Path):
    with pytest.raises(FolderError, match="isn't there"):
        add_folder(conn, tmp_path / "Unplugged", now=NOW)


def test_a_folder_already_in_the_library_or_inside_one_is_refused(
    conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    (phone / "2026").mkdir(parents=True)
    add_folder(conn, phone, now=NOW)

    with pytest.raises(FolderError, match="already in your library"):
        add_folder(conn, phone, now=NOW)
    with pytest.raises(FolderError, match="as part of"):
        add_folder(conn, phone / "2026", now=NOW)


def test_a_folder_holding_library_folders_takes_them_and_their_pictures_in(
    conn: sqlite3.Connection, tmp_path: Path
):
    draw(tmp_path / "Pictures" / "Phone" / "2026" / "IMG_2041.jpg")
    phone = add_folder(conn, tmp_path / "Pictures" / "Phone", now=NOW)
    find_pictures(conn, phone, stamp=STAMP)

    pictures = add_folder(conn, tmp_path / "Pictures", now=NOW)

    assert [folder.path for folder in folders(conn)] == [tmp_path / "Pictures"]
    [row] = rows(conn).values()
    assert (row["folder_id"], row["dir"]) == (pictures.id, "Phone/2026")


def test_forgetting_a_folder_forgets_its_pictures_but_leaves_the_files(
    conn: sqlite3.Connection, tmp_path: Path
):
    picture = draw(tmp_path / "Phone" / "IMG_2041.jpg")
    folder = add_folder(conn, tmp_path / "Phone", now=NOW)
    find_pictures(conn, folder, stamp=STAMP)
    [row] = rows(conn).values()

    assert remove_folder(conn, folder.id) == [row["id"]]
    assert folders(conn) == []
    assert rows(conn) == {}
    assert picture.is_file()
    assert remove_folder(conn, folder.id) is None  # not in the library any more


def test_a_walk_records_every_picture_with_its_size_folder_and_time(
    conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    modified = datetime(2026, 11, 12, 18, 42, 7)
    draw(phone / "IMG_2041.JPG", modified=modified)
    draw(phone / "2026" / "Trip" / "beach.png")
    (phone / "2026" / "_MG_0042.CR3").write_bytes(b"raw")
    (phone / "notes.txt").write_text("not a picture", encoding="utf-8")
    draw(phone / "$RECYCLE.BIN" / "deleted.jpg")
    draw(phone / ".thumbnails" / "small.jpg")
    draw(phone / "._IMG_2041.JPG", format="JPEG")
    folder = add_folder(conn, phone, now=NOW)

    found = find_pictures(conn, folder, stamp=STAMP)

    assert found is not None
    assert (found.pictures, found.added, found.changed, found.gone) == (3, 3, (), 0)
    found_rows = rows(conn)
    assert set(found_rows) == {"IMG_2041.JPG", "beach.png", "_MG_0042.CR3"}
    jpeg = found_rows["IMG_2041.JPG"]
    assert (jpeg["dir"], jpeg["size"]) == ("", (phone / "IMG_2041.JPG").stat().st_size)
    assert jpeg["taken_at"] == "2026-11-12T18:42:07"  # the file's time, till Mado reads it
    assert (jpeg["taken_from"], jpeg["read_at"]) == ("file", None)
    assert found_rows["beach.png"]["dir"] == "2026/Trip"
    raw = found_rows["_MG_0042.CR3"]
    assert (raw["raw"], raw["format"], raw["read_at"]) == (1, "CR3", None)  # read as any is
    assert folders(conn)[0].walked_at == STAMP


def test_a_later_walk_notices_new_changed_and_gone_pictures(
    conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    kept = draw(phone / "kept.jpg")
    changed = draw(phone / "changed.jpg", size=(40, 30))
    gone = draw(phone / "gone.jpg")
    folder = add_folder(conn, phone, now=NOW)
    find_pictures(conn, folder, stamp=STAMP)
    first = rows(conn)
    with conn:
        conn.execute("UPDATE pictures SET read_at = ?", (STAMP,))

    draw(changed, size=(80, 60))
    os.utime(changed, (kept.stat().st_mtime + 60, kept.stat().st_mtime + 60))
    gone.unlink()
    draw(phone / "new.jpg")
    found = find_pictures(conn, folder, stamp=LATER)

    assert found is not None
    assert (found.pictures, found.added, found.gone) == (3, 1, 1)
    assert found.changed == (first["changed.jpg"]["id"],)
    now = rows(conn)
    assert now["gone.jpg"]["gone_at"] == LATER
    assert now["changed.jpg"]["read_at"] is None  # read again
    assert now["kept.jpg"]["read_at"] == STAMP
    assert now["new.jpg"]["found_at"] == LATER


def test_a_picture_there_but_not_seen_by_the_walk_isnt_marked_gone(
    conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "kept.jpg")
    folder = add_folder(conn, phone, now=NOW)
    find_pictures(conn, folder, stamp=STAMP)

    def copied_in_and_opened(_path: Path) -> None:
        """A picture copied into the folder the walk has listed already, and opened meanwhile:
        recorded as a scan would (mado/outside.py), but not seen by this walk."""
        fresh = phone / "fresh.jpg"
        if fresh.exists():
            return
        draw(fresh)
        stat = fresh.stat()
        with conn:
            record(conn, folder.id, fresh, "", "picture", stat.st_size, stat.st_mtime_ns, LATER)

    found = find_pictures(conn, folder, stamp=LATER + "x", on_file=copied_in_and_opened)

    assert found is not None
    assert rows(conn)["fresh.jpg"]["gone_at"] is None


def test_a_picture_back_again_counts_as_found_anew(conn: sqlite3.Connection, tmp_path: Path):
    phone = tmp_path / "Phone"
    picture = draw(phone / "IMG.jpg")
    folder = add_folder(conn, phone, now=NOW)
    find_pictures(conn, folder, stamp=STAMP)
    saved = picture.read_bytes()
    picture.unlink()
    find_pictures(conn, folder, stamp=LATER)

    picture.write_bytes(saved)
    os.utime(picture, (0, 0))
    again = find_pictures(conn, folder, stamp="2026-11-22T11:00:00+00:00")

    assert again is not None
    assert again.added == 1
    assert rows(conn)["IMG.jpg"]["gone_at"] is None


def test_a_folder_that_isnt_there_marks_nothing_gone(conn: sqlite3.Connection, tmp_path: Path):
    phone = tmp_path / "Phone"
    draw(phone / "IMG.jpg")
    folder = add_folder(conn, phone, now=NOW)
    find_pictures(conn, folder, stamp=STAMP)
    phone.rename(tmp_path / "Unplugged")  # its drive unplugged, say

    assert find_pictures(conn, folder, stamp=LATER) is None
    assert rows(conn)["IMG.jpg"]["gone_at"] is None


def test_pictures_still_to_read_come_newest_file_first(conn: sqlite3.Connection, tmp_path: Path):
    phone = tmp_path / "Phone"
    draw(phone / "older.jpg", modified=datetime(2025, 6, 1, 12, 0))
    draw(phone / "newer.heic", format="PNG", modified=datetime(2026, 11, 1, 12, 0))
    draw(phone / "raw.nef", format="PNG", modified=datetime(2026, 11, 2, 12, 0))
    folder = add_folder(conn, phone, now=NOW)
    find_pictures(conn, folder, stamp=STAMP)

    waiting = unread(conn)

    assert [(each.path.name, each.kind) for each in waiting] == [
        ("raw.nef", "raw"),
        ("newer.heic", "heif"),
        ("older.jpg", "picture"),
    ]


def test_a_camera_raw_listed_while_its_reader_came_is_read_once_its_there(
    conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "_MG_0042.CR3", format="PNG")
    folder = add_folder(conn, phone, now=NOW)
    find_pictures(conn, folder, stamp=STAMP)
    [raw] = unread(conn)

    save_waiting(conn, raw.id, now=NOW)

    assert rows(conn)["_MG_0042.CR3"]["read_at"] is not None  # listed, as it is
    assert unread(conn, raws=False) == []  # nothing to read while the reader is away
    assert [each.id for each in unread(conn)] == [raw.id]  # read once it's there


def test_what_reading_found_is_kept_and_a_camera_clock_wins_over_the_files(
    conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "IMG.jpg", modified=datetime(2026, 11, 20, 8, 0))
    draw(phone / "Screenshot.png", modified=datetime(2026, 11, 21, 8, 0))
    folder = add_folder(conn, phone, now=NOW)
    find_pictures(conn, folder, stamp=STAMP)
    ids = {name: row["id"] for name, row in rows(conn).items()}

    taken = datetime(2026, 11, 12, 18, 42, 7)
    save_facts(
        conn, ids["IMG.jpg"], Facts("JPEG", 48, 64, 6, taken, "Pixelworks PW-7", True), now=NOW
    )
    save_facts(conn, ids["Screenshot.png"], Facts("PNG", 80, 60, None, None, None, False), now=NOW)

    found = rows(conn)
    jpeg, png = found["IMG.jpg"], found["Screenshot.png"]
    assert (jpeg["taken_at"], jpeg["taken_from"]) == ("2026-11-12T18:42:07", "camera")
    assert (jpeg["width"], jpeg["height"], jpeg["orientation"], jpeg["located"]) == (48, 64, 6, 1)
    assert jpeg["camera"] == "Pixelworks PW-7"
    assert (png["taken_at"], png["taken_from"]) == ("2026-11-21T08:00:00", "file")
    assert png["read_at"] == STAMP


def test_a_picture_that_wont_open_keeps_why(conn: sqlite3.Connection, tmp_path: Path):
    draw(tmp_path / "Phone" / "Old pier.tif")
    folder = add_folder(conn, tmp_path / "Phone", now=NOW)
    find_pictures(conn, folder, stamp=STAMP)
    [row] = rows(conn).values()

    save_problem(conn, row["id"], "The file is damaged or was only half copied.", now=NOW)

    [row] = rows(conn).values()
    assert row["problem"] == "The file is damaged or was only half copied."
    assert (row["read_at"], row["format"]) == (STAMP, "TIF")
    assert unread(conn) == []


def test_a_files_time_is_written_in_local_time_to_the_second():
    moment = datetime(2026, 11, 12, 18, 42, 7)

    assert file_time(int(moment.timestamp() * 1e9)) == "2026-11-12T18:42:07"
