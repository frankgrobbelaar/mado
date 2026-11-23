"""Looking after Mado while it's open, on a background thread: tonight's backup of its records,
from 03:00 or the first chance after (mado/backups.py), and once a day the clear-out of the
quarantine, deleting what's waited there longer than its 30 days (mado/quarantine.py), and
forgetting the pictures from outside the library not opened for a month (mado/outside.py). The
engine's log keeps its last 30 days by itself (mado/cli.py).
"""

import logging
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import date, datetime, timedelta

from mado import backups, db, outside
from mado.backups import BackupError
from mado.config import DataPaths
from mado.quarantine import Quarantine, clear_out

log = logging.getLogger(__name__)

EVERY = 300.0  # seconds between looks
_REST = timedelta(hours=1)  # after a backup fails, before it's tried again


class Care:
    def __init__(
        self,
        paths: DataPaths,
        quarantine: Quarantine,
        *,
        now: Callable[[], datetime],
        forget: Callable[[list[int]], None] = lambda _ids: None,
    ) -> None:
        """`forget` lets the copies of pictures forgotten go from the cache."""
        self._paths = paths
        self._quarantine = quarantine
        self._now = now
        self._forget = forget
        self._cleared_on: date | None = None  # the day the quarantine was last cleared out
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
        """Does what's due: tonight's backup, unless the last try failed within the hour, and
        today's clear-out of the quarantine and of the pictures from outside the library."""
        now = self._now()
        resting = self._resting_until is not None and now < self._resting_until
        if not resting and backups.due(self._paths, now):
            try:
                backups.back_up(self._paths, now)
            except BackupError as error:
                log.warning("%s", error)
                self._resting_until = now + _REST
        if self._cleared_on != now.date():
            with closing(db.connect(self._paths.database)) as conn:
                clear_out(conn, self._quarantine, now=now)
                outside.forget(conn, now=now, pasted=self._paths.pasted, copies=self._forget)
            self._cleared_on = now.date()

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
