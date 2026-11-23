"""Keeping the library current while Mado is open: catching up as it starts, and watching."""

import json
import shutil
import sqlite3
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    FileClosedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
)
from watchdog.observers import winapi

from mado.config import DataPaths
from mado.library import add_folder, find_pictures, folders
from mado.watch import QUIET, Changes, Watcher, observe
from tests.drawn import draw

NOW = datetime(2026, 11, 22, 9, 14, tzinfo=UTC)


class Scans:
    """A scanner that only counts the scans it's asked for."""

    def __init__(self) -> None:
        self.asked = 0

    def request(self) -> None:
        self.asked += 1


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def scans() -> Scans:
    return Scans()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def watcher(paths: DataPaths, scans: Scans, clock: Clock) -> Iterator[Watcher]:
    found = Watcher(paths, scans, clock=clock)
    yield found
    found.stop()


def set_up(conn: sqlite3.Connection, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    add_folder(conn, folder, now=NOW)
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('set_up', ?)", (json.dumps(True),))


def wait_for(happened: Callable[[], bool]) -> bool:
    """Windows tells the watcher within moments."""
    for _ in range(50):
        if happened():
            return True
        time.sleep(0.1)
    return False


def test_as_mado_starts_a_scan_catches_up(
    watcher: Watcher, scans: Scans, conn: sqlite3.Connection, tmp_path: Path
):
    set_up(conn, tmp_path / "Phone")

    assert watcher.catch_up()
    assert scans.asked == 1


def test_no_catching_up_before_setup_or_without_folders(
    watcher: Watcher, scans: Scans, conn: sqlite3.Connection, tmp_path: Path
):
    assert not watcher.catch_up()  # no setup, no folders
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('set_up', 'true')")
    assert not watcher.catch_up()  # set up, but nothing to look at
    assert scans.asked == 0


def test_a_change_asks_for_a_scan_once_the_folder_is_quiet(
    watcher: Watcher, scans: Scans, clock: Clock, conn: sqlite3.Connection
):
    watcher.notice()

    watcher.tick()
    assert scans.asked == 0  # still settling: a card's pictures may still be copying
    assert watcher.settling

    clock.now += QUIET
    watcher.tick()
    assert scans.asked == 1
    assert not watcher.pending

    watcher.tick()
    assert scans.asked == 1  # once per change


def test_a_change_is_scanned_within_moments_of_the_folder_going_quiet(
    watcher: Watcher, scans: Scans, clock: Clock, conn: sqlite3.Connection, tmp_path: Path
):
    set_up(conn, tmp_path / "Phone")
    watcher.start()  # catches up, then watches
    assert scans.asked == 1

    watcher.notice()
    clock.now += QUIET  # and the folder has been quiet since

    assert wait_for(lambda: scans.asked == 2)  # not a whole look-around later


def test_a_new_picture_in_a_watched_folder_is_noticed(
    watcher: Watcher, scans: Scans, clock: Clock, conn: sqlite3.Connection, tmp_path: Path
):
    folder = tmp_path / "Phone"
    set_up(conn, folder)
    watcher.tick()  # starts watching the folder
    time.sleep(0.5)  # Windows takes a moment to start telling

    draw(folder / "IMG_2041.jpg")
    assert wait_for(lambda: watcher.pending)
    time.sleep(0.5)  # "created" comes with "modified" just after; both count
    clock.now += QUIET
    watcher.tick()

    assert scans.asked == 1


def test_folders_are_watched_from_the_moment_mado_starts(
    watcher: Watcher, conn: sqlite3.Connection, tmp_path: Path
):
    folder = tmp_path / "Phone"
    set_up(conn, folder)

    watcher.start()
    time.sleep(0.5)  # Windows takes a moment to start telling
    draw(folder / "IMG_2041.jpg")  # a phone syncing as Windows starts, say

    assert wait_for(lambda: watcher.pending)  # not at the first look round, 15 seconds on


def test_a_folder_added_while_mado_runs_is_watched_at_once(
    watcher: Watcher, conn: sqlite3.Connection, tmp_path: Path
):
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('set_up', 'true')")
    watcher.start()  # nothing to watch yet
    folder = tmp_path / "Phone"
    folder.mkdir()
    add_folder(conn, folder, now=NOW)

    watcher.follow()  # as the API does when a folder is added
    time.sleep(0.5)  # Windows takes a moment to start telling
    draw(folder / "IMG_2041.jpg")

    assert wait_for(lambda: watcher.pending)  # not at the next look round, 15 seconds on


def test_files_that_arent_pictures_go_unnoticed(
    watcher: Watcher, conn: sqlite3.Connection, tmp_path: Path
):
    folder = tmp_path / "Phone"
    set_up(conn, folder)
    watcher.tick()
    time.sleep(0.5)

    (folder / "notes.txt").write_text("not a picture", encoding="utf-8")
    time.sleep(1)

    assert not watcher.pending


def test_a_folder_of_pictures_moved_out_of_the_library_is_noticed(
    watcher: Watcher, conn: sqlite3.Connection, tmp_path: Path
):
    folder = tmp_path / "Phone"
    draw(folder / "Trip" / "IMG.jpg")
    set_up(conn, folder)
    find_pictures(conn, folders(conn)[0], stamp=NOW.isoformat())
    watcher.tick()
    time.sleep(0.5)

    (folder / "Trip").rename(tmp_path / "Elsewhere")

    assert wait_for(lambda: watcher.pending)


def test_a_folder_that_comes_back_is_watched_again(
    watcher: Watcher, scans: Scans, clock: Clock, conn: sqlite3.Connection, tmp_path: Path
):
    folder = tmp_path / "Phone"
    set_up(conn, folder)
    watcher.tick()
    time.sleep(0.5)
    shutil.rmtree(folder)  # its drive unplugged, say
    time.sleep(0.5)
    watcher.tick()
    folder.mkdir()
    watcher.tick()
    clock.now += QUIET
    watcher.tick()  # a scan for whatever changed while it was away
    assert scans.asked == 1
    time.sleep(0.5)

    draw(folder / "IMG.jpg")

    assert wait_for(lambda: watcher.pending)


def test_a_folder_that_goes_has_its_handle_closed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # watchdog 6 closed a folder's handle itself when the folder went, and again when it was
    # stopped: by then the number could be another file's (the database's), and closing that
    # crashed Kura's engine. watchdog 7 closes it once, in the thread that reads the folder.
    closed: list[object] = []
    close: Callable[[Any], None] = vars(winapi)["_close_directory_handle"]

    def closing(handle: Any) -> None:
        closed.append(handle)
        close(handle)

    monkeypatch.setattr(winapi, "_close_directory_handle", closing)
    folder = tmp_path / "Phone"
    folder.mkdir()
    observer = observe(str(folder), Changes(lambda: None, holds=lambda _path: True))
    time.sleep(0.3)

    shutil.rmtree(folder)  # its drive unplugged, say
    assert wait_for(lambda: bool(closed))
    observer.stop()
    observer.join(timeout=5)

    assert len(closed) == 1


def test_what_counts_as_a_change_to_the_library():
    trip = r"D:\Pictures\Phone\Trip"
    picture = rf"{trip}\IMG_2041.jpg"
    noticed: list[bool] = []
    changes = Changes(lambda: noticed.append(True), holds=lambda path: path in (trip, picture))

    def counts(event: FileSystemEvent) -> bool:
        noticed.clear()
        changes.on_any_event(event)
        return bool(noticed)

    assert counts(FileCreatedEvent(rf"{trip}\IMG_2042.HEIC"))
    assert counts(FileModifiedEvent(picture))  # still copying
    assert counts(FileClosedEvent(picture))
    assert counts(FileMovedEvent(picture, rf"{trip}\Beach.jpg"))
    assert counts(FileCreatedEvent(rf"{trip}\_MG_0042.CR3"))  # RAW is listed too
    assert counts(DirCreatedEvent(r"D:\Pictures\Phone\2026"))  # a folder moved in
    assert counts(FileDeletedEvent(trip))  # how Windows tells of a folder moved out or deleted
    assert counts(FileDeletedEvent(picture))
    assert not counts(DirModifiedEvent(trip))  # something written in it
    assert not counts(FileCreatedEvent(rf"{trip}\notes.txt"))
    assert not counts(FileDeletedEvent(r"D:\Pictures\Phone\Downloads\old.part"))


def test_what_mado_writes_in_its_own_data_folder_is_never_a_change_to_the_library():
    data = Path(r"C:\Users\owner\AppData\Local\Mado")
    noticed: list[bool] = []
    changes = Changes(lambda: noticed.append(True), holds=lambda _path: False, away=data)

    changes.on_any_event(FileCreatedEvent(rf"{data}\cache\pictures\0\7-1-thumbnail.webp"))
    changes.on_any_event(FileCreatedEvent(rf"{data}\pasted\Pasted 2026-11-23 14.05.png"))
    assert noticed == []
    # A picture moved out of it into the library is one.
    changes.on_any_event(
        FileMovedEvent(rf"{data}\pasted\Pasted.png", r"C:\Users\owner\Pictures\Pasted.png")
    )
    changes.on_any_event(FileCreatedEvent(r"C:\Users\owner\Pictures\Mado.png"))
    assert noticed == [True, True]
