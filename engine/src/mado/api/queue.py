"""The queue, as its page shows it: the batch being made (or first to be), its pictures, how far
it's got and the time left, the batches after it, and a drive without room; with nothing in it,
the latest batch whose pictures didn't all work, till that's cleared; and what can be done with
it: pause, resume, cancel all, ticked pictures next, last or out of it, a picture tried again,
making what fits, and clearing what didn't work (mado/jobs.py)."""

import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import Field

from mado.api.batches import BatchOut, batch_of
from mado.api.common import ApiModel, Database, Working
from mado.api.jobs import PictureRef
from mado.batches import kept_steps, order_of
from mado.core.batch import MARGIN, at_night, fitting, morning
from mado.jobs import destination, needed_on
from mado.previews import version
from mado.quarantine import by_drive

router = APIRouter()

_LISTED = 3  # waiting pictures, and pictures done, listed before "+28 more"
_KEPT = timedelta(days=7)  # a batch whose pictures didn't all work stays this long, uncleared
_STEPS = {
    "cutout": "Cut out the subject",
    "fix": "Fix",
    "size": "Make it for a screen",
    "paint": "A painting style",
    "look": "A look",
}
# A job's stage as the step of its batch it's at: the edits are a batch's cut-out; reading the
# picture is its first step's.
_STAGE_STEP = {
    "editing": "cutout",
    "fixing": "fix",
    "shaping": "size",
    "making": "size",
    "painting": "paint",
    "looking": "look",
}


class Row(ApiModel):
    job: int
    batch: int
    name: str
    path: str
    picture: PictureRef | None  # its thumbnail, while it's in the library
    state: Literal["running", "queued", "done", "failed", "cancelled"]
    step: str | None  # what it's at while it's made: "A look 2/3"
    progress: float
    bytes: int | None  # as it was
    made_bytes: int | None
    result_name: str | None
    problem: str | None  # why it didn't work, in a sentence
    waits: str | None  # why it waits: "D: isn't connected"


class Room(ApiModel):
    drive: str  # "D:"
    fit: bool  # what fits there is being made while the rest wait
    free: int
    needed: int  # what the pictures waiting there want
    more: int  # what's wanted there past what's free, a margin kept free
    fitting: int  # how many of them fit now, in turn
    aside: int  # bytes its quarantine would free, emptied
    batch: str | None  # the batch waiting for it


class QueueOut(ApiModel):
    paused: bool
    working: bool  # a batch's picture is being made now
    room: Room | None
    batch: BatchOut | None  # the batch being made, or first to be; or one finished (`finished`)
    finished: bool  # nothing waits: the batch is the latest whose pictures didn't all work
    rows: list[Row]  # its pictures: being made, waiting, didn't work, done
    waiting_more: int  # waiting pictures not listed
    done_more: int  # pictures done not listed
    later: list[BatchOut]  # batches after it
    night: bool  # it's night now: a batch for tonight may start
    morning: str  # the 07:00 that ends tonight's run
    waits_for_night: bool  # the batch waits for tonight
    seconds_left: float | None  # all that waits


class QueueNow(ApiModel):
    """The queue in a word, for the rail's badge and the status bar."""

    working: bool
    paused: bool
    batch: str | None  # the batch being made
    over: int  # its pictures made, or didn't work
    total: int
    progress: float
    waiting: int  # pictures waiting in the queue


class Ticked(ApiModel):
    jobs: Annotated[list[int], Field(min_length=1, max_length=10_000)]


class Moved(ApiModel):
    moved: int


class FitOn(ApiModel):
    drive: str = Field(max_length=260)


@router.get("/queue")
def queue(conn: Database, jobs: Working, all: bool = False) -> QueueOut:  # noqa: A002 - the query's name
    """The queue as its page shows it. `all` lists every picture waiting and done."""
    order = _batches(conn)
    current = order[0] if order else _finished(conn)
    batch = batch_of(conn, jobs, current) if current is not None else None
    rows: list[Row] = []
    waiting_more = done_more = 0
    if current is not None:
        rows, waiting_more, done_more = _rows(conn, jobs, current, every=all)
    now = datetime.now().astimezone()
    later = [batch_of(conn, jobs, each) for each in order[1:]]
    left = sum(
        each.seconds_left
        for each in ([batch] if batch is not None and order else []) + later
        if each.seconds_left is not None
    )
    return QueueOut(
        paused=jobs.paused(conn),
        working=_working(conn) is not None,
        room=_room(conn, jobs),
        batch=batch,
        finished=batch is not None and not order,
        rows=rows,
        waiting_more=waiting_more,
        done_more=done_more,
        later=later[:5],
        night=at_night(now),
        morning=morning(now).isoformat(timespec="minutes"),
        waits_for_night=batch is not None
        and batch.starts == "tonight"
        and not at_night(now)
        and batch.waiting > 0,
        seconds_left=left if order else None,
    )


@router.get("/queue/now")
def queue_now(conn: Database, jobs: Working) -> QueueNow:
    """The queue in a word: the batch being made and how far it's got, or how many wait."""
    running = _working(conn)
    waiting = jobs.waiting(conn)
    if running is None:
        return QueueNow(
            working=False,
            paused=jobs.paused(conn),
            batch=None,
            over=0,
            total=0,
            progress=0.0,
            waiting=waiting,
        )
    found = batch_of(conn, jobs, running)
    return QueueNow(
        working=True,
        paused=jobs.paused(conn),
        batch=found.name,
        over=found.done + found.failed,
        total=found.total,
        progress=found.progress,
        waiting=waiting,
    )


@router.post("/queue/pause")
def pause(conn: Database, jobs: Working) -> QueueNow:
    """Pauses the queue: the picture being made stops at its next tile, first in line again."""
    jobs.pause(conn)
    return queue_now(conn, jobs)


@router.post("/queue/resume")
def resume(conn: Database, jobs: Working) -> QueueNow:
    jobs.resume(conn)
    return queue_now(conn, jobs)


@router.post("/queue/cancel")
def cancel_all(conn: Database, jobs: Working) -> Moved:
    """Cancels everything in the queue: what waits, and the picture being made at its next tile.
    Pictures made already stay, and History has them."""
    return Moved(moved=jobs.cancel_all(conn))


@router.post("/queue/next")
def do_next(body: Ticked, conn: Database, jobs: Working) -> Moved:
    """Ticked pictures waiting go next, together."""
    return Moved(moved=jobs.move(conn, body.jobs, "next"))


@router.post("/queue/last")
def to_the_end(body: Ticked, conn: Database, jobs: Working) -> Moved:
    """Ticked pictures waiting go to the end of the queue, together."""
    return Moved(moved=jobs.move(conn, body.jobs, "last"))


@router.post("/queue/remove")
def take_out(body: Ticked, conn: Database, jobs: Working) -> Moved:
    """Ticked pictures waiting come out of the queue, as if they'd never been put in."""
    return Moved(moved=jobs.remove(conn, body.jobs))


@router.post("/queue/fit")
def make_what_fits(body: FitOn, conn: Database, jobs: Working) -> QueueNow:
    """On a drive without room, the pictures that fit are made, and the rest wait for room."""
    jobs.fit(conn, body.drive)
    return queue_now(conn, jobs)


@router.post("/queue/clear")
def clear(conn: Database, jobs: Working) -> QueueNow:
    """Clears what didn't work of the batches done from the Queue. History still says which."""
    with conn:
        conn.execute(
            "UPDATE batches SET cleared_at = ?"
            " WHERE finished_at IS NOT NULL AND cleared_at IS NULL",
            (datetime.now().astimezone().isoformat(timespec="seconds"),),
        )
    return queue_now(conn, jobs)


@router.post("/queue/{job_id}/retry")
def try_again(job_id: int, conn: Database, jobs: Working) -> QueueNow:
    """A picture that didn't work goes back in the queue, at its end."""
    if not jobs.retry(conn, job_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That picture isn't one to try again: it worked, or waits."
        )
    return queue_now(conn, jobs)


def _batches(conn: sqlite3.Connection) -> list[int]:
    """The batches in the queue, the one being made first, then by their first picture waiting."""
    running = _working(conn)
    rows = conn.execute(
        """SELECT batch_id, MIN(position) AS first FROM jobs
           WHERE state = 'queued' AND batch_id IS NOT NULL GROUP BY batch_id ORDER BY first"""
    ).fetchall()
    found = [row["batch_id"] for row in rows if row["batch_id"] != running]
    return [running, *found] if running is not None else found


def _finished(conn: sqlite3.Connection) -> int | None:
    """The latest batch done in the last week whose pictures didn't all work, till it's cleared:
    the queue says why, and has Try again."""
    since = datetime.now().astimezone() - _KEPT
    for row in conn.execute(
        """SELECT id, finished_at FROM batches AS b
           WHERE finished_at IS NOT NULL AND cleared_at IS NULL
           AND EXISTS (SELECT 1 FROM jobs WHERE batch_id = b.id AND state = 'failed')
           ORDER BY finished_at DESC, id DESC LIMIT 5"""
    ):
        try:
            if datetime.fromisoformat(row["finished_at"]) >= since:
                return row["id"]
        except ValueError:
            continue
    return None


def _working(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT batch_id FROM jobs WHERE state = 'running' AND batch_id IS NOT NULL LIMIT 1"
    ).fetchone()
    return row["batch_id"] if row else None


def _rows(
    conn: sqlite3.Connection, jobs: Working, batch_id: int, *, every: bool
) -> tuple[list[Row], int, int]:
    """A batch's pictures as the queue lists them: the one being made, the next few waiting,
    those that didn't work, and the latest few done."""
    found = conn.execute(
        """SELECT j.*, p.modified, p.size AS picture_size, p.read_at FROM jobs AS j
           LEFT JOIN pictures AS p ON p.id = j.picture_id AND p.gone_at IS NULL
           WHERE j.batch_id = ? AND j.state <> 'cancelled'
           ORDER BY CASE j.state WHEN 'running' THEN 0 WHEN 'queued' THEN 1 WHEN 'failed' THEN 2
                    ELSE 3 END,
                    CASE WHEN j.state = 'done' THEN j.finished_at END DESC, j.position, j.id""",
        (batch_id,),
    ).fetchall()
    steps = _steps_of(conn, batch_id)
    waiting = [row for row in found if row["state"] == "queued"]
    done = [row for row in found if row["state"] == "done"]
    shown_waiting = waiting if every else waiting[:_LISTED]
    shown_done = done if every else done[:_LISTED]
    shown = {row["id"] for row in [*shown_waiting, *shown_done]}
    listed = [row for row in found if row["state"] in ("running", "failed") or row["id"] in shown]
    rows = [_row(conn, jobs, row, steps) for row in listed]
    return rows, len(waiting) - len(shown_waiting), len(done) - len(shown_done)


def _row(conn: sqlite3.Connection, jobs: Working, row: sqlite3.Row, steps: list[str]) -> Row:
    live = jobs.live(row["id"]) if row["state"] == "running" else None
    path = Path(row["source"])
    picture = (
        PictureRef(id=row["picture_id"], version=version(row["modified"], row["picture_size"]))
        if row["picture_id"] is not None and row["read_at"] is not None
        else None
    )
    result = row["result"] if row["state"] == "done" else None
    return Row(
        job=row["id"],
        batch=row["batch_id"],
        name=path.name,
        path=str(path),
        picture=picture,
        state=row["state"],
        step=_step(live.stage if live else row["stage"], steps)
        if row["state"] == "running"
        else None,
        progress=live.progress if live else row["progress"],
        bytes=row["bytes"],
        made_bytes=row["made_bytes"],
        result_name=Path(result).name if result else None,
        problem=row["problem"] if row["state"] == "failed" else None,
        waits=_waits(row) if row["state"] == "queued" else None,
    )


def _steps_of(conn: sqlite3.Connection, batch_id: int) -> list[str]:
    """A batch's steps by their kind, then its save."""
    row = conn.execute("SELECT steps FROM batches WHERE id = ?", (batch_id,)).fetchone()
    steps, _saving = kept_steps(row["steps"] if row else "{}")
    return [str(step.get("step")) for step in steps] + ["save"]


def _step(stage: str | None, steps: list[str]) -> str:
    """What a picture being made is at, as a step of its batch's: "A look 2/3"."""
    kind = steps[0] if stage == "reading" else _STAGE_STEP.get(stage or "", "save")
    if kind not in steps:
        kind = steps[0]
    at = steps.index(kind)
    title = _STEPS.get(kind, "Save")
    return f"{title} {at + 1}/{len(steps)}"


def _waits(row: sqlite3.Row) -> str | None:
    """Why a picture waiting can't go yet: it's open in another app, or its drive, or the drive
    it saves to, isn't connected."""
    if row["held_since"]:
        return "It's open in another app; Mado tries again by itself"
    source = Path(row["source"])
    into = destination(order_of(row["recipe"]), source)
    for path in (source, into):
        anchor = path.anchor
        if anchor and not Path(anchor).exists():
            drive = PureWindowsPath(path).drive or anchor
            return f"{drive} isn't connected; it waits for it"
    return None


def _room(conn: sqlite3.Connection, jobs: Working) -> Room | None:
    short = jobs.short_of_room(conn)
    if short is None:
        return None
    drive = str(short["drive"])
    needs: list[int] = []
    batch: str | None = None
    for row in conn.execute(
        """SELECT j.source, j.recipe, b.name FROM jobs AS j JOIN batches AS b ON b.id = j.batch_id
           WHERE j.state = 'queued' ORDER BY j.position, j.id"""
    ):
        order = order_of(row["recipe"])
        into = destination(order, Path(row["source"]))
        if (PureWindowsPath(into).drive or "").casefold() != drive.casefold():
            continue
        need = order.get("bytes")
        needs.append(need if isinstance(need, int) else 0)
        batch = batch or row["name"]
    try:
        free = shutil.disk_usage(f"{drive}\\").free
    except OSError:
        free = 0
    aside = next(
        (size for each, size in by_drive(conn).items() if each.casefold() == drive.casefold()), 0
    )
    needed = needed_on(conn, drive)
    return Room(
        drive=drive,
        fit=bool(short["fit"]),
        free=free,
        needed=needed,
        more=max(needed - max(free - MARGIN, 0), 0),
        fitting=fitting(needs, free),
        aside=aside,
        batch=batch,
    )
