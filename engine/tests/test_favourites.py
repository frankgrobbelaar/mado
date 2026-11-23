import sqlite3
from datetime import datetime, timedelta

from mado import favourites

NOW = datetime(2026, 11, 23, 12, 0).astimezone()


def _picture(
    conn: sqlite3.Connection,
    path: str,
    *,
    size: int = 1000,
    modified: int = 7,
    gone_at: str | None = None,
    found_at: str = "x",
    folder: int | None = 1,
) -> int:
    name = path.rsplit("\\", 1)[-1]
    with conn:
        if folder is not None:
            conn.execute(
                "INSERT OR IGNORE INTO folders (id, path, added_at) VALUES (?, ?, 'x')",
                (folder, r"D:\Pictures"),
            )
        return conn.execute(
            """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at, seen_at,
                                     gone_at, read_at, format, width, height, taken_at, taken_from)
               VALUES (?, ?, '', ?, ?, ?, ?, 'x', ?, 'x', 'JPEG', 4000, 2250, 'x', 'file')
               RETURNING id""",
            (folder, path, name, size, modified, found_at, gone_at),
        ).fetchone()[0]


def test_a_heart_is_given_and_taken_back(conn: sqlite3.Connection):
    pier = _picture(conn, r"D:\Pictures\Pier.jpg")

    assert favourites.set_favourite(conn, pier, True, NOW)
    assert favourites.is_favourite(conn, pier)
    assert favourites.set_favourite(conn, pier, True, NOW)  # again: still one, once
    assert favourites.count(conn) == 1
    assert favourites.set_favourite(conn, pier, False, NOW)
    assert not favourites.is_favourite(conn, pier)
    assert not favourites.set_favourite(conn, 99, True, NOW)  # no such picture


def test_which_of_some_pictures_are_favourites(conn: sqlite3.Connection):
    one, two, three = (_picture(conn, rf"D:\Pictures\{n}.jpg") for n in ("One", "Two", "Three"))
    favourites.set_favourite(conn, one, True, NOW)
    favourites.set_favourite(conn, three, True, NOW)

    assert favourites.among(conn, [one, two, three]) == {one, three}
    assert favourites.among(conn, []) == set()


def test_only_favourites_there_now_are_counted(conn: sqlite3.Connection):
    there = _picture(conn, r"D:\Pictures\There.jpg")
    gone = _picture(conn, r"D:\Pictures\Gone.jpg", gone_at=NOW.isoformat())
    for each in (there, gone):
        favourites.set_favourite(conn, each, True, NOW)

    assert favourites.count(conn) == 1


def test_a_favourite_renamed_or_moved_stays_one_where_it_went(conn: sqlite3.Connection):
    went = NOW.isoformat()
    renamed_from = _picture(conn, r"D:\Pictures\IMG_2041.jpg", size=5000, modified=11, gone_at=went)
    moved_from = _picture(conn, r"D:\Pictures\Pier.jpg", size=6000, modified=12, gone_at=went)
    favourites.set_favourite(conn, renamed_from, True, NOW)
    favourites.set_favourite(conn, moved_from, True, NOW)
    renamed = _picture(conn, r"D:\Pictures\Harbour at dusk.jpg", size=5000, modified=11,
                       found_at=went)  # fmt: skip
    elsewhere = _picture(conn, r"D:\Pictures\Kept\Another.jpg", size=6000, modified=12,
                         found_at=went)  # fmt: skip
    moved = _picture(conn, r"D:\Pictures\Trip\Pier.jpg", size=6000, modified=12, found_at=went)

    assert favourites.follow(conn) == 2

    assert favourites.among(conn, [renamed, moved, elsewhere, renamed_from, moved_from]) == {
        renamed,
        moved,
    }


def test_a_favourite_follows_a_rename_in_its_own_folder_before_another_folders(
    conn: sqlite3.Connection,
):
    went = NOW.isoformat()
    gone = _picture(conn, r"D:\Pictures\Old name.jpg", gone_at=went)
    favourites.set_favourite(conn, gone, True, NOW)
    away = _picture(conn, r"D:\Pictures\Trip\Copy.jpg", found_at=went)
    beside = _picture(conn, r"D:\Pictures\New name.jpg", found_at=went)

    favourites.follow(conn)

    assert favourites.among(conn, [away, beside]) == {beside}


def test_a_favourite_never_takes_another_favourites_picture_and_waits_while_nothing_matches(
    conn: sqlite3.Connection,
):
    went = NOW.isoformat()
    gone = _picture(conn, r"D:\Pictures\Gone.jpg", gone_at=went)
    loved = _picture(conn, r"D:\Pictures\Loved.jpg", found_at=went)
    other = _picture(conn, r"D:\Pictures\Other.jpg", size=4321, found_at=went)
    for each in (gone, loved):
        favourites.set_favourite(conn, each, True, NOW)

    assert favourites.follow(conn) == 0

    assert favourites.among(conn, [gone, loved, other]) == {gone, loved}


def test_a_picture_there_before_with_the_same_size_and_time_isnt_taken_for_one_that_moved(
    conn: sqlite3.Connection,
):
    # Two pictures written in the same instant can share a size and a file time: only one the
    # same scan found new, as it found the favourite gone, is where it went.
    went = NOW.isoformat()
    gone = _picture(conn, r"D:\Pictures\Snowfield.jpg", gone_at=went)
    favourites.set_favourite(conn, gone, True, NOW)
    before = _picture(conn, r"D:\Pictures\Little sail.jpg")
    renamed = _picture(conn, r"D:\Pictures\Snow on the hill.jpg", found_at=went)

    assert favourites.follow(conn) == 1

    assert favourites.among(conn, [before, renamed]) == {renamed}


def test_a_favourite_whose_picture_stays_gone_a_month_is_forgotten(conn: sqlite3.Connection):
    long_gone = _picture(conn, r"D:\Pictures\A.jpg", gone_at=(NOW - timedelta(days=31)).isoformat())
    lately = _picture(conn, r"D:\Pictures\B.jpg", gone_at=(NOW - timedelta(days=3)).isoformat())
    there = _picture(conn, r"D:\Pictures\C.jpg")
    for each in (long_gone, lately, there):
        favourites.set_favourite(conn, each, True, NOW)

    assert favourites.forget_gone(conn, now=NOW) == 1

    assert favourites.among(conn, [long_gone, lately, there]) == {lately, there}
