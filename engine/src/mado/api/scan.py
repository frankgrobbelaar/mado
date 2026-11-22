"""The scan: how the latest one is going. Adding a folder, or the watcher noticing a change,
starts one (mado/watch.py)."""

from fastapi import APIRouter

from mado.api.common import ApiModel, Scans
from mado.scan import Stage, State

router = APIRouter()


class Scan(ApiModel):
    state: State  # "stopped": Mado closed, or crashed, before it finished
    stage: Stage | None
    started_at: str | None
    finished_at: str | None
    found: int  # pictures this scan found
    to_read: int  # of those, the new and changed ones to read
    read: int
    current: str | None  # the picture being looked at now
    seconds_left: float | None
    unavailable: list[str]  # library folders that aren't there (a drive unplugged)
    problem: str | None  # why it stopped, when it failed
    added: int | None  # pictures it found that weren't there before
    gone: int | None  # pictures it found gone


@router.get("/scan")
def scan(scans: Scans) -> Scan:
    now = scans.status()
    return Scan(
        state=now.state,
        stage=now.stage,
        started_at=now.started_at,
        finished_at=now.finished_at,
        found=now.found,
        to_read=now.to_read,
        read=now.read,
        current=now.current,
        seconds_left=now.seconds_left,
        unavailable=list(now.unavailable),
        problem=now.problem,
        added=now.added,
        gone=now.gone,
    )
