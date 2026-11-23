"""Editing a picture by clicking (docs/stack/editing.md): picking parts, and making the edits in
order on the picture at its full size, each from the picture as the ones before it left it.

What's worked out is kept, so the window's preview, its before and after and the picture Save
makes are the same and quick: the last few pictures as edits left them and what SAM read of each,
in memory; and each edit's mask in the data folder's cache too (`cache/edits`, a folder for each
picture and its version), so Save, made later by the queue or after Mado restarts, makes the
same mask without picking again. A mask that's gone (the cache can be emptied) is made again from
the clicks kept in the recipe. Nothing here touches the picture's file.
"""

import hashlib
import json
import logging
import shutil
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from mado.ai import BIREFNET, BIREFNET_FILE, Ai, Selector, Timer
from mado.core.edits import (
    Blur,
    Click,
    CutOut,
    Edit,
    Erase,
    Part,
    Quality,
    Stroke,
    Subject,
    edit_json,
    parts_json,
)
from mado.core.hardware import Place
from mado.core.masks import Brush, Floats, Mask, feathered, stroked, together
from mado.cutting import cut, lens_blurred, refined
from mado.erasing import erased
from mado.selecting import (
    Answers,
    Read,
    answers,
    drawn,
    flat,
    grid_size,
    holding,
    mask_at,
    on_grid,
    readable,
    soft,
)
from mado.upscale import StoppedError

log = logging.getLogger(__name__)

MOST_PIXELS = 100_000_000  # the biggest picture Mado edits: a hundred megapixels
_STATES = 60_000_000  # pixels of pictures as edits left them, kept in memory at most (5 photos)
_MASKS = 160_000_000  # pixels of masks kept in memory at most
_READS = 3  # pictures SAM's reading of is kept for
_ANSWERS = 96  # parts whose answers are kept
_FEATHER = 0.004  # a look on a part fades in over this much of the picture's shorter side
_DAYS = 30  # a picture's masks are let go of once it hasn't been edited for this long
_LOCKS = 64  # pictures' edits are made under one of these, by the picture
_MADE = 256  # edits whose outcome is kept, to say how they went
_SMALLS = 4  # small copies of pictures as edits left them, for the Looks tab's looks


class EditingError(Exception):
    """An edit Mado can't make, with a sentence saying why."""


@dataclass(frozen=True)
class Picked:
    """The parts as picked now: an Alt-click goes to the part it's in, a click starts a part."""

    parts: tuple[Part, ...]  # each with the answer shown as its choice
    outline: str  # round all of them, as the window's SVG path in a frame 1000 square
    read: float | None  # seconds reading the picture took, when this pick read it
    place: Place  # where it was read
    waited: float  # seconds it waited for the graphics card
    missed: bool  # an Alt-click outside every part


@dataclass(frozen=True)
class Made:
    """What the last of some edits came to."""

    smeared: bool  # an erase whose fill came out much smoother than what's round it
    place: Place | None  # where its model ran
    seconds: float
    waited: float


class Editor:
    def __init__(self, ai: Ai, folder: Path) -> None:
        """`folder`: where each edit's mask is kept (the data folder's `cache/edits`)."""
        self._ai = ai
        self._folder = folder
        self._lock = threading.Lock()
        self._making = [threading.RLock() for _ in range(_LOCKS)]
        self._states: OrderedDict[str, Image.Image] = OrderedDict()
        self._reads: OrderedDict[str, tuple[Read, Place]] = OrderedDict()
        self._answers: OrderedDict[str, Answers] = OrderedDict()
        self._masks: OrderedDict[str, Mask] = OrderedDict()
        self._made: OrderedDict[str, Made] = OrderedDict()
        self._smalls: OrderedDict[str, Image.Image] = OrderedDict()

    def state(
        self,
        image: Image.Image,
        key: str,
        edits: tuple[Edit, ...],
        *,
        stop: Callable[[], bool] = lambda: False,
        report: Callable[[int], None] = lambda _done: None,
        keep: bool = True,
    ) -> Image.Image:
        """The picture (`image`, decoded at full size; `key` names it and its version) as the
        edits leave it, made one edit at a time from the last one kept; `report` hears how many
        are made. Without `keep` (a batch's picture, made once) nothing is kept of it: no mask in
        the cache and nothing in memory. Raises EditingError, ModelError when a model can't run,
        StoppedError when stopped between edits."""
        if not edits:
            return image
        _too_big(image)
        digest = _digest(key, edits)
        with self._lock:
            found = self._states.get(digest)
            if found is not None:
                self._states.move_to_end(digest)
                return found
        # A picture's edits are made under its one lock, so a thread making a chain of them only
        # ever holds that one, and two threads never wait for each other's.
        with self._making[hash(key) % _LOCKS]:
            with self._lock:
                found = self._states.get(digest)
            if found is not None:
                return found
            before = self.state(image, key, edits[:-1], stop=stop, report=report, keep=keep)
            if stop():
                raise StoppedError
            timer = Timer()
            began = time.perf_counter()
            made, smeared, place = self._edited(before, key, edits[:-1], edits[-1], timer, keep)
            took = time.perf_counter() - began
            report(len(edits))
            if keep:
                with self._lock:
                    outcome = Made(smeared, place, took, timer.waited)
                    self._keep(self._made, digest, outcome, _MADE, lambda _each: 1)
                    self._keep(self._states, digest, made, _STATES, _pixels)
            return made

    def small(
        self, image: Image.Image, key: str, edits: tuple[Edit, ...], longest: int
    ) -> Image.Image:
        """The picture as the edits leave it, `longest` pixels on its longer side: the copy the
        Looks tab shows each look on, made once for all of them. Raises as `state` does."""
        name = f"{_digest(key, edits)}|{longest}"
        with self._lock:
            found = self._smalls.get(name)
            if found is not None:
                self._smalls.move_to_end(name)
                return found
        state = self.state(image, key, edits)
        scale = min(longest / max(state.size), 1.0)
        size = (max(1, round(state.width * scale)), max(1, round(state.height * scale)))
        small = state.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
        profile = state.info.get("icc_profile")
        if isinstance(profile, bytes):
            small.info["icc_profile"] = profile
        with self._lock:
            self._keep(self._smalls, name, small, _SMALLS, lambda _each: 1)
        return small

    def made(self, key: str, edits: tuple[Edit, ...]) -> Made | None:
        """What the last of the edits came to, once they're made."""
        with self._lock:
            return self._made.get(_digest(key, edits))

    def pick(
        self,
        image: Image.Image,
        key: str,
        before: tuple[Edit, ...],
        parts: tuple[Part, ...],
        click: Click | None,
    ) -> Picked:
        """The parts picked on the picture as the edits `before` left it, with a click added: a
        click starts a part, an Alt-click takes from the last part it's in. Raises EditingError
        (a picture too big to edit says so before a part is picked), ModelError when SAM isn't
        there or can't run."""
        _too_big(image)
        state = self.state(image, key, before)
        at = _digest(key, before)
        timer = Timer()
        read, place, took = self._read(state, at, timer)
        picker = self._ai.selector()
        listed = list(parts)
        found = [self._answer(picker, read, at, part) for part in listed]
        shown = [
            on_grid(answer.logits[answer.choice(part.choice)], state.size)
            for answer, part in zip(found, listed, strict=True)
        ]
        missed = False
        if click is not None and click.keep:
            listed.append(Part((click,)))
            found.append(self._answer(picker, read, at, listed[-1]))
            shown.append(on_grid(found[-1].logits[found[-1].choice(None)], state.size))
        elif click is not None:
            inside = holding(shown, click.x, click.y)
            if inside is None:
                missed = True
            else:
                listed[inside] = Part((*listed[inside].clicks, click))
                found[inside] = self._answer(picker, read, at, listed[inside])
                answer = found[inside]
                shown[inside] = on_grid(answer.logits[answer.choice(None)], state.size)
        chosen = tuple(
            Part(part.clicks, answer.choice(part.choice))
            for part, answer in zip(listed, found, strict=True)
        )
        return Picked(chosen, drawn(shown, state.size), took, place, timer.waited, missed)

    def look_mask(
        self,
        image: Image.Image,
        key: str,
        edits: tuple[Edit, ...],
        parts: tuple[Part, ...],
        *,
        keep: bool = True,
    ) -> Mask:
        """Where a look goes, on the picture as the edits leave it: the parts, following the
        picture's edges, fading in softly. Without `keep`, nothing is kept of it. Raises
        EditingError."""
        _too_big(image)
        state = self.state(image, key, edits, keep=keep)
        at = _digest(key, edits)
        name = _named(at, {"look": parts_json(parts)})
        found = self._mask(name, key, state.size)
        if found is not None:
            return found
        mask = refined(state, self._parts_soft(state, at, parts))
        made = feathered(mask, max(2, round(min(state.size) * _FEATHER)))
        self._store(name, key, made, keep)
        return made

    def tidy(self) -> None:
        """As the engine starts: the masks of pictures not edited for a month go."""
        cutoff = time.time() - _DAYS * 86400
        try:
            pictures = list(self._folder.iterdir())
        except OSError:
            return
        for picture in pictures:
            try:
                versions = list(picture.iterdir())
                for each in versions:
                    if each.stat().st_mtime < cutoff:
                        shutil.rmtree(each, ignore_errors=True)
                if not any(picture.iterdir()):
                    picture.rmdir()
            except OSError as error:
                log.warning("Mado couldn't tidy %s: %s", picture, error)

    # What each edit does.

    def _edited(
        self,
        before: Image.Image,
        key: str,
        prior: tuple[Edit, ...],
        edit: Edit,
        timer: Timer,
        keep: bool,
    ) -> tuple[Image.Image, bool, Place | None]:
        at = _digest(key, prior)
        name = _named(at, edit_json(edit))
        match edit:
            case Erase(parts=parts, strokes=strokes, quality=quality):
                hole = self._mask(name, key, before.size)
                if hole is None:
                    hole = self._hole(before, at, parts, strokes)
                    self._store(name, key, hole, keep)
                return self._erase(before, hole, quality, timer)
            case CutOut(parts=parts, behind=behind, colour=colour):
                mask = self._refined(name, key, before, at, parts, keep)
                return cut(before, mask, behind, colour), False, self._read_place(at)
            case Blur(parts=parts):
                mask = self._refined(name, key, before, at, parts, keep)
                return lens_blurred(before, mask), False, self._read_place(at)
            case Subject(quality=quality, behind=behind, colour=colour):
                place: Place | None = None
                mask = self._mask(name, key, before.size)
                if mask is None:
                    matte, place = self._ai.matte(quality or cut_quality(self._ai), timer)
                    mask = refined(before, matte(flat(before)))
                    self._store(name, key, mask, keep)
                return cut(before, mask, behind, colour), False, place

    def _erase(
        self, before: Image.Image, hole: Mask, quality: Quality, timer: Timer
    ) -> tuple[Image.Image, bool, Place | None]:
        fill, place = self._ai.eraser(quality, timer)
        alpha = before.getchannel("A") if "A" in before.getbands() else None
        rgb = before.convert("RGB")
        pixels, smeared = erased(np.asarray(rgb), hole, fill)
        made = Image.fromarray(pixels)
        if alpha is not None:
            made.putalpha(alpha)
        profile = before.info.get("icc_profile")
        if isinstance(profile, bytes):
            made.info["icc_profile"] = profile
        return made, smeared, place

    def _hole(
        self,
        state: Image.Image,
        at: str,
        parts: tuple[Part, ...],
        strokes: tuple[Stroke, ...],
    ) -> Mask:
        """What an erase fills: the parts picked, and what the brush painted."""
        width, height = state.size
        masks: list[Mask] = []
        if parts:
            read, _place, _took = self._read(state, at, Timer())
            picker = self._ai.selector()
            for part in parts:
                answer = self._answer(picker, read, at, part)
                masks.append(mask_at(answer.logits[answer.choice(part.choice)], state.size))
        short = min(width, height)
        brushes = [
            Brush(
                tuple((x * width, y * height) for x, y in stroke.points),
                stroke.size * short,
                stroke.take,
            )
            for stroke in strokes
        ]
        hole = together(masks, (height, width))
        if brushes:
            painted = stroked(brushes, (width, height))
            np.maximum(hole, painted, out=hole)
        return hole

    def _refined(
        self,
        name: str,
        key: str,
        state: Image.Image,
        at: str,
        parts: tuple[Part, ...],
        keep: bool,
    ) -> Mask:
        found = self._mask(name, key, state.size)
        if found is None:
            found = refined(state, self._parts_soft(state, at, parts))
            self._store(name, key, found, keep)
        return found

    def _parts_soft(self, state: Image.Image, at: str, parts: tuple[Part, ...]) -> Floats:
        """The parts as one soft mask, on a copy 1024 across (enough for refining it)."""
        read, _place, _took = self._read(state, at, Timer())
        picker = self._ai.selector()
        work = grid_size(state.size)
        found = np.zeros((work[1], work[0]), np.float32)
        for part in parts:
            answer = self._answer(picker, read, at, part)
            np.maximum(found, soft(answer.logits[answer.choice(part.choice)], work), out=found)
        return found

    # What's kept.

    def _read(self, state: Image.Image, at: str, timer: Timer) -> tuple[Read, Place, float | None]:
        """What SAM read of the picture as some edits left it: read now (and how long that took,
        reading included) or as kept."""
        with self._lock:
            kept = self._reads.get(at)
            if kept is not None:
                self._reads.move_to_end(at)
                return kept[0], kept[1], None
        began = time.perf_counter()
        selector = self._ai.selector(timer)
        read = selector.read(readable(state))
        took = time.perf_counter() - began
        with self._lock:
            self._reads[at] = (read, selector.place)
            while len(self._reads) > _READS:
                self._reads.popitem(last=False)
        return read, selector.place, took

    def _read_place(self, at: str) -> Place | None:
        with self._lock:
            kept = self._reads.get(at)
        return kept[1] if kept else None

    def _answer(self, picker: Selector, read: Read, at: str, part: Part) -> Answers:
        name = _named(at, {"clicks": parts_json([Part(part.clicks)])[0]["clicks"]})
        with self._lock:
            found = self._answers.get(name)
            if found is not None:
                self._answers.move_to_end(name)
                return found
        made = answers(picker, read, part)
        with self._lock:
            self._answers[name] = made
            while len(self._answers) > _ANSWERS:
                self._answers.popitem(last=False)
        return made

    def _mask(self, name: str, key: str, size: tuple[int, int]) -> Mask | None:
        """An edit's mask as kept, in memory or in the cache; None when it isn't, or when it
        doesn't fit the picture (`size`) as it's read now."""
        shape = (size[1], size[0])
        with self._lock:
            found = self._masks.get(name)
            if found is not None and found.shape == shape:
                self._masks.move_to_end(name)
                return found
        path = self._path(name, key)
        try:
            with Image.open(path) as kept:
                found = np.asarray(kept.convert("L"))
            path.touch()
        except OSError:
            return None
        if found.shape != shape:
            return None  # made again from its clicks
        with self._lock:
            self._keep(self._masks, name, found, _MASKS, lambda mask: mask.size)
        return found

    def _store(self, name: str, key: str, mask: Mask, keep: bool = True) -> None:
        if not keep:
            return
        with self._lock:
            self._keep(self._masks, name, mask, _MASKS, lambda each: each.size)
        path = self._path(name, key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + ".partial")
            Image.fromarray(mask, "L").save(partial, format="PNG", compress_level=1)
            partial.replace(path)
        except OSError as error:  # kept in memory all the same; Save can make it again
            log.warning("Mado couldn't keep a mask in %s: %s", path.parent, error)

    def _path(self, name: str, key: str) -> Path:
        picture, _, version = key.rpartition("|")
        folder = hashlib.sha256(picture.encode()).hexdigest()[:16]
        return self._folder / folder / version / f"{name}.png"

    @staticmethod
    def _keep[T](
        kept: OrderedDict[str, T], name: str, value: T, most: int, size: Callable[[T], int]
    ) -> None:
        kept[name] = value
        kept.move_to_end(name)
        while len(kept) > 1 and sum(size(each) for each in kept.values()) > most:
            kept.popitem(last=False)


def picture_key(path: Path, version: str) -> str:
    """What names a picture and its version among the edits kept."""
    return f"{str(path).casefold()}|{version}"


def cut_quality(ai: Ai) -> Quality:
    """Which of Fast and Best cuts out a picture's subject when it's left to this PC: Best when
    its model is downloaded and the card has room for it, else Fast."""
    found = ai.edit_file(BIREFNET, BIREFNET_FILE)
    if found is None:
        return "fast"
    return "best" if ai.edit_place(BIREFNET, found) == "card" else "fast"


def _too_big(image: Image.Image) -> None:
    if image.width * image.height > MOST_PIXELS:
        megapixels = image.width * image.height / 1e6
        raise EditingError(
            f"It's {megapixels:.0f} megapixels, and Mado edits pictures up to "
            f"{MOST_PIXELS / 1e6:.0f}. Your picture is as it was; make a smaller copy of it on the "
            "Size tab, then edit that."
        )


def _digest(key: str, edits: tuple[Edit, ...]) -> str:
    text = json.dumps({"key": key, "edits": [edit_json(each) for each in edits]}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _named(at: str, what: object) -> str:
    text = json.dumps({"at": at, "what": what}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _pixels(image: Image.Image) -> int:
    return image.width * image.height
