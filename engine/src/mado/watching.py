"""Watch folders: a folder, the recipe it runs and where its new pictures go. Every new picture put
in it is taken once it has finished copying (its size and time the same for a few seconds, and
readable), made to its recipe as a batch in the queue, and saved as a new picture where the
folder says; its original stays as it is. What arrived while Mado was closed is taken as it
opens; what was there before the folder was watched (or turned on again) is left alone.

It can't loop: a watch folder never takes a picture in its own results folder (one inside it is
passed over, however it's named: a short name, or through a junction), nor any picture Mado
wrote, wherever (History knows them all), and it never follows a link to another folder.
docs/stack/queue.md has how batches run; the library's own watcher is mado/watch.py.
"""

import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mado import batches, db, recipes
from mado.ai import Ai
from mado.batches import BatchError, Picture
from mado.config import DataPaths
from mado.core.batch import StepError
from mado.core.files import kind_of, skipped_folder
from mado.core.naming import QUARANTINE
from mado.jobs import Jobs
from mado.pictures import PictureGoneError, UnreadableError, read_facts
from mado.previews import version

log = logging.getLogger(__name__)

QUIET = 5.0  # seconds a picture's size and time stay the same before it's taken
LOOK = 5.0  # seconds between looks round the watch folders
GIVE_UP = 120.0  # seconds a picture that won't open waits before it's left alone
REST = 300.0  # seconds a watch folder whose pictures couldn't go in waits to try again
MOST = 5_000  # files looked at in one watch folder at a look
BIG = 20  # a watch folder's batch bigger than this waits for the night, if Settings says so


class WatchError(ValueError):
    """A watch folder that can't be kept as asked, with a sentence saying why."""


@dataclass(frozen=True)
class Watch:
    id: int
    path: Path
    recipe_id: int
    recipe: str  # its name
    results: Path
    watching: bool
    added_at: str
    since: str  # it takes what arrives after this
    problem: str | None = None  # why its pictures couldn't go in the queue, lately


type Take = Callable[[sqlite3.Connection, Watch, list[Picture]], None]


def listed(conn: sqlite3.Connection) -> list[Watch]:
    """The watch folders, in the order they were added."""
    return [
        _watch(row)
        for row in conn.execute(
            """SELECT w.*, r.name AS recipe FROM watch_folders AS w
               JOIN recipes AS r ON r.id = w.recipe_id ORDER BY w.id"""
        )
    ]


def found(conn: sqlite3.Connection, watch_id: int) -> Watch | None:
    return next((each for each in listed(conn) if each.id == watch_id), None)


def added(
    conn: sqlite3.Connection, path: Path, recipe_id: int, results: Path, now: datetime
) -> Watch:
    """Watches a folder from now: what's in it already is left alone. Raises WatchError."""
    folder, into = _checked(conn, path, recipe_id, results)
    with conn:
        watch_id: int = conn.execute(
            """INSERT INTO watch_folders (path, recipe_id, results, added_at, since)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (str(folder), recipe_id, str(into), _stamp(now), _stamp(now)),
        ).fetchone()[0]
    _there_before(conn, watch_id, folder, into, now)
    watch = found(conn, watch_id)
    assert watch is not None  # noqa: S101 - just added
    return watch


def changed(
    conn: sqlite3.Connection,
    watch_id: int,
    *,
    path: Path,
    recipe_id: int,
    results: Path,
    watching: bool,
    now: datetime,
) -> Watch | None:
    """A watch folder changed: turned on again (or moved to another folder), it takes what
    arrives from now on. None when there's no such watch folder. Raises WatchError."""
    before = found(conn, watch_id)
    if before is None:
        return None
    folder, into = _checked(conn, path, recipe_id, results, but=watch_id)
    fresh = folder != before.path or (watching and not before.watching)
    with conn:
        conn.execute(
            """UPDATE watch_folders SET path = ?, recipe_id = ?, results = ?, watching = ?,
                      since = CASE WHEN ? THEN ? ELSE since END
               WHERE id = ?""",
            (str(folder), recipe_id, str(into), int(watching), fresh, _stamp(now), watch_id),
        )
    if fresh:
        with conn:
            conn.execute("DELETE FROM watched WHERE watch_id = ?", (watch_id,))
        _there_before(conn, watch_id, folder, into, now)
    return found(conn, watch_id)


def deleted(conn: sqlite3.Connection, watch_id: int) -> bool:
    """Stops watching a folder for good: its pictures, and what it made, stay as they are."""
    with conn:
        return conn.execute("DELETE FROM watch_folders WHERE id = ?", (watch_id,)).rowcount > 0


class WatchFolders:
    """Looks round the watch folders every few seconds, and takes their new pictures."""

    def __init__(
        self,
        paths: DataPaths,
        take: Take,
        *,
        now: Callable[[], datetime],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """`take` puts a watch folder's new pictures in the queue (mado/api/__init__.py)."""
        self._paths = paths
        self._take = take
        self._now = now
        self._clock = clock
        self._seen: dict[tuple[int, str], tuple[int, int, float]] = {}  # size, time, since
        self._resting: dict[int, float] = {}  # a watch folder's: when it tries again
        self._stopping = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="watch folders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def poke(self) -> None:
        """Looks round now: a watch folder was added or changed."""
        self._wake.set()

    def look(self) -> int:
        """One look round every watch folder that's on and connected: new pictures that have
        finished copying are taken. Returns how many were."""
        taken = 0
        with closing(db.connect(self._paths.database)) as conn:
            for watch in listed(conn):
                if watch.watching and watch.path.is_dir():
                    taken += self._look_in(conn, watch)
        return taken

    def _look_in(self, conn: sqlite3.Connection, watch: Watch) -> int:
        if self._clock() < self._resting.get(watch.id, 0.0):
            return 0  # its pictures couldn't go in lately: it rests a while
        known = {
            str(row["path"]).casefold(): (row["size"], row["modified"])
            for row in conn.execute(
                "SELECT path, size, modified FROM watched WHERE watch_id = ?", (watch.id,)
            )
        }
        ready: list[Picture] = []
        now = self._clock()
        for path in pictures_in(watch.path, watch.results):
            try:
                stat = path.stat()
            except OSError:
                continue  # gone meanwhile
            mark = (stat.st_size, stat.st_mtime_ns)
            if known.get(str(path).casefold()) == mark:
                continue  # taken, or there before
            if _mado_wrote(conn, path):
                _note(conn, watch.id, path, mark, taken=False, now=self._now())
                continue
            key = (watch.id, str(path).casefold())
            seen = self._seen.get(key)
            if seen is None or (seen[0], seen[1]) != mark:
                self._seen[key] = (*mark, now)  # still copying, or new: looked at again later
                continue
            if now - seen[2] < QUIET:
                continue
            picture = _readable(path, mark)
            if picture is None:
                if now - seen[2] >= GIVE_UP:  # it won't open: left alone, as it is
                    log.warning("A watch folder left %s alone: it won't open", path)
                    _note(conn, watch.id, path, mark, taken=False, now=self._now())
                continue
            ready.append(picture)
        if not ready:
            return 0
        try:
            self._take(conn, watch, ready)
        except Exception as error:  # said on its row, and tried again after a rest
            said = str(error) if isinstance(error, BatchError | StepError) else ""
            said = said or _COULDNT
            if said != watch.problem:  # told once, not at every look
                log.warning("A watch folder couldn't put %d pictures in the queue", len(ready))
                if not isinstance(error, BatchError | StepError):
                    log.exception("What happened")
                _problem(conn, watch.id, said)
            self._resting[watch.id] = self._clock() + REST
            return 0
        self._resting.pop(watch.id, None)
        if watch.problem is not None:
            _problem(conn, watch.id, None)
        for picture in ready:
            _note(conn, watch.id, picture.path, _mark_of(picture), taken=True, now=self._now())
            self._seen.pop((watch.id, str(picture.path).casefold()), None)
        return len(ready)

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                self.look()
            except Exception:  # the watching must outlive any one bad look
                log.exception("Looking round the watch folders hit a problem")
            self._wake.wait(LOOK)
            self._wake.clear()


def pictures_in(folder: Path, results: Path) -> list[Path]:
    """The pictures in a watch folder and the folders in it: its results folder (however it's
    named), a quarantine, Windows' own folders, links to other folders and camera RAW left
    out."""
    skip = _real(results)
    found: list[Path] = []
    looked = 0
    for here, folders, files in os.walk(folder):
        folders[:] = [
            name
            for name in folders
            if name != QUARANTINE
            and not skipped_folder(name)
            and not _linked(Path(here) / name)
            and _real(Path(here) / name) != skip
        ]
        for name in files:
            looked += 1
            if looked > MOST:
                return found
            kind = kind_of(name)
            if kind is not None and kind != "raw":
                found.append(Path(here) / name)
    return found


def queue_up(
    conn: sqlite3.Connection,
    jobs: Jobs,
    ai: Ai,
    watch: Watch,
    pictures: list[Picture],
    now: datetime,
) -> int | None:
    """A watch folder's new pictures, into the queue behind what waits: they join its batch not
    yet done, or make one, saved as new pictures where it says. A big one waits for the night,
    when the owner said so in Settings. Returns the batch's number."""
    kept = recipes.found(conn, watch.recipe_id)
    if kept is None:
        return None
    batch_id = open_batch(conn, watch.id)
    if batch_id is not None:
        batches.join(conn, jobs, ai, batch_id, pictures)
    else:
        batch_id = batches.put_in(
            conn,
            jobs,
            ai,
            name=kept.name,
            source=watch.path.name or str(watch.path),
            shared=str(watch.path),
            pictures=pictures,
            steps=kept.steps,
            saving={**kept.saving, "how": "new", "folder": str(watch.results)},
            starts="after",
            now=now,
            recipe_id=kept.id,
            watch_id=watch.id,
        )
    nights = conn.execute(
        "SELECT value FROM settings WHERE key = 'big_batches_at_night'"
    ).fetchone()
    if nights is not None and nights["value"] == "true" and big(conn, batch_id):
        with conn:
            conn.execute("UPDATE batches SET starts = 'tonight' WHERE id = ?", (batch_id,))
    return batch_id


def open_batch(conn: sqlite3.Connection, watch_id: int) -> int | None:
    """A watch folder's batch that isn't done yet, which its new pictures join."""
    row = conn.execute(
        """SELECT id FROM batches WHERE watch_id = ? AND finished_at IS NULL
           AND EXISTS (SELECT 1 FROM jobs WHERE batch_id = batches.id AND state = 'queued')
           ORDER BY id DESC LIMIT 1""",
        (watch_id,),
    ).fetchone()
    return row["id"] if row else None


def big(conn: sqlite3.Connection, batch_id: int) -> bool:
    """Whether a watch folder's batch holds more pictures waiting than a daytime one should."""
    waiting: int = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE batch_id = ? AND state = 'queued'", (batch_id,)
    ).fetchone()[0]
    return waiting > BIG


def _checked(
    conn: sqlite3.Connection,
    path: Path,
    recipe_id: int,
    results: Path,
    *,
    but: int | None = None,
) -> tuple[Path, Path]:
    folder = Path(os.path.normpath(path.absolute()))
    into = Path(os.path.normpath(results if results.is_absolute() else folder / results))
    if not folder.is_dir():
        raise WatchError(
            f"{folder} isn't there. Check its drive is connected and the folder exists."
        )
    if _real(into) == _real(folder):
        raise WatchError(
            "Its new pictures need a folder of their own: in the folder itself, Mado would make "
            "them again and again. Choose another, such as Done inside it."
        )
    if conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone() is None:
        raise WatchError("That recipe isn't there any more: pick another.")
    real = _real(folder)
    for row in conn.execute("SELECT path FROM watch_folders WHERE id IS NOT ?", (but,)):
        if _real(Path(row["path"])) == real:
            raise WatchError(f"{folder} is a watch folder already: change that one instead.")
    return folder, into


def _there_before(
    conn: sqlite3.Connection, watch_id: int, folder: Path, results: Path, now: datetime
) -> None:
    """What's in a watch folder as it begins: left alone."""
    rows: list[tuple[int, str, int, int, int, str]] = []
    for path in pictures_in(folder, results):
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append((watch_id, str(path), stat.st_size, stat.st_mtime_ns, 0, _stamp(now)))
    with conn:
        conn.executemany(
            """INSERT INTO watched (watch_id, path, size, modified, taken, at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (watch_id, path) DO UPDATE SET size = excluded.size,
                   modified = excluded.modified, taken = excluded.taken, at = excluded.at""",
            rows,
        )


def _note(
    conn: sqlite3.Connection,
    watch_id: int,
    path: Path,
    mark: tuple[int, int],
    *,
    taken: bool,
    now: datetime,
) -> None:
    with conn:
        conn.execute(
            """INSERT INTO watched (watch_id, path, size, modified, taken, at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (watch_id, path) DO UPDATE SET size = excluded.size,
                   modified = excluded.modified, taken = excluded.taken, at = excluded.at""",
            (watch_id, str(path), mark[0], mark[1], int(taken), _stamp(now)),
        )


_COULDNT = (
    "Mado couldn't put its new pictures in the queue: something went wrong inside Mado. It tries "
    "again in a few minutes; Mado's log says what happened."
)


def _problem(conn: sqlite3.Connection, watch_id: int, said: str | None) -> None:
    with conn:
        conn.execute("UPDATE watch_folders SET problem = ? WHERE id = ?", (said, watch_id))


def _mado_wrote(conn: sqlite3.Connection, path: Path) -> bool:
    """Whether Mado wrote a picture: a result History or a job knows, wherever it went, however
    its folder was named as it was saved (a short name, or through a junction)."""
    name = path.name.casefold()
    like = "%" + "".join(f"!{each}" if each in "!%_" else each for each in path.name)
    for sql in (
        "SELECT result FROM history WHERE result LIKE ? ESCAPE '!'",
        "SELECT result FROM jobs WHERE result LIKE ? ESCAPE '!'",
    ):
        for row in conn.execute(sql, (like,)):
            result = Path(row["result"])
            if result.name.casefold() != name:
                continue
            if str(result).casefold() == str(path).casefold() or _same_file(result, path):
                return True
    return False


def _same_file(one: Path, other: Path) -> bool:
    try:
        return one.samefile(other)
    except OSError:
        return False


def _real(path: Path) -> str:
    """A folder's own path, however it's reached (a short name, a junction), to compare."""
    return os.path.normcase(os.path.realpath(path))


def _linked(path: Path) -> bool:
    """A link to another folder (a junction, or a symbolic link): never followed, so nothing's
    looked at twice and a link back up can't go round for ever."""
    return path.is_symlink() or path.is_junction()


def _readable(path: Path, mark: tuple[int, int]) -> Picture | None:
    """A picture done copying, as a batch takes it; None while it won't open yet."""
    kind = kind_of(path.name)
    if kind is None:
        return None
    try:
        with path.open("rb") as file:  # a copy still being written is often locked
            file.read(1)
        facts = read_facts(path, kind)
    except OSError, UnreadableError, PictureGoneError:
        return None
    return Picture(
        None, path, path.name, mark[0], facts.width, facts.height, version(mark[1], mark[0])
    )


def _mark_of(picture: Picture) -> tuple[int, int]:
    modified, size = picture.version.split("-")
    return int(size, 16), int(modified, 16)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _watch(row: sqlite3.Row) -> Watch:
    return Watch(
        id=row["id"],
        path=Path(row["path"]),
        recipe_id=row["recipe_id"],
        recipe=row["recipe"],
        results=Path(row["results"]),
        watching=bool(row["watching"]),
        added_at=row["added_at"],
        since=row["since"],
        problem=row["problem"],
    )
