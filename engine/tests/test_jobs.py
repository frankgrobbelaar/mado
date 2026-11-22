"""Jobs: one at a time on a thread of their own, with progress and Cancel, and what's done about
a job Mado's closing cut short."""

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PIL import Image

from mado import history
from mado.config import DataPaths
from mado.jobs import JobError, Jobs, Stage, clear_partial, note_writing, recover
from mado.quarantine import Quarantine
from mado.upscale import StoppedError
from tests.drawn import draw

NOW = datetime(2026, 11, 22, 11, 20).astimezone()
type Report = Callable[[Stage, float], None]


def _jobs(paths: DataPaths, work: Callable[..., Path]) -> Jobs:
    return Jobs(paths, work, Quarantine(lambda _picture: paths.root / "q"), now=lambda: NOW)


def _add(jobs: Jobs, conn: sqlite3.Connection, tmp_path: Path) -> int:
    return jobs.add(
        conn, None, tmp_path / "Pier.jpg", {"recipe": {}, "saving": {}, "label": "TV 8K"}
    )


def test_a_job_is_made_and_marked_done_with_the_picture_saved(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    stages: list[str] = []

    def work(
        _conn: sqlite3.Connection,
        _row: sqlite3.Row,
        report: Report,
        _stop: Callable[[], bool],
        expect: Callable[[float], None],
    ) -> Path:
        expect(10.0)
        order: tuple[Stage, ...] = ("reading", "making", "saving")
        for stage in order:
            report(stage, 0.5)
            stages.append(stage)
        return tmp_path / "Pier (TV 8K).jpg"

    jobs = _jobs(paths, work)
    jobs.start()
    try:
        job = _add(jobs, conn, tmp_path)
        assert jobs.wait(10)
    finally:
        jobs.stop()

    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job,)).fetchone()
    assert row["state"] == "done"
    assert row["result"] == str(tmp_path / "Pier (TV 8K).jpg")
    assert row["progress"] == 1
    assert stages == ["reading", "making", "saving"]


def test_a_job_that_cant_be_made_says_why(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    def work(*_args: object) -> Path:
        raise JobError("Pier.jpg isn't there any more.")

    jobs = _jobs(paths, work)
    jobs.start()
    try:
        job = _add(jobs, conn, tmp_path)
        assert jobs.wait(10)
    finally:
        jobs.stop()

    row = conn.execute("SELECT state, problem FROM jobs WHERE id = ?", (job,)).fetchone()
    assert (row["state"], row["problem"]) == ("failed", "Pier.jpg isn't there any more.")


def test_cancelling_stops_a_job_at_its_next_tile_and_clears_its_half_written_picture(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    partial = tmp_path / "Pier (TV 8K).jpg.mado-partial"
    jobs_box: list[Jobs] = []

    def work(
        conn_: sqlite3.Connection,
        row: sqlite3.Row,
        _report: Report,
        stop: Callable[[], bool],
        _expect: Callable[[float], None],
    ) -> Path:
        partial.write_bytes(b"half")
        note_writing(conn_, row["id"], partial)
        jobs_box[0].cancel(conn_, row["id"])
        if stop():
            raise StoppedError
        return partial

    jobs = _jobs(paths, work)
    jobs_box.append(jobs)
    jobs.start()
    try:
        job = _add(jobs, conn, tmp_path)
        assert jobs.wait(10)
    finally:
        jobs.stop()

    row = conn.execute("SELECT state, result FROM jobs WHERE id = ?", (job,)).fetchone()
    assert row["state"] == "cancelled"
    assert row["result"] is None
    assert not partial.exists()


def test_a_waiting_job_is_cancelled_at_once(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    jobs = _jobs(paths, lambda *_args: tmp_path)  # not started: nothing takes it
    job = _add(jobs, conn, tmp_path)

    assert jobs.cancel(conn, job)
    assert conn.execute("SELECT state FROM jobs WHERE id = ?", (job,)).fetchone()[0] == (
        "cancelled"
    )
    assert not jobs.cancel(conn, job)  # over already


def test_a_job_cut_short_starts_again_once_then_says_why_it_stopped(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    partial = tmp_path / "Pier (TV 8K).jpg.mado-partial"
    partial.write_bytes(b"half")
    jobs = _jobs(paths, lambda *_args: tmp_path)
    job = _add(jobs, conn, tmp_path)
    with conn:
        conn.execute(
            "UPDATE jobs SET state = 'running', attempts = 1, result = ? WHERE id = ?",
            (str(partial), job),
        )

    recover(conn, NOW, Quarantine())
    assert conn.execute("SELECT state FROM jobs WHERE id = ?", (job,)).fetchone()[0] == "queued"
    assert not partial.exists()

    with conn:
        conn.execute("UPDATE jobs SET state = 'running', attempts = 2 WHERE id = ?", (job,))
    recover(conn, NOW, Quarantine())
    row = conn.execute("SELECT state, problem FROM jobs WHERE id = ?", (job,)).fetchone()
    assert row["state"] == "failed"
    assert "stopped twice" in row["problem"]


def test_only_a_file_mado_names_as_its_own_is_cleared_away(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    keep = tmp_path / "Pier.jpg"
    keep.write_bytes(b"the owner's")
    jobs = _jobs(paths, lambda *_args: tmp_path)
    job = _add(jobs, conn, tmp_path)
    note_writing(conn, job, keep)  # a damaged record

    clear_partial(conn, job)

    assert keep.exists()


def _running(jobs: Jobs, conn: sqlite3.Connection, tmp_path: Path, partial: Path) -> int:
    """A job that was saving its picture when Mado stopped."""
    job = _add(jobs, conn, tmp_path)
    with conn:
        conn.execute(
            "UPDATE jobs SET state = 'running', attempts = 1, stage = 'saving', result = ?"
            " WHERE id = ?",
            (str(partial), job),
        )
    return job


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _state(conn: sqlite3.Connection, job: int) -> tuple[str, str | None]:
    row = conn.execute("SELECT state, result FROM jobs WHERE id = ?", (job,)).fetchone()
    return row["state"], row["result"]


def test_a_replace_cut_short_before_its_picture_went_in_puts_the_original_back(
    paths: DataPaths, conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    original = draw(tmp_path / "Pier.jpg", size=(64, 48))
    partial = draw(tmp_path / "Pier.jpg.mado-partial", size=(80, 60), format="JPEG")
    job = _running(_jobs(paths, lambda *_args: tmp_path), conn, tmp_path, partial)
    aside = quarantine.set_aside(original, NOW)
    history.replaced(
        conn,
        now=NOW,
        job_id=job,
        name=original.name,
        made_for="TV 8K",
        original=original,
        result=original,
        aside=aside,
    )

    recover(conn, NOW, quarantine)

    assert _size(original) == (64, 48)  # the original, in its place again
    assert not aside.exists()
    assert not partial.exists()
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 0
    assert _state(conn, job) == ("queued", None)


def test_a_replace_cut_short_once_its_picture_was_in_is_done_not_made_again(
    paths: DataPaths, conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    original = draw(tmp_path / "Pier.jpg", size=(64, 48))
    partial = tmp_path / "Pier.jpg.mado-partial"
    job = _running(_jobs(paths, lambda *_args: tmp_path), conn, tmp_path, partial)
    aside = quarantine.set_aside(original, NOW)
    history.replaced(
        conn,
        now=NOW,
        job_id=job,
        name=original.name,
        made_for="TV 8K",
        original=original,
        result=original,
        aside=aside,
    )
    draw(original, size=(80, 60))  # the made picture, in the original's place

    recover(conn, NOW, quarantine)

    assert _state(conn, job) == ("done", str(original))
    assert _size(original) == (80, 60)
    assert _size(aside) == (64, 48)
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 1


def test_a_replace_cut_short_before_the_original_moved_starts_again(
    paths: DataPaths, conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    original = draw(tmp_path / "Pier.jpg", size=(64, 48))
    partial = draw(tmp_path / "Pier.jpg.mado-partial", size=(80, 60), format="JPEG")
    job = _running(_jobs(paths, lambda *_args: tmp_path), conn, tmp_path, partial)
    history.replaced(
        conn,
        now=NOW,
        job_id=job,
        name=original.name,
        made_for="TV 8K",
        original=original,
        result=original,
        aside=quarantine.place(original, NOW),  # where it was about to go
    )

    recover(conn, NOW, quarantine)

    assert _size(original) == (64, 48)
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 0
    assert _state(conn, job) == ("queued", None)


def test_a_new_picture_cut_short_before_it_went_in_leaves_no_line(
    paths: DataPaths, conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    original = draw(tmp_path / "Pier.jpg")
    target = tmp_path / "Pier (TV 8K).jpg"
    partial = draw(tmp_path / "Pier (TV 8K).jpg.mado-partial", format="JPEG")
    job = _running(_jobs(paths, lambda *_args: tmp_path), conn, tmp_path, partial)
    history.made(
        conn,
        now=NOW,
        job_id=job,
        name=original.name,
        made_for="TV 8K",
        original=original,
        result=target,
    )

    recover(conn, NOW, quarantine)

    assert not target.exists()
    assert not partial.exists()
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 0
    assert _state(conn, job) == ("queued", None)


def test_a_new_picture_cut_short_once_in_place_is_done_not_made_again(
    paths: DataPaths, conn: sqlite3.Connection, quarantine: Quarantine, tmp_path: Path
):
    original = draw(tmp_path / "Pier.jpg")
    target = draw(tmp_path / "Pier (TV 8K).jpg")
    partial = tmp_path / "Pier (TV 8K).jpg.mado-partial"
    jobs = _jobs(paths, lambda *_args: tmp_path)
    job = _running(jobs, conn, tmp_path, partial)
    with conn:
        conn.execute("UPDATE jobs SET attempts = 2 WHERE id = ?", (job,))  # its last try
    history.made(
        conn,
        now=NOW,
        job_id=job,
        name=original.name,
        made_for="TV 8K",
        original=original,
        result=target,
    )

    recover(conn, NOW, quarantine)

    assert _state(conn, job) == ("done", str(target))
    assert target.is_file()


def test_a_job_saving_its_picture_is_past_cancelling(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    answers: list[bool] = []
    jobs_box: list[Jobs] = []

    def work(
        conn_: sqlite3.Connection,
        row: sqlite3.Row,
        report: Report,
        stop: Callable[[], bool],
        _expect: Callable[[float], None],
    ) -> Path:
        report("saving", 0.0)
        answers.append(jobs_box[0].cancel(conn_, row["id"]))
        answers.append(stop())
        return tmp_path / "Pier (TV 8K).jpg"

    jobs = _jobs(paths, work)
    jobs_box.append(jobs)
    jobs.start()
    try:
        job = _add(jobs, conn, tmp_path)
        assert jobs.wait(10)
    finally:
        jobs.stop()

    assert answers == [False, False]
    assert _state(conn, job) == ("done", str(tmp_path / "Pier (TV 8K).jpg"))


def test_a_fault_inside_mado_is_told_plainly_not_in_pythons_words(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    def work(*_args: object) -> Path:
        raise IndexError("list index out of range")

    jobs = _jobs(paths, work)
    jobs.start()
    try:
        job = _add(jobs, conn, tmp_path)
        assert jobs.wait(10)
    finally:
        jobs.stop()

    problem = conn.execute("SELECT problem FROM jobs WHERE id = ?", (job,)).fetchone()[0]
    assert "index" not in problem
    assert problem.startswith("Mado couldn't make it")
    assert "the original is as it was" in problem
