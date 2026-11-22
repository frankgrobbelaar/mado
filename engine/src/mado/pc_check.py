"""Checking what this PC can do for Mado, and timing it (mado/hardware.py keeps what's found,
mado/core/hardware.py decides from it).

The AI model runs one tile on the graphics card (ONNX Runtime with DirectML) in a process of its
own, `mado check-model`, so a graphics driver that fails on it takes only that process with it,
never the engine. Testing the PC (as Mado first starts, and "Test again" under About in
Settings) times each model on a few tiles there as well: the general model at 512, and the
drawing model and the Best photo model (once downloaded) at the tile size this card gives them;
on a PC whose card can't run them, the general model on the processor. A model that couldn't be
timed keeps the time it had: no guess is kept as measured. While a picture is being made, a test
only checks, as its times would be off.

As the engine starts it checks again when this PC hasn't been checked, its last check found the
card didn't run the models (it may have been the moment: a driver mid-update), or its cards or
their drivers have changed; new cards' times are measured anew.
"""

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import numpy as np

from mado import db, hardware
from mado.ai import ASSETS
from mado.config import DataPaths
from mado.core.estimate import key
from mado.core.hardware import Card, Checked, Place, best_card, tile_for
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST, FAST_GRAIN
from mado.directml import Sessions, tensor
from mado.hardware import UNKNOWN, Facts

log = logging.getLogger(__name__)

_CHECK_SECONDS = 180  # the check's own process, loading and timing included
_BUDGET = 6.0  # seconds a model is timed for, at most
_MOST = 8  # tiles a model is timed on, at most
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class Probe:
    """What the check's own process found: whether the models run on the card, what the card
    said when they didn't, and each model's seconds for a megapixel of tiles ("model@place")."""

    runs: bool
    problem: str | None
    speeds: dict[str, float]


@dataclass(frozen=True)
class Checking:
    """A check of this PC under way, and whether it times the models too."""

    timing: bool


type Check = Callable[[bool, int, Path | None], Probe]  # timing, the heavy tile, Best's file


def probe(*, timing: bool, heavy_tile: int, best: Path | None) -> Probe:
    """Whether the AI models run on this PC's graphics card (one tile) and, with `timing`, how
    fast each goes there, or on the processor where the card can't. `mado check-model` runs this
    in a process of its own."""
    sessions = Sessions()
    fast = ASSETS / FAST.file
    try:
        sessions.get(fast, 512, "card").run({"input": tensor(np.zeros((1, 3, 512, 512)))})
        runs, problem = True, None
    except Exception as error:  # ModelError, or ONNX Runtime's own, all plain Exceptions
        log.info("The AI models don't run on this PC's card: %s", error)
        runs, problem = False, str(error)
    speeds: dict[str, float] = {}
    if not timing:
        return Probe(runs, problem, speeds)
    place: Place = "card" if runs else "processor"
    timings = (
        [(FAST.id, fast, 512), (BEST_DRAWING.id, ASSETS / BEST_DRAWING.file, heavy_tile)]
        if runs
        else [(FAST.id, fast, 256)]
    )
    if runs and best is not None:
        timings.append((BEST_PHOTO.id, best, heavy_tile))
    for model, path, tile in timings:
        found = timed(sessions, path, tile, place)
        if found is not None:
            speeds[key(model, place)] = found
    if key(FAST.id, place) in speeds:  # its twin: the same network, other weights
        speeds[key(FAST_GRAIN.id, place)] = speeds[key(FAST.id, place)]
    return Probe(runs, problem, speeds)


def check_in_own_process(command: Sequence[str]) -> Check:
    """The check run as `mado check-model` in a process of its own, `command` being the engine."""

    def check(timing: bool, heavy_tile: int, best: Path | None) -> Probe:
        asked = [*command, "check-model", "--heavy-tile", str(heavy_tile)]
        asked += ["--time"] if timing else []
        asked += ["--best", str(best)] if best is not None else []
        try:
            done = subprocess.run(  # noqa: S603 - Mado's own engine, never a shell
                asked,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=_CHECK_SECONDS,
                creationflags=_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return Probe(False, "The check took too long: the graphics card didn't answer.", {})
        except OSError as error:
            return Probe(False, f"The check couldn't start: {error.strerror or error}.", {})
        return said(done.stdout.decode("utf-8", "replace"), done.returncode)

    return check


def said(output: str, code: int) -> Probe:
    """What the check's process said: its last JSON line (ONNX Runtime may talk before it)."""
    for line in reversed(output.splitlines()):
        try:
            found: object = json.loads(line)
        except ValueError:
            continue
        if isinstance(found, dict):
            answer = cast("dict[str, object]", found)
            speeds = answer.get("speeds")
            kept = cast("dict[str, object]", speeds) if isinstance(speeds, dict) else {}
            problem = answer.get("problem")
            return Probe(
                answer.get("runs") is True,
                problem if isinstance(problem, str) else None,
                {k: float(v) for k, v in kept.items() if isinstance(v, int | float) and v > 0},
            )
    return Probe(False, f"The graphics card's check stopped (code {code}) without a word.", {})


class PcCheck:
    """The engine's look at this PC: checked as the engine starts when it needs to be, and tested
    on asking, one at a time, in the background."""

    def __init__(
        self,
        paths: DataPaths,
        check: Check,
        *,
        now: Callable[[], datetime],
        busy: Callable[[], bool] = lambda: False,
        best: Callable[[], Path | None] = lambda: None,
        looking: Callable[[], Facts | None] = hardware.look,
    ) -> None:
        """`check` runs the check (in a process of its own); `busy` says whether a picture is
        being made (a test then only checks); `best` is the Best photo model's file once it's
        downloaded; `looking` asks Windows what the PC has (None when it doesn't answer)."""
        self._paths = paths
        self._check = check
        self._now = now
        self._busy = busy
        self._best = best
        self._look = looking
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._checking: Checking | None = None
        self._facts: Facts | None = None
        self._again = False

    def facts(self) -> Facts:
        """What this PC has: as last looked at, or as kept from the last check."""
        with self._lock:
            if self._facts is not None:
                return self._facts
        with closing(db.connect(self._paths.database)) as conn:
            kept, _ = hardware.stored(conn)
        return kept or UNKNOWN

    def checking(self) -> Checking | None:
        with self._lock:
            return self._checking

    def refresh(self) -> None:
        """In the background: looks at this PC, and checks it when it hasn't been, its last
        check found the card didn't run the models, or its cards have changed (timing it too
        when they did, or when it was never timed)."""
        with self._lock:
            if self._checking is None:
                self._launch(Checking(timing=False), self._refresh)

    def test(self) -> None:
        """Checks and times this PC in the background; asked while a check is under way, right
        after it."""
        with self._lock:
            if self._checking is not None:
                self._again = True
            else:
                self._launch(Checking(timing=True), lambda: self._run(None, timing=True))

    def wait(self, timeout: float | None = None) -> None:
        """Till the check under way is over (tests)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _launch(self, checking: Checking, work: Callable[[], None]) -> None:
        """Starts `work` on its own thread. Call with the lock held."""
        self._checking = checking
        self._thread = threading.Thread(target=work, name="pc-check", daemon=True)
        self._thread.start()

    def _looked(self) -> Facts:
        found = self._look()
        with self._lock:
            if found is not None:
                self._facts = found
            known = self._facts
        if known is not None:
            return known
        with closing(db.connect(self._paths.database)) as conn:
            kept, _ = hardware.stored(conn)
        return kept or UNKNOWN

    def _refresh(self) -> None:
        try:
            facts = self._looked()
            with closing(db.connect(self._paths.database)) as conn:
                kept, checked = hardware.stored(conn)
                moved = kept is not None and _sizes(kept.cards) != _sizes(facts.cards)
                if moved:
                    hardware.forget_speeds(conn)
                untimed = hardware.measured(conn) is None
            fresh = checked is not None and kept is not None and kept.cards == facts.cards
            if not fresh or not checked or not checked.ai:
                self._run(facts, timing=moved or untimed)
                return
        except Exception:
            log.exception("Looking at this PC hit a problem")
        with self._lock:
            again, self._again = self._again, False
        if again:  # "Test again", pressed while Mado looked
            self._run(None, timing=True)
            return
        self._done()

    def _run(self, facts: Facts | None, *, timing: bool) -> None:
        while True:
            try:
                facts = facts or self._looked()
                timed = timing and not self._busy()
                with self._lock:
                    self._checking = Checking(timing=timed)
                heavy = tile_for(BEST_PHOTO, "card", best_card(facts.cards))
                found = self._check(timed, heavy, self._best() if timed else None)
                now = self._now()
                checked = Checked(found.runs, now.isoformat(timespec="seconds"), found.problem)
                with closing(db.connect(self._paths.database)) as conn:
                    hardware.keep(conn, facts, checked)
                    if timed:
                        hardware.keep_speeds(conn, found.speeds, now)
                log.info("Checked this PC: on the card %s; timed %s", found.runs, found.speeds)
            except Exception:
                log.exception("Checking this PC hit a problem")
            with self._lock:
                again, self._again = self._again, False
            if not again:
                self._done()
                return
            facts, timing = None, True  # a test asked for meanwhile, looking afresh

    def _done(self) -> None:
        with self._lock:
            self._checking = None


def timed(sessions: Sessions, model: Path, tile: int, place: Place) -> float | None:
    """A model's seconds for a megapixel of tiles here: a tile to warm it up (DirectML compiles
    for the size on its first), then a few more, as many as fit in a few seconds."""
    try:
        session = sessions.get(model, tile, place)
        batch = tensor(np.random.default_rng(0).random((1, 3, tile, tile)))
        session.run({"input": batch})
        began, done = time.perf_counter(), 0
        while done < _MOST and time.perf_counter() - began < _BUDGET:
            session.run({"input": batch})
            done += 1
    except Exception as error:
        log.info("Mado couldn't time %s here: %s", model.name, error)
        return None
    took = time.perf_counter() - began
    return took / (done * tile * tile / 1e6) if done else None


def _sizes(cards: Sequence[Card]) -> list[tuple[str, int | None]]:
    """The cards without their drivers: a new driver keeps the card's times."""
    return [(card.name, card.memory) for card in cards]
