"""The scan: finds every picture in the library's folders, then reads each new or changed one
(its facts, and its thumbnail made on the way, mado/previews.py).

One scan runs at a time, on a background thread with its own database connection. Everything it
learns is saved as it goes, so a scan stopped by Mado closing, or a crash, loses nothing: the
next one (the watcher starts one as Mado opens, mado/watch.py) reads only what's still to read.
A scan asked for while one runs follows it. Nothing in the folders changes: a scan only looks.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Literal

from mado import db
from mado.config import DataPaths
from mado.core.files import Kind
from mado.core.library import time_left
from mado.library import Unread, find_pictures, folders, save_facts, save_problem, unread
from mado.pictures import Facts, NeedsFfmpegError, PictureGoneError, UnreadableError, read_facts
from mado.previews import Previews, Source

log = logging.getLogger(__name__)

type State = Literal["idle", "running", "done", "failed", "stopped"]
type Stage = Literal["finding", "reading", "done"]


class ScanBusyError(Exception):
    """A scan is running, so another can't start."""

    def __init__(self) -> None:
        super().__init__("A scan is running.")


@dataclass(frozen=True)
class ScanStatus:
    state: State  # "stopped": Mado closed, or crashed, before it finished
    stage: Stage | None
    started_at: str | None
    finished_at: str | None
    found: int  # pictures this scan found
    to_read: int  # of those, the new and changed ones to read
    read: int
    current: str | None  # the picture being looked at now
    seconds_left: float | None
    unavailable: tuple[str, ...]  # library folders that aren't there (a drive unplugged)
    problem: str | None  # why it stopped, when it failed
    added: int | None = None  # pictures it found that weren't there before
    gone: int | None = None  # pictures it found gone


def _now() -> datetime:
    return datetime.now().astimezone()


class Scanner:
    """Runs scans and says how the latest one is going. One per engine."""

    def __init__(
        self,
        paths: DataPaths,
        previews: Previews,
        *,
        now: Callable[[], datetime] = _now,
        read: Callable[[Path, Kind], Facts] = read_facts,
    ) -> None:
        self._paths = paths
        self._previews = previews
        self._now = now
        self._read = read
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        # A scan is under way: set as one begins, cleared under the lock as it last looks for one
        # asked to follow it. Its thread may live a moment longer; a scan asked for then begins.
        self._busy = False
        self._again = False  # another scan was asked for while this one ran
        self._current: str | None = None
        self._reading_since: float | None = None
        self._read_live = 0
        self._to_read_live = 0

    def status(self) -> ScanStatus:
        with closing(db.connect(self._paths.database)) as conn:
            return self._status(conn)

    def start(self) -> ScanStatus:
        """Starts a scan of every library folder now. ScanBusyError while one runs."""
        with self._lock:
            if self._running():
                raise ScanBusyError
            self._begin()
        return self.status()

    def request(self) -> None:
        """Scans now or, while a scan runs, once it's done: what it may have missed is seen."""
        with self._lock:
            if self._running():
                self._again = True
            else:
                self._begin()

    def wait(self, timeout: float | None = None) -> None:
        """Waits for the scan running now (and one asked to follow it) to end."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while (thread := self._thread) is not None and thread.is_alive():
            thread.join(None if deadline is None else max(0.0, deadline - time.monotonic()))
            if thread.is_alive() or (deadline is not None and time.monotonic() >= deadline):
                return

    def stop(self) -> None:
        """Stops the running scan after the picture it's on (the engine is stopping)."""
        self._stopping.set()
        with self._lock:
            self._again = False
        if (thread := self._thread) is not None:
            thread.join(timeout=2)  # the app ends the engine 3 seconds after asking

    def _running(self) -> bool:
        return self._busy

    def _begin(self) -> None:
        started = self._now().isoformat()
        with closing(db.connect(self._paths.database)) as conn, conn:
            scan_id: int = conn.execute(
                "INSERT INTO scans (started_at, state, stage) VALUES (?, 'running', 'finding') "
                "RETURNING id",
                (started,),
            ).fetchone()[0]
        self._thread = threading.Thread(
            target=self._run, args=(scan_id, started), name="scan", daemon=True
        )
        self._busy = True
        self._thread.start()

    def _run(self, scan_id: int, started: str) -> None:
        with closing(db.connect(self._paths.database)) as conn:
            try:
                if not self._find(conn, started):
                    return
                _set(conn, scan_id, stage="reading")
                if not self._read_all(conn, started):
                    return
                added, gone = _changes(conn, started)
                _set(
                    conn,
                    scan_id,
                    state="done",
                    stage="done",
                    finished_at=self._now().isoformat(),
                    added=added,
                    gone=gone,
                )
            except Exception as error:
                log.exception("The scan stopped")
                _set(conn, scan_id, state="failed", problem=_stopped_by(error))
            finally:
                self._current = None
                self._reading_since = None
                with self._lock:
                    self._busy = False
                    if self._again and not self._stopping.is_set():
                        self._again = False
                        self._begin()

    def _find(self, conn: sqlite3.Connection, started: str) -> bool:
        """Walks every library folder, including any added while it walks. False when the
        engine is stopping."""
        walked: set[int] = set()
        while waiting := [folder for folder in folders(conn) if folder.id not in walked]:
            for folder in waiting:
                walked.add(folder.id)
                found = find_pictures(
                    conn,
                    folder,
                    stamp=started,
                    on_file=self._looking_at,
                    stop=self._stopping.is_set,
                )
                if self._stopping.is_set():
                    return False
                if found is not None:
                    for problem in found.problems:
                        log.warning("%s", problem)
                    self._previews.forget(found.changed)
        return True

    def _read_all(self, conn: sqlite3.Connection, started: str) -> bool:
        """Reads every picture still to read, except in folders that aren't there. False when
        the engine is stopping."""
        missing = [
            PureWindowsPath(folder.path) for folder in folders(conn) if not folder.path.is_dir()
        ]
        todo = [
            each
            for each in unread(conn)
            if not any(PureWindowsPath(each.path).is_relative_to(away) for away in missing)
        ]
        self._to_read_live, self._read_live = len(todo), 0
        self._reading_since = time.monotonic()
        for each in todo:
            if self._stopping.is_set():
                return False
            self._looking_at(each.path)
            if each.path.is_file():
                self._read_one(conn, each)
            elif each.path.parent.is_dir():  # its folder is there and it isn't: it's gone
                with conn:  # gone in this scan, which counts it so
                    conn.execute("UPDATE pictures SET gone_at = ? WHERE id = ?", (started, each.id))
            # else its folder went too (a drive dropping out, say): the next scan looks again
            self._read_live += 1
        return True

    def _read_one(self, conn: sqlite3.Connection, each: Unread) -> None:
        """Reads one picture's facts and makes its thumbnail, which shows it decodes: a picture
        that won't open is kept with why. A thumbnail Mado can't keep (its data folder's drive
        full) is no fault of the picture's: it's made when it's next asked for."""
        try:
            save_facts(conn, each.id, self._read(each.path, each.kind), now=self._now())
            row = conn.execute("SELECT * FROM pictures WHERE id = ?", (each.id,)).fetchone()
            if row is not None:
                self._previews.thumbnail(Source.of(row))
        except NeedsFfmpegError:
            pass  # a HEIC's thumbnail is made once ffmpeg is there
        except PictureGoneError:
            pass  # it went as it was read: the next scan sees it gone
        except UnreadableError as error:
            save_problem(conn, each.id, str(error), now=self._now())
        except sqlite3.Error:
            raise
        except OSError as error:  # keeping the thumbnail, not the picture
            log.warning("Mado couldn't keep the thumbnail of %s: %s", each.path, error)
        except Exception as error:  # whatever it was, one picture never stops the scan
            log.exception("Reading %s hit a problem", each.path)
            save_problem(conn, each.id, f"Mado couldn't read it: {error}.", now=self._now())

    def _looking_at(self, what: Path) -> None:
        self._current = str(what)

    def _status(self, conn: sqlite3.Connection) -> ScanStatus:
        latest = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        unavailable = tuple(str(f.path) for f in folders(conn) if not f.path.is_dir())
        if latest is None:
            return ScanStatus("idle", None, None, None, 0, 0, 0, None, None, unavailable, None)
        started: str = latest["started_at"]
        found, read, waiting, added, gone = conn.execute(
            f"""SELECT
                  COUNT(*) FILTER (WHERE seen_at = :started AND gone_at IS NULL),
                  COUNT(*) FILTER (WHERE read_at >= :started AND seen_at = :started AND raw = 0),
                  COUNT(*) FILTER (WHERE read_at IS NULL AND gone_at IS NULL),
                  {_CHANGES}
                FROM pictures""",  # noqa: S608 - a fixed fragment, no values
            {"started": started},
        ).fetchone()
        if latest["added"] is not None:  # kept when it finished
            added, gone = latest["added"], latest["gone"]
        running = latest["state"] == "running" and self._running()
        state: State = latest["state"]
        if state == "running" and not running:
            state = "stopped"  # Mado closed, or crashed, before it finished
        left = None
        to_read = read + waiting
        if running and self._reading_since is not None and latest["stage"] == "reading":
            elapsed = time.monotonic() - self._reading_since
            left = time_left(self._read_live, self._to_read_live, elapsed)
            # What this scan reads, leaving out pictures in folders that aren't there.
            read, to_read = self._read_live, self._to_read_live
        return ScanStatus(
            state=state,
            stage=latest["stage"],
            started_at=started,
            finished_at=latest["finished_at"],
            found=found,
            to_read=to_read,
            read=read,
            current=self._current if running else None,
            seconds_left=left,
            unavailable=unavailable,
            problem=latest["problem"],
            added=added,
            gone=gone,
        )


# What the scan that started at :started changed: the pictures it found that weren't there
# before and still are, and those it found gone.
_CHANGES = """COUNT(*) FILTER (WHERE found_at = :started AND gone_at IS NULL),
              COUNT(*) FILTER (WHERE gone_at = :started)"""


def _changes(conn: sqlite3.Connection, started: str) -> tuple[int, int]:
    added, gone = conn.execute(
        f"SELECT {_CHANGES} FROM pictures",  # noqa: S608 - a fixed fragment, no values
        {"started": started},
    ).fetchone()
    return added, gone


def _stopped_by(error: Exception) -> str:
    return (
        f"The scan stopped: {error}. Nothing in your folders was touched; Mado looks again "
        "the next time something changes, and as it starts."
    )


def _set(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    state: str | None = None,
    stage: str | None = None,
    finished_at: str | None = None,
    problem: str | None = None,
    added: int | None = None,
    gone: int | None = None,
) -> None:
    with conn:
        conn.execute(
            """UPDATE scans SET state = COALESCE(?, state), stage = COALESCE(?, stage),
                                finished_at = COALESCE(?, finished_at), problem = ?,
                                added = COALESCE(?, added), gone = COALESCE(?, gone)
               WHERE id = ?""",
            (state, stage, finished_at, problem, added, gone, scan_id),
        )
