"""Jobs and the queue: making a picture, one at a time on a thread of its own, with its stage, how
far it is, the time left and Cancel; and batches, many pictures made one after another in the
queue's order (docs/stack/queue.md).

A job is a row in the jobs table with what to make and how to save it (its recipe, as JSON). A
picture's own Save goes first; then the queue's: each batch's pictures by their place in it
(`position`), a batch put in "now" ahead of what waits, one "after what's in the queue" behind
it, and one for tonight only from 23:00 till 07:00 (the picture being made at 07:00 finishes).
The worker makes each (mado/making.py) and marks it done with the picture saved, failed with a
sentence saying why, or cancelled. Before the queue it does See it first's pictures, when any
wait (`first`). While it makes a batch's picture, Windows doesn't put the PC to sleep.

Pausing stops the picture being made at its next tile and puts it back first in line, and
starts no other batch's picture till the queue resumes; a picture's own Save still goes. A
picture whose drive (or the folder it saves into) isn't connected waits while the others go. So
does one open in another app, which Mado can't read or replace: it's tried again by itself every
30 seconds for 10 minutes (HOLD_EVERY, HOLD_FOR) before it counts as not working, and the owner
can try it again now or skip it. A drive without room for the next picture pauses the queue,
saying what it needs, and the queue carries on by itself once there's room; or it makes what
fits there while the rest wait. Once nothing of a batch waits, Mado tells the owner what it came
to (`notify`).

A job Mado's crashing cut short is started again when the engine next starts, once; cut short
twice, it's marked failed rather than tried for ever (a clean stop, like a pause, puts it back
in line without counting). A picture half written is cleared away either way. Saving writes
History's line before it moves a picture, so a job cut short while saving is finished or taken
back by that line: done, when its picture was in place; otherwise an original set aside goes
back where it was and the line's forgotten, as if the job hadn't saved.
"""

import ctypes
import json
import logging
import shutil
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Literal, cast

from mado import db, history
from mado.config import DataPaths
from mado.core.batch import MARGIN, Starts, fits, may_start, starts_of, told
from mado.events import Notify
from mado.history import Entry
from mado.quarantine import MoveError, Quarantine
from mado.upscale import StoppedError

log = logging.getLogger(__name__)

type Stage = Literal["reading", "editing", "shaping", "fixing", "making", "looking", "saving"]
type Where = Literal["next", "last"]

PARTIAL = ".mado-partial"  # a picture being written, beside where it goes
_TRIES = 2  # starts a job gets, counting one a crash cut short
_IDLE = 30.0  # seconds the worker rests with nothing to do; a change wakes it at once
_PAUSED = "queue_paused"  # the settings rows the queue keeps across restarts
_ROOM = "queue_room"  # {"drive": "D:", "fit": bool}: a drive without room, and what to do
_ROOM_MADE = 64 * 1024 * 1024  # bytes more than when a drive filled up before it's tried again
HOLD_EVERY = timedelta(seconds=30)  # a picture open in another app is tried again this often
HOLD_FOR = timedelta(minutes=10)  # and for this long, before it counts as not working
_SHARE: dict[Stage, tuple[float, float]] = {  # each stage's part of a job's whole
    "reading": (0.0, 0.05),
    "editing": (0.05, 0.12),
    "shaping": (0.12, 0.22),
    "fixing": (0.22, 0.22),
    "making": (0.22, 0.85),
    "looking": (0.85, 0.93),
    "saving": (0.93, 1.0),
}
# A job with fixes: they take the first part of making's, as they take about as long; all of it
# when nothing is made bigger.
_FIXED_SHARE: dict[Stage, tuple[float, float]] = {
    **_SHARE,
    "fixing": (0.22, 0.45),
    "making": (0.45, 0.85),
}
_ONLY_FIXED_SHARE: dict[Stage, tuple[float, float]] = {
    **_SHARE,
    "fixing": (0.22, 0.85),
    "making": (0.85, 0.85),
}


@dataclass(frozen=True)
class Live:
    """A job under way, as the worker knows it now."""

    stage: Stage
    progress: float  # of the whole job, 0 to 1
    seconds_left: float | None


@dataclass(frozen=True)
class NewBatch:
    """A batch about to join the queue."""

    name: str  # "Holiday prints"
    source: str  # where its pictures came from: "Holiday"
    shared: str | None  # the folder they share, when they do
    steps: dict[str, object]  # its steps and how it saves, as the recipes table keeps them
    starts: Starts
    recipe_id: int | None = None
    watch_id: int | None = None
    seen_first: bool = False


type Work = Callable[[sqlite3.Connection, sqlite3.Row, Callable[[Stage, float], None],
                      Callable[[], bool], Callable[[float], None]], Path]  # fmt: skip
type First = Callable[[Callable[[], bool]], bool]  # work before the queue's: True when it did some


class Jobs:
    def __init__(
        self,
        paths: DataPaths,
        work: Work,
        quarantine: Quarantine,
        *,
        now: Callable[[], datetime],
        notify: Notify = lambda _title, _body, link=None: None,
        connected: Callable[[Path], bool] | None = None,
        free: Callable[[Path], int | None] | None = None,
    ) -> None:
        """`work` makes one job's picture and says where it was saved: it's given the database,
        the job's row, where to report its stage and progress, whether to stop, and where to say
        how long it should take. `quarantine` is where a job cut short while saving left an
        original. `notify` tells the owner what a batch came to; `connected` says whether a
        path's drive is there, and `free` how many bytes are free where a picture is saved
        (tests pass their own)."""
        self._paths = paths
        self._work = work
        self._quarantine = quarantine
        self._now = now
        self._notify = notify
        self._connected = connected or drive_there
        self._free = free or _free
        self._first: First | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._cancelled: set[int] = set()
        self._pausing: set[int] = set()
        self._live: dict[int, Live] = {}
        self._thread: threading.Thread | None = None
        self._idle = threading.Event()
        self._idle.set()
        self._asked = 0  # changes asked for: the worker rests only once it has seen them all
        self._sampling = False

    def before_the_queue(self, first: First) -> None:
        """Work the worker does before the queue's, when there is some: See it first's."""
        self._first = first

    def start(self) -> None:
        """Clears up after a job cut short, then works through what's waiting."""
        with closing(db.connect(self._paths.database)) as conn:
            recover(conn, self._now(), self._quarantine)
            self.settle_all(conn)
        self._stopping.clear()
        self._idle.clear()
        self._thread = threading.Thread(target=self._loop, name="jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=15)

    def wake(self) -> None:
        """Looks for work now rather than at the next look: something changed."""
        with self._lock:
            self._asked += 1
            self._idle.clear()
        self._wake.set()

    def add(
        self, conn: sqlite3.Connection, picture_id: int | None, source: Path, recipe: object
    ) -> int:
        """Puts a picture's own job in line, ahead of the queue, and wakes the worker. Returns
        its number."""
        with conn:
            row = conn.execute(
                """INSERT INTO jobs (kind, picture_id, source, recipe, state, queued_at, position)
                   VALUES ('make', ?, ?, ?, 'queued', ?, ?) RETURNING id""",
                (picture_id, str(source), json.dumps(recipe), self._stamp(), _front(conn, 1)),
            ).fetchone()
        job_id: int = row["id"]
        self.wake()
        return job_id

    def add_batch(
        self,
        conn: sqlite3.Connection,
        batch: NewBatch,
        pictures: Sequence[tuple[int | None, Path, int, dict[str, object]]],
    ) -> int:
        """Puts a batch in the queue: each picture (its library id, its file, its bytes and its
        job's order) a job, in the order given; "now" ahead of what waits, else behind it.
        Returns the batch's number."""
        stamp = self._stamp()
        with conn:
            batch_id: int = conn.execute(
                """INSERT INTO batches (name, source, shared, recipe_id, watch_id, steps,
                                        seen_first, starts, added_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    batch.name,
                    batch.source,
                    batch.shared,
                    batch.recipe_id,
                    batch.watch_id,
                    json.dumps(batch.steps),
                    int(batch.seen_first),
                    batch.starts,
                    stamp,
                ),
            ).fetchone()[0]
            first = (
                _front(conn, len(pictures)) if batch.starts == "now" else _back(conn)
            )  # fmt: skip
            conn.executemany(
                """INSERT INTO jobs (kind, picture_id, source, recipe, state, queued_at, position,
                                     batch_id, bytes)
                   VALUES ('make', ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                [
                    (picture_id, str(path), json.dumps(order), stamp, first + at, batch_id, size)
                    for at, (picture_id, path, size, order) in enumerate(pictures)
                ],
            )
        self.wake()
        return batch_id

    def join(
        self,
        conn: sqlite3.Connection,
        batch_id: int,
        pictures: Sequence[tuple[int | None, Path, int, dict[str, object]]],
    ) -> None:
        """More pictures for a batch not yet done (a watch folder's), at the end of the queue."""
        stamp = self._stamp()
        with conn:
            first = _back(conn)
            conn.executemany(
                """INSERT INTO jobs (kind, picture_id, source, recipe, state, queued_at, position,
                                     batch_id, bytes)
                   VALUES ('make', ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                [
                    (picture_id, str(path), json.dumps(order), stamp, first + at, batch_id, size)
                    for at, (picture_id, path, size, order) in enumerate(pictures)
                ],
            )
            conn.execute("UPDATE batches SET finished_at = NULL WHERE id = ?", (batch_id,))
        self.wake()

    def cancel(self, conn: sqlite3.Connection, job_id: int) -> bool:
        """Cancels a job: one waiting at once, one under way at its next step (a tile, or before
        it saves). False when it's over already, or saving: a picture half moved helps no one."""
        row = conn.execute("SELECT state, batch_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["state"] not in ("queued", "running"):
            return False
        with self._lock:
            live = self._live.get(job_id)
            if live is not None and live.stage == "saving":
                return False
        if row["state"] == "queued":
            with conn:
                waited = conn.execute(
                    "UPDATE jobs SET state = 'cancelled', finished_at = ?, held_since = NULL,"
                    " held_until = NULL, held_why = NULL WHERE id = ? AND state = 'queued'",
                    (self._stamp(), job_id),
                ).rowcount
            if waited:  # it never started: nothing to stop, and a try again starts it afresh
                if row["batch_id"] is not None:
                    self._settle(conn, row["batch_id"])
                return True
        with self._lock:  # under way (or started as it was cancelled): stopped at its next step
            self._cancelled.add(job_id)
        return True

    def cancel_all(self, conn: sqlite3.Connection) -> int:
        """Cancels the queue: every batch's picture waiting, and the one being made (at its next
        tile). A picture's own Save goes on. Returns how many were cancelled."""
        stamp = self._stamp()
        with conn:
            waiting = conn.execute(
                """UPDATE jobs SET state = 'cancelled', finished_at = ?, held_since = NULL,
                          held_until = NULL, held_why = NULL
                   WHERE state = 'queued' AND batch_id IS NOT NULL RETURNING batch_id""",
                (stamp,),
            ).fetchall()
            running = conn.execute(
                "SELECT id, batch_id FROM jobs WHERE state = 'running' AND batch_id IS NOT NULL"
            ).fetchall()
            batches = {row["batch_id"] for row in [*waiting, *running]}
            conn.executemany(
                "UPDATE batches SET seen_at = COALESCE(seen_at, ?) WHERE id = ?",
                [(stamp, batch_id) for batch_id in batches],
            )
        stopping = 0
        with self._lock:
            for row in running:
                live = self._live.get(row["id"])
                if live is None or live.stage != "saving":  # one saving is past cancelling
                    self._cancelled.add(row["id"])
                    stopping += 1
        for batch_id in batches:
            self._settle(conn, batch_id)
        self.wake()
        return len(waiting) + stopping

    def pause(self, conn: sqlite3.Connection) -> None:
        """Stops the batch's picture being made at its next tile, first in line again, and starts
        no other batch's picture till `resume`."""
        _save(conn, _PAUSED, value=True)
        running = conn.execute(
            "SELECT id FROM jobs WHERE state = 'running' AND batch_id IS NOT NULL"
        ).fetchall()
        with self._lock:
            self._pausing.update(row["id"] for row in running)

    def resume(self, conn: sqlite3.Connection) -> None:
        """Goes on with the queue, and looks again for room on a drive without it. A picture a
        pause hadn't stopped yet goes on."""
        _save(conn, _PAUSED, value=False)
        _save(conn, _ROOM, value=None)
        with self._lock:
            self._pausing.clear()
        self.wake()

    def paused(self, conn: sqlite3.Connection) -> bool:
        return _setting(conn, _PAUSED) is True

    def short_of_room(self, conn: sqlite3.Connection) -> dict[str, object] | None:
        """The drive without room for the next picture, and whether what fits there is being
        made while the rest wait (`fit`)."""
        found = _setting(conn, _ROOM)
        if not isinstance(found, dict):
            return None
        room = cast("dict[str, object]", found)
        drive = room.get("drive")
        return {"drive": drive, "fit": room.get("fit") is True} if isinstance(drive, str) else None

    def fit(self, conn: sqlite3.Connection, drive: str) -> None:
        """On a drive without room, the pictures that fit are made and the rest wait for room,
        while the queue goes on."""
        _save(conn, _ROOM, value={"drive": drive, "fit": True})
        _save(conn, _PAUSED, value=False)
        self.wake()

    def move(self, conn: sqlite3.Connection, job_ids: Iterable[int], where: Where) -> int:
        """Ticked pictures waiting in the queue go next, or to the end, together, in the order
        they wait in. Returns how many moved."""
        wanted = set(job_ids)
        with conn:
            moving = [
                row["id"]
                for row in conn.execute(
                    """SELECT id FROM jobs WHERE state = 'queued' AND batch_id IS NOT NULL
                       ORDER BY position, id"""
                )
                if row["id"] in wanted
            ]
            start = _front(conn, len(moving)) if where == "next" else _back(conn)
            conn.executemany(
                "UPDATE jobs SET position = ? WHERE id = ?",
                [(start + at, job_id) for at, job_id in enumerate(moving)],
            )
        self.wake()
        return len(moving)

    def remove(self, conn: sqlite3.Connection, job_ids: Iterable[int]) -> int:
        """Takes ticked pictures waiting in the queue out of it, as if they'd never been put in;
        a batch with nothing left goes too. Returns how many went."""
        wanted = list(dict.fromkeys(job_ids))
        with conn:
            gone = [
                row["batch_id"]
                for job_id in wanted
                for row in conn.execute(
                    """DELETE FROM jobs WHERE id = ? AND state = 'queued'
                       AND batch_id IS NOT NULL RETURNING batch_id""",
                    (job_id,),
                )
            ]
            for batch_id in set(gone):
                conn.execute(
                    """DELETE FROM batches WHERE id = ?
                       AND NOT EXISTS (SELECT 1 FROM jobs WHERE batch_id = ?)""",
                    (batch_id, batch_id),
                )
        for batch_id in set(gone):
            self._settle(conn, batch_id)
        return len(gone)

    def retry(self, conn: sqlite3.Connection, job_id: int) -> bool:
        """A batch's picture that didn't work (or was cancelled) goes back in the queue, at its
        end. False when it isn't one."""
        with conn:
            row = conn.execute(
                """UPDATE jobs SET state = 'queued', position = ?, problem = NULL, result = NULL,
                          attempts = 0, started_at = NULL, finished_at = NULL, stage = NULL,
                          progress = 0, made_bytes = NULL, held_since = NULL, held_until = NULL,
                          held_why = NULL
                   WHERE id = ? AND state IN ('failed', 'cancelled') AND batch_id IS NOT NULL
                   RETURNING batch_id""",
                (_back(conn), job_id),
            ).fetchone()
            if row is not None:  # done again, it's told and on Home again
                conn.execute(
                    "UPDATE batches SET finished_at = NULL, seen_at = NULL, cleared_at = NULL"
                    " WHERE id = ?",
                    (row["batch_id"],),
                )
        if row is None:
            return False
        with self._lock:  # a cancel or pause it had is over: it starts afresh
            self._cancelled.discard(job_id)
            self._pausing.discard(job_id)
        self.wake()
        return True

    def try_now(self, conn: sqlite3.Connection, job_id: int) -> bool:
        """A picture waiting while it's open in another app is tried again now, its ten minutes
        afresh. False when it isn't waiting so."""
        with conn:
            tried = conn.execute(
                """UPDATE jobs SET held_until = NULL, held_since = ?
                   WHERE id = ? AND state = 'queued' AND held_since IS NOT NULL""",
                (self._stamp(), job_id),
            ).rowcount
        if tried:
            self.wake()
        return bool(tried)

    def skip(self, conn: sqlite3.Connection, job_id: int) -> bool:
        """A picture waiting while it's open in another app isn't made after all: it's left as it
        is, and counts as not working, to try again later. The others go on."""
        row = conn.execute(
            "SELECT source, batch_id FROM jobs WHERE id = ? AND state = 'queued'"
            " AND held_since IS NOT NULL",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        with conn:
            skipped = conn.execute(
                """UPDATE jobs SET state = 'failed', finished_at = ?, problem = ?,
                          held_since = NULL, held_until = NULL, held_why = NULL
                   WHERE id = ? AND state = 'queued' AND held_since IS NOT NULL""",
                (self._stamp(), _skipped(Path(row["source"]).name), job_id),
            ).rowcount
        if not skipped:  # taken to be made as it was skipped: it goes on
            return False
        if row["batch_id"] is not None:
            self._settle(conn, row["batch_id"])
        self.wake()
        return True

    def waiting(self, conn: sqlite3.Connection) -> int:
        """Batches' pictures waiting in the queue."""
        found: int = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE state = 'queued' AND batch_id IS NOT NULL"
        ).fetchone()[0]
        return found

    def batch_progress(self, conn: sqlite3.Connection, batch_id: int) -> tuple[int, int]:
        """A batch's pictures over (made, or didn't work), of all it holds but those cancelled."""
        row = conn.execute(
            """SELECT COUNT(*) FILTER (WHERE state IN ('done', 'failed')) AS over,
                      COUNT(*) FILTER (WHERE state <> 'cancelled') AS whole
               FROM jobs WHERE batch_id = ?""",
            (batch_id,),
        ).fetchone()
        return row["over"], row["whole"]

    def settle_all(self, conn: sqlite3.Connection) -> None:
        """Every batch with nothing left waiting marked done, and told: one whose last picture
        was made as Mado stopped."""
        for row in conn.execute("SELECT id FROM batches WHERE finished_at IS NULL").fetchall():
            self._settle(conn, row["id"])

    def live(self, job_id: int) -> Live | None:
        with self._lock:
            return self._live.get(job_id)

    def busy(self) -> bool:
        """Whether a job is under way: the PC check then only checks, as timing would be off."""
        with self._lock:
            return bool(self._live) or self._sampling

    def wait(self, timeout: float | None = None) -> bool:
        """Till nothing's waiting that can be made now, or under way (tests). True when so."""
        return self._idle.wait(timeout)

    def _loop(self) -> None:
        while not self._stopping.is_set():
            with self._lock:
                seen = self._asked
            try:
                worked = self._next()
            except Exception:  # the worker must outlive any one problem
                log.exception("A job hit a problem")
                worked = True
            if not worked:
                with self._lock:
                    if self._asked == seen:  # nothing was asked for meanwhile
                        self._idle.set()
                self._wake.wait(self._rest())
                self._wake.clear()

    def _next(self) -> bool:
        """Makes a picture's own Save first, then See it first's next picture, then the next job
        the queue can make now. False when there was nothing to do."""
        if self._first is not None and not self._own_waits():
            with self._lock:
                self._sampling = True
            try:
                if self._first(self._stopping.is_set):
                    return True
            finally:
                with self._lock:
                    self._sampling = False
        with closing(db.connect(self._paths.database)) as conn:
            row = None
            for _ in range(5):  # one cancelled or taken out as it's chosen: the next one
                chosen = self._choose(conn)
                if chosen is None:
                    return False
                # Taken in one statement, so a job cancelled as it's taken is never started.
                with conn:
                    row = conn.execute(
                        """UPDATE jobs SET state = 'running', started_at = ?,
                                  attempts = attempts + 1, stage = 'reading', progress = 0,
                                  problem = NULL
                           WHERE id = ? AND state = 'queued' RETURNING *""",
                        (self._stamp(), chosen),
                    ).fetchone()
                if row is not None:
                    break
            if row is None:
                return False
            batch_id: int | None = row["batch_id"]
            if batch_id is None:
                self._run(conn, row)
                return True
            if self.paused(conn):  # paused as it was taken: first in line again, not a try
                self._finish(conn, row["id"], "queued", again=True)
                return False
            with conn:
                conn.execute(
                    "UPDATE batches SET started_at = COALESCE(started_at, ?) WHERE id = ?",
                    (self._stamp(), batch_id),
                )
            with _awake():
                self._run(conn, row)
            self._settle(conn, batch_id)
        return True

    def _own_waits(self) -> bool:
        """Whether a picture's own Save waits, and may go now: it goes before See it first's
        pictures."""
        with closing(db.connect(self._paths.database)) as conn:
            rows = conn.execute(
                "SELECT held_until FROM jobs WHERE state = 'queued' AND batch_id IS NULL"
            ).fetchall()
        now = self._now()
        return any(_due(row["held_until"], now) for row in rows)

    def _rest(self) -> float:
        """Seconds the worker rests with nothing to do: till the next picture waiting while it
        was open in another app is due, _IDLE at most. One due already that still can't go (the
        queue paused, a batch for tonight, its drive away) is no reason to look sooner: a resume
        or a change wakes the worker."""
        with closing(db.connect(self._paths.database)) as conn:
            rows = conn.execute(
                "SELECT held_until FROM jobs WHERE state = 'queued' AND held_until IS NOT NULL"
            ).fetchall()
        now = self._now()
        later = [
            (moment - now).total_seconds()
            for row in rows
            if (moment := _moment(row["held_until"])) is not None and moment > now
        ]
        return min(max(min(later, default=_IDLE), 0.2), _IDLE)

    def _choose(self, conn: sqlite3.Connection) -> int | None:
        """The job to make now: a picture's own first; then, unless the queue is paused, the
        first batch's picture that may start now (tonight's only at night), whose drives are
        there and which has room. A drive without room pauses the queue, saying so, till there's
        room, or makes what fits there while the rest wait."""
        now = self._now()
        for own in conn.execute(
            "SELECT id, held_until FROM jobs WHERE state = 'queued' AND batch_id IS NULL"
            " ORDER BY position, id"
        ).fetchall():
            if _due(own["held_until"], now):
                return own["id"]
        if self.paused(conn):
            return None
        room = _object(_setting(conn, _ROOM)) or None
        drive = str(room.get("drive")) if room is not None else ""
        seen_there = False
        for candidate in self._candidates(conn):
            there = room is not None and _same_drive(candidate.into, drive)
            if room is not None and room.get("fit") is not True:
                if not there:
                    continue  # paused for room: what's there first, as the owner was told
                # On by itself once the first picture waiting there fits.
                full = room.get("full")
                if not self._room_back(candidate, full if isinstance(full, int) else None):
                    return None
                _save(conn, _ROOM, value=None)
                room, there = None, False
            seen_there = seen_there or there
            if self._room_for(candidate):
                return candidate.job
            if there:
                continue  # making what fits: this one waits for room while the others go
            self._short(conn, drive_of(candidate.into), candidate.into, candidate.name)
            return None
        if room is not None and not seen_there:  # nothing waits there now (or isn't connected)
            _save(conn, _ROOM, value=None)
        return None

    def _candidates(self, conn: sqlite3.Connection) -> Iterator[_Candidate]:
        """The batches' pictures waiting, in the queue's order, that may start now and whose
        drives are there, each drive looked at once (an unplugged share can take a while)."""
        now = self._now()
        drives: dict[str, bool] = {}

        def there(path: Path) -> bool:
            anchor = path.anchor.casefold()
            if anchor not in drives:
                drives[anchor] = self._connected(path)
            return drives[anchor]

        for row in conn.execute(
            """SELECT j.id, j.source, j.recipe, j.held_until, b.starts, b.name
               FROM jobs AS j JOIN batches AS b ON b.id = j.batch_id
               WHERE j.state = 'queued' ORDER BY j.position, j.id"""
        ):
            if not may_start(starts_of(row["starts"]), now) or not _due(row["held_until"], now):
                continue
            source = Path(row["source"])
            order = _object(json.loads(row["recipe"]))
            into = destination(order, source)
            if not there(source) or not there(into):
                continue  # waits for its drive
            need = order.get("bytes")
            yield _Candidate(row["id"], into, need if isinstance(need, int) else 0, row["name"])

    def _room_for(self, candidate: _Candidate) -> bool:
        if candidate.need <= 0:
            return True
        free = self._free(candidate.into)
        return free is None or fits(candidate.need, free)

    def _room_back(self, candidate: _Candidate, full: int | None) -> bool:
        """Whether a drive the queue paused for has room again: by Mado's reckoning, or, when it
        filled up as a picture was saved (`full`: what was free then), once more is free."""
        free = self._free(candidate.into)
        if free is None:
            return False  # Mado can't tell: the owner resumes
        if full is not None and free <= full + max(candidate.need, _ROOM_MADE):
            return False
        return fits(candidate.need, free)

    def _short(
        self,
        conn: sqlite3.Connection,
        drive: str,
        into: Path,
        name: str | None,
        *,
        full: int | None = None,
    ) -> None:
        """Pauses the queue for room on `drive`, and tells the owner what it needs, once. `full`:
        what was free as a picture filled the drive while it was saved."""
        before = self.short_of_room(conn)
        room: dict[str, object] = {"drive": drive, "fit": False}
        if full is not None:
            room["full"] = full
        _save(conn, _ROOM, value=room)
        if before is not None and before["drive"] == drive and not before["fit"]:
            return
        free = self._free(into) or 0
        more = max(needed_on(conn, drive) - max(free - MARGIN, 0), 0)
        what = f" for {name}" if name else ""
        self._notify(
            "The queue paused itself",
            f"{drive} needs about {_size_words(more)} more{what}. Make room there, or make "
            "what fits.",
            link="/queue",
        )

    def _settle(self, conn: sqlite3.Connection, batch_id: int) -> None:
        """A batch with nothing left waiting or under way is done: Mado tells the owner what it
        came to, unless they stopped the queue (Cancel all marks it seen) or nothing of it was
        made."""
        row = conn.execute(
            """SELECT COUNT(*) FILTER (WHERE state IN ('queued', 'running')) AS left,
                      COUNT(*) FILTER (WHERE state = 'done') AS made,
                      COUNT(*) FILTER (WHERE state = 'failed') AS failed
               FROM jobs WHERE batch_id = ?""",
            (batch_id,),
        ).fetchone()
        if row["left"]:
            return
        with conn:
            batch = conn.execute(
                """UPDATE batches SET finished_at = ? WHERE id = ? AND finished_at IS NULL
                   RETURNING name, seen_at""",
                (self._stamp(), batch_id),
            ).fetchone()
        if batch is None or batch["seen_at"] is not None or not (row["made"] or row["failed"]):
            return
        first = conn.execute(
            "SELECT recipe FROM jobs WHERE batch_id = ? ORDER BY position LIMIT 1", (batch_id,)
        ).fetchone()
        order = _object(json.loads(first["recipe"])) if first else {}
        label, look, edit = order.get("label"), order.get("look"), order.get("edit")
        fix = order.get("fix")
        title, body = told(
            batch["name"],
            made=row["made"],
            failed=row["failed"],
            made_for=label if isinstance(label, str) else None,
            look=look if isinstance(look, str) else None,
            edit=edit if isinstance(edit, str) else None,
            fix=fix if isinstance(fix, str) else None,
        )
        self._notify(title, body, link="/")

    def _run(self, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        job_id: int = row["id"]
        began = time.monotonic()
        expected: list[float] = []
        shares = _shares(row["recipe"])

        def report(stage: Stage, within: float) -> None:
            low, high = shares[stage]
            progress = low + (high - low) * min(max(within, 0.0), 1.0)
            with self._lock:
                self._live[job_id] = Live(stage, progress, _left(began, progress, expected))

        def stop() -> bool:
            with self._lock:
                live = self._live.get(job_id)
                if live is not None and live.stage == "saving":
                    return False  # past cancelling, and past stopping: it's moments
                asked = job_id in self._cancelled or job_id in self._pausing
                return asked or self._stopping.is_set()

        report("reading", 0.0)
        try:
            result = self._work(conn, row, report, stop, expected.append)
        except StoppedError:
            with self._lock:
                cancelled = job_id in self._cancelled and job_id not in self._pausing
            if cancelled and not self._stopping.is_set():
                self._finish(conn, job_id, "cancelled")
            else:  # paused, or Mado stopping: first in line again, not counted as a try
                self._finish(conn, job_id, "queued", again=True)
        except NoRoomError as error:
            if row["batch_id"] is None:
                self._finish(conn, job_id, "failed", problem=str(error))
            else:  # back in line, and the queue waits for room to be made
                self._finish(conn, job_id, "queued", again=True)
                into = destination(_object(json.loads(row["recipe"])), Path(row["source"]))
                free = self._free(into)
                self._short(conn, drive_of(into), into, None, full=free if free else 0)
        except DriveGoneError as error:
            if row["batch_id"] is None:
                self._finish(conn, job_id, "failed", problem=str(error))
            else:  # back in line, waiting for its drive while the others go: not a try
                self._finish(conn, job_id, "queued", again=True)
        except HeldError as error:  # open in another app: back in line for a while, not a try
            self._hold(conn, row, error)
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
                self._pausing.discard(job_id)

    def _hold(self, conn: sqlite3.Connection, row: sqlite3.Row, error: HeldError) -> None:
        """A picture open in another app: back in line to be tried again in HOLD_EVERY, its try
        given back, while the others go on; HOLD_FOR after it was first found so, it counts as
        not working."""
        job_id: int = row["id"]
        now = self._now()
        since = _moment(row["held_since"]) or now
        clear_partial(conn, job_id)
        with self._lock:
            cancelled = job_id in self._cancelled and job_id not in self._pausing
        if cancelled:  # Cancel was asked for as it was found open: it's over
            self._finish(conn, job_id, "cancelled")
            return
        if now - since >= HOLD_FOR:
            self._finish(conn, job_id, "failed", problem=_held_too_long(error.name))
            return
        with conn:
            conn.execute(
                """UPDATE jobs SET state = 'queued', started_at = NULL, stage = NULL,
                          progress = 0, attempts = MAX(attempts - 1, 0), problem = ?,
                          held_since = ?, held_until = ?, held_why = ?
                   WHERE id = ?""",
                (
                    str(error),
                    since.isoformat(timespec="seconds"),
                    (now + HOLD_EVERY).isoformat(timespec="seconds"),
                    error.verb,
                    job_id,
                ),
            )

    def _finish(
        self,
        conn: sqlite3.Connection,
        job_id: int,
        state: str,
        *,
        result: Path | None = None,
        problem: str | None = None,
        again: bool = False,
    ) -> None:
        """A job over (or back in line: `again` gives its try back)."""
        clear_partial(conn, job_id)
        made: int | None = None
        if result is not None:
            try:
                made = result.stat().st_size
            except OSError:
                made = None
        with conn:
            conn.execute(
                """UPDATE jobs SET state = ?, finished_at = ?, problem = ?,
                          result = COALESCE(?, CASE WHEN ? = 'done' THEN result END),
                          progress = CASE WHEN ? = 'done' THEN 1 WHEN ? THEN 0 ELSE progress END,
                          attempts = MAX(attempts - ?, 0), made_bytes = ?,
                          started_at = CASE WHEN ? THEN NULL ELSE started_at END,
                          stage = CASE WHEN ? THEN NULL ELSE stage END,
                          held_since = NULL, held_until = NULL, held_why = NULL
                   WHERE id = ?""",
                (
                    state,
                    None if state == "queued" else self._stamp(),
                    problem,
                    str(result) if result else None,
                    state,
                    state,
                    again,
                    int(again),
                    made,
                    again,
                    again,
                    job_id,
                ),
            )

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class _Candidate:
    """A batch's picture the queue could make now."""

    job: int
    into: Path  # the folder it saves into
    need: int  # about how many bytes it wants there
    name: str  # its batch's


class JobError(Exception):
    """A job that can't be made, with a sentence for the owner (nothing went wrong in Mado)."""


class NoRoomError(JobError):
    """The drive a picture saves to filled up: a batch's picture waits in line for room."""

    def __init__(self, drive: str, sentence: str) -> None:
        super().__init__(sentence)
        self.drive = drive


class HeldError(JobError):
    """The picture a job makes from is open in another app, so Mado can't read it (`verb`
    "read") or replace it ("replace") now: the job waits and tries again by itself."""

    def __init__(self, name: str, verb: Literal["read", "replace"]) -> None:
        super().__init__(
            f"{name} is open in another app. Mado can't {verb} it while it's open. Close it "
            "there and Mado tries again by itself."
        )
        self.name = name
        self.verb: Literal["read", "replace"] = verb


def _held_too_long(name: str) -> str:
    minutes = round(HOLD_FOR.total_seconds() / 60)
    return (
        f"{name} was open in another app for {minutes} minutes, so Mado stopped trying. "
        "Nothing was saved, and the original is as it was. Close it there, then try again."
    )


def _skipped(name: str) -> str:
    return (
        f"You skipped {name} while it was open in another app. Nothing was saved, and the "
        "original is as it was. Try again makes it."
    )


def _moment(stamp: object) -> datetime | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        found = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return found if found.tzinfo else found.astimezone()


def _due(held_until: object, now: datetime) -> bool:
    """Whether a job may go now: it isn't waiting on a picture open in another app, or its wait
    is over."""
    moment = _moment(held_until)
    return moment is None or moment <= now


class DriveGoneError(JobError):
    """The drive a picture is on, or saves to, went while it was made, before anything moved: a
    batch's picture waits in line for it, a picture's own Save says so."""

    def __init__(self, drive: str) -> None:
        super().__init__(
            f"{drive} isn't connected any more, so nothing was saved and the original is as it "
            "was. Connect it and try again."
        )
        self.drive = drive


def needed_on(conn: sqlite3.Connection, drive: str) -> int:
    """About how many bytes the batches' pictures waiting to be saved on a drive want."""
    needed = 0
    for row in conn.execute(
        "SELECT source, recipe FROM jobs WHERE state = 'queued' AND batch_id IS NOT NULL"
    ):
        order = _object(json.loads(row["recipe"]))
        need = order.get("bytes")
        if isinstance(need, int) and _same_drive(destination(order, Path(row["source"])), drive):
            needed += need
    return needed


def destination(order: dict[str, object], source: Path) -> Path:
    """The folder a job saves into: beside its original (or in its place), a folder by name
    beside it ("Edited"), or a folder of its own."""
    saving = _object(order.get("saving"))
    folder = saving.get("folder")
    if saving.get("how") == "replace" or not isinstance(folder, str) or not folder:
        return source.parent
    found = Path(folder)
    return found if found.is_absolute() else source.parent / found


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
    """After Mado crashed mid-job: a job whose picture was saved marked done; else what its
    saving began taken back, its half-written picture cleared away, and the job started again,
    unless that's happened before."""
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
                conn.execute(
                    "UPDATE jobs SET state = 'queued', started_at = NULL WHERE id = ?", (job_id,)
                )


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


def _shares(kept: str) -> dict[Stage, tuple[float, float]]:
    """Each stage's part of a job's whole, by its recipe (as the jobs table keeps it): its fixes
    take a part of making's, or all of it when there's no size to make."""
    try:
        recipe = _object(_object(json.loads(kept)).get("recipe"))
    except ValueError:
        return _SHARE
    if recipe.get("fix") is None:
        return _SHARE
    return _FIXED_SHARE if recipe.get("size") is not None else _ONLY_FIXED_SHARE


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


def _front(conn: sqlite3.Connection, count: int) -> int:
    """Where `count` jobs start to go ahead of everything waiting."""
    row = conn.execute(
        "SELECT MIN(position) AS first, (SELECT MAX(position) FROM jobs) AS last"
        " FROM jobs WHERE state = 'queued'"
    ).fetchone()
    if row["first"] is None:
        return (row["last"] or 0) + 1
    return int(row["first"]) - count


def _back(conn: sqlite3.Connection) -> int:
    """Where jobs start to go behind everything in the queue."""
    found = conn.execute("SELECT MAX(position) FROM jobs").fetchone()[0]
    return (found or 0) + 1


def _object(found: object) -> dict[str, object]:
    return cast("dict[str, object]", found) if isinstance(found, dict) else {}


def _setting(conn: sqlite3.Connection, key: str) -> object:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def _save(conn: sqlite3.Connection, key: str, *, value: object) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def drive_of(path: Path) -> str:
    """A path's drive as Windows names it: "D:", or a share's "\\\\server\\share"."""
    drive = PureWindowsPath(path).drive
    return drive.upper() if drive else str(path.anchor or path)


def _same_drive(path: Path, drive: str) -> bool:
    return drive_of(path).casefold() == drive.casefold()


def drive_there(path: Path) -> bool:
    """Whether a path's drive is there: an unplugged drive's letter is gone."""
    anchor = path.anchor
    return not anchor or Path(anchor).exists()


def _free(path: Path) -> int | None:
    """Bytes free on the drive a folder is on (the folder itself may not be made yet)."""
    here = path
    while not here.exists():
        if here.parent == here:
            return None
        here = here.parent
    try:
        return shutil.disk_usage(here).free
    except OSError:
        return None


def _size_words(size: int) -> str:
    if size >= 1e9:
        return f"{size / 1e9:.1f} GB".replace(".0 ", " ")
    return f"{max(round(size / 1e6), 1)} MB"


@contextmanager
def _awake() -> Generator[None]:
    """Keeps Windows from sleeping while a batch's picture is made (the screen may still turn
    off), as a batch running at night must."""
    if sys.platform != "win32":
        yield
        return
    continuous, system = 0x80000000, 0x00000001  # ES_CONTINUOUS, ES_SYSTEM_REQUIRED
    kernel = ctypes.windll.kernel32
    kernel.SetThreadExecutionState(continuous | system)
    try:
        yield
    finally:
        kernel.SetThreadExecutionState(continuous)
