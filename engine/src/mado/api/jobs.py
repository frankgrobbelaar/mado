"""The jobs that make pictures: how each is going (its stage, how far, the time left), what it
saved, and Cancel. The Size tab follows its picture's job; the status bar, any under way."""

import json
import sqlite3
from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Query, status

from mado.api.common import ApiModel, Database, Working
from mado.jobs import Jobs
from mado.previews import version

router = APIRouter()

type JobState = Literal["queued", "running", "done", "failed", "cancelled"]


class PictureRef(ApiModel):
    """A picture in the library, enough to show its thumbnail or open it."""

    id: int
    version: str


class Job(ApiModel):
    id: int
    picture_id: int | None
    name: str  # the original's file name
    made_for: str | None  # what its size makes it for: "TV 8K"; None with no size
    look: str | None  # what it's made with: "Warm film at 60%"; None with no look
    how: Literal["new", "replace"]
    state: JobState
    stage: Literal["reading", "shaping", "making", "looking", "saving"] | None
    progress: float  # 0 to 1
    seconds_left: float | None
    queued_at: str
    started_at: str | None
    finished_at: str | None
    result: str | None  # the picture saved
    result_name: str | None
    result_picture: PictureRef | None  # the picture saved, once the library has read it
    problem: str | None


@router.get("/jobs")
def jobs_list(
    conn: Database,
    jobs: Working,
    picture: int | None = None,
    active: bool = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[Job]:
    """The latest pictures' own Saves, newest first: a picture's (`picture`), or those waiting
    or under way (`active`). A batch's pictures are the queue's (/queue)."""
    where: list[str] = ["batch_id IS NULL"]
    values: list[object] = []
    if picture is not None:
        where.append("picture_id = ?")
        values.append(picture)
    if active:
        where.append("state IN ('queued', 'running')")
    rows = conn.execute(
        f"SELECT id FROM jobs WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",  # noqa: S608
        [*values, limit],
    ).fetchall()
    return [job_of(conn, jobs, row["id"]) for row in rows]


@router.get("/jobs/{job_id}")
def job(job_id: int, conn: Database, jobs: Working) -> Job:
    return job_of(conn, jobs, job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: int, conn: Database, jobs: Working) -> Job:
    """Cancels a job: one waiting at once, one under way at its next step (a tile, or before it
    saves). Nothing is saved. One saving its picture is past cancelling, and goes on."""
    if not jobs.cancel(conn, job_id):
        found = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Mado has no such job.")
    return job_of(conn, jobs, job_id)


def job_of(conn: sqlite3.Connection, jobs: Jobs, job_id: int) -> Job:
    """A job as the window shows it: as it's kept, and as it's going, when it's under way."""
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mado has no such job.")
    order = _object(json.loads(row["recipe"]))
    saving = _object(order.get("saving"))
    live = jobs.live(job_id) if row["state"] == "running" else None
    result = row["result"] if row["state"] == "done" else None
    return Job(
        id=row["id"],
        picture_id=row["picture_id"],
        name=Path(row["source"]).name,
        made_for=str(order["label"]) if order.get("label") else None,
        look=str(order["look"]) if order.get("look") else None,
        how="replace" if saving.get("how") == "replace" else "new",
        state=row["state"],
        stage=live.stage if live else row["stage"],
        progress=live.progress if live else row["progress"],
        seconds_left=live.seconds_left if live else None,
        queued_at=row["queued_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        result=result,
        result_name=Path(result).name if result else None,
        result_picture=_in_library(conn, result) if result else None,
        problem=row["problem"],
    )


def _object(found: object) -> dict[str, object]:
    """A JSON object as Mado wrote it, or nothing much when it isn't one."""
    return cast("dict[str, object]", found) if isinstance(found, dict) else {}


def _in_library(conn: sqlite3.Connection, path: str) -> PictureRef | None:
    row = conn.execute(
        """SELECT id, modified, size FROM pictures
           WHERE path = ? AND gone_at IS NULL AND read_at IS NOT NULL""",
        (path,),
    ).fetchone()
    return PictureRef(id=row["id"], version=version(row["modified"], row["size"])) if row else None
