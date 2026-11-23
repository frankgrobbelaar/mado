"""Checking what this PC can do: what Windows says it has, whether the models run on its card (in
a process of its own), timing them, and keeping all of it as this PC's own."""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pytest

from mado import hardware
from mado.ai import ASSETS
from mado.config import DataPaths
from mado.core.hardware import GIB, Card, Checked
from mado.core.models import FAST
from mado.directml import Sessions
from mado.hardware import Facts
from mado.pc_check import PcCheck, Probe, said, timed

NOW = datetime(2026, 11, 22, 9, 30).astimezone()
SUPER = Card("NVIDIA GeForce GTX 1660 SUPER", "nvidia", 6 * GIB, False, "617.42")
HERE = Facts((SUPER,), "Intel Core i5-9600K", 6, 24 * GIB)


class Recorder:
    """A stand-in for the check's own process, saying what it was asked."""

    def __init__(self, probe: Probe) -> None:
        self.probe = probe
        self.asked: list[tuple[bool, int, Path | None]] = []

    def __call__(self, timing: bool, heavy_tile: int, best: Path | None) -> Probe:
        self.asked.append((timing, heavy_tile, best))
        return self.probe


def _check(paths: DataPaths, recorder: Recorder, facts: Facts = HERE) -> PcCheck:
    return PcCheck(paths, recorder, now=lambda: NOW, looking=lambda: facts)


def test_the_first_check_tests_and_times_this_pc_and_keeps_it(
    paths: DataPaths, conn: sqlite3.Connection
):
    recorder = Recorder(Probe(True, None, {"realesr-general-x4v3@card": 0.6}))
    check = _check(paths, recorder)

    check.refresh()
    check.wait(10)

    assert recorder.asked == [(True, 256, None)]  # timed; a 6 GB card gives Best 256 tiles
    facts, checked = hardware.stored(conn)
    assert facts == HERE
    assert checked == Checked(True, NOW.isoformat(timespec="seconds"), None)
    assert hardware.speeds(conn) == {"realesr-general-x4v3@card": 0.6}
    here = hardware.here(conn)
    assert here.place == "card"
    assert here.card == SUPER
    assert check.checking() is None


def test_a_pc_checked_before_with_the_same_card_isnt_checked_again(
    paths: DataPaths, conn: sqlite3.Connection
):
    hardware.keep(conn, HERE, Checked(True, "2026-11-21T09:00:00+02:00"))
    hardware.keep_speeds(conn, {"realesr-general-x4v3@card": 0.6}, NOW)
    recorder = Recorder(Probe(True, None, {}))
    check = _check(paths, recorder)

    check.refresh()
    check.wait(10)

    assert recorder.asked == []


def test_a_new_card_forgets_the_old_ones_times_and_is_timed_anew(
    paths: DataPaths, conn: sqlite3.Connection
):
    old = Facts((Card("Old card", "amd", 4 * GIB, False, None),), None, None, None)
    hardware.keep(conn, old, Checked(True, "2026-11-21T09:00:00+02:00"))
    hardware.keep_speeds(conn, {"realesrgan-x4plus@card": 20.0}, NOW)
    recorder = Recorder(Probe(True, None, {"realesr-general-x4v3@card": 0.6}))
    check = _check(paths, recorder)

    check.refresh()
    check.wait(10)

    assert recorder.asked[0][0]  # timed
    assert hardware.speeds(conn) == {"realesr-general-x4v3@card": 0.6}


def test_a_card_that_cant_run_the_models_sends_them_to_the_processor_and_says_why(
    paths: DataPaths, conn: sqlite3.Connection
):
    recorder = Recorder(Probe(False, "The graphics card couldn't run the AI model.", {}))
    check = _check(paths, recorder)

    check.test()
    check.wait(10)

    _, checked = hardware.stored(conn)
    assert checked is not None
    assert not checked.ai
    assert checked.problem == "The graphics card couldn't run the AI model."
    assert hardware.here(conn).place == "processor"
    assert hardware.here(conn).starts_on() == {"photo": "fast", "drawing": "fast"}


def test_a_test_while_a_picture_is_being_made_only_checks(paths: DataPaths):
    recorder = Recorder(Probe(True, None, {}))
    check = PcCheck(paths, recorder, now=lambda: NOW, busy=lambda: True, looking=lambda: HERE)

    check.test()
    check.wait(10)

    assert recorder.asked == [(False, 256, None)]


def test_the_checks_process_is_read_by_its_last_json_line():
    output = 'ONNX Runtime says hello\n{"runs": true, "problem": null, "speeds": {"a@card": 0.5}}\n'

    assert said(output, 0) == Probe(True, None, {"a@card": 0.5})
    assert said("", 3).runs is False
    assert "code 3" in (said("", 3).problem or "")


def test_a_picture_made_teaches_mado_this_pcs_speed(conn: sqlite3.Connection):
    hardware.learn(conn, {f"{FAST.id}@processor": 10.0}, NOW)
    hardware.learn(conn, {f"{FAST.id}@processor": 20.0}, NOW)

    assert hardware.speeds(conn)[f"{FAST.id}@processor"] == pytest.approx(13.0)
    measured = hardware.measured(conn)
    assert measured is not None
    assert measured.pictures == 2


def test_a_picture_made_by_two_models_is_counted_once(conn: sqlite3.Connection):
    hardware.learn(conn, {f"{FAST.id}@card": 0.5, "scunet@processor": 30.0}, NOW)

    assert hardware.speeds(conn)["scunet@processor"] == pytest.approx(30.0)
    measured = hardware.measured(conn)
    assert measured is not None
    assert measured.pictures == 1


def test_a_model_is_timed_in_seconds_for_a_megapixel_of_tiles():
    found = timed(Sessions(), ASSETS / FAST.file, 32, "processor")

    assert found is not None
    assert found > 0


def test_a_test_asked_for_while_mado_first_looks_at_this_pc_runs_once(
    paths: DataPaths, conn: sqlite3.Connection
):
    hardware.keep(conn, HERE, Checked(True, "2026-11-21T09:00:00+02:00"))
    hardware.keep_speeds(conn, {"realesr-general-x4v3@card": 0.6}, NOW)
    recorder = Recorder(Probe(True, None, {"realesr-general-x4v3@card": 0.5}))
    looking, go_on = threading.Event(), threading.Event()

    def slowly() -> Facts:
        looking.set()
        go_on.wait(10)
        return HERE

    check = PcCheck(paths, recorder, now=lambda: NOW, looking=slowly)
    check.refresh()  # the PC was checked before: only a look
    looking.wait(10)
    check.test()  # "Test again", pressed meanwhile
    go_on.set()
    check.wait(10)
    check.wait(10)

    assert [timing for timing, _tile, _best in recorder.asked] == [True]
    check.test()
    check.wait(10)
    assert len(recorder.asked) == 2  # once more, not twice
