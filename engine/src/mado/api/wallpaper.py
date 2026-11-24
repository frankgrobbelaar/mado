"""The wallpaper studio: the owner's monitors as Windows arranges them, the picture each has (or
one across all) and where it's cut, each part as it'll be made, setting or saving them, the
daily change, and the owner's own wallpaper put back (mado/wallpaper.py)."""

import sqlite3
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import Field

from mado.api.common import ApiModel, Database, Paths
from mado.core.framing import Box, Shape
from mado.core.models import Quality
from mado.core.quality import Format
from mado.core.wallpaper import (
    ALL,
    GAP_MOST,
    ZOOM_MOST,
    Cut,
    Layout,
    Monitor,
    Rect,
    arrangement,
    bounds,
    key_of,
    spread,
)
from mado.desktop import DesktopError
from mado.previews import save_copy, version
from mado.wallpaper import Asked, Choice, Planned, Studio, StudioError, What, gap_for

router = APIRouter()

_SHOWN = 480  # a monitor's wallpaper shown in the studio, at most this many pixels across
_KEEP = {"Cache-Control": "private, max-age=31536000, immutable"}  # its address names its version


class Place(ApiModel):
    """Where a monitor sits with the gap for its bezels, in pixels."""

    x: float
    y: float
    width: float
    height: float


class MonitorItem(ApiModel):
    key: str  # a short name for it that stays the same
    name: str  # its own name ("Studio 27"), or "Screen 2"
    number: int  # Windows' number for it
    x: int  # in Windows' arrangement, in its pixels
    y: int
    width: int  # its pixels, as it's turned
    height: int
    scale: float  # Windows' scale for it: 1.25 for 125%
    rotation: int  # 0, 90, 180 or 270
    main: bool
    place: Place  # where it sits with the gap for the bezels: one across all lays a picture here
    wallpaper: str | None  # the file Windows says it shows
    mine: bool  # that's one of Mado's wallpapers
    shown: bool  # its wallpaper can be shown: the file is there
    version: str | None  # the wallpaper file's, which its thumbnail's address carries


class Point(ApiModel):
    x: float
    y: float


class ChosenPicture(ApiModel):
    id: int
    name: str
    path: str
    width: int | None
    height: int | None
    version: str
    outside: bool  # from outside the library
    hdr: bool = False  # an HDR photo: Windows shows a wallpaper as an ordinary picture
    focus: Point | None  # where Mado found its subject, as fractions; None till it's seen


class PictureChoice(ApiModel):
    monitor: str | None  # its monitor's key; None: one across all
    picture: ChosenPicture
    shape: Shape
    x: float | None  # the part's middle as fractions; None: around its subject
    y: float | None
    zoom: float  # 1: the biggest part with the monitor's shape; up to 4
    quality: Quality | None  # None: as this PC suits
    connected: bool  # its monitor is connected now (one across all: always)
    problem: str | None  # why Mado can't make a wallpaper from it (it won't open), in words


class Area(ApiModel):
    """A part of the picture, as fractions of it: past 0 and 1 where its edges are drawn."""

    x: float
    y: float
    width: float
    height: float


class PartPlan(ApiModel):
    monitor: str  # its monitor's key
    picture: int
    width: int  # exactly its monitor's pixels
    height: int
    area: Area
    scale: float  # how many times bigger it's made from the picture
    method: Literal["ai", "pixels", "smooth", "shrink", "keep"]
    quality: Quality
    how: str  # "Made with the photo model, guessed from the picture."
    warning: str | None  # what it can't make look real
    needs: list[str]  # downloads it waits for


class Making(ApiModel):
    """A wallpaper Mado makes, or made."""

    id: int
    purpose: Literal["set", "save", "daily"]
    state: Literal["waiting", "making", "ready", "set", "saved", "failed", "cancelled"]
    progress: float  # 0 to 1
    seconds_left: float | None  # by the pace so far; None till it's far enough along to say
    problem: str | None
    set_at: str | None
    saved: list[str]  # the pictures a Save wrote


class YourWallpaper(ApiModel):
    monitor: str  # its monitor's key
    name: str  # the monitor's name then
    path: str | None  # their own file; None: a colour
    there: bool  # their file, or Mado's copy of it, is there to put back


class Yours(ApiModel):
    """Mado's record of the owner's own wallpaper, from before it set one."""

    kept: list[YourWallpaper]
    slideshow: bool  # Windows' slideshow was on: putting back starts it again
    spotlight: bool  # Windows spotlight was on: only Windows turns it on again
    showing_mine: bool  # one of Mado's wallpapers is on a monitor now


class DailyState(ApiModel):
    on: bool
    at: str  # "07:00"
    layout: Layout
    folder: int | None  # a library folder's pictures; None: the favourites
    next: str | None  # when it next changes the wallpaper, local time
    ready: bool  # that change's wallpaper is made already
    candidates: int  # pictures it can show
    skipped: int  # not there now: gone, moved since, or on a drive that isn't connected
    changed_on: str | None  # the day it last made its change
    problem: str | None  # why it couldn't, that day


class StudioState(ApiModel):
    desktop: bool  # Windows lets Mado set wallpapers here
    problem: str | None  # why Windows didn't say what monitors there are
    monitors: list[MonitorItem]  # the main one first
    arrangement: str  # changes once a monitor's pixels, place or turn do
    layout: Layout
    gap: int  # pixels left between monitors for their bezels, one across all
    width: int  # the monitors laid out (one across all: with the gap)
    height: int
    choices: list[PictureChoice]
    parts: list[PartPlan]
    making: Making | None  # the latest wallpaper set or saved from the studio
    slideshow: bool  # Windows' slideshow is on now: Mado's wallpaper turns it off
    spotlight: bool  # Windows spotlight is on now: Mado's wallpaper turns it off
    yours: Yours
    daily: DailyState
    kept: int  # bytes Mado's own wallpapers take


class Arranged(ApiModel):
    layout: Layout
    gap: Annotated[int, Field(ge=0, le=GAP_MOST)] = 0


class ChoiceIn(ApiModel):
    monitor: str | None = None  # its monitor's key; None: one across all
    picture_id: int
    shape: Shape = "crop"
    x: Annotated[float | None, Field(ge=0, le=1)] = None
    y: Annotated[float | None, Field(ge=0, le=1)] = None
    zoom: Annotated[float, Field(ge=1, le=ZOOM_MOST)] = 1.0
    quality: Quality | None = None


class SaveIn(ApiModel):
    what: What  # each monitor's part, or one picture of the whole arrangement
    folder: str  # the folder the owner picked
    format: Format = "PNG"


class PutBackIn(ApiModel):
    monitor: str | None = None  # one monitor's key; None: every monitor


class YoursBack(ApiModel):
    studio: StudioState
    told: list[str]  # what couldn't be put back, and how the owner can


class DailyIn(ApiModel):
    on: bool
    at: Annotated[str, Field(pattern=r"^\d{1,2}:\d{2}$")] = "07:00"
    layout: Layout = "each"
    folder: int | None = None


def _studio(request: Request) -> Studio:
    found: Studio = request.app.state.wallpaper
    return found


@router.get("/wallpaper")
def studio(request: Request, conn: Database) -> StudioState:
    """The studio as it is: the monitors now, the pictures chosen and where they're cut, each
    part as it'll be made, the latest wallpaper set or saved, the owner's own and the daily
    change."""
    return state_of(_studio(request), conn)


@router.put("/wallpaper")
def arrange(body: Arranged, request: Request, conn: Database) -> StudioState:
    """One for each monitor, or one across all, and the gap for the bezels."""
    found = _studio(request)
    found.arrange(conn, body.layout, body.gap)
    return state_of(found, conn)


@router.put("/wallpaper/pictures")
def choose(body: ChoiceIn, request: Request, conn: Database) -> StudioState:
    """The picture for a monitor (or for all of them), where it's cut, and Fast or Best."""
    found = _studio(request)
    monitor = ALL if body.monitor is None else _monitor_id(found, conn, body.monitor)
    cut = Cut(body.x, body.y, body.zoom)
    choice = Choice(monitor, body.picture_id, body.shape, cut, body.quality)
    _answer(lambda: found.choose(conn, choice))
    return state_of(found, conn)


@router.delete("/wallpaper/pictures")
def let_go(request: Request, conn: Database, monitor: str | None = None) -> StudioState:
    """A monitor's picture let go (or the one across all)."""
    found = _studio(request)
    found.forget_choice(conn, ALL if monitor is None else _monitor_id(found, conn, monitor))
    return state_of(found, conn)


@router.post("/wallpaper/set")
def set_it(request: Request, conn: Database) -> StudioState:
    """Makes each part at exactly its monitor's pixels, then sets them as Windows' wallpaper:
    the owner's own kept first. The making is a small job before the queue's pictures."""
    found = _studio(request)
    _answer(lambda: found.ask(conn, "set"))
    return state_of(found, conn)


@router.post("/wallpaper/save")
def save(body: SaveIn, request: Request, conn: Database) -> StudioState:
    """Makes the parts, then saves them (or one picture of the whole arrangement) as new
    pictures into the folder the owner picked, each in History, as any Save."""
    folder = Path(body.folder)
    if not folder.is_absolute():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick a folder to save into.")
    found = _studio(request)
    saving: dict[str, object] = {"what": body.what, "folder": str(folder), "format": body.format}
    _answer(lambda: found.ask(conn, "save", saving))
    return state_of(found, conn)


@router.post("/wallpaper/cancel")
def cancel(request: Request, conn: Database) -> StudioState:
    """The wallpaper being made to set or save, stopped: nothing is set, and what it made goes."""
    found = _studio(request)
    found.cancel(conn)
    return state_of(found, conn)


@router.post("/wallpaper/put-back")
def put_back(body: PutBackIn, request: Request, conn: Database) -> YoursBack:
    """The owner's own wallpaper back, on every monitor or one: their own file, or Mado's copy
    of it when it's gone; Windows' slideshow started again, as Windows allows. Every monitor put
    back stops the daily change too."""
    found = _studio(request)
    monitor = None if body.monitor is None else _monitor_id(found, conn, body.monitor)
    told: list[str] = []

    def putting() -> None:
        told.extend(found.put_back(conn, monitor))

    _answer(putting)
    return YoursBack(studio=state_of(found, conn), told=told)


@router.put("/wallpaper/daily")
def daily(body: DailyIn, request: Request, conn: Database) -> StudioState:
    """The daily change: on or off, its time (07:00 at first), one for each monitor or one
    across all, and from the favourites or a library folder."""
    found = _studio(request)
    _answer(
        lambda: found.set_daily(
            conn, on=body.on, at=body.at, layout=body.layout, folder=body.folder
        )
    )
    return state_of(found, conn)


_WEBP: dict[int | str, dict[str, Any]] = {200: {"content": {"image/webp": {}}}}


@router.get("/wallpaper/monitors/{key}/wallpaper", response_class=FileResponse, responses=_WEBP)
def monitor_wallpaper(key: str, request: Request, paths: Paths) -> FileResponse:
    """What Windows shows on a monitor now, small (WebP), when it names a file that's there.
    The file is only read."""
    found = _studio(request)
    shown = next((each for each in found.seen() if key_of(each.monitor.id) == key), None)
    if shown is None or not shown.wallpaper:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Windows doesn't name a picture there.")
    source = Path(shown.wallpaper)
    try:
        stat = source.stat()
    except OSError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That wallpaper's file isn't there."
        ) from None
    copy = paths.cache / "wallpapers" / f"{key}-{version(stat.st_mtime_ns, stat.st_size)}.webp"
    if not copy.is_file():
        try:
            with Image.open(source) as image:
                small = image.convert("RGB")
                small.thumbnail((_SHOWN, _SHOWN), Image.Resampling.LANCZOS)
            save_copy(small, copy, "WEBP", quality=82, method=4)
        except OSError, ValueError, Image.DecompressionBombError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Mado can't show that wallpaper."
            ) from None
        for older in copy.parent.glob(f"{key}-*.webp"):  # one for each monitor: what it shows
            if older != copy:
                with suppress(OSError):
                    older.unlink()
    return FileResponse(copy, media_type="image/webp", headers=_KEEP)


def state_of(found: Studio, conn: sqlite3.Connection) -> StudioState:
    """The studio as the window shows it."""
    seen = found.seen()
    monitors = [each.monitor for each in seen]
    chosen = found.chosen(conn)
    choices = found.choices(conn)
    gap = gap_for(chosen.layout, chosen.gap)
    places = spread(monitors, gap)
    whole = bounds(places.values()) if monitors else None
    connected = {each.id.casefold() for each in monitors}
    planned = found.planned(conn, monitors, chosen.layout, gap, choices)
    shown_choices = [
        item for each in choices if (item := _choice_item(found, conn, each, connected)) is not None
    ]
    candidates, skipped = found.candidates(conn, chosen.daily.folder, look=False)
    upcoming = found.next_change(conn)
    daily_made = found.daily_made(conn)
    yours = found.yours(conn)
    before = found.before(conn)
    return StudioState(
        desktop=found.desktop.here,
        problem=found.problem,
        monitors=[_monitor_item(found, each.monitor, each.wallpaper, places) for each in seen],
        arrangement=_arrangement(monitors),
        layout=chosen.layout,
        gap=chosen.gap,
        width=round(whole.width) if whole else 0,
        height=round(whole.height) if whole else 0,
        choices=shown_choices,
        parts=[_part_plan(each) for each in planned],
        making=_making(found.latest(conn)),
        slideshow=_quietly(lambda: found.desktop.slideshow() is not None),
        spotlight=_quietly(found.desktop.spotlight),
        yours=Yours(
            kept=[
                YourWallpaper(
                    monitor=key_of(each.monitor),
                    name=each.name,
                    path=each.path,
                    there=each.path is None
                    or Path(each.path).is_file()
                    or bool(each.kept and Path(each.kept).is_file()),
                )
                for each in yours
            ],
            slideshow=bool(before and before.slideshow),
            spotlight=bool(before and before.spotlight),
            showing_mine=any(each.wallpaper and found.mine(each.wallpaper) for each in seen),
        ),
        daily=DailyState(
            on=chosen.daily.on,
            at=chosen.daily.at,
            layout=chosen.daily.layout,
            folder=chosen.daily.folder,
            next=upcoming.isoformat(timespec="minutes") if upcoming else None,
            ready=bool(
                upcoming
                and daily_made
                and daily_made.state == "ready"
                and daily_made.day == upcoming.date().isoformat()
            ),
            candidates=len(candidates),
            skipped=skipped,
            changed_on=chosen.daily.changed_on,
            problem=chosen.daily.problem,
        ),
        kept=found.bytes_kept(),
    )


def _monitor_item(
    found: Studio, monitor: Monitor, wallpaper: str | None, places: Mapping[str, Rect]
) -> MonitorItem:
    place = places[monitor.id]
    file_version: str | None = None
    if wallpaper:
        with suppress(OSError):
            stat = Path(wallpaper).stat()
            file_version = version(stat.st_mtime_ns, stat.st_size)
    return MonitorItem(
        key=key_of(monitor.id),
        name=monitor.name,
        number=monitor.number,
        x=monitor.x,
        y=monitor.y,
        width=monitor.width,
        height=monitor.height,
        scale=monitor.scale,
        rotation=monitor.rotation,
        main=monitor.main,
        place=Place(x=place.x, y=place.y, width=place.width, height=place.height),
        wallpaper=wallpaper,
        mine=bool(wallpaper and found.mine(wallpaper)),
        shown=file_version is not None,
        version=file_version,
    )


def _choice_item(
    found: Studio, conn: sqlite3.Connection, choice: Choice, connected: set[str]
) -> PictureChoice | None:
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (choice.picture_id,)
    ).fetchone()
    if row is None:
        return None
    across = choice.monitor == ALL
    focus, problem = found.focus_of(conn, choice.picture_id)
    return PictureChoice(
        monitor=None if across else key_of(choice.monitor),
        picture=ChosenPicture(
            id=row["id"],
            name=row["name"],
            path=row["path"],
            width=row["width"],
            height=row["height"],
            version=version(row["modified"], row["size"]),
            outside=row["folder_id"] is None,
            hdr=row["hdr"] == 1,
            focus=Point(x=focus[0], y=focus[1]) if focus else None,
        ),
        shape=choice.shape,
        x=choice.cut.x,
        y=choice.cut.y,
        zoom=choice.cut.zoom,
        quality=choice.quality,
        connected=across or choice.monitor.casefold() in connected,
        problem=problem,
    )


def _part_plan(each: Planned) -> PartPlan:
    width, height = each.size
    box: Box = each.part.box
    return PartPlan(
        monitor=key_of(each.part.monitor.id),
        picture=each.choice.picture_id,
        width=each.part.monitor.width,
        height=each.part.monitor.height,
        area=Area(
            x=box.x / width, y=box.y / height, width=box.width / width, height=box.height / height
        ),
        scale=round(each.way.scale, 3),
        method=each.way.method,
        quality=each.quality,
        how=each.way.how,
        warning=each.way.warning,
        needs=list(each.needs),
    )


def _making(asked: Asked | None) -> Making | None:
    if asked is None:
        return None
    return Making(
        id=asked.id,
        purpose=asked.purpose,
        state=cast("Any", asked.state),  # one of the table's states: its CHECK holds it
        progress=round(asked.progress, 3),
        seconds_left=round(asked.seconds_left, 1) if asked.seconds_left is not None else None,
        problem=asked.problem,
        set_at=asked.set_at,
        saved=list(asked.saved),
    )


def _monitor_id(found: Studio, conn: sqlite3.Connection, key: str) -> str:
    """Windows' id for a monitor by its key: one connected now, or one a picture waits for."""
    for each in found.seen():
        if key_of(each.monitor.id) == key:
            return each.monitor.id
    for choice in found.choices(conn):
        if choice.monitor != ALL and key_of(choice.monitor) == key:
            return choice.monitor
    for kept in found.yours(conn):
        if key_of(kept.monitor) == key:
            return kept.monitor
    raise HTTPException(status.HTTP_404_NOT_FOUND, "That monitor isn't connected.")


def _arrangement(monitors: list[Monitor]) -> str:
    return arrangement(monitors) if monitors else ""


def _answer(work: Callable[[], object]) -> None:
    """Runs a change, answering StudioError (and Windows refusing) in its own words."""
    try:
        work()
    except StudioError as error:
        raise HTTPException(error.status, str(error)) from None
    except DesktopError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


def _quietly(read: Callable[[], object]) -> bool:
    """A yes or no Windows may not give: no, when it won't."""
    try:
        return bool(read())
    except DesktopError, OSError:
        return False
