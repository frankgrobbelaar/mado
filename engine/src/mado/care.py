"""Looking after Mado while it's open, on a background thread: tonight's backup of its records,
from 03:00 or the first chance after (mado/backups.py). The engine's log keeps its last 30 days
by itself (mado/cli.py).
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from mado import backups
from mado.backups import BackupError
from mado.config import DataPaths

log = logging.getLogger(__name__)

EVERY = 300.0  # seconds between looks
_REST = timedelta(hours=1)  # after a backup fails, before it's tried again


class Care:
    def __init__(self, paths: DataPaths, *, now: Callable[[], datetime]) -> None:
        self._paths = paths
        self._now = now
        self._resting_until: datetime | None = None  # after a backup failed
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Looks after what's due now, then every few minutes until `stop`."""
        self._thread = threading.Thread(target=self._loop, name="care", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def look_after(self) -> None:
        """Does what's due: tonight's backup, unless the last try failed within the hour."""
        now = self._now()
        if self._resting_until is not None and now < self._resting_until:
            return
        if backups.due(self._paths, now):
            try:
                backups.back_up(self._paths, now)
            except BackupError as error:
                log.warning("%s", error)
                self._resting_until = now + _REST

    def _loop(self) -> None:
        while True:
            try:
                self.look_after()
            except Exception:  # care must outlive any one problem
                log.exception("Looking after Mado hit a problem")
            self._wake.wait(EVERY)
            self._wake.clear()
            if self._stopping.is_set():
                return
