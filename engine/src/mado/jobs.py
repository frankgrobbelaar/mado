"""Jobs: making a picture, one at a time on a thread of its own, with its stage, how far it is,
the time left and Cancel. The queue of many pictures builds on this table next.

A job is a row in the jobs table with what to make and how to save it (its recipe, as JSON).
The worker takes the oldest waiting job, makes it (mado/making.py), and marks it done with the
picture saved, failed with a sentence saying why, or cancelled. A job Mado's closing (or a
crash) cut short is started again when the engine next starts, once; cut short twice, it's
marked failed rather than tried for ever. A picture half written is cleared away either way.

Saving writes History's line before it moves a picture, so a job cut short while saving is
finished or taken back by that line: done, when its picture was in place; otherwise an original
set aside goes back where it was and the line's forgotten, as if the job hadn't saved.
"""

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from mado import db, history
from mado.config import DataPaths
from mado.history import Entry
from mado.quarantine import MoveError, Quarantine
from mado.upscale import StoppedError

log = logging.getLogger(__name__)

type Stage = Literal["reading", "shaping", "making", "saving"]

PARTIAL = ".mado-partial"  # a picture being written, beside where it goes
_TRIES = 2  # starts a job gets, counting one Mado's closing cut short
_SHARE: dict[Stage, tuple[float, float]] = {  # each stage's part of a job's whole
    "reading": (0.0, 0.05),
    "shaping": (0.05, 0.2),
    "making": (0.2, 0.93),
    "saving": (0.93, 1.0),
}


@dataclass(frozen=True)
class Live:
    """A job under way, as the worker knows it now."""

    stage: Stage
    progress: float  # of the whole job, 0 to 1
    seconds_left: float | None


type Work = Callable[[sqlite3.Connection, sqlite3.Row, Callable[[Stage, float], None],
                      Callable[[], bool], Callable[[float], None]], Path]  # fmt: skip


class Jobs:
    def __init__(
        self,
        paths: DataPaths,
        work: Work,
        quarantine: Quarantine,
        *,
        now: Callable[[], datetime],
    ) -> None:
        """`work` makes one job's picture and says where it was saved: it's given the database,
        the job's row, where to report its stage and progress, whether to stop, and where to say
        how long it should take. `quarantine` is where a job cut short while saving left an
        original."""
        self._paths = paths
        self._work = work
        self._quarantine = quarantine
        self._now = now
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._cancelled: set[int] = set()
        self._live: dict[int, Live] = {}
        self._thread: threading.Thread | None = None
        self._idle = threading.Event()
        self._idle.set()

    def start(self) -> None:
        """Clears up after a job cut short, then works through what's waiting."""
        with closing(db.connect(self._paths.database)) as conn:
            recover(conn, self._now(), self._quarantine)
        self._thread = threading.Thread(target=self._loop, name="jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=15)

    def add(
        self, conn: sqlite3.Connection, picture_id: int | None, source: Path, recipe: object
    ) -> int:
        """Puts a job in line and wakes the worker. Returns its number."""
        with conn:
            row = conn.execute(
                """INSERT INTO jobs (kind, picture_id, source, recipe, state, queued_at)
                   VALUES ('make', ?, ?, ?, 'queued', ?) RETURNING id""",
                (picture_id, str(source), json.dumps(recipe), self._stamp()),
            ).fetchone()
        job_id: int = row["id"]
        self._idle.clear()
        self._wake.set()
        return job_id

    def cancel(self, conn: sqlite3.Connection, job_id: int) -> bool:
        """Cancels a job: one waiting at once, one under way at its next step (a tile, or before
        it saves). False when it's over already, or saving: a picture half moved helps no one."""
        row = conn.execute("SELECT state FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["state"] not in ("queued", "running"):
            return False
        with self._lock:
            live = self._live.get(job_id)
            if live is not None and live.stage == "saving":
                return False
        if row["state"] == "queued":
            with conn:
                conn.execute(
                    "UPDATE jobs SET state = 'cancelled', finished_at = ?"
                    " WHERE id = ? AND state = 'queued'",
                    (self._stamp(), job_id),
                )
        with self._lock:
            self._cancelled.add(job_id)
        return True

    def live(self, job_id: int) -> Live | None:
        with self._lock:
            return self._live.get(job_id)

    def busy(self) -> bool:
        """Whether a job is under way: the PC check then only checks, as timing would be off."""
        with self._lock:
            return bool(self._live)

    def wait(self, timeout: float | None = None) -> bool:
        """Till nothing's waiting or under way (tests). True when that's so."""
        return self._idle.wait(timeout)

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                worked = self._next()
            except Exception:  # the worker must outlive any one problem
                log.exception("A job hit a problem")
                worked = True
            if not worked:
                self._idle.set()
                self._wake.wait(30)
                self._wake.clear()

    def _next(self) -> bool:
        """Makes the oldest waiting job. False when none is waiting."""
        with closing(db.connect(self._paths.database)) as conn:
            # Taken in one statement, so a job cancelled as it's taken is never started.
            with conn:
                row = conn.execute(
                    """UPDATE jobs SET state = 'running', started_at = ?, attempts = attempts + 1,
                              stage = 'reading', progress = 0, problem = NULL
                       WHERE id = (SELECT id FROM jobs WHERE state = 'queued' ORDER BY id LIMIT 1)
                         AND state = 'queued'
                       RETURNING *""",
                    (self._stamp(),),
                ).fetchone()
            if row is None:
                return False
            self._run(conn, row)
        return True

    def _run(self, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        job_id: int = row["id"]
        began = time.monotonic()
        expected: list[float] = []

        def report(stage: Stage, within: float) -> None:
            low, high = _SHARE[stage]
            progress = low + (high - low) * min(max(within, 0.0), 1.0)
            with self._lock:
                self._live[job_id] = Live(stage, progress, _left(began, progress, expected))

        def stop() -> bool:
            with self._lock:
                live = self._live.get(job_id)
                if live is not None and live.stage == "saving":
                    return False  # past cancelling, and past stopping: it's moments
                return job_id in self._cancelled or self._stopping.is_set()

        report("reading", 0.0)
        try:
            result = self._work(conn, row, report, stop, expected.append)
        except StoppedError:
            self._finish(conn, job_id, "cancelled" if not self._stopping.is_set() else "queued")
        except Exception as error:
            if not isinstance(error, JobError):
                log.exception("Making job %d's picture failed", job_id)
            self._finish(conn, job_id, "failed", problem=_sentence(error))
        else:
            self._finish(conn, job_id, "done", result=result)
        finally:
            with self._lock:
                self._live.pop(job_id, None)
                self._cancelled.discard(job_id)

    def _finish(
        self,
        conn: sqlite3.Connection,
        job_id: int,
        state: str,
        *,
        result: Path | None = None,
        problem: str | None = None,
    ) -> None:
        clear_partial(conn, job_id)
        with conn:
            conn.execute(
                """UPDATE jobs SET state = ?, finished_at = ?, problem = ?,
                          result = COALESCE(?, CASE WHEN ? = 'done' THEN result END),
                          progress = CASE WHEN ? = 'done' THEN 1 ELSE progress END
                   WHERE id = ?""",
                (
                    state,
                    None if state == "queued" else self._stamp(),
                    problem,
                    str(result) if result else None,
                    state,
                    state,
                    job_id,
                ),
            )

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")


class JobError(Exception):
    """A job that can't be made, with a sentence for the owner (nothing went wrong in Mado)."""


def note_writing(conn: sqlite3.Connection, job_id: int, partial: Path) -> None:
    """The file a job is writing its picture to, so a job cut short can clear it away."""
    with conn:
        conn.execute("UPDATE jobs SET result = ? WHERE id = ?", (str(partial), job_id))


def clear_partial(conn: sqlite3.Connection, job_id: int) -> None:
    """Clears away a picture a job left half written: only a file Mado names as its own."""
    row = conn.execute("SELECT result FROM jobs WHERE id = ?", (job_id,)).fetchone()
    found = row["result"] if row else None
    if found and str(found).endswith(PARTIAL):
        try:
            Path(found).unlink(missing_ok=True)
        except OSError as error:
            log.warning("Mado couldn't clear away %s: %s", found, error)
        with conn:
            conn.execute("UPDATE jobs SET result = NULL WHERE id = ?", (job_id,))


def recover(conn: sqlite3.Connection, now: datetime, quarantine: Quarantine) -> None:
    """After Mado closed (or crashed) mid-job: a job whose picture was saved marked done; else
    what its saving began taken back, its half-written picture cleared away, and the job started
    again, unless that's happened before."""
    stamp = now.isoformat(timespec="seconds")
    rows = conn.execute("SELECT id, attempts, result FROM jobs WHERE state = 'running'").fetchall()
    for row in rows:
        job_id: int = row["id"]
        line = history.for_job(conn, job_id)
        problem = _CUT_SHORT if row["attempts"] >= _TRIES else None
        if line is not None:
            if _saved(line, row["result"]):
                with conn:
                    conn.execute(
                        "UPDATE jobs SET state = 'done', finished_at = ?, result = ?,"
                        " progress = 1 WHERE id = ?",
                        (stamp, line.result, job_id),
                    )
                continue
            if not _taken_back(conn, quarantine, line):
                problem = _LEFT_ASIDE
        clear_partial(conn, job_id)
        with conn:
            if problem is not None:
                conn.execute(
                    "UPDATE jobs SET state = 'failed', finished_at = ?, problem = ? WHERE id = ?",
                    (stamp, problem, job_id),
                )
            else:
                conn.execute("UPDATE jobs SET state = 'queued' WHERE id = ?", (job_id,))


def _saved(line: Entry, writing: str | None) -> bool:
    """Whether a job's picture got to its place before Mado stopped: it's there, no longer half
    written beside it, and an original it replaced is set aside."""
    if not line.result or not Path(line.result).exists():
        return False
    if writing and str(writing).endswith(PARTIAL) and Path(writing).exists():
        return False
    return line.kind != "replaced" or bool(line.aside and Path(line.aside).exists())


def _taken_back(conn: sqlite3.Connection, quarantine: Quarantine, line: Entry) -> bool:
    """What a job's saving began, taken back: an original set aside put back where it was, and
    the line forgotten. False when the original can't go back, so the line stays for History
    to put it back from."""
    if line.kind == "replaced" and line.aside and line.original and Path(line.aside).exists():
        try:
            quarantine.put_back(Path(line.aside), Path(line.original))
        except MoveError as error:
            log.warning("Mado couldn't put %s back: %s", line.original, error)
            return False
    history.forget(conn, line.id)
    return True


_CUT_SHORT = (
    "Mado stopped twice while making this one, so it stopped trying. Nothing was saved and the "
    "original is as it was. Try again; if it stops again, try Fast."
)
_LEFT_ASIDE = (
    "Mado stopped while saving this one, and its original waits in quarantine: History puts it "
    "back."
)


def _left(began: float, progress: float, expected: list[float]) -> float | None:
    """Seconds left: by the estimate at first, then by the pace so far."""
    elapsed = time.monotonic() - began
    guess = expected[-1] - elapsed if expected else None
    if progress < 0.1 or elapsed < 1.0:
        return max(guess, 1.0) if guess is not None else None
    paced = elapsed / progress - elapsed
    return max(paced if guess is None else (paced + guess) / 2, 0.0)


def _sentence(error: Exception) -> str:
    """What the owner reads about a job that failed: a JobError's own sentence; anything else
    went wrong inside Mado, and its own words (in the log) would mean nothing to them."""
    said = str(error).strip()
    if isinstance(error, JobError) and said:
        return said
    if isinstance(error, MemoryError):
        return (
            "There wasn't enough memory to make it this big, so nothing was saved and the "
            "original is as it was. Close other apps, or pick a smaller size."
        )
    return (
        "Mado couldn't make it: something went wrong inside Mado, so nothing was saved and "
        "the original is as it was. Try again; Mado's log says what happened."
    )
