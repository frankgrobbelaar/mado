"""Duplicates and bursts, for their review: the groups found (a page at a time, the kinds told
apart), how far looking has got, which of each group is kept, "Not the same", and setting the
rest aside, a group at a time or all at once (mado/duplicates.py)."""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import Field

from mado import duplicates
from mado.api.common import ApiModel, Database, Finding, Scans, SetAside
from mado.core.duplicates import Group
from mado.duplicates import Found, Left, Where, choices, kept, where
from mado.jobs import drive_of
from mado.library import file_time
from mado.previews import version

router = APIRouter()

PAGE = 30  # groups a page, unless asked for fewer
_PUT_BACK_SHOWN = timedelta(days=7)  # a review put back whole is said so this long

type Kind = Literal["all", "duplicates", "bursts"]


class GroupPicture(ApiModel):
    id: int
    name: str
    path: str
    folder: str  # the folder it's in
    width: int
    height: int
    size: int  # bytes
    format: str | None
    taken_at: str  # local time: "2026-11-14T10:02:14"
    taken_from: Literal["camera", "file"]
    version: str  # its copies' addresses carry it
    keep: bool  # kept: as Mado suggests, or as the owner chose
    suggested: bool  # the one Mado suggests keeping
    there: Literal["there", "away", "gone", "changed"]  # as it was when compared, or not


class GroupOut(ApiModel):
    key: int  # its first picture's number, which names it
    kind: Literal["duplicates", "burst"]
    exact: bool  # every one the same bytes
    pictures: list[GroupPicture]  # a burst's in time, else biggest first
    chosen: bool  # the owner chose which to keep
    reason: Literal["sharpest", "pixels", "larger", "name", "older"]  # what decided Mado's pick
    aside: int  # pictures setting it aside sets aside now
    bytes: int  # what that frees
    ready: bool  # it can be set aside now
    problem: str | None  # why not: "F: isn't connected"


class LookingOut(ApiModel):
    looked: int
    of: int


class PutBack(ApiModel):
    """The latest review, every picture of it put back."""

    at: str  # when it was set aside
    pictures: int


class DuplicatesOut(ApiModel):
    looking: LookingOut | None  # still looking: how far it's got
    groups: list[GroupOut]  # this page
    next: int | None  # where the next page starts; None on the last
    duplicates: int  # groups of duplicates, in all
    bursts: int
    pictures: int  # what setting every group of the kind asked for aside sets aside now
    bytes: int  # and frees
    away: int  # pictures in its groups waiting for a drive to be connected
    put_back: PutBack | None
    version: str  # the groups and what's kept of them as they are now: setting all aside names it


class Keep(ApiModel):
    keep: Annotated[list[int], Field(min_length=1, max_length=10_000)]
    members: Annotated[list[int], Field(min_length=1, max_length=10_000)]  # as the owner saw them


class ShownGroup(ApiModel):
    """A group as the review showed it."""

    key: int
    members: Annotated[list[int], Field(min_length=2, max_length=10_000)]
    keep: Annotated[list[int], Field(min_length=1, max_length=10_000)]


class AsideAsk(ApiModel):
    groups: Annotated[list[ShownGroup] | None, Field(max_length=100_000)] = None
    kind: Kind = "all"  # with no groups: every group of this kind
    version: str | None = None  # with no groups: what the review saw (DuplicatesOut.version)


class LeftOut(ApiModel):
    name: str
    why: str


class AsideOut(ApiModel):
    review: int | None
    pictures: int
    bytes: int
    left: list[LeftOut]  # what was left as it is, and why


@router.get("/duplicates")
def found(
    conn: Database,
    finder: Finding,
    scans: Scans,
    kind: Kind = "all",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0, le=200)] = PAGE,
    reach: int | None = None,
) -> DuplicatesOut:
    """The groups found, newest first (a page of them: `offset`, `limit`; `kind` for only
    duplicates or only bursts), with what setting all of them of that kind aside would do.
    `limit=0` asks only for the counts (Home). `reach` makes the page long enough to hold that
    group (its key), as the Library's tag opens the review there."""
    latest = finder.found()
    chosen = choices(conn)
    drives = _Drives()
    wanted = [group for group in _newest_first(latest) if _of_kind(group, kind)]
    if reach is not None and limit:
        at = next((i for i, group in enumerate(wanted) if min(group.members) == reach), None)
        if at is not None and at >= offset:
            limit = max(limit, at - offset + 1)
    page = wanted[offset : offset + limit] if limit else []
    pictures = size = away = 0
    for group in wanted:
        rest = [member for member in group.members if member not in kept(group, chosen)]
        if drives.ready(group, latest):
            pictures += len(rest)
            size += sum(latest.pictures[member].size for member in rest)
        else:
            away += len(rest)
    looking = finder.progress(conn, scanning=scans.running)
    return DuplicatesOut(
        looking=LookingOut(looked=looking.looked, of=looking.of) if looking else None,
        groups=[_group_out(group, latest, chosen, drives) for group in page],
        next=offset + limit if limit and offset + limit < len(wanted) else None,
        duplicates=sum(1 for group in latest.groups if group.kind == "duplicates"),
        bursts=sum(1 for group in latest.groups if group.kind == "burst"),
        pictures=pictures,
        bytes=size,
        away=away,
        put_back=_put_back(conn),
        version=_version(latest, chosen),
    )


@router.put("/duplicates/{key}/keep")
def keep(key: int, body: Keep, conn: Database, finder: Finding) -> GroupOut:
    """Which of a group to keep, one or more of it: the owner's choice among its pictures as
    they saw them (`members`); one that joined since is left to Mado."""
    latest = finder.found()
    group = _group(latest, key)
    try:
        duplicates.choose(conn, group, latest, body.keep, _now(), shown=body.members)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    return _group_out(group, latest, choices(conn), _Drives())


@router.post("/duplicates/{key}/not-same", status_code=status.HTTP_204_NO_CONTENT)
def not_same(key: int, conn: Database, finder: Finding) -> None:
    """A group's pictures aren't the same: Mado doesn't ask again, unless one of them changes."""
    latest = finder.found()
    duplicates.not_the_same(conn, _group(latest, key), latest, _now())
    finder.regroup(conn)


@router.post("/duplicates/aside")
def set_aside(body: AsideAsk, conn: Database, finder: Finding, quarantine: SetAside) -> AsideOut:
    """Sets aside the rest of each group as the review showed it (or of every group of a kind,
    as long as none changed since the review saw them, `version`): each picture into its own
    drive's quarantine for 30 days, with a line of History, all under one line. A group that
    changed since it was shown, and a picture that changed since it was compared, is open in
    another app or is on a drive that isn't connected, is left as it is, and said so."""
    latest = finder.found()
    chosen = choices(conn)
    left: list[Left] = []
    if body.groups is None:
        if body.version != _version(latest, chosen):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "The groups changed since you looked, so Mado set nothing aside. The review shows "
                "them as they are now: look them over, then set them aside again.",
            )
        keys = [min(group.members) for group in latest.groups if _of_kind(group, body.kind)]
    else:
        keys: list[int] = []
        for each in body.groups:
            group = next((g for g in latest.groups if min(g.members) == each.key), None)
            if (
                group is not None
                and set(group.members) == set(each.members)
                and kept(group, chosen) == set(each.keep)
            ):
                keys.append(each.key)
                continue
            left.extend(
                Left(name, f"{name}'s group changed since you looked, so Mado left it as it is.")
                for name in _names(latest, [m for m in each.members if m not in set(each.keep)])
            )
    done = duplicates.set_aside(conn, quarantine, latest, keys=keys, now=_now())
    finder.regroup(conn)
    return AsideOut(
        review=done.review,
        pictures=done.pictures,
        bytes=done.bytes,
        left=[LeftOut(name=each.name, why=each.why) for each in [*left, *done.left]],
    )


def _version(latest: Found, chosen: dict[int, bool]) -> str:
    """What names the groups as they are now, with what's kept of each."""
    made = hashlib.blake2b(digest_size=12)
    for group in sorted(latest.groups, key=lambda each: min(each.members)):
        made.update(json.dumps([sorted(group.members), sorted(kept(group, chosen))]).encode())
    return made.hexdigest()


def _names(latest: Found, members: list[int]) -> list[str]:
    return [
        latest.pictures[member].name if member in latest.pictures else "A picture"
        for member in members
    ]


class _Drives:
    """Whether drives are connected, each asked once (an unplugged share can take a while)."""

    def __init__(self) -> None:
        self._there: dict[str, bool] = {}
        self._where: dict[int, Where] = {}

    def connected(self, path: str) -> bool:
        anchor = Path(path).anchor.casefold()
        if anchor not in self._there:
            self._there[anchor] = not anchor or Path(anchor).exists()
        return self._there[anchor]

    def ready(self, group: Group, latest: Found) -> bool:
        return all(self.connected(latest.pictures[member].path) for member in group.members)

    def where(self, latest: Found, member: int) -> Where:
        if member not in self._where:
            picture = latest.pictures[member]
            self._where[member] = where(picture) if self.connected(picture.path) else "away"
        return self._where[member]


def _group_out(group: Group, latest: Found, chosen: dict[int, bool], drives: _Drives) -> GroupOut:
    keep = kept(group, chosen)
    pictures: list[GroupPicture] = []
    for member in group.members:
        known = latest.pictures[member]
        path = PureWindowsPath(known.path)
        pictures.append(
            GroupPicture(
                id=member,
                name=known.name,
                path=known.path,
                folder=str(path.parent),
                width=known.width,
                height=known.height,
                size=known.size,
                format=known.format,
                taken_at=_taken(known.taken, known.modified),
                taken_from="camera" if known.taken is not None else "file",
                version=version(known.modified, known.size),
                keep=member in keep,
                suggested=member == group.keep,
                there=drives.where(latest, member),
            )
        )
    rest = [each for each in pictures if not each.keep]
    away = next((each for each in pictures if each.there == "away"), None)
    problem = (
        f"{drive_of(Path(away.path))} isn't connected. Connect it to set these aside."
        if away is not None
        else None
    )
    kept_there = any(each.keep and each.there == "there" for each in pictures)
    return GroupOut(
        key=min(group.members),
        kind=group.kind,
        exact=group.exact,
        pictures=pictures,
        chosen=any(member in chosen for member in group.members),
        reason=group.reason,
        aside=len(rest),
        bytes=sum(each.size for each in rest),
        ready=away is None and kept_there and any(each.there == "there" for each in rest),
        problem=problem,
    )


def _taken(taken: datetime | None, modified: int) -> str:
    """When a picture was taken, as the library says it: by the camera, else the file's time."""
    return taken.isoformat(timespec="seconds") if taken is not None else file_time(modified)


def _newest_first(latest: Found) -> list[Group]:
    """The groups, the newest taken first, as the Library shows pictures."""

    def newest(group: Group) -> tuple[str, int]:
        moments = [
            _taken(latest.pictures[member].taken, latest.pictures[member].modified)
            for member in group.members
        ]
        return max(moments), min(group.members)

    return sorted(latest.groups, key=newest, reverse=True)


def _of_kind(group: Group, kind: Kind) -> bool:
    match kind:
        case "all":
            return True
        case "duplicates":
            return group.kind == "duplicates"
        case "bursts":
            return group.kind == "burst"


def _group(latest: Found, key: int) -> Group:
    found = next((group for group in latest.groups if min(group.members) == key), None)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Those pictures aren't a group any more: one changed, went, or was set aside.",
        )
    return found


def _put_back(conn: sqlite3.Connection) -> PutBack | None:
    """The latest review, when every picture it set aside has been put back, lately."""
    row = conn.execute(
        """SELECT r.at, COUNT(h.id) AS lines,
                  COUNT(h.id) FILTER (WHERE h.undone_at IS NOT NULL) AS back
           FROM reviews AS r LEFT JOIN history AS h ON h.review_id = r.id
           GROUP BY r.id ORDER BY r.id DESC LIMIT 1"""
    ).fetchone()
    if row is None or not row["lines"] or row["back"] < row["lines"]:
        return None
    try:
        when = datetime.fromisoformat(row["at"])
    except ValueError:
        return None
    if _now() - when > _PUT_BACK_SHOWN:
        return None
    return PutBack(at=row["at"], pictures=row["lines"])


def _now() -> datetime:
    return datetime.now().astimezone()
