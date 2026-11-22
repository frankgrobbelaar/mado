"""Keeping the library current while Mado is open.

- As Mado starts, a scan catches up on what changed while it was closed (once setup is done).
- The library's folders are watched: when a picture is added, changed, removed or renamed, a
  scan starts once the folder has been quiet for a few seconds (a card's pictures still copying
  wait until they're done), looked for every second while a change waits.
- A folder that goes (its drive unplugged) is watched again once it's back, with a scan for
  what changed meanwhile.
"""

import logging
import threading
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Protocol

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.api import DEFAULT_OBSERVER_TIMEOUT, BaseObserver
from watchdog.observers.read_directory_changes import WindowsApiEmitter

from mado import db
from mado.config import DataPaths
from mado.core.files import kind_of

log = logging.getLogger(__name__)

QUIET = 5.0  # seconds without a change before a scan starts
TICK = 15.0  # how often the watcher looks around
SOON = 1.0  # how often, while a change waits for its scan


class Scans(Protocol):
    """What the watcher needs of the scanner (mado/scan.py)."""

    def request(self) -> None: ...


class Watcher:
    def __init__(
        self, paths: DataPaths, scanner: Scans, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._paths = paths
        self._scanner = scanner
        self._clock = clock
        self._lock = threading.Lock()
        self._changed_at: float | None = None  # when a picture last changed, not yet scanned
        self._watched: dict[str, BaseObserver] = {}
        self._stopping = threading.Event()
        self._wake = threading.Event()  # a change noticed, or stopping
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Watches the folders, then catches up on what changed while Mado was closed, so
        nothing that arrives as it starts falls in between; then looks round until `stop`."""
        try:
            self._follow_folders()
        except Exception:  # the next look round tries again
            log.exception("Mado couldn't start watching the library")
        self.catch_up()
        self._thread = threading.Thread(target=self._loop, name="watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        for observer in self._watched.values():
            observer.stop()
        self._watched.clear()

    def catch_up(self) -> bool:
        """Asks for a scan of what changed while Mado was closed. False when it didn't: setup
        isn't done, or there are no folders."""
        with closing(db.connect(self._paths.database)) as conn:
            set_up = conn.execute("SELECT value FROM settings WHERE key = 'set_up'").fetchone()
            has_folders = conn.execute("SELECT 1 FROM folders LIMIT 1").fetchone() is not None
        if set_up is None or set_up["value"] != "true" or not has_folders:
            return False
        self._scanner.request()
        return True

    def follow(self) -> None:
        """A folder was added to the library, or taken out: watch it, or stop, now rather than at
        the next look round, so a picture saved into a new folder straight away is noticed."""
        self._wake.set()

    def notice(self) -> None:
        """A picture changed in a library folder."""
        with self._lock:
            self._changed_at = self._clock()
        self._wake.set()

    @property
    def pending(self) -> bool:
        """A change was noticed and hasn't been scanned yet."""
        with self._lock:
            return self._changed_at is not None

    @property
    def settling(self) -> bool:
        """A change was noticed and its folder hasn't been quiet long enough to scan yet."""
        with self._lock:
            changed = self._changed_at
        return changed is not None and self._clock() - changed < QUIET

    def tick(self) -> None:
        """One look around: follow the folders, and scan after changes once they're quiet."""
        self._follow_folders()
        with self._lock:
            changed = self._changed_at
            if changed is None or self._clock() - changed < QUIET:
                return
            self._changed_at = None
        self._scanner.request()

    def _loop(self) -> None:
        while not self._stopping.is_set():
            # A change wakes the watcher; it then looks every second till the folder is quiet.
            if self.settling:
                if self._stopping.wait(SOON):
                    return
            else:
                self._wake.wait(TICK)
            self._wake.clear()
            if self._stopping.is_set():
                return
            try:
                self.tick()
            except Exception:  # the watcher must outlive any one bad look around
                log.exception("Watching the library hit a problem")

    def _follow_folders(self) -> None:
        """Watches every library folder that's there, stops watching forgotten ones, and watches
        a folder again when it comes back (a drive plugged in again): Windows stops telling
        about a folder once it goes."""
        with closing(db.connect(self._paths.database)) as conn:
            wanted = {row["path"] for row in conn.execute("SELECT path FROM folders")}
        for path, observer in list(self._watched.items()):
            if path not in wanted:
                self._watched.pop(path).stop()
            elif not Path(path).is_dir() or not all(e.is_alive() for e in observer.emitters):
                self._watched.pop(path).stop()
                self.notice()  # its pictures went with it
        for path in wanted - set(self._watched):
            if not Path(path).is_dir():
                continue  # its drive is unplugged: watched once it's back
            try:
                observer = observe(path, Changes(self.notice, self._holds))
            except OSError as error:
                log.warning("Mado can't watch %s: %s", path, error)
                continue
            self._watched[path] = observer

    def _holds(self, path: str) -> bool:
        """Whether the library has a picture at this path, or in a folder there."""
        folder = path.rstrip("\\/") + "\\"
        with closing(db.connect(self._paths.database)) as conn:
            row = conn.execute(
                """SELECT 1 FROM pictures
                   WHERE gone_at IS NULL
                     AND (lower(path) = lower(?) OR lower(substr(path, 1, ?)) = lower(?))
                   LIMIT 1""",
                (path, len(folder), folder),
            ).fetchone()
        return row is not None


def observe(path: str, changes: FileSystemEventHandler) -> BaseObserver:
    """Starts watching a folder and everything in it."""
    observer = BaseObserver(WindowsApiEmitter, timeout=DEFAULT_OBSERVER_TIMEOUT)
    observer.schedule(changes, path, recursive=True)
    observer.start()
    return observer


class Changes(FileSystemEventHandler):
    """Tells the watcher when a picture, or a folder that holds or may hold pictures, comes or
    goes. Something written inside a folder isn't a change: files tell for themselves. Windows
    tells of a folder moved out or deleted as a file gone, so a gone path counts when the
    library has pictures there (`holds`)."""

    def __init__(self, notice: Callable[[], None], holds: Callable[[str], bool]) -> None:
        self._notice = notice
        self._holds = holds

    def on_any_event(self, event: FileSystemEvent) -> None:
        source = str(event.src_path)
        target = str(event.dest_path) if event.dest_path else ""
        match event.event_type:
            case "created":
                changed = event.is_directory or _picture(source)
            case "modified" | "closed":
                changed = not event.is_directory and _picture(source)
            case "deleted":
                changed = _picture(source) or self._holds(source)
            case "moved":
                changed = (
                    event.is_directory
                    or _picture(source)
                    or _picture(target)
                    or self._holds(source)
                )
            case _:
                changed = False  # opened, or closed without writing
        if changed:
            self._notice()


def _picture(path: str) -> bool:
    return kind_of(Path(path).name) is not None
