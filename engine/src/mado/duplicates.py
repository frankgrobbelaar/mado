"""Duplicates and bursts in the library: found in the background, reviewed by the owner, and the
rest of each group set aside (docs/stack/duplicates.md).

- Looking: a thread of its own looks at each picture once it's read, and again once its file
  changes: its fingerprints, from the thumbnail the scan made (so nothing is decoded twice), kept
  in `prints`; for files that share a size, their bytes' digest; and for the shots of a burst,
  their sharpness, from the picture itself at a fixed size, as the thumbnail is too small to
  tell a sharp shot from a soft one.
- Grouping: what was looked at, the owner's "not the same" and History's families (an original
  and what Mado made from it) through mado/core/duplicates.py, kept for the review and found
  again after each look and each change the owner makes.
- Setting aside: the rest of a group, each picture into its own drive's quarantine with a line of
  History, a review's all under one line. Each is checked first to be as it was when compared,
  and its group's kept picture too; one that changed, is open in another app or is on a drive
  that isn't connected is left as it is, with a sentence. Nothing is ever deleted.
"""

import hashlib
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Literal

import numpy as np
from PIL import Image

from mado import db, history
from mado.config import DataPaths
from mado.core.duplicates import Group, Known, groups
from mado.core.files import kind_of
from mado.core.likeness import FINE_SIDE, SIDE, fine, fingerprint, sharpness
from mado.core.naming import QUARANTINE
from mado.jobs import drive_of, drive_there
from mado.pictures import (
    Command,
    NeedsFfmpegError,
    PictureGoneError,
    UnreadableError,
    decode,
)
from mado.previews import Previews, Source
from mado.quarantine import InUseMoveError, MoveError, Quarantine

log = logging.getLogger(__name__)

SHARP_SIDE = 1024  # the grey copy a shot's sharpness is measured on, its longer side
_REST = 300.0  # seconds the thread rests with nothing to look at; a scan ending wakes it
_CHUNK = 64  # pictures looked at between saves
_GROUP_EVERY = 20.0  # seconds between groupings while a long look goes on
_READ = 1 << 20  # bytes read at a time for a digest
# What the review looks at: read, opens, not camera RAW, there.
_LISTED = (
    "p.gone_at IS NULL AND p.read_at IS NOT NULL AND p.problem IS NULL AND p.raw = 0"
    " AND p.folder_id IS NOT NULL"  # the library's, never a picture opened from outside it
)


@dataclass(frozen=True)
class Found:
    """The groups found lately, and what Mado knows of every picture in them."""

    groups: tuple[Group, ...] = ()
    pictures: Mapping[int, Known] = field(default_factory=dict[int, Known])


@dataclass(frozen=True)
class Looking:
    looked: int  # pictures looked at, as they are now
    of: int  # pictures to look at: every one that opens, or will once it's read


@dataclass(frozen=True)
class Left:
    """A picture left as it is, and why."""

    name: str
    why: str


@dataclass(frozen=True)
class SetAside:
    review: int | None  # the review's number, when anything was set aside
    pictures: int
    bytes: int
    left: tuple[Left, ...]


class Finder:
    """Looks at the library's pictures in the background and keeps the groups found."""

    def __init__(
        self,
        paths: DataPaths,
        previews: Previews,
        ffmpeg: Callable[[], Command | None],
        *,
        now: Callable[[], datetime],
        workers: int = 4,
    ) -> None:
        self._paths = paths
        self._previews = previews
        self._ffmpeg = ffmpeg
        self._now = now
        self._workers = workers
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._asked = 0  # wakes asked for: the thread rests only once it has seen them all
        self._thread: threading.Thread | None = None
        self._found = Found()
        self._looking = False
        self._grouped = False  # grouped since the engine started
        self._had_ffmpeg = False  # ffmpeg was there at the last look

    def start(self) -> None:
        """Groups what was looked at before, then looks at what's new in the background. A
        picture whose thumbnail couldn't be made last time (no ffmpeg yet, say) is tried again."""
        with closing(db.connect(self._paths.database)) as conn, conn:
            conn.execute("DELETE FROM prints WHERE hash IS NULL")
        self._had_ffmpeg = self._ffmpeg() is not None
        self._stopping.clear()
        self.wake()
        self._thread = threading.Thread(target=self._loop, name="duplicates", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        """Looks again now: a scan ended, or the owner changed something."""
        with self._lock:
            self._asked += 1
            self._idle.clear()
        self._wake.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Till nothing's left to look at (tests). True when so."""
        return self._idle.wait(timeout)

    def found(self) -> Found:
        with self._lock:
            return self._found

    def progress(self, conn: sqlite3.Connection, *, scanning: bool = False) -> Looking | None:
        """How far looking has got, of the pictures read so far: while the thread looks, or a
        scan reads what it will look at next (`scanning`) and some aren't looked at yet. None
        otherwise: a picture it can't look at now (its drive away) never keeps it "looking"."""
        with self._lock:
            looking = self._looking
        if not looking and not scanning:
            return None
        row = conn.execute(
            f"""SELECT COUNT(*) AS of, COUNT(f.picture_id) AS looked FROM pictures AS p
                LEFT JOIN prints AS f
                  ON f.picture_id = p.id AND f.size = p.size AND f.modified = p.modified
                WHERE {_LISTED}"""  # noqa: S608 - a fixed fragment
        ).fetchone()
        if not looking and row["looked"] >= row["of"]:
            return None
        return Looking(looked=min(row["looked"], row["of"]), of=row["of"])

    def regroup(self, conn: sqlite3.Connection) -> Found:
        """Groups again now, as the owner changed something: what's been looked at already, the
        shots' sharpness as it's known (the thread measures what's missing)."""
        found = _grouped(conn)
        with self._lock:
            self._found = found
        return found

    def _loop(self) -> None:
        woken = True
        while not self._stopping.is_set():
            with self._lock:
                seen = self._asked
            try:
                self._look(woken)
            except Exception:  # looking must outlive any one problem
                log.exception("Looking for duplicates hit a problem")
            with self._lock:
                if self._asked == seen:
                    self._idle.set()
            woken = self._wake.wait(_REST)
            self._wake.clear()

    def _look(self, woken: bool) -> None:
        """Looks at every picture not looked at as it is now, then groups them, when anything
        changed: it was woken, found something to look at, or ffmpeg came (a HEIC's empty print
        is tried again then)."""
        with closing(db.connect(self._paths.database)) as conn:
            changed = woken or not self._grouped
            has_ffmpeg = self._ffmpeg() is not None
            if has_ffmpeg and not self._had_ffmpeg:
                with conn:
                    conn.execute("DELETE FROM prints WHERE hash IS NULL")
                changed = True
            self._had_ffmpeg = has_ffmpeg
            todo = conn.execute(
                f"""SELECT p.* FROM pictures AS p LEFT JOIN prints AS f ON f.picture_id = p.id
                    WHERE {_LISTED}
                      AND (f.picture_id IS NULL OR f.size <> p.size OR f.modified <> p.modified)
                    ORDER BY p.modified DESC, p.id"""  # noqa: S608 - a fixed fragment
            ).fetchall()
            with self._lock:
                self._looking = bool(todo)
            try:
                grouped_at = time.monotonic()
                with ThreadPoolExecutor(self._workers, thread_name_prefix="looking") as pool:
                    for start in range(0, len(todo), _CHUNK):
                        if self._stopping.is_set():
                            return
                        chunk = todo[start : start + _CHUNK]
                        _keep_prints(conn, chunk, pool.map(self._print, chunk), self._stamp())
                        if time.monotonic() - grouped_at > _GROUP_EVERY:
                            self.regroup(conn)  # the review fills in as Mado looks
                            grouped_at = time.monotonic()
                digested = _digests(conn, self._stopping.is_set, self._stamp())
                if not (changed or todo or digested):
                    return  # nothing new since the last look: the groups stand
                found = self.regroup(conn)
                self._grouped = True
                if self._sharpen(conn, found):
                    self.regroup(conn)
            finally:
                with self._lock:
                    self._looking = False

    def _print(self, row: sqlite3.Row) -> tuple[int, bytes] | None:
        """A picture's fingerprints from its thumbnail (made now if the cache lost it, while the
        picture is still in the library as it was); None when it's gone since, or left the
        library (the next scan sees to it); no fingerprint when its thumbnail can't be made (it's
        tried again as the engine next starts, or once ffmpeg comes)."""
        source = Source.of(row)
        try:
            thumbnail = self._previews.kept_thumbnail(source)
            if thumbnail is None:
                if not self._still_listed(row):
                    return None
                thumbnail = self._previews.thumbnail(source)
            with Image.open(thumbnail) as opened:
                grey = opened.convert("L")
        except PictureGoneError:
            return None
        except (UnreadableError, NeedsFfmpegError, OSError, ValueError) as error:
            log.info("Mado couldn't look at %s: %s", row["path"], error)
            return (0, b"")
        small = np.asarray(grey.resize((SIDE, SIDE), Image.Resampling.BOX), np.float32)
        finer = np.asarray(grey.resize((FINE_SIDE, FINE_SIDE), Image.Resampling.BOX), np.float32)
        return fingerprint(small), fine(finer)

    def _still_listed(self, row: sqlite3.Row) -> bool:
        """Whether a picture is still in the library, its file as it was when it was to be
        looked at: one whose folder was taken out meanwhile isn't decoded for nothing."""
        with closing(db.connect(self._paths.database)) as conn:
            found = conn.execute(
                "SELECT 1 FROM pictures WHERE id = ? AND gone_at IS NULL AND size = ?"
                " AND modified = ?",
                (row["id"], row["size"], row["modified"]),
            ).fetchone()
        return found is not None

    def _sharpen(self, conn: sqlite3.Connection, found: Found) -> bool:
        """Measures the sharpness of each burst's shots not yet measured. True when it did."""
        wanted = [
            found.pictures[member]
            for group in found.groups
            if group.kind == "burst"
            for member in group.members
            if found.pictures[member].sharpness is None
        ]
        measured = 0
        for picture in wanted:
            if self._stopping.is_set():
                break
            value = self._sharpness_of(picture)
            if value is None:
                continue
            with conn:
                conn.execute(
                    "UPDATE prints SET sharpness = ? WHERE picture_id = ? AND size = ?"
                    " AND modified = ?",
                    (value, picture.id, picture.size, picture.modified),
                )
            measured += 1
        return measured > 0

    def _sharpness_of(self, picture: Known) -> float | None:
        path = Path(picture.path)
        if not drive_there(path):
            return None
        try:
            image = decode(
                path, kind_of(path.name) or "picture", longest=SHARP_SIDE, ffmpeg=self._ffmpeg()
            )
        except (UnreadableError, PictureGoneError, NeedsFfmpegError, OSError) as error:
            log.info("Mado couldn't measure how sharp %s is: %s", path, error)
            return None
        grey = image.convert("L")
        if max(grey.size) < SHARP_SIDE:  # smaller than the fixed size: grown to it
            scale = SHARP_SIDE / max(grey.size)
            size = (max(1, round(grey.width * scale)), max(1, round(grey.height * scale)))
            grey = grey.resize(size, Image.Resampling.BILINEAR)
        return sharpness(np.asarray(grey, np.float32))

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")


def _keep_prints(
    conn: sqlite3.Connection,
    rows: Sequence[sqlite3.Row],
    prints: Iterable[tuple[int, bytes] | None],
    stamp: str,
) -> None:
    """Keeps what looking at each picture found, as its file was then; a picture taken out of
    the library meanwhile is passed over."""
    with conn:
        for row, made in zip(rows, prints, strict=True):
            if made is None:
                continue
            value, finer = made
            conn.execute(
                """INSERT INTO prints (picture_id, size, modified, hash, fine, at)
                   SELECT id, ?, ?, ?, ?, ? FROM pictures WHERE id = ?
                   ON CONFLICT (picture_id) DO UPDATE SET
                       size = excluded.size, modified = excluded.modified,
                       hash = excluded.hash, fine = excluded.fine, sharpness = NULL,
                       digest = NULL, at = excluded.at""",
                (
                    row["size"],
                    row["modified"],
                    value if finer else None,
                    finer or None,
                    stamp,
                    row["id"],
                ),
            )


def _digests(conn: sqlite3.Connection, stop: Callable[[], bool], stamp: str) -> int:
    """The bytes' digest of every picture that shares its size with another, read a little at a
    time; a picture on a drive that isn't connected waits for it. Says how many it took."""
    rows = conn.execute(
        f"""SELECT p.id, p.path, p.size, p.modified FROM pictures AS p
            JOIN prints AS f ON f.picture_id = p.id AND f.size = p.size AND f.modified = p.modified
            WHERE {_LISTED} AND f.digest IS NULL AND p.size IN (
                SELECT size FROM pictures AS p WHERE {_LISTED} GROUP BY size HAVING COUNT(*) > 1
            )"""  # noqa: S608 - fixed fragments
    ).fetchall()
    taken = 0
    for row in rows:
        if stop():
            break
        path = Path(row["path"])
        if not drive_there(path):
            continue
        found = digest(path, row["size"], row["modified"])
        if found is None:
            continue
        with conn:
            conn.execute(
                "UPDATE prints SET digest = ?, at = ? WHERE picture_id = ? AND size = ?"
                " AND modified = ?",
                (found, stamp, row["id"], row["size"], row["modified"]),
            )
        taken += 1
    return taken


def digest(path: Path, size: int, modified: int) -> str | None:
    """A file's bytes' blake2b, read a megabyte at a time; None when it isn't as it was
    (`size`, `modified`) or can't be read."""
    try:
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (size, modified):
            return None
        made = hashlib.blake2b(digest_size=32)
        with path.open("rb") as file:
            while chunk := file.read(_READ):
                made.update(chunk)
    except OSError:
        return None
    return made.hexdigest()


def _grouped(conn: sqlite3.Connection) -> Found:
    """The groups among the pictures looked at as they are now."""
    families = _families(conn)
    pictures: list[Known] = []
    for row in conn.execute(
        f"""SELECT p.id, p.path, p.name, p.width, p.height, p.size, p.format, p.modified,
                   p.taken_at, p.taken_from, p.camera, f.hash, f.fine, f.digest, f.sharpness
            FROM pictures AS p
            JOIN prints AS f ON f.picture_id = p.id AND f.size = p.size AND f.modified = p.modified
            WHERE {_LISTED} AND f.hash IS NOT NULL"""  # noqa: S608 - a fixed fragment
    ):
        path = str(row["path"])
        if _in_a_quarantine(path) or not row["width"] or not row["height"]:
            continue
        pictures.append(
            Known(
                id=row["id"],
                name=row["name"],
                folder=str(PureWindowsPath(path).parent),
                width=row["width"],
                height=row["height"],
                size=row["size"],
                format=row["format"],
                modified=row["modified"],
                taken=_camera_time(row["taken_at"], row["taken_from"]),
                camera=row["camera"],
                hash=row["hash"],
                fine=row["fine"],
                digest=row["digest"],
                sharpness=row["sharpness"],
                family=families.get(path.casefold()),
                path=path,
            )
        )
    found = groups(pictures, not_same=_not_same(conn))
    by_id = {each.id: each for each in pictures}
    members = {member for group in found for member in group.members}
    return Found(tuple(found), {member: by_id[member] for member in members})


def _camera_time(taken: str, source: str) -> datetime | None:
    if source != "camera":
        return None
    try:
        return datetime.fromisoformat(taken)
    except ValueError:
        return None


def _in_a_quarantine(path: str) -> bool:
    folded = QUARANTINE.casefold()
    return any(part.casefold() == folded for part in PureWindowsPath(path).parts)


def _families(conn: sqlite3.Connection) -> dict[str, int]:
    """Each picture History made, and each original it was made from, by its path (folded), with
    a number its whole family shares: an original and everything made from it, and from that."""
    parent: dict[str, str] = {}

    def root(path: str) -> str:
        parent.setdefault(path, path)
        while parent[path] != path:
            parent[path] = parent[parent[path]]
            path = parent[path]
        return path

    for row in conn.execute(
        """SELECT original, result FROM history WHERE kind IN ('made', 'replaced')
           AND original IS NOT NULL AND result IS NOT NULL"""
    ):
        first, second = root(str(row["original"]).casefold()), root(str(row["result"]).casefold())
        if first != second:
            parent[second] = first
    numbers: dict[str, int] = {}
    return {path: numbers.setdefault(root(path), len(numbers)) for path in list(parent)}


def _not_same(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """The pairs the owner said aren't the same, while both files are as they were then."""
    found: list[tuple[int, int]] = []
    for row in conn.execute(
        """SELECT n.first, n.second, n.versions, a.size AS a_size, a.modified AS a_modified,
                  b.size AS b_size, b.modified AS b_modified
           FROM not_same AS n
           JOIN pictures AS a ON a.id = n.first JOIN pictures AS b ON b.id = n.second"""
    ):
        now = f"{row['a_size']}-{row['a_modified']} {row['b_size']}-{row['b_modified']}"
        if row["versions"] == now:
            found.append((row["first"], row["second"]))
    return found


# The owner's choices.


def choices(conn: sqlite3.Connection) -> dict[int, bool]:
    """Whether the owner keeps each picture they chose about, while its file is as it was."""
    return {
        row["picture_id"]: bool(row["keep"])
        for row in conn.execute(
            """SELECT c.picture_id, c.keep FROM choices AS c JOIN pictures AS p
                 ON p.id = c.picture_id AND p.size = c.size AND p.modified = c.modified"""
        )
    }


def kept(group: Group, chosen: Mapping[int, bool]) -> set[int]:
    """The pictures of a group kept: as the owner chose, else the one Mado suggests; never
    none."""
    keep = {member for member in group.members if chosen.get(member, member == group.keep)}
    return keep or {group.keep}


def choose(
    conn: sqlite3.Connection,
    group: Group,
    found: Found,
    keep: Collection[int],
    now: datetime,
    *,
    shown: Collection[int],
) -> None:
    """The owner's choice of which of a group's pictures, as they were `shown`, to keep: a
    picture that joined the group since, unseen, is left to Mado's suggestion. Raises ValueError
    for a choice that keeps none of it, or names a picture that isn't in it."""
    wanted = set(keep)
    if not wanted:
        raise ValueError("Keep at least one of them: the rest are set aside for it.")
    if not wanted <= set(group.members):
        raise ValueError("That picture isn't in this group any more.")
    seen = [member for member in group.members if member in set(shown)]
    stamp = now.isoformat(timespec="seconds")
    with conn:
        conn.executemany(
            """INSERT INTO choices (picture_id, keep, size, modified, at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (picture_id) DO UPDATE SET keep = excluded.keep,
                   size = excluded.size, modified = excluded.modified, at = excluded.at""",
            [
                (
                    member,
                    int(member in wanted),
                    found.pictures[member].size,
                    found.pictures[member].modified,
                    stamp,
                )
                for member in seen
            ],
        )


def not_the_same(conn: sqlite3.Connection, group: Group, found: Found, now: datetime) -> None:
    """Remembers that a group's pictures aren't the same, each pair as its files are now: Mado
    asks again only once one changes."""
    stamp = now.isoformat(timespec="seconds")
    members = sorted(group.members)
    rows: list[tuple[int, int, str, str]] = []
    for at, first in enumerate(members):
        for second in members[at + 1 :]:
            a, b = found.pictures[first], found.pictures[second]
            rows.append((first, second, f"{a.size}-{a.modified} {b.size}-{b.modified}", stamp))
    with conn:
        conn.executemany(
            """INSERT INTO not_same (first, second, versions, at) VALUES (?, ?, ?, ?)
               ON CONFLICT (first, second) DO UPDATE SET versions = excluded.versions,
                   at = excluded.at""",
            rows,
        )
        conn.executemany(
            "DELETE FROM choices WHERE picture_id = ?", [(member,) for member in members]
        )


# Setting aside.


def set_aside(
    conn: sqlite3.Connection,
    quarantine: Quarantine,
    found: Found,
    *,
    keys: Collection[int] | None,
    now: datetime,
) -> SetAside:
    """Sets aside the rest of each group named by its key (None: every group): each picture into
    its own drive's quarantine with a line of History, under one review. A picture is left as it
    is, with a sentence, when it changed since it was compared, isn't there, is on a drive that
    isn't connected, or is open in another app; a whole group is, when its kept picture isn't
    there as it was."""
    chosen = choices(conn)
    wanted = None if keys is None else set(keys)
    stamp = now.isoformat(timespec="seconds")
    left: list[Left] = []
    review: int | None = None
    count = size = 0
    kinds: set[tuple[int, str]] = set()
    with history.MOVES:  # an undo never comes between a line and its picture's move
        for group in found.groups:
            key = min(group.members)
            if wanted is not None and key not in wanted:
                continue
            keep = kept(group, chosen)
            keepers = [found.pictures[member] for member in group.members if member in keep]
            there = [each for each in keepers if where(each) == "there"]
            rest = [found.pictures[member] for member in group.members if member not in keep]
            if not there:
                left.extend(Left(each.name, _kept_isnt(keepers[0], each)) for each in rest)
                continue
            for picture in rest:
                if (state := where(picture)) != "there":
                    left.append(Left(picture.name, _isnt(picture, state)))
                    continue
                if review is None:
                    review = _new_review(conn, stamp)
                if _set_one_aside(conn, quarantine, picture, there[0], review, now, left):
                    count += 1
                    size += picture.size
                    kinds.add((key, group.kind))
        if review is not None:
            with conn:
                conn.execute(
                    "UPDATE reviews SET duplicates = ?, bursts = ? WHERE id = ?",
                    (
                        sum(1 for _key, kind in kinds if kind == "duplicates"),
                        sum(1 for _key, kind in kinds if kind == "burst"),
                        review,
                    ),
                )
                if not count:
                    conn.execute("DELETE FROM reviews WHERE id = ?", (review,))
    return SetAside(review if count else None, count, size, tuple(left))


def _set_one_aside(
    conn: sqlite3.Connection,
    quarantine: Quarantine,
    picture: Known,
    keeper: Known,
    review: int,
    now: datetime,
    left: list[Left],
) -> bool:
    """One picture into its drive's quarantine: History's line first, so a stop between the two
    leaves a line to put it back from; the line forgotten when the move doesn't happen. One that's
    the kept picture's own file under another name (a link, a drive letter for a folder) stays."""
    path = Path(picture.path)
    if _same_file(path, Path(keeper.path)):
        left.append(
            Left(
                picture.name,
                f"{picture.name} is the same file as {keeper.name}, under another name, so Mado "
                "left it as it is.",
            )
        )
        return False
    target = quarantine.place(path, now)
    entry = history.aside(
        conn,
        now=now,
        name=picture.name,
        original=path,
        kept=Path(keeper.path),
        aside=target,
        size=picture.size,
        review_id=review,
    )
    try:
        quarantine.set_aside(path, now, to=target)
    except MoveError as error:
        history.forget(conn, entry)
        if isinstance(error, InUseMoveError):
            left.append(
                Left(
                    picture.name,
                    f"{picture.name} is open in another app, so Mado left it as it is. Close it "
                    "there, then set it aside again.",
                )
            )
        else:
            left.append(Left(picture.name, str(error)))
        return False
    with conn:  # the library forgets it till it's put back
        conn.execute(
            "UPDATE pictures SET gone_at = ? WHERE id = ?",
            (now.isoformat(timespec="seconds"), picture.id),
        )
    return True


def _same_file(path: Path, other: Path) -> bool:
    try:
        return path.samefile(other)
    except OSError:
        return False


def _new_review(conn: sqlite3.Connection, stamp: str) -> int:
    with conn:
        row = conn.execute(
            "INSERT INTO reviews (at, duplicates, bursts) VALUES (?, 0, 0) RETURNING id",
            (stamp,),
        ).fetchone()
    review: int = row["id"]
    return review


type Where = Literal["there", "away", "gone", "changed"]


def where(picture: Known) -> Where:
    """Whether a picture is there as it was when compared: "away" on a drive that isn't
    connected, "gone" since, or "changed" since."""
    path = Path(picture.path)
    if not drive_there(path):
        return "away"
    try:
        stat = path.stat()
    except OSError:
        return "gone"
    if (stat.st_size, stat.st_mtime_ns) != (picture.size, picture.modified):
        return "changed"
    return "there"


def _isnt(picture: Known, state: Where) -> str:
    """Why a picture was left as it is."""
    name = picture.name
    match state:
        case "away":
            drive = drive_of(Path(picture.path))
            return f"{name} is on {drive}, which isn't connected, so Mado left it as it is."
        case "gone":
            return f"{name} isn't there any more: it was moved or deleted since."
        case _:
            return f"{name} changed since Mado compared it, so Mado left it as it is."


def _kept_isnt(keeper: Known, picture: Known) -> str:
    """Why a picture was left as it is when its group's kept picture isn't there as it was."""
    state = where(keeper)
    match state:
        case "away":
            why = f"is on {drive_of(Path(keeper.path))}, which isn't connected"
        case "gone":
            why = "isn't there any more"
        case _:
            why = "changed since Mado compared it"
    return f"{keeper.name}, the one kept, {why}, so Mado left {picture.name} as it is too."
