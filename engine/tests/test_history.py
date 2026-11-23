"""History: lines for pictures made, a week of days at a time, their undo, and clearing it."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from mado import history
from mado.history import UndoError
from mado.quarantine import Quarantine, empty
from tests.drawn import draw

NOW = datetime(2026, 11, 22, 14, 2).astimezone()


def _made(conn: sqlite3.Connection, folder: Path, at: datetime, name: str = "Tide.jpg") -> int:
    original = draw(folder / name)
    result = draw(folder / f"{original.stem} (TV 8K).jpg")
    return history.made(
        conn,
        now=at,
        job_id=None,
        name=original.name,
        made_for="TV 8K",
        original=original,
        result=result,
    )


def test_a_new_picture_can_be_taken_away_and_put_back(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    line = _made(conn, tmp_path / "Phone", NOW)
    made = tmp_path / "Phone" / "Tide (TV 8K).jpg"

    taken = history.undo(conn, quarantine, line, NOW)

    assert not made.exists()
    assert taken.aside is not None
    assert Path(taken.aside).is_file()
    assert taken.undone_at is not None
    back = history.redo(conn, quarantine, line, NOW)
    assert made.is_file()
    assert back.aside is None
    assert back.undone_at is None


def test_a_replaced_original_is_put_back_and_the_made_picture_set_aside(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    folder = tmp_path / "Phone"
    original = draw(folder / "Old harbour.heic", format="PNG")
    aside = quarantine.set_aside(original, NOW)
    result = draw(folder / "Old harbour.jpg")
    line = history.replaced(
        conn,
        now=NOW,
        job_id=None,
        name=original.name,
        made_for="TV 8K",
        original=original,
        result=result,
        aside=aside,
    )

    done = history.undo(conn, quarantine, line, NOW)

    assert original.is_file()
    assert not result.exists()
    assert done.aside is not None
    assert Path(done.aside).name == "Old harbour.jpg"
    with pytest.raises(UndoError, match="undone already"):
        history.undo(conn, quarantine, line, NOW)


def test_an_original_cleared_out_of_quarantine_cant_be_put_back(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    original = draw(tmp_path / "Pier.jpg")
    aside = quarantine.set_aside(original, NOW)
    line = history.replaced(
        conn,
        now=NOW,
        job_id=None,
        name="Pier.jpg",
        made_for="A4 print",
        original=original,
        result=draw(tmp_path / "Pier (made).jpg"),
        aside=aside,
    )
    with conn:
        conn.execute("UPDATE history SET cleared_at = '2026-12-23T03:00:00+02:00'")

    with pytest.raises(UndoError, match="cleared out of quarantine on 2026-12-23"):
        history.undo(conn, quarantine, line, NOW)


def test_history_comes_a_week_of_days_at_a_time_newest_first(
    conn: sqlite3.Connection, tmp_path: Path
):
    for days in range(9):
        _made(conn, tmp_path / str(days), NOW - timedelta(days=days))

    first = history.page(conn)
    second = history.page(conn, before=first.older)

    assert [line.at[:10] for line in first.entries][:2] == ["2026-11-22", "2026-11-21"]
    assert len({line.at[:10] for line in first.entries}) == 7
    assert first.older == "2026-11-16"
    assert [line.at[:10] for line in second.entries] == ["2026-11-15", "2026-11-14"]
    assert second.older is None


def test_a_search_finds_the_lines_that_name_a_picture(conn: sqlite3.Connection, tmp_path: Path):
    _made(conn, tmp_path / "Phone", NOW, "Harbour at dusk.jpg")
    _made(conn, tmp_path / "Phone", NOW, "Little sail.jpg")

    found = history.page(conn, query="harbour dusk")

    assert [line.name for line in found.entries] == ["Harbour at dusk.jpg"]


def test_clearing_history_forgets_lines_but_keeps_what_can_still_be_put_back(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    old = _made(conn, tmp_path / "Old", NOW - timedelta(days=10))
    waiting = _made(conn, tmp_path / "Waiting", NOW - timedelta(days=10))
    history.undo(conn, quarantine, waiting, NOW - timedelta(days=10))  # its picture waits aside
    _made(conn, tmp_path / "New", NOW)

    assert history.clear(conn, keep=timedelta(days=7), now=NOW) == 1

    left = [row["id"] for row in conn.execute("SELECT id FROM history ORDER BY id")]
    assert old not in left
    assert waiting in left
    assert history.clear(conn, keep=None, now=NOW) == 1  # all but the one still aside


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _replace(
    conn: sqlite3.Connection,
    quarantine: Quarantine,
    path: Path,
    size: tuple[int, int],
    at: datetime,
    made_for: str = "TV 8K",
) -> int:
    """What saving over a picture does: the picture there set aside, a made one in its place."""
    aside = quarantine.set_aside(path, at)
    draw(path, size=size)
    return history.replaced(
        conn,
        now=at,
        job_id=None,
        name=path.name,
        made_for=made_for,
        original=path,
        result=path,
        aside=aside,
    )


def test_a_picture_replaced_twice_is_put_back_newest_first(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    path = draw(tmp_path / "Dunes.jpg", size=(64, 48))
    first = _replace(conn, quarantine, path, (80, 60), NOW)
    second = _replace(conn, quarantine, path, (96, 72), NOW + timedelta(minutes=5), "Phone")

    with pytest.raises(UndoError, match="newest first"):
        history.undo(conn, quarantine, first, NOW + timedelta(minutes=9))
    assert _size(path) == (96, 72)  # nothing moved

    history.undo(conn, quarantine, second, NOW + timedelta(minutes=10))
    assert _size(path) == (80, 60)
    history.undo(conn, quarantine, first, NOW + timedelta(minutes=11))
    assert _size(path) == (64, 48)  # the true original, in its place


def test_a_new_picture_replaced_since_is_taken_away_only_after_that(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    line = _made(conn, tmp_path, NOW)
    made = tmp_path / "Tide (TV 8K).jpg"
    later = _replace(conn, quarantine, made, (96, 72), NOW + timedelta(minutes=5))

    with pytest.raises(UndoError, match="newest first"):
        history.undo(conn, quarantine, line, NOW + timedelta(minutes=9))
    assert made.is_file()

    history.undo(conn, quarantine, later, NOW + timedelta(minutes=10))
    history.undo(conn, quarantine, line, NOW + timedelta(minutes=11))
    assert not made.exists()


def test_more_sizes_made_from_one_picture_are_each_taken_away_in_any_order(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    original = draw(tmp_path / "Reef.jpg")
    lines: list[int] = []
    for at, made_for in ((NOW, "TV 8K"), (NOW + timedelta(minutes=5), "Phone")):
        result = draw(tmp_path / f"Reef ({made_for}).jpg")
        lines.append(
            history.made(
                conn,
                now=at,
                job_id=None,
                name=original.name,
                made_for=made_for,
                original=original,
                result=result,
            )
        )

    history.undo(conn, quarantine, lines[0], NOW + timedelta(minutes=9))

    assert not (tmp_path / "Reef (TV 8K).jpg").exists()
    assert (tmp_path / "Reef (Phone).jpg").is_file()


def test_a_replaced_original_put_back_can_be_replaced_again(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    path = draw(tmp_path / "Lagoon.png", size=(64, 48))
    line = _replace(conn, quarantine, path, (80, 60), NOW)
    history.undo(conn, quarantine, line, NOW + timedelta(minutes=1))
    assert _size(path) == (64, 48)

    again = history.redo(conn, quarantine, line, NOW + timedelta(minutes=2))

    assert _size(path) == (80, 60)
    assert again.undone_at is None
    assert again.aside is not None
    assert _size(Path(again.aside)) == (64, 48)  # the original, set aside again
    history.undo(conn, quarantine, line, NOW + timedelta(minutes=3))
    assert _size(path) == (64, 48)


def test_an_original_replaced_anew_isnt_replaced_again_by_an_older_line(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    path = draw(tmp_path / "Cove.png", size=(64, 48))
    older = _replace(conn, quarantine, path, (80, 60), NOW)
    history.undo(conn, quarantine, older, NOW + timedelta(minutes=1))
    _replace(conn, quarantine, path, (96, 72), NOW + timedelta(minutes=2), "Phone")

    with pytest.raises(UndoError, match="newest first"):
        history.redo(conn, quarantine, older, NOW + timedelta(minutes=3))
    assert _size(path) == (96, 72)


def test_an_original_emptied_out_by_the_owner_says_so(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    path = draw(tmp_path / "Bay.jpg", size=(64, 48))
    line = _replace(conn, quarantine, path, (80, 60), NOW)
    empty(conn, quarantine, tmp_path.drive, now=NOW + timedelta(days=1))

    with pytest.raises(UndoError, match="You emptied it out of quarantine on 2026-11-23"):
        history.undo(conn, quarantine, line, NOW + timedelta(days=2))


def _set_aside(
    conn: sqlite3.Connection, quarantine: Quarantine, folder: Path, name: str, review: int
) -> tuple[int, Path]:
    """A picture set aside from its group, its line first, as a review does it."""
    picture = draw(folder / name)
    target = quarantine.place(picture, NOW)
    line = history.aside(
        conn,
        now=NOW,
        name=name,
        original=picture,
        kept=folder / "Tide.jpg",
        aside=target,
        size=picture.stat().st_size,
        review_id=review,
    )
    quarantine.set_aside(picture, NOW, to=target)
    return line, picture


def _review(conn: sqlite3.Connection) -> int:
    with conn:
        row = conn.execute(
            "INSERT INTO reviews (at, duplicates, bursts) VALUES (?, 1, 0) RETURNING id",
            (NOW.isoformat(),),
        ).fetchone()
    return row["id"]


def test_a_picture_set_aside_from_its_duplicates_is_put_back_where_it_was(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    line, picture = _set_aside(conn, quarantine, tmp_path / "Phone", "Tide (2).jpg", _review(conn))
    assert not picture.exists()

    back = history.undo(conn, quarantine, line, NOW)

    assert picture.is_file()
    assert (back.undone_at, back.aside) == (NOW.isoformat(timespec="seconds"), None)
    with pytest.raises(UndoError, match="undone already"):
        history.undo(conn, quarantine, line, NOW)
    with pytest.raises(UndoError, match="nothing to put back"):
        history.redo(conn, quarantine, line, NOW)


def test_a_picture_set_aside_cant_go_back_over_another_or_once_its_cleared_out(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    review = _review(conn)
    first, picture = _set_aside(conn, quarantine, tmp_path / "Phone", "Tide (2).jpg", review)
    second, _ = _set_aside(conn, quarantine, tmp_path / "Phone", "Tide (3).jpg", review)
    draw(picture)  # a new picture by that name since

    with pytest.raises(UndoError, match=r"another Tide \(2\).jpg in its place"):
        history.undo(conn, quarantine, first, NOW)
    empty(conn, quarantine, Path(str(tmp_path)).drive or "C:", now=NOW)
    with pytest.raises(UndoError, match="emptied it out of quarantine"):
        history.undo(conn, quarantine, second, NOW)


def test_a_line_whose_picture_never_moved_is_simply_undone(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    picture = draw(tmp_path / "Phone" / "Tide (2).jpg")
    line = history.aside(  # written, then Mado stopped before the move
        conn,
        now=NOW,
        name=picture.name,
        original=picture,
        kept=tmp_path / "Phone" / "Tide.jpg",
        aside=quarantine.place(picture, NOW),
        size=picture.stat().st_size,
        review_id=_review(conn),
    )

    back = history.undo(conn, quarantine, line, NOW)

    assert back.undone_at is not None
    assert picture.is_file()


def test_a_review_is_put_back_whole_saying_why_any_couldnt_be(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    review = _review(conn)
    _, first = _set_aside(conn, quarantine, tmp_path / "Phone", "Tide (2).jpg", review)
    _, second = _set_aside(conn, quarantine, tmp_path / "Phone", "Tide (3).jpg", review)
    draw(second)  # in the way

    done, problems = history.undo_review(conn, quarantine, review, NOW)

    assert done == 1
    assert first.is_file()
    assert len(problems) == 1
    assert problems[0].startswith("Tide (3).jpg: There's another")
    lines = history.of_review(conn, review)
    assert [each.name for each in lines] == ["Tide (3).jpg", "Tide (2).jpg"]
    assert history.clear(conn, keep=None, now=NOW) == 1  # what still waits stays
    assert [each.name for each in history.of_review(conn, review)] == ["Tide (3).jpg"]


def test_a_picture_set_aside_on_a_drive_that_isnt_connected_says_so(
    conn: sqlite3.Connection, quarantine: Quarantine
):
    line = history.aside(
        conn,
        now=NOW,
        name="Pier (2).jpg",
        original=Path(r"Q:\Pictures\Pier (2).jpg"),
        kept=Path(r"Q:\Pictures\Pier.jpg"),
        aside=Path(r"Q:\Mado quarantine\2026-11-22\Pier (2).jpg"),
        size=10,
        review_id=_review(conn),
    )

    with pytest.raises(UndoError, match="Q: isn't connected"):
        history.undo(conn, quarantine, line, NOW)
