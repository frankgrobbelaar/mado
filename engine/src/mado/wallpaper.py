"""The wallpaper studio: the owner's monitors as Windows arranges them, a picture made for each (or
one laid across them all) at exactly its pixels, set as Windows' own per-monitor wallpaper or
saved as pictures; changed every day from favourites when the owner wants; and the owner's own
wallpaper kept and put back (docs/stack/wallpaper.md).

- The parts are made into Mado's data folder (`wallpapers\\made\\<number>`), never the owner's
  folders, as PNG in sRGB: Windows makes a JPEG wallpaper again at its own quality (85 unless
  told otherwise, a setting Mado leaves alone), while a PNG is shown as it is, and a part exactly
  the monitor's pixels is shown pixel for pixel. Saving them as pictures is a Save like any
  other: into a folder the owner picks, with History.
- Making is the jobs' worker's, a wallpaper at a time before the queue's pictures, as See it
  first's are, so it takes the graphics card in turn (mado/jobs.py).
- Each time Mado sets a wallpaper over the owner's own, it first keeps a copy of each monitor's
  (`wallpapers\\yours`; Windows may hold it only in its own cache) and how Windows showed it
  (spanned, a slideshow, spotlight), and puts them back when asked. It never deletes or moves the
  owner's file, nor changes any Windows setting but the wallpaper.
- The daily change, off till it's turned on: from 12 hours before its time (19:00 the evening
  before a 07:00 change) the day's pictures are picked and made, then set at the time, or as Mado
  next starts once the time's past; made then, when they weren't ready, or when making them ahead
  failed. A day's change comes only at a time after the change was turned on or its time set.
- Mado's own wallpapers: those showing now and those of the last three days are kept; only
  Mado's older ones are deleted, and only from its own folder.
"""

import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import closing, suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Literal, cast

import numpy as np
from PIL import Image

from mado import db, encode, history
from mado.ai import LAMA, Ai, Timer
from mado.core.framing import Box, Shape
from mado.core.models import Quality
from mado.core.naming import QUARANTINE
from mado.core.quality import Format
from mado.core.wallpaper import (
    ALL,
    GAP_MOST,
    Candidate,
    Cut,
    Layout,
    Made,
    Monitor,
    Part,
    arrangement,
    bounds,
    key_of,
    made,
    ordered,
    part_for,
    parts_across,
    picks,
    spread,
)
from mado.desktop import FILL, SPAN, Desktop, DesktopError, Seen, Slideshow
from mado.directml import ModelError
from mado.jobs import PARTIAL
from mado.making import (
    Naming,
    Picture,
    Saving,
    SavingError,
    Sight,
    keep,
    picture_of,
    split_alpha,
    write,
)
from mado.pictures import NeedsFfmpegError, NeedsReaderError, PictureGoneError, UnreadableError
from mado.previews import version
from mado.quarantine import Quarantine
from mado.upscale import Pixels, StoppedError, by_pixels, smaller, smoothly, through_model

log = logging.getLogger(__name__)

type Purpose = Literal["set", "save", "daily"]
type What = Literal["parts", "whole"]

AHEAD = timedelta(hours=12)  # the day's pictures are made this long before the change
KEPT_DAYS = 3  # Mado's own wallpapers kept besides those showing now
EVERY = 30.0  # seconds between the daily change's looks
ASK_AGAIN = 600.0  # seconds before the day's pictures are looked for again, when none suited
DRIVES_FOR = 60.0  # seconds a drive's being connected is taken as known
_TRANSCODED = "TranscodedWallpaper"  # Windows' own copy of the wallpaper it shows


class StudioError(Exception):
    """Something the studio can't do now, with a sentence saying why, and the answer it makes."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


class MonitorsChangedError(StudioError):
    """The monitors changed while a wallpaper was being made for them."""

    def __init__(self) -> None:
        super().__init__(
            "Your monitors changed while it was being made, so Mado didn't set it. The studio "
            "shows them as they are now: set it again."
        )


_AROUND_THE_SUBJECT = Cut()  # cut around the picture's subject, the biggest part


@dataclass(frozen=True)
class Choice:
    """The picture the studio has for a monitor (Windows' id for it), or for all (`ALL`)."""

    monitor: str
    picture_id: int
    shape: Shape = "crop"
    cut: Cut = _AROUND_THE_SUBJECT
    quality: Quality | None = None  # None: as this PC suits


@dataclass(frozen=True)
class Daily:
    on: bool
    at: str  # "07:00"
    layout: Layout
    folder: int | None  # a library folder's pictures; None: the favourites
    changed_on: str | None  # the day it last made its change, or gave up on it
    problem: str | None  # why it couldn't, that day
    since: datetime | None = None  # turned on, or its time set, then: a change comes after it


@dataclass(frozen=True)
class Chosen:
    """The studio's choices: its layout, the gap for the bezels, and the daily change."""

    layout: Layout
    gap: int
    daily: Daily


@dataclass(frozen=True)
class Planned:
    """A part as it'll be made: where it's cut, from which picture, and how."""

    part: Part
    choice: Choice
    picture: Picture
    version: str
    size: tuple[int, int]  # the picture's, as it's shown
    way: Made  # how it's made
    quality: Quality
    needs: tuple[str, ...]  # downloads it waits for


@dataclass(frozen=True)
class Asked:
    """A wallpaper Mado makes or made, as the studio tells of it."""

    id: int
    purpose: Purpose
    state: str  # waiting, making, ready, set, saved, failed, cancelled
    progress: float
    seconds_left: float | None  # by the pace so far, once it's far enough along to say
    problem: str | None
    day: str | None
    set_at: str | None
    saved: tuple[str, ...]  # what a Save wrote


@dataclass(frozen=True)
class Kept:
    """Mado's record of the owner's own wallpaper on a monitor."""

    monitor: str
    name: str
    path: str | None  # their file; None: a colour
    kept: str | None  # Mado's copy


@dataclass(frozen=True)
class Before:
    """How Windows showed the owner's own wallpaper."""

    position: int | None
    slideshow: Slideshow | None
    spotlight: bool


def _now() -> datetime:
    return datetime.now().astimezone()


class Studio:
    def __init__(
        self,
        folder: Path,
        desktop: Desktop,
        ai: Ai,
        sight: Sight,
        quarantine: Quarantine,
        *,
        database: Path,
        wake: Callable[[], None],
        now: Callable[[], datetime] = _now,
        themes: Path | None = None,
    ) -> None:
        """`folder` is the data folder's `wallpapers`, `database` Mado's records; `wake` asks
        the jobs' worker to look for work; `themes` is where Windows keeps its copy of the
        wallpaper it shows (tests pass their own)."""
        self.folder = folder
        self.desktop = desktop
        self.now = now
        self._database = database
        self._ai = ai
        self._sight = sight
        self._quarantine = quarantine
        self._wake = wake
        self.themes = themes
        self._lock = threading.RLock()  # one change to the desktop at a time
        self._live: dict[int, float] = {}  # how far the wallpaper being made has got
        self._began: dict[int, float] = {}  # when it started being made, by the clock
        self._cancelled: set[int] = set()  # wallpapers being made that are to stop
        self._drives: dict[str, tuple[float, bool]] = {}  # each drive: when looked at, there
        self._asked_ahead: dict[tuple[str, str], float] = {}  # the day's pictures looked for
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._tidied_on: str | None = None
        self.problem: str | None = None  # why Windows didn't say what monitors there are

    def recover(self, conn: sqlite3.Connection) -> None:
        """As the engine starts: the daily change's wallpaper a stop cut short is made again,
        unless its day has passed; one the owner asked to set or save isn't finished days later,
        but says it was cut short, what a Save had half written cleared away."""
        today = self.now().date().isoformat()
        with conn:
            conn.execute(
                """UPDATE wallpapers SET state = 'cancelled' WHERE purpose = 'daily'
                   AND state IN ('waiting', 'making', 'ready') AND day < ?""",
                (today,),
            )
            conn.execute(
                "UPDATE wallpapers SET state = 'waiting' "
                "WHERE purpose = 'daily' AND state = 'making'"
            )
        cut_short = conn.execute(
            "SELECT * FROM wallpapers WHERE purpose IN ('set', 'save') "
            "AND state IN ('waiting', 'making')"
        ).fetchall()
        for row in cut_short:
            if row["purpose"] == "save":
                self._finish_cut_short(conn, row)
            else:
                _state(conn, row["id"], "failed", problem=_CLOSED_SETTING)

    def _finish_cut_short(self, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        """A Save Mado's closing cut short: the picture it was writing kept when it got to its
        place, else its half-written file (only one Mado names as its own) and its line in
        History let go; the row says how many were saved."""
        plan = _plan_of(row["plan"])
        saved = [str(each) for each in cast("list[object]", plan.get("saved") or [])]
        writing = plan.pop("writing", None)
        if isinstance(writing, str) and writing.endswith(PARTIAL):
            partial = Path(writing)
            target = Path(writing.removesuffix(PARTIAL))
            if target.is_file() and not partial.exists():
                saved.append(str(target))
            else:
                for line in conn.execute(
                    "SELECT id FROM history WHERE kind = 'made' AND result = ? COLLATE NOCASE",
                    (str(target),),
                ).fetchall():
                    history.forget(conn, line["id"])
                try:
                    partial.unlink(missing_ok=True)
                except OSError as error:
                    log.warning("Mado couldn't clear away %s: %s", partial, error)
        plan["saved"] = saved
        problem = (
            "Mado was closed before it saved them. Save them again."
            if not saved
            else f"Mado was closed while it saved them: {len(saved)} "
            f"{'was' if len(saved) == 1 else 'were'} saved before it. Save again for the rest."
        )
        with conn:
            conn.execute(
                "UPDATE wallpapers SET state = 'failed', problem = ?, plan = ? WHERE id = ?",
                (problem, json.dumps(plan), row["id"]),
            )

    # What's there.

    def seen(self) -> list[Seen]:
        """The monitors showing now, with what each shows; none, and why, when Windows won't
        say."""
        try:
            found = self.desktop.monitors()
        except DesktopError as error:
            self.problem = str(error)
            return []
        self.problem = None
        return found

    def chosen(self, conn: sqlite3.Connection) -> Chosen:
        row = conn.execute("SELECT * FROM studio WHERE id = 1").fetchone()
        if row is None:  # records restored from before the studio: it starts as it would
            return Chosen("each", 0, Daily(False, "07:00", "each", None, None, None))
        # Its folder taken out of the library, the daily change is off till it's given another.
        taken_out = row["daily_from"] == "folder" and row["daily_folder"] is None
        return Chosen(
            layout=row["layout"],
            gap=row["gap"],
            daily=Daily(
                on=bool(row["daily"]) and not taken_out,
                at=row["daily_at"],
                layout=row["daily_layout"],
                folder=row["daily_folder"],
                changed_on=row["changed_on"],
                problem=_TAKEN_OUT if taken_out and row["daily"] else row["problem"],
                since=_moment_of(row["daily_since"]),
            ),
        )

    def choices(self, conn: sqlite3.Connection) -> list[Choice]:
        return [
            Choice(
                monitor=row["monitor"],
                picture_id=row["picture_id"],
                shape=row["shape"],
                cut=Cut(row["x"], row["y"], row["zoom"]),
                quality=row["quality"],
            )
            for row in conn.execute("SELECT * FROM studio_pictures ORDER BY monitor")
        ]

    def choose(self, conn: sqlite3.Connection, choice: Choice) -> None:
        """The picture for a monitor, or for all, and where it's cut. Raises StudioError for a
        picture that isn't there."""
        there = conn.execute(
            "SELECT 1 FROM pictures WHERE id = ? AND gone_at IS NULL", (choice.picture_id,)
        ).fetchone()
        if there is None:
            raise StudioError("That picture isn't there any more.", 404)
        cut = choice.cut
        with conn:
            conn.execute(
                """INSERT INTO studio_pictures (monitor, picture_id, shape, x, y, zoom, quality, at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (monitor) DO UPDATE SET picture_id = excluded.picture_id,
                       shape = excluded.shape, x = excluded.x, y = excluded.y,
                       zoom = excluded.zoom, quality = excluded.quality, at = excluded.at""",
                (
                    choice.monitor,
                    choice.picture_id,
                    choice.shape,
                    _fraction(cut.x),
                    _fraction(cut.y),
                    min(max(cut.zoom, 1.0), 4.0),
                    choice.quality,
                    self._stamp(),
                ),
            )

    def forget_choice(self, conn: sqlite3.Connection, monitor: str) -> None:
        with conn:
            conn.execute("DELETE FROM studio_pictures WHERE monitor = ?", (monitor,))

    def arrange(self, conn: sqlite3.Connection, layout: Layout, gap: int) -> None:
        with conn:
            conn.execute(
                "UPDATE studio SET layout = ?, gap = ? WHERE id = 1",
                (layout, min(max(gap, 0), GAP_MOST)),
            )

    def set_daily(
        self, conn: sqlite3.Connection, *, on: bool, at: str, layout: Layout, folder: int | None
    ) -> None:
        """The daily change's choices. A day's change comes only at a time after the change was
        turned on or its time set, so one set once the day's time has passed first changes the
        next day's. Turned off, turned on again, or given other pictures or another layout, what
        was made ahead goes (one being made stops)."""
        hour, minute = _time(at)
        if (
            folder is not None
            and conn.execute("SELECT 1 FROM folders WHERE id = ?", (folder,)).fetchone() is None
        ):
            raise StudioError("That folder isn't in your library any more.", 404)
        before = self.chosen(conn).daily
        at = f"{hour:02}:{minute:02}"
        since = before.since
        if on and (not before.on or before.at != at or since is None):
            since = self.now()
        with conn:
            conn.execute(
                """UPDATE studio SET daily = ?, daily_at = ?, daily_since = ?, daily_layout = ?,
                                     daily_from = ?, daily_folder = ?,
                                     problem = CASE WHEN ? THEN problem END
                   WHERE id = 1""",
                (
                    int(on),
                    at,
                    since.isoformat(timespec="seconds") if since else None,
                    layout,
                    "favourites" if folder is None else "folder",
                    folder,
                    int(on),
                ),
            )
        if not on or not before.on or (before.layout, before.folder) != (layout, folder):
            self._cancel_daily(conn)

    def _cancel_daily(self, conn: sqlite3.Connection, before: str | None = None) -> None:
        """The daily change's wallpapers not set yet (waiting, being made or made ahead) let go:
        every one, or those for a day before `before`. One being made stops."""
        query = "WHERE purpose = 'daily' AND state IN ('waiting', 'making', 'ready')"
        given: tuple[str, ...] = ()
        if before is not None:
            query += " AND day < ?"
            given = (before,)
        with conn:
            making = conn.execute(
                f"SELECT id FROM wallpapers {query} AND state = 'making'",  # noqa: S608 - fixed
                given,
            ).fetchall()
            conn.execute(f"UPDATE wallpapers SET state = 'cancelled' {query}", given)  # noqa: S608
        self._cancelled.update(row["id"] for row in making)

    def cancel(self, conn: sqlite3.Connection) -> None:
        """The wallpaper the owner asked for, while it waits or is being made, stopped."""
        row = conn.execute(
            "SELECT id, state FROM wallpapers WHERE purpose IN ('set', 'save') "
            "AND state IN ('waiting', 'making') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return
        with conn:
            waiting = conn.execute(
                "UPDATE wallpapers SET state = 'cancelled' WHERE id = ? AND state = 'waiting'",
                (row["id"],),
            ).rowcount
        if not waiting:  # being made: the worker stops it, and says so
            self._cancelled.add(row["id"])

    # Planning.

    def planned(
        self,
        conn: sqlite3.Connection,
        monitors: Sequence[Monitor],
        layout: Layout,
        gap: int,
        choices: Sequence[Choice],
    ) -> list[Planned]:
        """Each part as it'll be made for these monitors: one for each monitor with a picture,
        or one across all. A picture that isn't there, or won't open, is left out."""
        by_monitor = {each.monitor.casefold(): each for each in choices}
        starts_on = self._ai.starts_on()
        found: list[Planned] = []
        if layout == "across":
            choice = by_monitor.get(ALL)
            seen = self._seen_picture(conn, choice) if choice and monitors else None
            if choice is None or seen is None or isinstance(seen, str):
                return []
            picture, kind, focus, size, picture_version = seen
            for part in parts_across(monitors, gap, size, choice.shape, choice.cut, focus):
                found.append(
                    self._plan(part, choice, picture, picture_version, size, kind, starts_on)
                )
            return found
        for monitor in ordered(monitors):
            choice = by_monitor.get(monitor.id.casefold())
            seen = self._seen_picture(conn, choice) if choice else None
            if choice is None or seen is None or isinstance(seen, str):
                continue
            picture, kind, focus, size, picture_version = seen
            part = part_for(monitor, size, choice.shape, choice.cut, focus)
            found.append(self._plan(part, choice, picture, picture_version, size, kind, starts_on))
        return found

    def _plan(
        self,
        part: Part,
        choice: Choice,
        picture: Picture,
        picture_version: str,
        size: tuple[int, int],
        kind: str,
        starts_on: dict[Literal["photo", "drawing"], Quality],
    ) -> Planned:
        sort = cast("Literal['photo', 'drawing', 'pixels', 'screenshot']", kind)
        quality = choice.quality or starts_on["drawing" if sort == "drawing" else "photo"]
        way = made(part, *size, sort, quality, guessed=True)
        needs: list[str] = []
        if way.model is not None and way.model.download and self._ai.file(way.model) is None:
            needs.append(way.model.download)
        extending = part.frame.shape == "extend" and part.frame.sides != "none"
        if extending and self._ai.lama_file() is None:
            needs.append(LAMA)
        return Planned(part, choice, picture, picture_version, size, way, quality, tuple(needs))

    def focus_of(
        self, conn: sqlite3.Connection, picture_id: int
    ) -> tuple[tuple[float, float] | None, str | None]:
        """Where Mado found a picture's subject, as fractions, or why it can't see it."""
        seen = self._seen_picture(conn, Choice(ALL, picture_id))
        if seen is None:
            return None, None
        if isinstance(seen, str):
            return None, seen
        return seen[2], None

    def _seen_picture(
        self, conn: sqlite3.Connection, choice: Choice
    ) -> tuple[Picture, str, tuple[float, float], tuple[int, int], str] | str | None:
        """A chosen picture as Mado sees it: what it is, its subject and its size; why not, in
        words, when it won't open; None when it isn't there."""
        row = conn.execute(
            "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (choice.picture_id,)
        ).fetchone()
        if row is None:
            return None
        picture = picture_of(conn, choice.picture_id, Path(row["path"]))
        picture_version = version(row["modified"], row["size"])
        try:
            seen = self._sight.of(picture, picture_version)
        except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
            return str(error) or _UNREAD
        except OSError:
            return _UNREAD
        return picture, seen.kind, seen.focus, (seen.width, seen.height), picture_version

    # Asking for a wallpaper.

    def ask(
        self, conn: sqlite3.Connection, purpose: Purpose, saving: dict[str, object] | None = None
    ) -> int:
        """A wallpaper made from the studio's choices, for the monitors as they are: set once
        it's made, or saved as pictures. Raises StudioError when there's nothing to make, or it
        waits for a download."""
        monitors = [each.monitor for each in self.seen()]
        if not monitors:
            raise StudioError(
                self.problem
                or "Windows didn't say what monitors this PC has, so Mado can't make a wallpaper "
                "for them."
            )
        chosen = self.chosen(conn)
        choices = self.choices(conn)
        gap = gap_for(chosen.layout, chosen.gap)
        found = self.planned(conn, monitors, chosen.layout, gap, choices)
        if not found:
            connected = {each.id.casefold() for each in monitors}
            for each in choices:
                across = each.monitor == ALL
                if across != (chosen.layout == "across") or not (
                    across or each.monitor.casefold() in connected
                ):
                    continue
                if isinstance(unseen := self._seen_picture(conn, each), str):
                    raise StudioError(unseen)
            raise StudioError("Pick a picture first: there's nothing to make yet.")
        needs = sorted({need for each in found for need in each.needs})
        if needs:
            raise StudioError(
                "It needs a model Mado downloads the first time it's asked for: download it, "
                "then try again."
            )
        return self._insert(conn, purpose, None, monitors, chosen.layout, gap, choices, saving)

    def _insert(
        self,
        conn: sqlite3.Connection,
        purpose: Purpose,
        day: str | None,
        monitors: Sequence[Monitor],
        layout: Layout,
        gap: int,
        choices: Sequence[Choice],
        saving: dict[str, object] | None,
    ) -> int:
        plan = {
            "layout": layout,
            "gap": gap,
            "monitors": [asdict(each) for each in monitors],
            "choices": [_choice_data(each) for each in choices],
            "saving": saving,
        }
        with conn:
            asked: int = conn.execute(
                """INSERT INTO wallpapers (asked_at, purpose, day, arrangement, plan, state)
                   VALUES (?, ?, ?, ?, ?, 'waiting') RETURNING id""",
                (self._stamp(), purpose, day, arrangement(monitors), json.dumps(plan)),
            ).fetchone()[0]
        self._wake()
        return asked

    def latest(self, conn: sqlite3.Connection) -> Asked | None:
        """The latest wallpaper the owner asked for in the studio (to set or save)."""
        row = conn.execute(
            "SELECT * FROM wallpapers WHERE purpose IN ('set', 'save') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._asked(row) if row is not None else None

    def daily_made(self, conn: sqlite3.Connection) -> Asked | None:
        """The daily change's latest wallpaper: made ahead, being made, or set."""
        row = conn.execute(
            "SELECT * FROM wallpapers WHERE purpose = 'daily' AND state <> 'cancelled' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._asked(row) if row is not None else None

    def _asked(self, row: sqlite3.Row) -> Asked:
        plan = _plan_of(row["plan"])
        saved = plan.get("saved")
        progress = self._live.get(row["id"], 1.0 if row["state"] in _DONE else 0.0)
        began = self._began.get(row["id"])
        left: float | None = None
        if began is not None and row["state"] == "making":
            elapsed = time.monotonic() - began
            if progress >= 0.05 and elapsed >= 1.0:  # by the pace so far
                left = max(elapsed / progress - elapsed, 0.0)
        return Asked(
            id=row["id"],
            purpose=row["purpose"],
            state=row["state"],
            progress=progress,
            seconds_left=left,
            problem=row["problem"],
            day=row["day"],
            set_at=row["set_at"],
            saved=tuple(str(each) for each in cast("list[object]", saved))
            if isinstance(saved, list)
            else (),
        )

    # The worker's turn.

    def __call__(self, stopping: Callable[[], bool]) -> bool:
        """Makes the next wallpaper waiting, then sets it, saves it, or keeps it for its day.
        False when none waits."""
        with closing(db.connect(self._database)) as conn:
            with conn:
                row = conn.execute(
                    """UPDATE wallpapers SET state = 'making', problem = NULL
                       WHERE id = (SELECT id FROM wallpapers WHERE state = 'waiting'
                                   ORDER BY id LIMIT 1)
                       RETURNING *"""
                ).fetchone()
            if row is None:
                return False
            asked: int = row["id"]
            self._live[asked] = 0.0
            self._began[asked] = time.monotonic()

            def stop() -> bool:
                return asked in self._cancelled or stopping()

            try:
                made_parts = self._make(conn, row, stop)
                if stop():
                    raise StoppedError
                match row["purpose"]:
                    case "set":
                        self._set(conn, row, made_parts)
                    case "save":
                        self._save(conn, row, made_parts, stop)
                    case _:
                        self._made_for_the_day(conn, row, made_parts)
            except StoppedError:
                self._stopped(conn, row)
            except (
                StudioError,
                DesktopError,
                SavingError,
                ModelError,
                UnreadableError,
                PictureGoneError,
                NeedsFfmpegError,
                NeedsReaderError,
                encode.SaveError,
            ) as error:
                _state(conn, asked, "failed", problem=str(error))
                if row["purpose"] == "daily":
                    self._daily_failed(conn, row["day"], str(error))
            except Exception:  # the worker must outlive any one wallpaper
                log.exception("Making wallpaper %d hit a problem", asked)
                _state(conn, asked, "failed", problem=_INSIDE)
                if row["purpose"] == "daily":
                    self._daily_failed(conn, row["day"], _INSIDE)
            finally:
                self._live.pop(asked, None)
                self._began.pop(asked, None)
                self._cancelled.discard(asked)
        return True

    def _stopped(self, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        """A wallpaper stopped while it was made: cancelled ones let go; Mado stopping, the daily
        change's made again as it next starts, one the owner asked for not finished then."""
        asked: int = row["id"]
        if asked in self._cancelled:
            _state(conn, asked, "cancelled")
            _delete_made(self.folder / "made" / str(asked), self.folder / "made")
        elif row["purpose"] == "daily":
            _state(conn, asked, "waiting")
        elif row["purpose"] == "save":
            fresh = conn.execute("SELECT * FROM wallpapers WHERE id = ?", (asked,)).fetchone()
            self._finish_cut_short(conn, fresh)
        else:
            _state(conn, asked, "failed", problem=_CLOSED_SETTING)

    def _make(
        self, conn: sqlite3.Connection, row: sqlite3.Row, stopping: Callable[[], bool]
    ) -> list[tuple[Monitor, Path, Picture]]:
        """Each part made at exactly its monitor's pixels, into its own folder in Mado's."""
        plan = _plan_of(row["plan"])
        monitors = [_monitor_from(each) for each in _listed(plan.get("monitors"))]
        choices = [_choice_from(each) for each in _listed(plan.get("choices"))]
        layout: Layout = "across" if plan.get("layout") == "across" else "each"
        gap_given = plan.get("gap")
        gap = int(gap_given) if isinstance(gap_given, int) else 0
        found = self.planned(conn, monitors, layout, gap, choices)
        if not found:
            raise StudioError("Its pictures aren't there any more, so Mado couldn't make it.")
        folder = self.folder / "made" / str(row["id"])
        folder.mkdir(parents=True, exist_ok=True)
        whole = _object(plan.get("saving")).get("what") == "whole"
        if whole and layout == "across":  # one piece at the arrangement's size: made once
            path = folder / "all.png"
            image = self._whole_across(found, monitors, gap, self._told(row["id"], 0, 1), stopping)
            _write_png(image, path)
            return [(_everything(monitors, gap), path, found[0].picture)]
        results: list[tuple[Monitor, Path, Picture]] = []
        for index, each in enumerate(found):
            image = self._part_image(each, self._told(row["id"], index, len(found)), stopping)
            path = folder / f"{each.part.monitor.number} {key_of(each.part.monitor.id)}.png"
            _write_png(image, path)
            results.append((each.part.monitor, path, each.picture))
        if whole:
            path = folder / "all.png"
            _write_png(_whole_each(results, monitors), path)
            results = [(_everything(monitors, 0), path, found[0].picture)]
        return results

    def _told(self, asked: int, index: int, count: int) -> Callable[[float], None]:
        """How far the wallpaper has got, as one of its `count` parts goes along."""

        def told(done: float) -> None:
            self._live[asked] = (index + min(max(done, 0.0), 1.0)) / count

        return told

    def _part_image(
        self, each: Planned, told: Callable[[float], None], stop: Callable[[], bool]
    ) -> Image.Image:
        """One part: the picture (its edges extended once, when they're drawn, so parts laid
        across meet), cut where the owner cut it and made at exactly its monitor's pixels, in
        sRGB with see-through parts on black."""
        image = self._sight.picture(each.picture, each.version)
        profile = image.info.get("icc_profile")
        colours, alpha = split_alpha(image)
        pixels: Pixels = colours
        if alpha is not None:  # a wallpaper is never see-through: what shows through is black
            pixels = (colours.astype(np.float32) * (alpha[..., None] / 255.0)).astype(np.uint8)
        frame = each.part.frame
        offset = (0.0, 0.0)
        if frame.shape == "extend" and frame.sides != "none":
            drawn, exact, _at = self._sight.extended(
                each.picture, each.version, frame.canvas, self._ai.filler, also="wallpaper"
            )
            pixels = drawn[..., :3]
            if drawn.shape[2] == 4:  # see-through parts, and edges drawn as see-through: black
                shown = drawn[..., 3:4].astype(np.float32) / 255.0
                pixels = (pixels.astype(np.float32) * shown).astype(np.uint8)
            offset = (exact.x - frame.canvas.x, exact.y - frame.canvas.y)
        box = each.part.box
        box = Box(box.x + offset[0], box.y + offset[1], box.width, box.height)
        target = (each.part.monitor.width, each.part.monitor.height)
        match each.way.method:
            case "ai":
                assert each.way.model is not None  # noqa: S101 - "ai" always names one
                tiling = self._ai.tiling(each.way.model, Timer())
                out = through_model(
                    pixels,
                    box,
                    target,
                    tiling,
                    told=lambda done, total: told(done / total),
                    stop=stop,
                )
            case "pixels":
                out = by_pixels(pixels, box, target)
            case "smooth":
                out = smoothly(pixels, box, target)
            case _:
                out = smaller(pixels, box, target)
        if stop():
            raise StoppedError
        told(1.0)
        result = Image.fromarray(out).convert("RGB")
        return encode.in_srgb(result, profile if isinstance(profile, bytes) else None)

    def _whole_across(
        self,
        found: list[Planned],
        monitors: Sequence[Monitor],
        gap: int,
        told: Callable[[float], None],
        stop: Callable[[], bool],
    ) -> Image.Image:
        """One across all as one picture: made at the arrangement's size in one piece, at the
        scale every part is made at, what the bezels hide included."""
        first = found[0]
        everything = Part(_everything(monitors, gap), first.part.frame.canvas, first.part.frame)
        planned = Planned(
            everything,
            first.choice,
            first.picture,
            first.version,
            first.size,
            first.way,
            first.quality,
            (),
        )
        return self._part_image(planned, told, stop)

    # Setting.

    def _set(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        made_parts: list[tuple[Monitor, Path, Picture]],
    ) -> None:
        """Sets each part on its monitor, the owner's own kept first. Raises
        MonitorsChangedError when the monitors changed since it was asked for, DesktopError
        when Windows won't, saying what's on the desktop then."""
        with self._lock:
            seen = self.desktop.monitors()
            if arrangement(each.monitor for each in seen) != row["arrangement"]:
                raise MonitorsChangedError
            self._keep_yours(conn, seen)
            filled = False
            if self.desktop.position() == SPAN:  # spanned, Windows shows one picture across all
                self.desktop.set_position(FILL)
                filled = True
            done: list[Monitor] = []
            try:
                for monitor, path, _picture in made_parts:
                    self.desktop.set_wallpaper(monitor.id, str(path))
                    done.append(monitor)
            except DesktopError as error:
                if not done:
                    if filled:  # nothing of Mado's showing: spanned again, as it was
                        with suppress(DesktopError):
                            self.desktop.set_position(SPAN)
                    raise DesktopError(
                        f"{error} Your wallpaper is as it was: try again in a moment."
                    ) from None
                names = ", ".join(each.name for each in done)
                raise DesktopError(
                    f"{error} {names} {'shows' if len(done) == 1 else 'show'} Mado's now, the "
                    "rest as it was: try again in a moment."
                ) from None
            plan = _plan_of(row["plan"])
            plan["set"] = [each.id for each in done]  # the monitors it's on, for tidying
            with conn:
                conn.execute(
                    "UPDATE wallpapers SET state = 'set', made_at = ?, set_at = ?, plan = ? "
                    "WHERE id = ?",
                    (self._stamp(), self._stamp(), json.dumps(plan), row["id"]),
                )
        self.tidy(conn, self.now())

    def _keep_yours(self, conn: sqlite3.Connection, seen: Sequence[Seen]) -> None:
        """Before Mado sets one: each monitor's own wallpaper (one that isn't Mado's) copied
        into Mado's folder, unless kept already, and how Windows showed it, the first time (once
        Mado's wallpaper shows, Windows shows what Mado left, not what the owner had)."""
        mine_showing = any(each.wallpaper and self.mine(each.wallpaper) for each in seen)
        for each in seen:
            current = each.wallpaper
            row = conn.execute(
                "SELECT * FROM desktop_yours WHERE monitor = ?", (each.monitor.id,)
            ).fetchone()
            if current and self.mine(current):
                self._copy_again(conn, row)
                continue
            colour = not current
            same = row is not None and (
                (colour and row["path"] is None)
                or _same(row["path"], current)
                or _same(row["kept"], current)
            )
            copied = colour or bool(row is not None and row["kept"] and Path(row["kept"]).is_file())
            if same and copied:
                continue  # kept already, as it is
            copy = self._copy_yours(each.monitor, current, seen)
            with conn:
                conn.execute(
                    """INSERT INTO desktop_yours (monitor, name, path, kept, at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (monitor) DO UPDATE SET name = excluded.name,
                           path = excluded.path, kept = excluded.kept, at = excluded.at""",
                    (
                        each.monitor.id,
                        each.monitor.name,
                        current or None,
                        str(copy) if copy else None,
                        self._stamp(),
                    ),
                )
            if (
                row is not None
                and row["kept"]
                and not _same(row["kept"], str(copy) if copy else None)
            ):
                self._let_go_of_copy(Path(row["kept"]), seen)
        has_before = conn.execute("SELECT 1 FROM desktop_before").fetchone() is not None
        if not has_before or not mine_showing:
            slideshow = self.desktop.slideshow()
            with conn:
                conn.execute(
                    """INSERT INTO desktop_before (id, position, slideshow, spotlight, at)
                       VALUES (1, ?, ?, ?, ?)
                       ON CONFLICT (id) DO UPDATE SET position = excluded.position,
                           slideshow = excluded.slideshow, spotlight = excluded.spotlight,
                           at = excluded.at""",
                    (
                        self.desktop.position(),
                        json.dumps(asdict(slideshow)) if slideshow else None,
                        int(self.desktop.spotlight()),
                        self._stamp(),
                    ),
                )

    def _copy_again(self, conn: sqlite3.Connection, row: sqlite3.Row | None) -> None:
        """A monitor showing Mado's wallpaper whose owner's own Mado couldn't copy before: copied
        now, while their file is still there."""
        if row is None or not row["path"] or not Path(row["path"]).is_file():
            return
        if row["kept"] and Path(row["kept"]).is_file():
            return
        monitor = Monitor(row["monitor"], row["name"], 0, 0, 0, 0, 0)
        copy = self._copy_yours(monitor, row["path"], [])
        if copy is not None:
            with conn:
                conn.execute(
                    "UPDATE desktop_yours SET kept = ? WHERE monitor = ?",
                    (str(copy), row["monitor"]),
                )

    def _copy_yours(
        self, monitor: Monitor, current: str | None, seen: Sequence[Seen]
    ) -> Path | None:
        """A copy of the owner's own wallpaper in Mado's folder: their file, or, when it's gone
        and one picture shows on every monitor, Windows' own copy of it (with a picture of its own
        on each, Windows keeps a copy for each in an order it doesn't say, so Mado doesn't
        guess). Their file is only read. A colour has nothing to copy."""
        if not current:
            return None
        if Path(current).is_file():
            source: Path | None = Path(current)
        else:
            pictures = {str(each.wallpaper).casefold() for each in seen if each.wallpaper}
            source = self._windows_copy() if pictures == {current.casefold()} else None
        if source is None:
            return None
        folder = self.folder / "yours"
        folder.mkdir(parents=True, exist_ok=True)
        extension = source.suffix.lower() or _sniffed(source)
        target = folder / f"{key_of(monitor.id)} {self.now():%Y-%m-%d %H.%M.%S}{extension}"
        partial = target.with_name(target.name + ".partial")
        try:
            shutil.copyfile(source, partial)
            partial.replace(target)
        except OSError as error:
            partial.unlink(missing_ok=True)
            log.warning("Mado couldn't keep a copy of the wallpaper %s: %s", source, error)
            return None
        return target

    def _windows_copy(self) -> Path | None:
        themes = self.themes
        if themes is None:
            roaming = os.environ.get("APPDATA")
            if not roaming:
                return None
            themes = Path(roaming) / "Microsoft" / "Windows" / "Themes"
        found = themes / _TRANSCODED
        return found if found.is_file() else None

    def _let_go_of_copy(self, copy: Path, seen: Sequence[Seen]) -> None:
        """A copy Mado kept of the owner's wallpaper that's been kept anew: deleted, if it's
        Mado's own and Windows isn't showing it."""
        if not _inside(copy, self.folder / "yours"):
            return
        if any(each.wallpaper and _same(each.wallpaper, str(copy)) for each in seen):
            return
        with suppress(OSError):
            copy.unlink(missing_ok=True)

    def mine(self, path: str) -> bool:
        """Whether a wallpaper is one Mado made. Its copy of the owner's own stands for theirs."""
        return _inside(Path(path), self.folder / "made")

    def yours(self, conn: sqlite3.Connection) -> list[Kept]:
        return [
            Kept(row["monitor"], row["name"], row["path"], row["kept"])
            for row in conn.execute("SELECT * FROM desktop_yours ORDER BY monitor")
        ]

    def before(self, conn: sqlite3.Connection) -> Before | None:
        row = conn.execute("SELECT * FROM desktop_before WHERE id = 1").fetchone()
        if row is None:
            return None
        slideshow = None
        if row["slideshow"]:
            with suppress(ValueError, TypeError):
                data = json.loads(row["slideshow"])
                slideshow = Slideshow(
                    str(data["folder"]), int(data["interval"]), bool(data["shuffle"])
                )
        return Before(row["position"], slideshow, bool(row["spotlight"]))

    def put_back(self, conn: sqlite3.Connection, monitor: str | None = None) -> list[str]:
        """The owner's own wallpaper back on each monitor showing Mado's (one the owner gave a
        wallpaper of their own since is theirs), or on the one asked for: their file, or Mado's
        copy when it's gone; Windows' slideshow started again and a span spanned again, as
        Windows allows. All of them back stops the daily change first. Says what couldn't be,
        and how the owner can, in sentences; a monitor Windows refuses doesn't stop the rest."""
        told: list[str] = []
        whole = monitor is None
        if whole:  # first, so it's off whatever Windows says below
            with conn:
                conn.execute("UPDATE studio SET daily = 0 WHERE id = 1")
            self._cancel_daily(conn)
        with self._lock:
            seen = self.desktop.monitors()
            before = self.before(conn)
            kept = {each.monitor.casefold(): each for each in self.yours(conn)}
            if monitor is None:
                shown = [each for each in seen if each.wallpaper and self.mine(each.wallpaper)]
            else:
                shown = [each for each in seen if each.monitor.id.casefold() == monitor.casefold()]
            # A monitor showing a wallpaper the owner chose since Mado set its own.
            theirs_since = [
                each
                for each in seen
                if each.wallpaper
                and not self.mine(each.wallpaper)
                and not _kept_as(kept.get(each.monitor.id.casefold()), each.wallpaper)
            ]
            started = False
            refused = False
            if whole and before is not None and before.slideshow is not None:
                if theirs_since:
                    told.append(
                        "Your slideshow wasn't started again, as a monitor shows a wallpaper you "
                        "chose since: turn it on in Settings › Personalisation › Background."
                    )
                else:
                    try:
                        self.desktop.start_slideshow(before.slideshow)
                        started = True
                    except DesktopError:
                        told.append(
                            "Windows wouldn't start your slideshow again. Turn it on in Settings "
                            "› Personalisation › Background."
                        )
            if not started:
                for each in shown:
                    try:
                        told.extend(self._put_back_one(each, kept.get(each.monitor.id.casefold())))
                    except DesktopError:
                        refused = True
                        told.append(
                            f"Windows wouldn't put your own wallpaper back on {each.monitor.name}: "
                            "try again in a moment."
                        )
            # Spanned again only while Windows has the fill Mado set: a fit the owner chose since
            # is theirs.
            if whole and before is not None and before.position == SPAN:
                with suppress(DesktopError):
                    if self.desktop.position() == FILL:
                        self.desktop.set_position(SPAN)
            if whole and before is not None and before.spotlight:
                told.append(
                    "Windows spotlight was on, and only Windows turns it on again: choose Windows "
                    "spotlight in Settings › Personalisation › Background."
                )
            if whole and not refused:  # all back: the next set notes how Windows shows it then
                with conn:
                    conn.execute("DELETE FROM desktop_before")
        return told

    def _put_back_one(self, each: Seen, kept: Kept | None) -> list[str]:
        """One monitor's own wallpaper back. Raises DesktopError when Windows won't."""
        name = each.monitor.name
        if kept is None:
            return [f"Mado hasn't set a wallpaper on {name}, so there's nothing to put back there."]
        if kept.path is None:
            self.desktop.set_wallpaper(each.monitor.id, "")
            return []
        if Path(kept.path).is_file():
            self.desktop.set_wallpaper(each.monitor.id, kept.path)
            return []
        if kept.kept and Path(kept.kept).is_file():
            self.desktop.set_wallpaper(each.monitor.id, kept.kept)
            return []
        return [f"Your own wallpaper for {name} isn't there any more, nor Mado's copy of it."]

    # Saving as pictures.

    def _save(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        made_parts: list[tuple[Monitor, Path, Picture]],
        stop: Callable[[], bool],
    ) -> None:
        """The parts (or the whole arrangement) saved as new pictures into the folder the owner
        picked, each with its line in History, as any Save. The file each is written to is noted
        first, so a Save Mado's closing cuts short is cleared away as it next starts; a stop
        between pictures saves no more."""
        plan = _plan_of(row["plan"])
        saving = _object(plan.get("saving"))
        if not saving.get("folder"):
            raise StudioError("Mado doesn't know where to save it.")
        folder = Path(str(saving.get("folder")))
        format_ = cast("Format", saving.get("format") or "PNG")
        quality = saving.get("quality")
        chosen = Saving(
            how="new",
            format=format_,
            quality=int(quality) if isinstance(quality, int) else _quality_for(format_),
            folder=folder,
            keep_location=False,
        )
        written: list[str] = []

        def noted(writing: Path | None) -> None:
            plan["saved"] = written
            if writing is None:
                plan.pop("writing", None)
            else:
                plan["writing"] = str(writing)
            with conn:
                conn.execute(
                    "UPDATE wallpapers SET plan = ? WHERE id = ?", (json.dumps(plan), row["id"])
                )

        for monitor, path, picture in made_parts:
            if stop():
                raise StoppedError
            with Image.open(path) as opened:
                image = opened.convert("RGB")
            size = image.size
            across = monitor.id == ALL
            named = f"{monitor.name} wallpaper"  # "Harbour at dusk (Studio 27 wallpaper).png"
            made_for = (
                "a wallpaper across all monitors" if across else f"a wallpaper on {monitor.name}"
            )
            naming = Naming(size[0], size[1], named, made_for, None)
            saved = keep(
                lambda target, shown=image, at=size, pic=picture: write(
                    shown, pic, at, chosen, target, dpi=None, reader=self._sight.reader
                ),
                picture,
                naming,
                chosen,
                conn=conn,
                quarantine=self._quarantine,
                now=self.now(),
                job_id=None,
                writing=noted,
            )
            written.append(str(saved.path))
            noted(None)
        plan["saved"] = written
        with conn:
            conn.execute(
                "UPDATE wallpapers SET state = 'saved', made_at = ?, plan = ? WHERE id = ?",
                (self._stamp(), json.dumps(plan), row["id"]),
            )

    # The daily change.

    def start(self) -> None:
        """Looks after the daily change, and Mado's own wallpapers, every half minute."""
        self._stopping.clear()
        self._thread = threading.Thread(target=self._loop, name="wallpaper", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                self.tick()
            except Exception:  # the daily change must outlive any one look
                log.exception("The daily wallpaper hit a problem")
            self._stopping.wait(EVERY)

    def tick(self) -> None:
        """One look: a day's wallpaper never set let go once its day has passed; today's change
        once its time has come (made then, when it wasn't made ahead); the next made ahead from
        12 hours before; and Mado's own wallpapers tidied once a day."""
        now = self.now()
        today = now.date().isoformat()
        with closing(db.connect(self._database)) as conn:
            self._cancel_daily(conn, before=today)
            daily = self.chosen(conn).daily
            if daily.on:
                due = _due(daily, now)
                if now >= due:
                    self._change(conn, due.date().isoformat())
                elif now >= due - AHEAD:
                    self._prepare(conn, due.date().isoformat())
            if self._tidied_on != today:
                self.tidy(conn, now)
                self._tidied_on = today

    def next_change(self, conn: sqlite3.Connection) -> datetime | None:
        """When the daily change next changes the wallpaper; None while it's off."""
        daily = self.chosen(conn).daily
        return _due(daily, self.now()) if daily.on else None

    def _change(self, conn: sqlite3.Connection, day: str) -> None:
        """Today's change: the wallpaper made ahead, set now, when it's for these monitors and
        its files are there; else made now, and set once it is."""
        seen = self.seen()
        if not seen:
            return  # Windows will say next look
        here = arrangement(each.monitor for each in seen)
        rows = conn.execute(
            """SELECT * FROM wallpapers WHERE purpose = 'daily' AND day = ?
               AND state IN ('waiting', 'making', 'ready') ORDER BY id DESC""",
            (day,),
        ).fetchall()
        for row in rows:
            if row["arrangement"] != here:  # the monitors changed: made again
                self._let_go(conn, row)
                continue
            if row["state"] != "ready":
                return  # waiting, or being made: set as soon as it is
            try:
                made_parts = self._made_parts(conn, row)
            except StudioError:  # its files went: made again now
                self._let_go(conn, row)
                break
            self._set_for_the_day(conn, row, made_parts)
            return
        self._ask_for_the_day(conn, day, seen, now_too=True)

    def _let_go(self, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        """A daily wallpaper not wanted after all: cancelled, and stopped if it's being made."""
        if row["state"] == "making":
            self._cancelled.add(row["id"])
        _state(conn, row["id"], "cancelled")

    def _prepare(self, conn: sqlite3.Connection, day: str) -> None:
        """The day's wallpaper made ahead, so the change is instant: asked for once (one that
        failed is tried again at the change time), and when none suits, looked for again every
        ten minutes rather than every look."""
        seen = self.seen()
        if not seen:
            return
        here = arrangement(each.monitor for each in seen)
        row = conn.execute(
            """SELECT 1 FROM wallpapers WHERE purpose = 'daily' AND day = ? AND arrangement = ?
               AND state IN ('waiting', 'making', 'ready', 'set', 'failed')""",
            (day, here),
        ).fetchone()
        if row is not None:
            return
        looked = self._asked_ahead.get((day, here))
        if looked is not None and time.monotonic() - looked < ASK_AGAIN:
            return
        self._asked_ahead = {(day, here): time.monotonic()}
        self._ask_for_the_day(conn, day, seen, now_too=False)

    def _ask_for_the_day(
        self, conn: sqlite3.Connection, day: str, seen: Sequence[Seen], *, now_too: bool
    ) -> None:
        chosen = self.chosen(conn)
        monitors = [each.monitor for each in seen]
        candidates, skipped = self.candidates(conn, chosen.daily.folder)
        gap = gap_for(chosen.daily.layout, chosen.gap)
        found = picks(candidates, monitors, chosen.daily.layout, gap, day)
        if not found:
            if now_too:
                self._daily_problem(
                    conn, day, self._nothing_suits(conn, chosen.daily, candidates, skipped)
                )
            return
        choices = [Choice(monitor, picture) for monitor, picture in found.items()]
        self._insert(conn, "daily", day, monitors, chosen.daily.layout, gap, choices, None)

    def candidates(
        self, conn: sqlite3.Connection, folder: int | None, *, look: bool = True
    ) -> tuple[list[Candidate], int]:
        """The pictures the daily change could show, and how many it skips: gone, moved since,
        on a drive that isn't connected, or in a quarantine. Each with the day it was last
        shown. `look`: each file is looked for too, as a pick does; without it (the studio's
        counts, asked every few seconds), Mado's records and each drive say."""
        if folder is None:
            rows = conn.execute(
                """SELECT p.* FROM favourites AS f JOIN pictures AS p ON p.id = f.picture_id
                   WHERE p.read_at IS NOT NULL AND p.problem IS NULL
                     AND NOT (p.raw = 1 AND p.width IS NULL)"""
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM pictures WHERE folder_id = ? AND gone_at IS NULL
                   AND read_at IS NOT NULL AND problem IS NULL
                   AND NOT (raw = 1 AND width IS NULL)""",
                (folder,),
            ).fetchall()
        shown = self.shown(conn)
        found: list[Candidate] = []
        skipped = 0
        for row in rows:
            path = Path(row["path"])
            if (
                row["gone_at"] is not None
                or _in_quarantine(path)
                or not self._drive_there(path)
                or (look and not path.is_file())
            ):
                skipped += 1
                continue
            if row["width"] and row["height"]:
                found.append(
                    Candidate(row["id"], row["width"], row["height"], shown.get(row["id"]))
                )
        return found, skipped

    def _drive_there(self, path: Path) -> bool:
        """Whether a picture's drive is connected: each drive looked at once a minute, as one
        that's away can take a while to say so."""
        anchor = path.anchor.casefold()
        if not anchor:
            return True
        looked = self._drives.get(anchor)
        if looked is None or time.monotonic() - looked[0] >= DRIVES_FOR:
            looked = (time.monotonic(), Path(path.anchor).exists())
            self._drives[anchor] = looked
        return looked[1]

    def shown(self, conn: sqlite3.Connection) -> dict[int, str]:
        """The day the daily change last showed each picture."""
        found: dict[int, str] = {}
        for row in conn.execute(
            "SELECT day, plan FROM wallpapers WHERE purpose = 'daily' AND state = 'set' "
            "ORDER BY day, id"
        ):
            for each in _listed(_plan_of(row["plan"]).get("choices")):
                picture = each.get("picture")
                if isinstance(picture, int):
                    found[picture] = str(row["day"])
        return found

    def _nothing_suits(
        self, conn: sqlite3.Connection, daily: Daily, candidates: list[Candidate], skipped: int
    ) -> str:
        if daily.folder is not None:
            row = conn.execute("SELECT path FROM folders WHERE id = ?", (daily.folder,)).fetchone()
            name = PureWindowsPath(row["path"]).name if row else "that folder"
            if not candidates and not skipped:
                return (
                    f"There are no pictures in {name} Mado can show, so the wallpaper stayed as "
                    "it was."
                )
        elif not candidates and not skipped:
            return (
                "No favourites yet: give pictures a heart, and the wallpaper changes to one of "
                "them each day."
            )
        if not candidates:
            return (
                "None of them are there now (gone, moved or on a drive that isn't connected), so "
                "the wallpaper stayed as it was."
            )
        return (
            "None of them suit your monitors: a wallpaper needs a picture its way round, big "
            "enough not to look painted. The wallpaper stayed as it was."
        )

    def _made_for_the_day(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        made_parts: list[tuple[Monitor, Path, Picture]],
    ) -> None:
        """A daily wallpaper made: set now when its change is due, else ready for it."""
        daily = self.chosen(conn).daily
        now = self.now()
        if daily.on and row["day"] == now.date().isoformat() and now >= _due(daily, now):
            self._set_for_the_day(conn, row, made_parts)
            return
        with conn:
            conn.execute(
                "UPDATE wallpapers SET state = 'ready', made_at = ? WHERE id = ?",
                (self._stamp(), row["id"]),
            )

    def _set_for_the_day(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        made_parts: list[tuple[Monitor, Path, Picture]],
    ) -> None:
        try:
            self._set(conn, row, made_parts)
        except MonitorsChangedError:  # made again for the monitors as they are, next look
            _state(conn, row["id"], "cancelled")
            return
        except (StudioError, DesktopError) as error:
            _state(conn, row["id"], "failed", problem=str(error))
            self._daily_problem(conn, row["day"], str(error))
            return
        with conn:
            conn.execute(
                "UPDATE studio SET changed_on = ?, problem = NULL WHERE id = 1", (row["day"],)
            )

    def _daily_failed(self, conn: sqlite3.Connection, day: str | None, problem: str) -> None:
        """A daily wallpaper that couldn't be made: its day's change given up on, and why, once
        its time has come; made ahead, it's tried again at the change time."""
        daily = self.chosen(conn).daily
        now = self.now()
        due = _due(daily, now)
        if daily.on and day == due.date().isoformat() and now >= due:
            self._daily_problem(conn, day, problem)

    def _daily_problem(self, conn: sqlite3.Connection, day: str | None, problem: str) -> None:
        """The day's change given up on, and why: tried again the next day."""
        with conn:
            conn.execute(
                "UPDATE studio SET changed_on = ?, problem = ? WHERE id = 1", (day, problem)
            )

    def _made_parts(
        self, conn: sqlite3.Connection, row: sqlite3.Row
    ) -> list[tuple[Monitor, Path, Picture]]:
        """A wallpaper made ahead: each monitor's part, as its folder holds them."""
        plan = _plan_of(row["plan"])
        folder = self.folder / "made" / str(row["id"])
        found: list[tuple[Monitor, Path, Picture]] = []
        for each in _listed(plan.get("monitors")):
            monitor = _monitor_from(each)
            path = folder / f"{monitor.number} {key_of(monitor.id)}.png"
            if path.is_file():
                found.append((monitor, path, Picture(path, "picture", "PNG", None)))
        if not found:
            raise StudioError("The wallpaper made ahead isn't there any more.")
        return found

    # Mado's own files.

    def tidy(self, conn: sqlite3.Connection, now: datetime) -> None:
        """Mado's own wallpapers that no monitor shows, nor set in the last three days, nor
        waiting for their day, deleted from its folder (one saved, cancelled or that failed at
        once); the daily change's records stay, as what it showed which day."""
        cutoff = (now - timedelta(days=KEPT_DAYS)).isoformat(timespec="seconds")
        made_folder = self.folder / "made"
        keep_ids: set[int] = set()
        for each in self.seen():  # what a monitor shows now, whatever its records say
            path = Path(each.wallpaper) if each.wallpaper and self.mine(each.wallpaper) else None
            if path is not None and path.parent.name.isdigit():
                keep_ids.add(int(path.parent.name))
        showing: set[str] = set()
        newest = 0
        for row in conn.execute(
            "SELECT id, state, set_at, asked_at, plan FROM wallpapers "
            "ORDER BY COALESCE(set_at, asked_at) DESC, id DESC"
        ):
            newest = max(newest, row["id"])
            if row["state"] in ("waiting", "making", "ready"):
                keep_ids.add(row["id"])
                continue
            if row["state"] != "set":
                continue  # saved into the owner's folder, failed or cancelled: not needed
            plan = _plan_of(row["plan"])
            set_on = plan.get("set")
            monitors = (
                {str(each).casefold() for each in cast("list[object]", set_on)}
                if isinstance(set_on, list)
                else {str(each.get("id", "")).casefold() for each in _listed(plan.get("monitors"))}
            )
            if monitors - showing:  # the latest on a monitor
                keep_ids.add(row["id"])
                showing |= monitors
            if str(row["set_at"]) >= cutoff:
                keep_ids.add(row["id"])
        if made_folder.is_dir():
            for each in made_folder.iterdir():
                if not (each.is_dir() and each.name.isdigit()):
                    continue
                number = int(each.name)
                if number not in keep_ids and number <= newest:  # newer: asked for meanwhile
                    _delete_made(each, made_folder)
        old = [
            (row["id"],)
            for row in conn.execute(
                """SELECT id FROM wallpapers WHERE asked_at < ?
                   AND NOT (purpose = 'daily' AND state = 'set')""",
                (cutoff,),
            )
            if row["id"] not in keep_ids
        ]
        with conn:
            conn.executemany("DELETE FROM wallpapers WHERE id = ?", old)

    def bytes_kept(self) -> int:
        """How much room Mado's own wallpapers take."""
        total = 0
        if self.folder.is_dir():
            for each in self.folder.rglob("*"):
                with suppress(OSError):
                    if each.is_file():
                        total += each.stat().st_size
        return total

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")


_DONE = ("ready", "set", "saved")
_INSIDE = "Something went wrong inside Mado making the wallpaper; its log says what."
_CLOSED_SETTING = "Mado was closed before it was set, so your wallpaper is as it was. Set it again."
_TAKEN_OUT = (
    "The folder every day's wallpaper came from was taken out of the library, so the change is "
    "off: turn it on with your favourites or another folder."
)
_UNREAD = "Mado couldn't open that picture, so it can't make a wallpaper from it."


def gap_for(layout: Layout, gap: int) -> int:
    """The gap for the bezels as a layout has it: one across all's only."""
    return gap if layout == "across" else 0


def _due(daily: Daily, now: datetime) -> datetime:
    """When the daily change is next due: today's time, unless today's change is made (or given
    up on) or that time came before the change was turned on or its time set; else tomorrow's.
    Past already when it's due and the next look makes it."""
    hour, minute = _time(daily.at)
    due = _moment(now, hour, minute)
    if (daily.changed_on or "") >= now.date().isoformat() or (
        daily.since is not None and due < daily.since
    ):
        due += timedelta(days=1)
    return due


def _moment_of(text: object) -> datetime | None:
    """A moment as the records keep it; None for none."""
    if not isinstance(text, str) or not text:
        return None
    try:
        found = datetime.fromisoformat(text)
    except ValueError:
        return None
    return found if found.tzinfo is not None else found.astimezone()


def _kept_as(kept: Kept | None, wallpaper: str) -> bool:
    """Whether a monitor shows the owner's own wallpaper as Mado kept it."""
    return kept is not None and (_same(kept.path, wallpaper) or _same(kept.kept, wallpaper))


def _whole_each(
    made_parts: list[tuple[Monitor, Path, Picture]], monitors: Sequence[Monitor]
) -> Image.Image:
    """One for each as one picture: every part where its monitor sits, on black."""
    places = spread(monitors, 0)
    whole = bounds(places.values())
    canvas = Image.new("RGB", (round(whole.width), round(whole.height)), (0, 0, 0))
    for monitor, path, _picture in made_parts:
        place = places[monitor.id]
        with Image.open(path) as part:
            canvas.paste(part.convert("RGB"), (round(place.x - whole.x), round(place.y - whole.y)))
    return canvas


def _state(conn: sqlite3.Connection, asked: int, state: str, *, problem: str | None = None) -> None:
    with conn:
        conn.execute(
            "UPDATE wallpapers SET state = ?, problem = ? WHERE id = ?", (state, problem, asked)
        )


def _plan_of(text: object) -> dict[str, object]:
    try:
        found = json.loads(str(text))
    except ValueError:
        return {}
    return cast("dict[str, object]", found) if isinstance(found, dict) else {}


def _choice_data(choice: Choice) -> dict[str, object]:
    return {
        "monitor": choice.monitor,
        "picture": choice.picture_id,
        "shape": choice.shape,
        "x": choice.cut.x,
        "y": choice.cut.y,
        "zoom": choice.cut.zoom,
        "quality": choice.quality,
    }


def _choice_from(data: dict[str, object]) -> Choice:
    def number(key: str) -> float | None:
        value = data.get(key)
        return float(value) if isinstance(value, int | float) else None

    shape = data.get("shape")
    quality = data.get("quality")
    return Choice(
        monitor=str(data.get("monitor", "")),
        picture_id=int(picture) if isinstance(picture := data.get("picture"), int) else 0,
        shape="extend" if shape == "extend" else "crop",
        cut=Cut(number("x"), number("y"), number("zoom") or 1.0),
        quality="fast" if quality == "fast" else "best" if quality == "best" else None,
    )


def _monitor_from(data: dict[str, object]) -> Monitor:
    """A monitor as a wallpaper's plan keeps it."""

    def whole(key: str) -> int:
        value = data.get(key)
        return int(value) if isinstance(value, int | float) else 0

    scale = data.get("scale")
    return Monitor(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        number=whole("number"),
        x=whole("x"),
        y=whole("y"),
        width=whole("width"),
        height=whole("height"),
        scale=float(scale) if isinstance(scale, int | float) else 1.0,
        rotation=whole("rotation"),
        main=data.get("main") is True,
    )


def _object(found: object) -> dict[str, object]:
    """A plan's object as a dict; empty for anything else."""
    return cast("dict[str, object]", found) if isinstance(found, dict) else {}


def _listed(found: object) -> list[dict[str, object]]:
    """The objects in a plan's list, each as a dict; none for anything else."""
    if not isinstance(found, list):
        return []
    return [
        cast("dict[str, object]", each)
        for each in cast("list[object]", found)
        if isinstance(each, dict)
    ]


def _everything(monitors: Sequence[Monitor], gap: int) -> Monitor:
    """The whole arrangement as one monitor would be: its size with the gap."""
    whole = bounds(spread(monitors, gap).values())
    return Monitor(ALL, "All monitors", 0, 0, 0, round(whole.width), round(whole.height))


def _write_png(image: Image.Image, path: Path) -> None:
    """A wallpaper's file: PNG, which Windows shows as it is, checked whole."""
    partial = path.with_name(path.name + ".partial")
    try:
        image.save(partial, format="PNG", compress_level=6)
        encode.check(partial, image.size)
        partial.replace(path)
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise StudioError(
            f"Mado couldn't keep the wallpaper in its data folder: {error.strerror or error}."
        ) from None


def _delete_made(folder: Path, made_folder: Path) -> None:
    """One of Mado's own wallpapers deleted: only what it writes, only in its own folder."""
    if folder.parent != made_folder:
        return
    for each in folder.iterdir():
        if each.is_file() and each.suffix.lower() in (".png", ".partial"):
            with suppress(OSError):
                each.unlink()
    with suppress(OSError):
        folder.rmdir()


def _sniffed(path: Path) -> str:
    """The extension a file without one should have, by what's in it: Windows' own copy of a
    wallpaper has none."""
    try:
        with Image.open(path) as image:
            found = image.format or ""
    except OSError, ValueError:
        return ".jpg"
    return {"PNG": ".png", "BMP": ".bmp", "WEBP": ".webp"}.get(found, ".jpg")


def _quality_for(format_: Format) -> int | None:
    return {"JPEG": 92, "WebP": 90, "AVIF": 80}.get(format_)


def _fraction(value: float | None) -> float | None:
    return None if value is None else min(max(value, 0.0), 1.0)


def _time(at: str) -> tuple[int, int]:
    """A time of day, "07:00", as its hour and minute. Raises StudioError for another."""
    try:
        hour_text, minute_text = at.split(":")
        hour, minute = int(hour_text), int(minute_text)
    except ValueError:
        raise StudioError("Give the time as hours and minutes: 07:00.", 422) from None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise StudioError("Give the time as hours and minutes: 07:00.", 422)
    return hour, minute


def _moment(now: datetime, hour: int, minute: int) -> datetime:
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _same(first: object, second: object) -> bool:
    return bool(first) and bool(second) and str(first).casefold() == str(second).casefold()


def _inside(path: Path, folder: Path) -> bool:
    return PureWindowsPath(os.path.normpath(path)).is_relative_to(
        PureWindowsPath(os.path.normpath(folder))
    )


def _in_quarantine(path: Path) -> bool:
    folded = QUARANTINE.casefold()
    return any(part.casefold() == folded for part in PureWindowsPath(path).parts)
