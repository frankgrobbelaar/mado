"""The scan: finding every picture in the library's folders, reading each, saying how it goes."""

import errno
import itertools
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mado.config import DataPaths
from mado.core.files import Kind
from mado.library import add_folder, find_pictures
from mado.pictures import Facts, read_facts
from mado.previews import Previews
from mado.scan import Scanner
from tests.drawn import draw, exif
from tests.heif_files import exif_item, heif

NOW = datetime(2026, 11, 22, 9, 14, tzinfo=UTC)


@pytest.fixture
def scanner(paths: DataPaths, conn: sqlite3.Connection) -> Scanner:
    return Scanner(paths, Previews(paths, ffmpeg=lambda: None), now=lambda: NOW)


def scanned(scanner: Scanner) -> None:
    scanner.start()
    scanner.wait(timeout=30)


def pictures(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {row["name"]: row for row in conn.execute("SELECT * FROM pictures")}


def test_before_any_scan_there_is_nothing_to_say(scanner: Scanner):
    status = scanner.status()

    assert (status.state, status.stage, status.found, status.read) == ("idle", None, 0, 0)


def test_a_scan_finds_and_reads_every_picture_and_makes_its_thumbnail(
    scanner: Scanner, conn: sqlite3.Connection, paths: DataPaths, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "IMG_2041.JPG", described=exif(taken="2026:11:12 18:42:07", make="Pixelworks"))
    draw(phone / "2026" / "beach.png")
    add_folder(conn, phone, now=NOW)

    scanned(scanner)

    status = scanner.status()
    assert (status.state, status.stage) == ("done", "done")
    assert (status.found, status.to_read, status.read) == (2, 2, 2)
    assert (status.added, status.gone, status.problem) == (2, 0, None)
    jpeg = pictures(conn)["IMG_2041.JPG"]
    assert (jpeg["taken_at"], jpeg["taken_from"], jpeg["camera"]) == (
        "2026-11-12T18:42:07",
        "camera",
        "Pixelworks",
    )
    assert len(list(paths.cache.rglob("*-thumbnail.webp"))) == 2


def test_a_picture_that_wont_open_is_listed_with_why_and_the_rest_carry_on(
    scanner: Scanner, conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    whole = draw(phone / "good.jpg", size=(400, 300))
    (phone / "Old pier.jpg").write_bytes(whole.read_bytes()[:900])
    (phone / "notes.jpg").write_text("not a picture", encoding="utf-8")
    add_folder(conn, phone, now=NOW)

    scanned(scanner)

    found = pictures(conn)
    assert found["good.jpg"]["problem"] is None
    assert "half copied" in found["Old pier.jpg"]["problem"]
    assert "not a picture" in found["notes.jpg"]["problem"]
    assert scanner.status().state == "done"


def test_a_full_data_drive_leaves_pictures_readable_their_thumbnails_made_later(
    scanner: Scanner, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draw(tmp_path / "Phone" / "IMG.jpg")
    add_folder(conn, tmp_path / "Phone", now=NOW)

    def full(*_: object, **__: object) -> None:
        raise OSError(errno.ENOSPC, "There is not enough space on the disk")

    monkeypatch.setattr("mado.previews.save_copy", full)
    scanned(scanner)

    row = pictures(conn)["IMG.jpg"]
    assert row["problem"] is None
    assert row["read_at"] is not None
    assert scanner.status().state == "done"


def test_pictures_in_a_folder_that_isnt_there_dont_count_as_still_to_read(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    away, here = tmp_path / "Camera", tmp_path / "Phone"
    draw(away / "a.jpg")
    draw(away / "b.jpg")
    draw(here / "c.jpg")
    for folder in (away, here):
        find_pictures(conn, add_folder(conn, folder, now=NOW), stamp=NOW.isoformat())
    away.rename(tmp_path / "Unplugged")  # found, then its drive went before it was read
    reading, go_on = threading.Event(), threading.Event()

    def slow(path: Path, kind: Kind) -> Facts:
        reading.set()
        go_on.wait(timeout=10)
        return read_facts(path, kind)

    scanner = Scanner(paths, Previews(paths, ffmpeg=lambda: None), now=lambda: NOW, read=slow)
    scanner.request()
    assert reading.wait(timeout=10)
    status = scanner.status()
    go_on.set()
    scanner.wait(timeout=30)

    assert (status.read, status.to_read) == (0, 1)


def test_a_picture_gone_before_it_was_read_counts_as_gone_in_that_scan(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "newer.jpg", modified=datetime(2026, 11, 2, 12, 0))
    older = draw(phone / "older.jpg", modified=datetime(2026, 11, 1, 12, 0))
    add_folder(conn, phone, now=NOW)
    times = (NOW + timedelta(seconds=second) for second in itertools.count())

    def deleting(path: Path, kind: Kind) -> Facts:
        if path.name == "newer.jpg":  # read first, being newer: the other goes meanwhile
            older.unlink()
        return read_facts(path, kind)

    previews = Previews(paths, ffmpeg=lambda: None)
    scanner = Scanner(paths, previews, now=lambda: next(times), read=deleting)
    scanned(scanner)

    assert scanner.status().gone == 1


def test_camera_raw_is_listed_without_being_read(
    scanner: Scanner, conn: sqlite3.Connection, paths: DataPaths, tmp_path: Path
):
    (tmp_path / "Camera").mkdir()
    (tmp_path / "Camera" / "_MG_0042.CR3").write_bytes(b"raw")
    add_folder(conn, tmp_path / "Camera", now=NOW)

    scanned(scanner)

    raw = pictures(conn)["_MG_0042.CR3"]
    assert (raw["raw"], raw["problem"], raw["format"]) == (1, None, "CR3")
    assert scanner.status().to_read == 0
    assert list(paths.cache.rglob("*.webp")) == []


def test_a_heic_is_read_without_ffmpeg_and_its_thumbnail_waits_for_it(
    scanner: Scanner, conn: sqlite3.Connection, paths: DataPaths, tmp_path: Path
):
    phone = tmp_path / "Phone"
    phone.mkdir()
    item = exif_item(exif(taken="2026:11:12 18:42:07"))
    (phone / "IMG_2041.HEIC").write_bytes(heif(width=4032, height=3024, exif=item))
    add_folder(conn, phone, now=NOW)

    scanned(scanner)

    heic = pictures(conn)["IMG_2041.HEIC"]
    assert (heic["format"], heic["width"], heic["problem"]) == ("HEIC", 4032, None)
    assert heic["taken_at"] == "2026-11-12T18:42:07"
    assert list(paths.cache.rglob("*.webp")) == []  # made once ffmpeg is there


def test_a_later_scan_reads_only_whats_new_or_changed_and_says_what_came_and_went(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "kept.jpg")
    gone = draw(phone / "gone.jpg")
    add_folder(conn, phone, now=NOW)
    first = Scanner(paths, Previews(paths, ffmpeg=lambda: None), now=lambda: NOW)
    scanned(first)
    read: list[str] = []

    def counting(path: Path, kind: Kind) -> Facts:
        read.append(path.name)
        return read_facts(path, kind)

    gone.unlink()
    draw(phone / "new.jpg")
    later = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)
    second = Scanner(paths, Previews(paths, ffmpeg=lambda: None), now=lambda: later, read=counting)
    scanned(second)

    status = second.status()
    assert read == ["new.jpg"]
    assert (status.found, status.to_read, status.added, status.gone) == (2, 1, 1, 1)


def test_a_scan_asked_for_while_one_runs_follows_it(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "first.jpg")
    add_folder(conn, phone, now=NOW)
    reading = threading.Event()
    go_on = threading.Event()
    starts: list[int] = []

    def slow(path: Path, kind: Kind) -> Facts:
        reading.set()
        go_on.wait(timeout=10)
        return read_facts(path, kind)

    scanner = Scanner(paths, Previews(paths, ffmpeg=lambda: None), now=lambda: NOW, read=slow)
    scanner.request()
    assert reading.wait(timeout=10)
    starts.append(conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0])
    draw(phone / "second.jpg")
    scanner.request()  # while the first reads

    go_on.set()
    scanner.wait(timeout=30)
    scanner.wait(timeout=30)  # and the one after it

    assert starts == [1]
    assert conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0] == 2
    assert set(pictures(conn)) == {"first.jpg", "second.jpg"}
    assert all(row["read_at"] for row in pictures(conn).values())


def test_a_folder_whose_drive_isnt_connected_waits_and_says_so(
    scanner: Scanner, conn: sqlite3.Connection, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "IMG.jpg")
    add_folder(conn, phone, now=NOW)
    scanned(scanner)
    phone.rename(tmp_path / "Unplugged")

    scanned(scanner)

    status = scanner.status()
    assert status.unavailable == (str(phone),)
    assert status.gone == 0
    assert pictures(conn)["IMG.jpg"]["gone_at"] is None


def test_a_scan_that_stopped_with_mado_says_so_rather_than_running(
    scanner: Scanner, conn: sqlite3.Connection
):
    with conn:
        conn.execute(
            "INSERT INTO scans (started_at, state, stage) VALUES (?, 'running', 'reading')",
            (NOW.isoformat(),),
        )

    assert scanner.status().state == "stopped"
