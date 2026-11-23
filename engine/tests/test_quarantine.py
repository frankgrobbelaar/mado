"""The quarantine: setting a picture aside on its own drive, putting it back, the daily
clear-out after 30 days, and emptying a drive's by hand."""

import errno
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mado import history
from mado.quarantine import (
    InUseMoveError,
    MoveError,
    Quarantine,
    by_drive,
    clear_out,
    empty,
    move,
)
from tests.drawn import draw

NOW = datetime(2026, 11, 22, 11, 20).astimezone()


def test_a_picture_set_aside_waits_in_todays_folder_and_comes_back(
    quarantine: Quarantine, tmp_path: Path
):
    picture = draw(tmp_path / "Phone" / "Old harbour.jpg")

    aside = quarantine.set_aside(picture, NOW)

    assert aside == tmp_path / "Mado quarantine" / "2026-11-22" / "Old harbour.jpg"
    assert aside.is_file()
    assert not picture.exists()
    assert quarantine.holds(aside)
    quarantine.put_back(aside, picture)
    assert picture.is_file()
    assert not (tmp_path / "Mado quarantine").exists()  # emptied folders go


def test_two_pictures_of_one_name_set_aside_the_same_day_are_both_kept(
    quarantine: Quarantine, tmp_path: Path
):
    first = quarantine.set_aside(draw(tmp_path / "A" / "Pier.jpg"), NOW)
    second = quarantine.set_aside(draw(tmp_path / "B" / "Pier.jpg"), NOW)

    assert first.name == "Pier.jpg"
    assert second.name == "Pier (2).jpg"


def test_a_picture_is_never_put_back_over_another(quarantine: Quarantine, tmp_path: Path):
    picture = draw(tmp_path / "Pier.jpg")
    aside = quarantine.set_aside(picture, NOW)
    draw(picture)  # something else took its place meanwhile

    with pytest.raises(MoveError, match=r"another Pier.jpg in its place"):
        quarantine.put_back(aside, picture)
    assert aside.is_file()


def test_moving_never_writes_over_a_file(tmp_path: Path):
    source, target = draw(tmp_path / "a.jpg"), draw(tmp_path / "b.jpg")

    with pytest.raises(MoveError, match=r"already a b\.jpg there"):
        move(source, target)
    assert source.is_file()


def _replaced(conn: sqlite3.Connection, quarantine: Quarantine, folder: Path, at: datetime) -> Path:
    original = draw(folder / "Old harbour.jpg")
    aside = quarantine.set_aside(original, at)
    draw(folder / "Old harbour (made).jpg")
    history.replaced(
        conn,
        now=at,
        job_id=None,
        name="Old harbour.jpg",
        made_for="TV 8K",
        original=original,
        result=folder / "Old harbour (made).jpg",
        aside=aside,
    )
    return aside


def test_the_clear_out_deletes_what_waited_longer_than_30_days(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    old = _replaced(conn, quarantine, tmp_path / "Old", NOW - timedelta(days=31))
    fresh = _replaced(conn, quarantine, tmp_path / "Fresh", NOW - timedelta(days=2))

    assert clear_out(conn, quarantine, now=NOW) == 1

    assert not old.exists()
    assert fresh.exists()
    cleared = conn.execute("SELECT cleared_at FROM history ORDER BY id").fetchall()
    assert [row["cleared_at"] is not None for row in cleared] == [True, False]


def test_the_clear_out_never_deletes_a_picture_outside_a_quarantine(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    elsewhere = draw(tmp_path / "Pictures" / "Keep me.jpg")
    with conn:  # a damaged or imported record pointing at a picture in the library
        conn.execute(
            "INSERT INTO history (at, kind, name, aside, aside_at) VALUES (?, 'replaced', ?, ?, ?)",
            (NOW.isoformat(), "Keep me.jpg", str(elsewhere), "2026-01-01T00:00:00+02:00"),
        )

    assert clear_out(conn, quarantine, now=NOW) == 0
    assert elsewhere.is_file()


def test_emptying_a_drives_quarantine_by_hand_frees_it_now_and_history_says_so(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    aside = _replaced(conn, quarantine, tmp_path / "Phone", NOW)
    drive = tmp_path.drive
    size = aside.stat().st_size

    assert by_drive(conn) == {drive.upper(): size}
    assert empty(conn, quarantine, drive, now=NOW) == size
    assert not aside.exists()
    assert by_drive(conn) == {}
    emptied = conn.execute("SELECT * FROM history WHERE kind = 'emptied'").fetchone()
    assert emptied["name"] == drive.upper()
    assert emptied["bytes"] == size


def test_whats_set_aside_on_a_drive_not_connected_waits_for_it(conn: sqlite3.Connection):
    missing = next(
        f"{letter}:" for letter in "ZYXWVUTSRQPONMLKJIHG" if not Path(f"{letter}:\\").exists()
    )
    aside = Path(f"{missing}/") / "Mado quarantine" / "2026-10-01" / "Pier.jpg"
    with conn:
        conn.execute(
            "INSERT INTO history (at, kind, name, aside, aside_at) VALUES (?, 'replaced', ?, ?, ?)",
            (NOW.isoformat(), "Pier.jpg", str(aside), (NOW - timedelta(days=40)).isoformat()),
        )

    assert clear_out(conn, Quarantine(), now=NOW) == 0

    line = conn.execute("SELECT cleared_at FROM history").fetchone()
    assert line["cleared_at"] is None  # cleared once its drive is back


def test_history_knows_whether_the_days_or_the_owner_cleared_a_picture_out(
    conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    _replaced(conn, quarantine, tmp_path / "Old", NOW - timedelta(days=31))
    clear_out(conn, quarantine, now=NOW)
    _replaced(conn, quarantine, tmp_path / "Fresh", NOW)
    empty(conn, quarantine, tmp_path.drive, now=NOW)

    rows = conn.execute(
        "SELECT cleared_by FROM history WHERE kind = 'replaced' ORDER BY id"
    ).fetchall()
    assert [row["cleared_by"] for row in rows] == ["days", "owner"]


def test_a_move_to_another_drive_that_cant_finish_leaves_no_copy_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = draw(tmp_path / "Phone" / "Pier.jpg")
    target = tmp_path / "Other drive" / "Mado quarantine" / "2026-11-23" / "Pier.jpg"
    rename, unlink = Path.rename, Path.unlink

    def across(self: Path, to: Path) -> Path:
        if self == source:
            raise OSError(errno.EXDEV, "Not the same device")
        return rename(self, to)

    def held(self: Path, missing_ok: bool = False) -> None:
        if self == source:  # another app has it open: it can't be removed
            raise PermissionError(13, "The process cannot access the file", str(self), 32)
        unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "rename", across)
    monkeypatch.setattr(Path, "unlink", held)

    with pytest.raises(InUseMoveError):
        move(source, target)

    assert source.exists()
    assert not target.exists()  # nothing left in quarantine with no line to clear it out
    assert list(target.parent.glob("*")) == []
