"""The queue: batches of pictures made one at a time by the jobs' worker, in the queue's order,
with nights, pausing, cancelling, ticked rows, drives that aren't connected, room on a drive,
and carrying on after Mado stops."""

import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from mado.config import DataPaths
from mado.jobs import HOLD_EVERY, HOLD_FOR, HeldError, Jobs, NewBatch, NoRoomError, Stage, recover
from mado.quarantine import Quarantine
from mado.upscale import StoppedError

DAY = datetime(2026, 11, 22, 14, 0).astimezone()
NIGHT = datetime(2026, 11, 22, 23, 30).astimezone()
type Report = Callable[[Stage, float], None]


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


class Told:
    def __init__(self) -> None:
        self.said: list[tuple[str, str, str | None]] = []

    def __call__(self, title: str, body: str, /, *, link: str | None = None) -> None:
        self.said.append((title, body, link))


def _jobs(
    paths: DataPaths,
    work: Callable[..., Path],
    *,
    now: Callable[[], datetime] = lambda: DAY,
    told: Told | None = None,
    connected: Callable[[Path], bool] = lambda _path: True,
    free: Callable[[Path], int | None] = lambda _path: None,
) -> Jobs:
    return Jobs(
        paths,
        work,
        Quarantine(lambda _picture: paths.root / "q"),
        now=now,
        notify=told or Told(),
        connected=connected,
        free=free,
    )


def _made(tmp_path: Path, record: list[str] | None = None) -> Callable[..., Path]:
    """Work that makes each picture at once, noting which it made."""

    def work(
        _conn: sqlite3.Connection,
        row: sqlite3.Row,
        _report: Report,
        _stop: Callable[[], bool],
        _expect: Callable[[float], None],
    ) -> Path:
        name = Path(row["source"]).name
        if record is not None:
            record.append(name)
        made = tmp_path / "made" / f"{Path(name).stem} (TV 8K).jpg"
        made.parent.mkdir(exist_ok=True)
        made.write_bytes(b"x" * 10)
        return made

    return work


def _batch(
    jobs: Jobs,
    conn: sqlite3.Connection,
    tmp_path: Path,
    names: list[str],
    *,
    starts: str = "now",
    name: str = "Holiday prints",
    folder: str | None = None,
    bytes_each: int = 0,
    places: dict[str, Path] | None = None,
) -> int:
    """A batch of pictures in tmp_path's Holiday folder, or each in its `places` folder."""
    order: dict[str, Any] = {
        "recipe": {"size": {"size": "tv-8k"}, "look": None},
        "saving": {"how": "new", "format": "JPEG", "quality": 95, "folder": folder},
        "label": "TV 8K",
        "look": None,
        "seconds": 10.0,
        "bytes": bytes_each,
    }
    return jobs.add_batch(
        conn,
        NewBatch(
            name=name,
            source="Holiday",
            shared=str(tmp_path / "Holiday"),
            steps={"steps": [{"step": "size", "size": "tv-8k"}], "saving": order["saving"]},
            starts=starts,  # type: ignore[arg-type]
        ),
        [
            (None, (places or {}).get(each, tmp_path / "Holiday") / each, 1000, order)
            for each in names
        ],
    )


def _states(conn: sqlite3.Connection, batch: int) -> list[tuple[str, str]]:
    return [
        (Path(row["source"]).name, row["state"])
        for row in conn.execute(
            "SELECT source, state FROM jobs WHERE batch_id = ? ORDER BY position, id", (batch,)
        )
    ]


def _run(jobs: Jobs, timeout: float = 10) -> None:
    jobs.start()
    try:
        assert jobs.wait(timeout), "the queue didn't settle in time"
    finally:
        jobs.stop()


def test_a_batch_is_made_a_picture_at_a_time_in_its_order_then_told(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    record: list[str] = []
    told = Told()
    jobs = _jobs(paths, _made(tmp_path, record), told=told)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg", "Dunes.jpg"])

    _run(jobs)

    assert record == ["Pier.jpg", "Sail.jpg", "Dunes.jpg"]
    assert _states(conn, batch) == [
        ("Pier.jpg", "done"),
        ("Sail.jpg", "done"),
        ("Dunes.jpg", "done"),
    ]
    row = conn.execute("SELECT started_at, finished_at FROM batches").fetchone()
    assert row["started_at"]
    assert row["finished_at"]
    assert told.said == [("Holiday prints is done", "3 pictures made for TV 8K", "/")]
    made = conn.execute("SELECT bytes, made_bytes FROM jobs").fetchone()
    assert (made["bytes"], made["made_bytes"]) == (1000, 10)


def test_a_pictures_own_save_goes_ahead_of_a_batch(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    record: list[str] = []
    jobs = _jobs(paths, _made(tmp_path, record))
    _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg"])
    jobs.add(conn, None, tmp_path / "Rose.jpg", {"recipe": {}, "saving": {}})

    _run(jobs)

    assert record == ["Rose.jpg", "Pier.jpg", "Sail.jpg"]


def test_a_batch_for_tonight_waits_for_the_night(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    clock = Clock(DAY)
    record: list[str] = []
    jobs = _jobs(paths, _made(tmp_path, record), now=clock)
    tonight = _batch(jobs, conn, tmp_path, ["Pier.jpg"], starts="tonight")
    _batch(jobs, conn, tmp_path, ["Sail.jpg"], starts="after", name="Phone wallpapers")

    _run(jobs)
    assert record == ["Sail.jpg"]
    assert _states(conn, tonight) == [("Pier.jpg", "queued")]

    clock.moment = NIGHT
    _run(jobs)
    assert record == ["Sail.jpg", "Pier.jpg"]


def test_now_goes_ahead_of_what_waits_and_after_goes_behind_it(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    record: list[str] = []
    jobs = _jobs(paths, _made(tmp_path, record))
    _batch(jobs, conn, tmp_path, ["Pier.jpg"], starts="after")
    _batch(jobs, conn, tmp_path, ["Sail.jpg"], starts="now")
    _batch(jobs, conn, tmp_path, ["Dunes.jpg"], starts="after")

    _run(jobs)

    assert record == ["Sail.jpg", "Pier.jpg", "Dunes.jpg"]


class Gate:
    """Work that waits at its first tile till the test lets it go, saying when it got there."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.started = threading.Event()
        self.go = threading.Event()
        self.made: list[str] = []
        self.stopped: list[str] = []

    def __call__(
        self,
        _conn: sqlite3.Connection,
        row: sqlite3.Row,
        report: Report,
        stop: Callable[[], bool],
        _expect: Callable[[float], None],
    ) -> Path:
        name = Path(row["source"]).name
        report("making", 0.1)
        self.started.set()
        self.go.wait(10)
        if stop():
            self.stopped.append(name)
            raise StoppedError
        self.made.append(name)
        return self.tmp_path / f"{name} (TV 8K).jpg"


def test_pausing_puts_the_picture_being_made_back_first_and_starts_no_other(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    gate = Gate(tmp_path)
    jobs = _jobs(paths, gate)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg"])
    jobs.start()
    try:
        assert gate.started.wait(10)
        jobs.pause(conn)
        gate.go.set()
        assert jobs.wait(10)
        assert gate.stopped == ["Pier.jpg"]
        assert _states(conn, batch) == [("Pier.jpg", "queued"), ("Sail.jpg", "queued")]
        attempts = conn.execute("SELECT MAX(attempts) FROM jobs").fetchone()[0]
        assert attempts == 0  # a pause isn't a try: only crashes count

        jobs.resume(conn)
        assert jobs.wait(10)
    finally:
        jobs.stop()

    assert gate.made == ["Pier.jpg", "Sail.jpg"]


def test_cancel_all_cancels_what_waits_and_stops_the_picture_being_made(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    gate = Gate(tmp_path)
    told = Told()
    jobs = _jobs(paths, gate, told=told)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg", "Dunes.jpg"])
    jobs.start()
    try:
        assert gate.started.wait(10)
        assert jobs.cancel_all(conn) == 3
        gate.go.set()
        assert jobs.wait(10)
    finally:
        jobs.stop()

    assert {state for _name, state in _states(conn, batch)} == {"cancelled"}
    assert told.said == []  # nothing to tell: the owner stopped it
    assert conn.execute("SELECT finished_at, seen_at FROM batches").fetchone()[0] is not None


def test_ticked_pictures_go_next_or_to_the_end_or_out_of_the_queue(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    jobs = _jobs(paths, _made(tmp_path))  # not started: everything waits
    batch = _batch(jobs, conn, tmp_path, ["A.jpg", "B.jpg", "C.jpg", "D.jpg"])
    ids = {
        Path(row["source"]).name: row["id"]
        for row in conn.execute("SELECT id, source FROM jobs WHERE batch_id = ?", (batch,))
    }

    assert jobs.move(conn, [ids["C.jpg"], ids["D.jpg"]], "next") == 2
    assert [name for name, _ in _states(conn, batch)] == ["C.jpg", "D.jpg", "A.jpg", "B.jpg"]
    assert jobs.move(conn, [ids["C.jpg"]], "last") == 1
    assert [name for name, _ in _states(conn, batch)] == ["D.jpg", "A.jpg", "B.jpg", "C.jpg"]

    assert jobs.remove(conn, [ids["A.jpg"], ids["B.jpg"]]) == 2
    assert [name for name, _ in _states(conn, batch)] == ["D.jpg", "C.jpg"]
    assert jobs.remove(conn, [ids["C.jpg"], ids["D.jpg"]]) == 2
    assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0  # nothing left of it


def test_a_picture_that_didnt_work_can_be_tried_again(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    tries: list[str] = []

    def work(_conn: sqlite3.Connection, row: sqlite3.Row, *_rest: object) -> Path:
        tries.append(Path(row["source"]).name)
        if len(tries) == 1:
            from mado.jobs import JobError

            raise JobError("Pier.jpg is open in another app, so Mado can't move it.")
        return tmp_path / "Pier (TV 8K).jpg"

    told = Told()
    jobs = _jobs(paths, work, told=told)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg"])
    _run(jobs)
    job = conn.execute("SELECT id, state, problem FROM jobs").fetchone()
    assert job["state"] == "failed"
    assert "open in another app" in job["problem"]
    assert told.said[-1][0] == "Holiday prints didn't work"

    assert jobs.retry(conn, job["id"])
    assert conn.execute("SELECT finished_at FROM batches").fetchone()[0] is None
    _run(jobs)

    assert _states(conn, batch) == [("Pier.jpg", "done")]
    assert told.said[-1] == ("Holiday prints is done", "1 picture made for TV 8K", "/")


def test_a_picture_on_a_drive_that_isnt_connected_waits_while_the_others_go(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    record: list[str] = []
    unplugged = Path("Q:/Holiday")
    plugged = {"in": False}
    asked: list[Path] = []

    def connected(path: Path) -> bool:
        asked.append(path)
        return plugged["in"] or path.anchor.casefold() != unplugged.anchor.casefold()

    jobs = _jobs(paths, _made(tmp_path, record), connected=connected)
    away = [f"Away {at}.jpg" for at in range(30)]
    batch = _batch(
        jobs,
        conn,
        tmp_path,
        [*away, "Sail.jpg"],
        places=dict.fromkeys(away, unplugged),
    )

    _run(jobs)
    assert record == ["Sail.jpg"]
    assert _states(conn, batch)[0] == ("Away 0.jpg", "queued")
    assert len(asked) < 10  # each drive asked about once a look, not once a picture

    plugged["in"] = True  # plugged in again
    _run(jobs)
    assert record == ["Sail.jpg", *away]


def test_without_room_the_queue_pauses_saying_what_it_needs_and_carries_on_once_theres_room(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    from mado.core.batch import MARGIN

    record: list[str] = []
    room = {"free": MARGIN + 150}
    told = Told()
    make = _made(tmp_path, record)

    def work(*args: Any) -> Path:  # each picture made takes its room on the drive
        room["free"] -= 100
        return make(*args)

    jobs = _jobs(paths, work, told=told, free=lambda _path: room["free"])
    _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg", "Dunes.jpg"], bytes_each=100)

    _run(jobs)
    assert record == ["Pier.jpg"]  # it fit; then the drive filled as far as Mado reckons
    short = jobs.short_of_room(conn)
    assert short is not None
    assert short["fit"] is False
    assert told.said[-1][0] == "The queue paused itself"

    room["free"] = MARGIN + 1000  # room was made: it carries on by itself
    _run(jobs)
    assert record == ["Pier.jpg", "Sail.jpg", "Dunes.jpg"]
    assert jobs.short_of_room(conn) is None


def test_making_what_fits_takes_the_pictures_that_fit_while_the_rest_wait_for_room(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    from mado.core.batch import MARGIN

    record: list[str] = []
    jobs = _jobs(paths, _made(tmp_path, record), free=lambda _path: MARGIN + 50)
    _batch(jobs, conn, tmp_path, ["Big.jpg"], bytes_each=100)
    _batch(jobs, conn, tmp_path, ["Small.jpg"], bytes_each=10, name="Small ones", starts="after")

    _run(jobs)
    assert record == []
    drive = jobs.short_of_room(conn)
    assert drive is not None

    jobs.fit(conn, str(drive["drive"]))
    _run(jobs)

    assert record == ["Small.jpg"]


def test_a_full_drive_found_while_saving_puts_the_picture_back_in_line_and_pauses(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    drive = tmp_path.drive.upper()
    tries: list[int] = []

    def work(*_args: object) -> Path:
        tries.append(1)
        raise NoRoomError(drive, f"There isn't enough space on {drive} for it.")

    free = {"bytes": 10**9}
    jobs = _jobs(paths, work, free=lambda _path: free["bytes"])
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg"])

    _run(jobs)

    assert _states(conn, batch) == [("Pier.jpg", "queued")]
    assert jobs.short_of_room(conn) == {"drive": drive, "fit": False}
    assert tries == [1]  # it waits for room to be made, rather than trying again and again

    free["bytes"] += 10**9  # room was made
    _run(jobs)
    assert tries == [1, 1]


def test_a_batch_mado_closed_on_carries_on_as_it_opens(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    record: list[str] = []
    jobs = _jobs(paths, _made(tmp_path, record))
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg"])
    with conn:  # Mado stopped (a crash) while Pier was being made
        conn.execute(
            "UPDATE jobs SET state = 'running', attempts = 1 WHERE source LIKE '%Pier.jpg'"
        )
        conn.execute("UPDATE batches SET started_at = '2026-11-22T13:00:00+02:00'")

    _run(jobs)  # starting recovers first

    assert record == ["Pier.jpg", "Sail.jpg"]
    assert _states(conn, batch) == [("Pier.jpg", "done"), ("Sail.jpg", "done")]


def test_a_batch_finished_as_mado_stopped_is_settled_as_it_opens(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    told = Told()
    jobs = _jobs(paths, _made(tmp_path), told=told)
    _batch(jobs, conn, tmp_path, ["Pier.jpg"])
    with conn:
        conn.execute("UPDATE jobs SET state = 'done'")

    recover(conn, DAY, Quarantine(lambda _picture: tmp_path / "q"))
    jobs.settle_all(conn)

    assert conn.execute("SELECT finished_at FROM batches").fetchone()[0] is not None
    assert told.said[0][0] == "Holiday prints is done"


@pytest.mark.parametrize("starts", ["now", "after"])
def test_the_queue_says_what_waits_and_how_far_the_batch_has_got(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path, starts: str
):
    jobs = _jobs(paths, _made(tmp_path))
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg"], starts=starts)
    with conn:
        conn.execute("UPDATE jobs SET state = 'done' WHERE source LIKE '%Pier.jpg'")

    assert jobs.waiting(conn) == 1
    assert jobs.batch_progress(conn, batch) == (1, 2)


def test_a_cancelled_picture_tried_again_is_made_not_cancelled_again(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    record: list[str] = []
    make = _made(tmp_path, record)

    def work(
        conn_: sqlite3.Connection,
        row: sqlite3.Row,
        report: Report,
        stop: Callable[[], bool],
        expect: Callable[[float], None],
    ) -> Path:
        if stop():  # as making does, once it's read the picture
            raise StoppedError
        return make(conn_, row, report, stop, expect)

    jobs = _jobs(paths, work)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg"])
    pier = conn.execute("SELECT id FROM jobs WHERE source LIKE '%Pier.jpg'").fetchone()[0]

    assert jobs.cancel(conn, pier)  # while it waited
    assert jobs.retry(conn, pier)
    _run(jobs)

    assert dict(_states(conn, batch))["Pier.jpg"] == "done"


def test_one_picture_cancelled_still_lets_the_batch_be_told(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    told = Told()
    jobs = _jobs(paths, _made(tmp_path), told=told)
    _batch(jobs, conn, tmp_path, ["A.jpg", "B.jpg", "C.jpg"])
    one = conn.execute("SELECT id FROM jobs WHERE source LIKE '%C.jpg'").fetchone()[0]

    jobs.cancel(conn, one)
    _run(jobs)

    assert told.said == [("Holiday prints is done", "2 pictures made for TV 8K", "/")]


def test_resuming_soon_after_pausing_lets_the_picture_being_made_go_on(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    gate = Gate(tmp_path)
    jobs = _jobs(paths, gate)
    _batch(jobs, conn, tmp_path, ["Pier.jpg"])
    jobs.start()
    try:
        assert gate.started.wait(10)
        jobs.pause(conn)
        jobs.resume(conn)  # before its next tile
        gate.go.set()
        assert jobs.wait(10)
    finally:
        jobs.stop()

    assert gate.stopped == []
    assert gate.made == ["Pier.jpg"]


def test_a_pictures_own_save_goes_ahead_of_see_it_first(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    order: list[str] = []
    jobs = _jobs(paths, _made(tmp_path, order))
    seen = {"left": 1}

    def first(_stopping: Callable[[], bool]) -> bool:
        if not seen["left"]:
            return False
        seen["left"] -= 1
        order.append("see it first")
        return True

    jobs.before_the_queue(first)
    jobs.add(conn, None, tmp_path / "Rose.jpg", {"recipe": {}, "saving": {}})

    _run(jobs)

    assert order == ["Rose.jpg", "see it first"]


def test_a_drive_unplugged_mid_picture_puts_it_back_to_wait(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    from mado.jobs import DriveGoneError

    plugged = {"in": True}

    def work(*_args: object) -> Path:
        plugged["in"] = False  # the drive goes as the picture is read
        raise DriveGoneError("D:")

    jobs = _jobs(paths, work, connected=lambda _path: plugged["in"])
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg"])

    _run(jobs)

    assert _states(conn, batch) == [("Pier.jpg", "queued")]
    assert conn.execute("SELECT attempts FROM jobs").fetchone()[0] == 0


def _held_on(names: set[str], tmp_path: Path, record: list[str]) -> Callable[..., Path]:
    """Work that finds the pictures in `names` open in another app, as long as they're in it."""

    def work(_conn: sqlite3.Connection, row: sqlite3.Row, *_rest: object) -> Path:
        name = Path(row["source"]).name
        record.append(name)
        if name in names:
            raise HeldError(name, "replace")
        made = tmp_path / "made" / f"{Path(name).stem} (TV 8K).jpg"
        made.parent.mkdir(exist_ok=True)
        made.write_bytes(b"x" * 10)
        return made

    return work


def test_a_picture_open_in_another_app_waits_while_the_others_go_then_is_tried_again(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    clock = Clock(DAY)
    record: list[str] = []
    held = {"Pier.jpg"}
    jobs = _jobs(paths, _held_on(held, tmp_path, record), now=clock)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg"])

    _run(jobs)

    assert record == ["Pier.jpg", "Sail.jpg"]
    assert _states(conn, batch) == [("Pier.jpg", "queued"), ("Sail.jpg", "done")]
    row = conn.execute("SELECT * FROM jobs WHERE source LIKE '%Pier.jpg'").fetchone()
    assert row["problem"] == (
        "Pier.jpg is open in another app. Mado can't replace it while it's open. Close it there "
        "and Mado tries again by itself."
    )
    assert (row["held_why"], row["attempts"]) == ("replace", 0)  # not counted as a try
    assert datetime.fromisoformat(row["held_until"]) == DAY + HOLD_EVERY
    assert conn.execute("SELECT finished_at FROM batches").fetchone()[0] is None

    _run(jobs)  # not yet due
    assert record == ["Pier.jpg", "Sail.jpg"]

    held.clear()  # closed in the other app
    clock.moment = DAY + HOLD_EVERY
    _run(jobs)
    assert record == ["Pier.jpg", "Sail.jpg", "Pier.jpg"]
    assert _states(conn, batch) == [("Pier.jpg", "done"), ("Sail.jpg", "done")]
    done = conn.execute("SELECT held_since, held_until FROM jobs").fetchall()
    assert all(row["held_since"] is None and row["held_until"] is None for row in done)


def test_a_picture_open_in_another_app_for_ten_minutes_counts_as_not_working(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    clock = Clock(DAY)
    record: list[str] = []
    told = Told()
    jobs = _jobs(paths, _held_on({"Pier.jpg"}, tmp_path, record), now=clock, told=told)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg"])
    _run(jobs)

    while clock.moment < DAY + HOLD_FOR:
        clock.moment += HOLD_EVERY
        _run(jobs)

    assert len(record) == round(HOLD_FOR / HOLD_EVERY) + 1  # every 30 s for 10 minutes
    assert _states(conn, batch) == [("Pier.jpg", "failed")]
    problem = conn.execute("SELECT problem FROM jobs").fetchone()[0]
    assert problem.startswith("Pier.jpg was open in another app for 10 minutes")
    assert told.said[-1][0] == "Holiday prints didn't work"


def test_try_again_now_and_skip_it(paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path):
    clock = Clock(DAY)
    record: list[str] = []
    held = {"Pier.jpg", "Sail.jpg"}
    jobs = _jobs(paths, _held_on(held, tmp_path, record), now=clock)
    batch = _batch(jobs, conn, tmp_path, ["Pier.jpg", "Sail.jpg", "Dunes.jpg"])
    _run(jobs)
    ids = {
        Path(row["source"]).name: row["id"] for row in conn.execute("SELECT id, source FROM jobs")
    }

    held.discard("Pier.jpg")
    assert jobs.try_now(conn, ids["Pier.jpg"])
    assert jobs.skip(conn, ids["Sail.jpg"])
    _run(jobs)

    assert _states(conn, batch) == [
        ("Pier.jpg", "done"),
        ("Sail.jpg", "failed"),
        ("Dunes.jpg", "done"),
    ]
    skipped = conn.execute("SELECT problem FROM jobs WHERE id = ?", (ids["Sail.jpg"],)).fetchone()
    assert skipped[0].startswith("You skipped Sail.jpg while it was open in another app")
    assert not jobs.try_now(conn, ids["Dunes.jpg"])  # it wasn't waiting
    assert not jobs.skip(conn, ids["Dunes.jpg"])
    assert jobs.retry(conn, ids["Sail.jpg"])  # Try again, as for any that didn't work


def test_a_pictures_own_save_open_in_another_app_waits_without_holding_up_the_queue(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    clock = Clock(DAY)
    record: list[str] = []
    jobs = _jobs(paths, _held_on({"Rose.jpg"}, tmp_path, record), now=clock)
    own = jobs.add(conn, None, tmp_path / "Rose.jpg", {"recipe": {}, "saving": {}})
    _batch(jobs, conn, tmp_path, ["Pier.jpg"])

    _run(jobs)

    assert record == ["Rose.jpg", "Pier.jpg"]
    state = conn.execute("SELECT state, held_why FROM jobs WHERE id = ?", (own,)).fetchone()
    assert tuple(state) == ("queued", "replace")


def test_the_worker_rests_its_while_when_a_picture_due_again_cant_go_yet(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    clock = Clock(DAY)
    jobs = _jobs(paths, _made(tmp_path), now=clock)
    _batch(jobs, conn, tmp_path, ["Pier.jpg"])
    jobs.pause(conn)  # it waits all night, say
    with conn:
        conn.execute(
            "UPDATE jobs SET held_since = ?, held_until = ?",
            ((DAY - HOLD_EVERY * 3).isoformat(), (DAY - HOLD_EVERY).isoformat()),
        )
    assert jobs._rest() == 30.0  # pyright: ignore[reportPrivateUsage]

    with conn:
        conn.execute("UPDATE jobs SET held_until = ?", ((DAY + HOLD_EVERY / 3).isoformat(),))
    assert jobs._rest() == pytest.approx(10.0)  # pyright: ignore[reportPrivateUsage]


def test_a_picture_cancelled_as_it_was_found_open_in_another_app_stays_cancelled(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    def work(job_conn: sqlite3.Connection, row: sqlite3.Row, *_rest: object) -> Path:
        jobs.cancel(job_conn, row["id"])  # Cancel, clicked while it was read
        raise HeldError(Path(row["source"]).name, "read")

    jobs = _jobs(paths, work)
    own = jobs.add(conn, None, tmp_path / "Rose.jpg", {"recipe": {}, "saving": {}})

    _run(jobs)

    row = conn.execute("SELECT state, held_until FROM jobs WHERE id = ?", (own,)).fetchone()
    assert tuple(row) == ("cancelled", None)
