"""Looking after Mado in the background: tonight's backup."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from mado import backups
from mado.backups import BackupError
from mado.care import Care
from mado.config import DataPaths

NIGHT = datetime(2026, 10, 11, 3, 5).astimezone()


def look_after(paths: DataPaths, at: list[datetime]) -> Care:
    """Mado's care, at the time `at` holds (a test moves it on)."""
    return Care(paths, now=lambda: at[0])


def test_tonights_backup_is_made_once_from_three(paths: DataPaths, conn: sqlite3.Connection):
    at = [NIGHT - timedelta(hours=1)]  # 02:05, and last night's was never made: it is now
    care = look_after(paths, at)

    care.look_after()
    care.look_after()
    at[0] = NIGHT
    care.look_after()
    care.look_after()

    assert [backup.name for backup in backups.backups(paths)] == [
        "mado 2026-10-11 0305.db",
        "mado 2026-10-11 0205.db",
    ]


def test_a_backup_that_fails_is_tried_again_an_hour_later(
    paths: DataPaths, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    tries: list[datetime] = []

    def full(paths: DataPaths, now: datetime) -> backups.Backup:
        tries.append(now)
        raise BackupError("Mado couldn't make a backup: there's no room on the drive")

    monkeypatch.setattr("mado.care.backups.back_up", full)
    at = [NIGHT]
    care = look_after(paths, at)

    care.look_after()
    at[0] += timedelta(minutes=30)
    care.look_after()
    at[0] += timedelta(minutes=31)
    care.look_after()

    assert tries == [NIGHT, NIGHT + timedelta(minutes=61)]


def test_care_looks_after_things_at_once_and_stops_when_asked(
    paths: DataPaths, conn: sqlite3.Connection
):
    care = look_after(paths, [NIGHT])

    care.start()
    care.stop()

    assert [backup.name for backup in backups.backups(paths)] == ["mado 2026-10-11 0305.db"]
