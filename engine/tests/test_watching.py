"""Watch folders: only new pictures that have finished copying are taken, never their own results
nor anything Mado wrote, and what arrived while Mado was closed is taken as it opens."""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

if sys.platform == "win32":
    import _winapi

from mado import history, recipes, watching
from mado.batches import BatchError, Picture
from mado.config import DataPaths
from mado.libraw import Reader
from mado.watching import QUIET, Watch, WatchError, WatchFolders
from tests.dng_files import dng
from tests.drawn import draw, scene

NOW = datetime(2026, 11, 22, 14, 2).astimezone()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Taken:
    def __init__(self) -> None:
        self.pictures: list[tuple[int, list[str]]] = []

    def __call__(self, _conn: sqlite3.Connection, watch: Watch, found: list[Picture]) -> None:
        self.pictures.append((watch.id, sorted(each.name for each in found)))


@pytest.fixture
def recipe(conn: sqlite3.Connection) -> int:
    return recipes.kept(
        conn, "Holiday prints", [{"step": "size", "size": "tv-8k"}], {"how": "new"}, NOW
    ).id


def _folders(paths: DataPaths, taken: Taken, clock: Clock) -> WatchFolders:
    return WatchFolders(paths, taken, now=lambda: NOW, clock=clock)


def test_what_was_there_before_is_left_alone_and_new_pictures_are_taken_once_quiet(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    draw(inbox / "Before.jpg")
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    taken, clock = Taken(), Clock()
    folders = _folders(paths, taken, clock)

    draw(inbox / "New.jpg")
    assert folders.look() == 0  # just arrived: it may still be copying
    clock.now += QUIET / 2
    assert folders.look() == 0
    clock.now += QUIET
    assert folders.look() == 1
    assert taken.pictures == [(1, ["New.jpg"])]

    clock.now += QUIET * 3
    assert folders.look() == 0  # taken once


def test_a_picture_still_growing_waits_till_its_size_stays_the_same(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "Phone dump"
    inbox.mkdir()
    watching.added(conn, inbox, recipe, inbox / "Done", NOW)
    taken, clock = Taken(), Clock()
    folders = _folders(paths, taken, clock)
    copying = inbox / "Copying.png"

    copying.write_bytes(b"x" * 10)
    folders.look()
    clock.now += QUIET * 2
    copying.write_bytes(b"x" * 20)  # still being copied
    assert folders.look() == 0
    clock.now += QUIET * 2
    draw(copying, size=(64, 48), format="PNG")  # done, and readable
    folders.look()
    clock.now += QUIET * 2

    assert folders.look() == 1


def test_its_own_results_and_anything_mado_wrote_are_never_taken(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    draw(inbox / "Done" / "Sail (TV 8K).jpg")  # its results, inside it
    made = draw(inbox / "Rose (Phone).jpg")  # a picture another batch made, saved here
    history.made(
        conn,
        now=NOW,
        job_id=None,
        name="Rose.jpg",
        made_for="Phone",
        original=tmp_path / "Rose.jpg",
        result=made,
    )
    taken, clock = Taken(), Clock()
    folders = _folders(paths, taken, clock)

    folders.look()
    clock.now += QUIET * 2
    folders.look()

    assert taken.pictures == []


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows' own")
def test_its_results_reached_by_another_name_and_links_in_it_are_never_taken(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    (inbox / "Done").mkdir(parents=True)
    outside = tmp_path / "Outside"
    outside.mkdir()
    another_name = tmp_path / "TV done"
    _winapi.CreateJunction(str(inbox / "Done"), str(another_name))
    _winapi.CreateJunction(str(outside), str(inbox / "Shortcut"))
    watching.added(conn, inbox, recipe, another_name, NOW)  # its results: Done, named otherwise
    draw(inbox / "Done" / "Sail (TV 8K).jpg")
    draw(outside / "Far away.jpg")  # only through a link in it
    taken, clock = Taken(), Clock()
    folders = _folders(paths, taken, clock)

    folders.look()
    clock.now += QUIET * 2
    folders.look()

    assert taken.pictures == []


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows' own")
def test_a_picture_mado_wrote_through_another_name_for_the_folder_is_never_taken(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    another_name = tmp_path / "Inbox link"
    _winapi.CreateJunction(str(inbox), str(another_name))
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    made = draw(inbox / "Rose (Phone).jpg")  # another batch saved it into the link
    history.made(
        conn,
        now=NOW,
        job_id=None,
        name="Rose.jpg",
        made_for="Phone",
        original=tmp_path / "Rose.jpg",
        result=another_name / made.name,
    )
    taken, clock = Taken(), Clock()
    folders = _folders(paths, taken, clock)

    folders.look()
    clock.now += QUIET * 2
    folders.look()

    assert taken.pictures == []


def test_a_watch_folder_whose_pictures_cant_go_in_says_why_and_rests_before_trying_again(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    failing = {"yes": True}
    tries: list[int] = []
    why = "It needs a model Mado downloads the first time it's asked for: download it first."

    def take(_conn: sqlite3.Connection, _watch: Watch, found: list[Picture]) -> None:
        tries.append(len(found))
        if failing["yes"]:
            raise BatchError(why)

    clock = Clock()
    folders = WatchFolders(paths, take, now=lambda: NOW, clock=clock)
    draw(inbox / "New.jpg")
    folders.look()
    clock.now += QUIET * 2
    assert folders.look() == 0
    assert tries == [1]
    assert [each.problem for each in watching.listed(conn)] == [why]

    clock.now += QUIET * 2  # soon after, it rests rather than trying at every look
    folders.look()
    assert tries == [1]

    failing["yes"] = False  # the model was downloaded
    clock.now += watching.REST
    assert folders.look() == 1
    assert [each.problem for each in watching.listed(conn)] == [None]


def test_what_arrived_while_mado_was_closed_is_taken_as_it_opens(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "Scans"
    inbox.mkdir()
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    draw(inbox / "Arrived.jpg")  # while Mado was closed
    taken, clock = Taken(), Clock()
    folders = _folders(paths, taken, clock)  # Mado opens

    folders.look()
    clock.now += QUIET + 0.1
    folders.look()

    assert taken.pictures == [(1, ["Arrived.jpg"])]


def test_a_folder_turned_off_takes_nothing_and_on_again_only_what_comes_after(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    watch = watching.added(conn, inbox, recipe, Path("Done"), NOW)
    watching.changed(
        conn, watch.id, path=inbox, recipe_id=recipe, results=watch.results, watching=False, now=NOW
    )
    taken, clock = Taken(), Clock()
    folders = _folders(paths, taken, clock)
    draw(inbox / "While off.jpg")
    folders.look()
    clock.now += QUIET * 2
    folders.look()
    assert taken.pictures == []

    watching.changed(
        conn, watch.id, path=inbox, recipe_id=recipe, results=watch.results, watching=True, now=NOW
    )
    draw(inbox / "After.jpg")
    folders.look()
    clock.now += QUIET * 2
    folders.look()

    assert taken.pictures == [(1, ["After.jpg"])]


def test_a_watch_folder_needs_a_results_folder_of_its_own(
    conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()

    with pytest.raises(WatchError, match="folder of their own"):
        watching.added(conn, inbox, recipe, inbox, NOW)
    with pytest.raises(WatchError, match="isn't there"):
        watching.added(conn, tmp_path / "Gone", recipe, Path("Done"), NOW)
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    with pytest.raises(WatchError, match="already"):
        watching.added(conn, inbox, recipe, Path("Done"), NOW)


def test_a_camera_raw_waits_for_mados_raw_reader_saying_so_then_is_taken(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path, libraw_folder: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    there: dict[str, Path | None] = {"folder": None}
    taken, clock = Taken(), Clock()
    reader = Reader(lambda: there["folder"])
    folders = WatchFolders(paths, taken, now=lambda: NOW, clock=clock, reader=reader)
    dng(inbox / "Green sky.dng", scene(4, (240, 160)))
    folders.look()
    clock.now += QUIET * 2

    assert folders.look() == 0
    assert [each.problem for each in watching.listed(conn)] == [watching.READER_COMING]
    clock.now += watching.GIVE_UP * 2
    assert folders.look() == 0  # never given up on: it opens once the reader is here

    there["folder"] = libraw_folder  # the reader came
    clock.now += QUIET
    assert folders.look() == 1
    assert taken.pictures == [(1, ["Green sky.dng"])]
    assert [each.problem for each in watching.listed(conn)] == [None]


def test_a_watch_folder_stops_saying_the_reader_is_coming_once_no_raw_waits_for_it(
    paths: DataPaths, conn: sqlite3.Connection, recipe: int, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    watching.added(conn, inbox, recipe, Path("Done"), NOW)
    taken, clock = Taken(), Clock()
    folders = WatchFolders(paths, taken, now=lambda: NOW, clock=clock, reader=Reader(lambda: None))
    raw = dng(inbox / "Green sky.dng", scene(4, (240, 160)))
    folders.look()
    clock.now += QUIET * 2
    folders.look()
    assert [each.problem for each in watching.listed(conn)] == [watching.READER_COMING]

    raw.unlink()  # taken away before the reader came
    clock.now += QUIET
    folders.look()

    assert [each.problem for each in watching.listed(conn)] == [None]
