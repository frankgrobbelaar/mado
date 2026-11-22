"""See it first: three of a batch's pictures made in full but not saved, timed and sized, before
it goes in the queue (docs/stack/queue.md). The jobs' worker makes them before the queue's
pictures (mado/jobs.py), one at a time on the graphics card like everything else. Each is kept in
the data folder's cache as Save would write it, with copies to show before and after; the batch
keeps them rather than make them again, as long as its steps and saving are the same and the
pictures haven't changed. Asking for three others, or leaving, lets the last ones go.
"""

import json
import logging
import secrets
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import closing, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

from PIL import Image

from mado import db
from mado.ai import Ai, Timer
from mado.batches import Picture, kept_key
from mado.config import DataPaths
from mado.core.naming import EXTENSIONS
from mado.core.quality import about_bytes
from mado.core.recipe import Recipe
from mado.jobs import JobError
from mado.looks import seed_of
from mado.making import (
    Saving,
    dpi_of,
    estimated,
    make,
    picture_of,
    planned,
    see,
    waiting_for,
    write,
)
from mado.pictures import Command, NeedsFfmpegError, PictureGoneError, UnreadableError, decode
from mado.previews import save_copy
from mado.upscale import StoppedError

log = logging.getLogger(__name__)

type State = Literal["waiting", "making", "done", "failed"]
type Side = Literal["before", "after", "full"]

SHOWN = 1280  # the copies shown before and after, at most this many pixels on their long side
_KEPT_SETS = 2  # sets of three kept: the one on show, and the one before it while it's left


@dataclass(frozen=True)
class Sample:
    index: int  # its place in the batch
    picture: Picture
    state: State = "waiting"
    progress: float = 0.0
    seconds: float | None = None  # what making it took
    guess: float | None = None  # what Mado reckoned it would
    guess_bytes: int | None = None
    made_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    named: str | None = None  # what its name says it was made for and with
    made_for: str | None = None
    look: str | None = None
    problem: str | None = None


@dataclass(frozen=True)
class SampleSet:
    id: str
    key: str  # what they were made to: the steps and the saving, as JSON
    round: int  # how many times three others were asked for
    samples: tuple[Sample, ...]

    @property
    def seconds(self) -> float | None:
        """What making all of them took, once they're made."""
        if any(sample.state in ("waiting", "making") for sample in self.samples):
            return None
        return sum(sample.seconds or 0.0 for sample in self.samples)


@dataclass
class _Asked:
    shown: SampleSet
    recipe: Recipe
    saving: Saving
    dropped: bool = False


class Samples:
    def __init__(
        self,
        paths: DataPaths,
        ai: Ai,
        ffmpeg: Callable[[], Command | None],
        *,
        wake: Callable[[], None],
    ) -> None:
        """`wake` asks the jobs' worker to look for work: three to make."""
        self._paths = paths
        self._folder = paths.cache / "samples"
        self._ai = ai
        self._ffmpeg = ffmpeg
        self._wake = wake
        self._lock = threading.Lock()
        self._asked: dict[str, _Asked] = {}
        self._order: list[str] = []  # oldest first

    def tidy(self, conn: sqlite3.Connection) -> None:
        """As the engine starts: what an earlier run left in the cache goes, but for the pictures
        a batch waiting in the queue keeps."""
        kept = {
            str(path).casefold()
            for (recipe,) in conn.execute(
                "SELECT recipe FROM jobs WHERE state IN ('queued', 'running')"
            )
            if (path := _kept_path(recipe)) is not None
        }
        if not self._folder.is_dir():
            return
        for each in self._folder.rglob("*"):
            if each.is_file() and str(each).casefold() not in kept:
                with suppress(OSError):
                    each.unlink()

    def ask(
        self,
        pictures: Sequence[tuple[int, Picture]],
        recipe: Recipe,
        saving: Saving,
        key: str,
        round_: int,
    ) -> SampleSet:
        """Asks for these pictures (each with its place in the batch) to be made to `recipe` and
        written as `saving` says, before the queue's. Lets go of sets asked for before the last."""
        shown = SampleSet(
            secrets.token_hex(6), key, round_, tuple(Sample(at, each) for at, each in pictures)
        )
        with self._lock:
            self._asked[shown.id] = _Asked(shown, recipe, saving)
            self._order.append(shown.id)
            while len(self._order) > _KEPT_SETS:
                self._let_go(self._order.pop(0))
        self._wake()
        return shown

    def get(self, set_id: str) -> SampleSet | None:
        with self._lock:
            asked = self._asked.get(set_id)
            return asked.shown if asked else None

    def drop(self, set_id: str) -> None:
        """Lets go of a set: the picture being made stops at its next tile, and its files go."""
        with self._lock:
            if set_id in self._order:
                self._order.remove(set_id)
            self._let_go(set_id)

    def file(self, set_id: str, index: int, side: Side) -> Path | None:
        """A made picture of a set, or its copy before or after, once it's there."""
        with self._lock:
            asked = self._asked.get(set_id)
            sample = (
                next((s for s in asked.shown.samples if s.index == index), None) if asked else None
            )
        if sample is None or sample.state != "done":
            return None
        found = self._path(set_id, index, side, asked.saving if asked else None)
        return found if found is not None and found.is_file() else None

    def found(self, set_id: str | None, key: str) -> list[tuple[str, float, float, int, int]]:
        """What a set made to `key` found: each picture's file, its guessed and measured seconds,
        then bytes, for reckoning what the rest of its batch takes."""
        shown = self.get(set_id) if set_id else None
        if shown is None or shown.key != key:
            return []
        return [
            (str(s.picture.path), s.guess, s.seconds, s.guess_bytes, s.made_bytes)
            for s in shown.samples
            if s.state == "done"
            and s.guess is not None
            and s.seconds is not None
            and s.guess_bytes is not None
            and s.made_bytes is not None
        ]

    def keep(self, set_id: str | None, key: str) -> dict[str, dict[str, object]]:
        """A set's pictures made to `key`, moved where a batch's jobs keep them till they're
        saved: by each one's file (`kept_key`), what a job needs to keep it rather than make it
        again (mado/making.py), whatever its place in the batch now."""
        with self._lock:
            asked = self._asked.get(set_id) if set_id else None
            if asked is None or asked.shown.key != key:
                return {}
            done = [s for s in asked.shown.samples if s.state == "done"]
            saving = asked.saving
        kept: dict[str, dict[str, object]] = {}
        for sample in done:
            made = self._path(asked.shown.id, sample.index, "full", saving)
            if made is None or not made.is_file():
                continue
            target = self._folder / "kept" / f"{secrets.token_hex(6)}{made.suffix}"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(made, target)
            except OSError as error:
                log.warning("Mado couldn't keep a picture See it first made: %s", error)
                continue
            kept[kept_key(sample.picture.path)] = {
                "path": str(target),
                "source": str(sample.picture.path),
                "version": sample.picture.version,
                "width": sample.width,
                "height": sample.height,
                "named": sample.named,
                "madeFor": sample.made_for,
                "look": sample.look,
            }
        return kept

    def __call__(self, stopping: Callable[[], bool]) -> bool:
        """The worker's turn: makes the next picture waiting in the newest set asked for. False
        when none waits."""
        with self._lock:
            chosen: tuple[_Asked, Sample] | None = None
            for set_id in reversed(self._order):
                asked = self._asked[set_id]
                waiting = next((s for s in asked.shown.samples if s.state == "waiting"), None)
                if waiting is not None:
                    chosen = (asked, waiting)
                    break
            if chosen is None:
                return False
            asked, sample = chosen
            self._update(asked, replace(sample, state="making", progress=0.0))
        try:
            made = self._make(asked, sample, lambda: stopping() or asked.dropped)
        except StoppedError:
            with self._lock:
                if not asked.dropped:
                    self._update(asked, replace(sample, state="waiting", progress=0.0))
            if asked.dropped:  # let go as it was made: its files go now
                self._remove(asked.shown.id)
            return True
        except (JobError, UnreadableError, PictureGoneError, NeedsFfmpegError) as error:
            made = replace(sample, state="failed", problem=str(error))
        except Exception:  # the worker must outlive any one picture
            log.exception("See it first couldn't make %s", sample.picture.name)
            made = replace(
                sample,
                state="failed",
                problem="Something went wrong inside Mado making this one; its log says what.",
            )
        with self._lock:
            if not asked.dropped:
                self._update(asked, made)
        if asked.dropped:
            self._remove(asked.shown.id)
        return True

    def _make(self, asked: _Asked, sample: Sample, stop: Callable[[], bool]) -> Sample:
        with closing(db.connect(self._paths.database)) as conn:
            picture = picture_of(conn, sample.picture.id, sample.picture.path)
        began = time.monotonic()
        image = decode(picture.path, picture.kind, longest=None, ffmpeg=self._ffmpeg())
        here = self._ai.where()
        made = planned(asked.recipe, see(image, picture), self._ai.starts_on(here))
        if made.empty:
            raise JobError("There's nothing to make: no size, and no look that changes it.")
        if waiting_for(made, self._ai):
            raise JobError("It needs a model Mado downloads the first time it's asked for.")
        guess = estimated(made, here)

        def report(_stage: object, within: float) -> None:
            with self._lock:
                current = next(s for s in asked.shown.samples if s.index == sample.index)
                self._update(asked, replace(current, progress=min(max(within, 0.0), 1.0) * 0.9))

        result = make(
            image,
            made,
            self._ai,
            report=report,
            stop=stop,
            timer=Timer(),
            seed=seed_of(picture.path),
        )
        if stop():
            raise StoppedError
        full = self._path(asked.shown.id, sample.index, "full", asked.saving)
        assert full is not None  # noqa: S101 - its saving says its format
        full.parent.mkdir(parents=True, exist_ok=True)
        size = (made.width, made.height)
        made_bytes = write(result, picture, size, asked.saving, full, dpi=dpi_of(asked.recipe))
        seconds = time.monotonic() - began
        before = image
        if made.frame.shape == "crop":
            kept = made.frame.kept
            before = image.crop(
                (
                    round(kept.x),
                    round(kept.y),
                    round(kept.x + kept.width),
                    round(kept.y + kept.height),
                )
            )
        shown_sides: tuple[tuple[Side, Image.Image], ...] = (("before", before), ("after", result))
        for side, shown in shown_sides:
            copy = shown.copy()
            copy.thumbnail((SHOWN, SHOWN), Image.Resampling.LANCZOS)
            target = self._path(asked.shown.id, sample.index, side, asked.saving)
            assert target is not None  # noqa: S101
            save_copy(copy, target, "WEBP", quality=88, method=4)
        return replace(
            sample,
            state="done",
            progress=1.0,
            seconds=seconds,
            guess=guess,
            guess_bytes=_reckoned_bytes(asked.saving, made.width * made.height),
            made_bytes=made_bytes,
            width=made.width,
            height=made.height,
            named=made.named,
            made_for=made.made_for,
            look=made.look,
        )

    def _update(self, asked: _Asked, sample: Sample) -> None:
        """A set's picture as it is now (under the lock)."""
        asked.shown = replace(
            asked.shown,
            samples=tuple(
                sample if each.index == sample.index else each for each in asked.shown.samples
            ),
        )

    def _let_go(self, set_id: str) -> None:
        """A set forgotten (under the lock): its picture being made stops, and its files go once
        nothing is making them."""
        asked = self._asked.pop(set_id, None)
        if asked is None:
            return
        asked.dropped = True
        if not any(sample.state == "making" for sample in asked.shown.samples):
            self._remove(set_id)

    def _remove(self, set_id: str) -> None:
        for each in self._folder.glob(f"{set_id}-*"):
            with suppress(OSError):
                each.unlink()

    def _path(self, set_id: str, index: int, side: Side, saving: Saving | None) -> Path | None:
        if side == "full":
            if saving is None:
                return None
            return self._folder / f"{set_id}-{index}{EXTENSIONS[saving.format]}"
        return self._folder / f"{set_id}-{index}-{side}.webp"


def _reckoned_bytes(saving: Saving, pixels: int) -> int:
    return about_bytes(saving.format, saving.quality, "photo", pixels)


def _kept_path(recipe: str) -> Path | None:
    """The picture See it first made that a job's order keeps, if any."""
    try:
        order: object = json.loads(recipe)
    except ValueError:
        return None
    made = cast("dict[str, object]", order).get("made") if isinstance(order, dict) else None
    path = cast("dict[str, object]", made).get("path") if isinstance(made, dict) else None
    return Path(path) if isinstance(path, str) else None
