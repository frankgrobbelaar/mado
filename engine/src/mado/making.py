"""Making a picture right for a size, and saving it: the work of a job (mado/jobs.py).

1. Reading: the picture decoded at full size, as the library reads it, turned upright.
2. Shaping: cropped around its subject (the crop is the part kept, resized from exactly), or its
   edges extended by LaMa (mado/extend.py).
3. Making: four times bigger through the AI model a tile at a time, then resized exactly, or
   without AI for pixel art, screenshots and a picture already big enough (mado/upscale.py).
4. Saving: as a new picture beside the original (or in a folder the owner chose), named after
   it with what it was made for, or in the original's place, the original going into
   quarantine; either way written beside first, checked, then put in place, and in History.

What Mado sees in a picture (what it is, where its subject is, its colours) is worked out once
a picture and kept for the engine's life, so the Size tab and the job agree.
"""

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Literal, cast

import numpy as np
from PIL import Image

from mado import encode, hardware, history
from mado.ai import LAMA, Ai, Timer
from mado.core.estimate import seconds_for
from mado.core.files import Kind as FileKind
from mado.core.files import kind_of
from mado.core.framing import Box, subject
from mado.core.hardware import Place, overlap_for, tile_for
from mado.core.kind import Kind, guess
from mado.core.models import Quality
from mado.core.naming import EXTENSIONS, aside_name, new_name, replacement_name
from mado.core.quality import Format
from mado.core.recipe import Plan, Recipe, plan
from mado.core.sizes import DPI, Screen, Size, SizeError, resolve
from mado.core.tiles import count
from mado.directml import ModelError
from mado.extend import Filler, canvas_around, extended, squares_needed
from mado.hardware import Here
from mado.jobs import PARTIAL, JobError, Stage, note_writing
from mado.pictures import (
    Command,
    NeedsFfmpegError,
    PictureGoneError,
    UnreadableError,
    decode,
    read_exif,
)
from mado.quarantine import MoveError, Quarantine, move
from mado.upscale import (
    Pixels,
    StoppedError,
    bled,
    by_pixels,
    resize_alpha,
    smaller,
    smoothly,
    through_model,
)

log = logging.getLogger(__name__)

type Report = Callable[[Stage, float], None]  # the stage, and how far within it, 0 to 1

_SMALL = 512  # the copy what a picture is is guessed from, when it's bigger than _AS_IS
_AS_IS = 1024  # pictures this small are looked at pixel by pixel
_GREY = 128  # the grey copy its subject is found in


@dataclass(frozen=True)
class Picture:
    """The picture a job makes from, as the library knows it."""

    path: Path
    kind: FileKind
    format: str | None
    camera: str | None


@dataclass(frozen=True)
class Seen:
    """What Mado sees in a picture: what it is, where its subject is, and its colours."""

    kind: Kind
    focus: tuple[float, float]
    width: int
    height: int
    profile: str | None  # its colour profile's name: "Display P3"
    alpha: bool  # it has see-through parts


@dataclass(frozen=True)
class Saving:
    how: Literal["new", "replace"]
    format: Format
    quality: int | None
    folder: Path | None = None  # new pictures: here, not beside the original
    keep_camera: bool = True
    keep_colours: bool = True
    keep_location: bool = False


@dataclass(frozen=True)
class Saved:
    path: Path
    history_id: int
    bytes: int


class SavingError(Exception):
    """The picture was made but couldn't be kept, with a sentence saying why. The original is as
    it was."""


def see(image: Image.Image, picture: Picture) -> Seen:
    """What a picture is and where its subject is, from the picture decoded at full size."""
    rgb = image.convert("RGB")
    longest = max(rgb.size)
    small = rgb if longest <= _AS_IS else _shrunk(rgb, _SMALL, Image.Resampling.NEAREST)
    grey = np.asarray(_shrunk(rgb.convert("L"), _GREY, Image.Resampling.BOX), np.float32)
    grey /= 255.0
    kind = guess(
        np.asarray(small),
        name=picture.path.name,
        camera=picture.camera,
        format_=picture.format,
        width=image.width,
        height=image.height,
    )
    profile = image.info.get("icc_profile")
    return Seen(
        kind=kind,
        focus=subject(grey),
        width=image.width,
        height=image.height,
        profile=encode.profile_name(profile if isinstance(profile, bytes) else None),
        alpha=_see_through(image),
    )


def _see_through(image: Image.Image) -> bool:
    """Whether a picture has parts that are see-through, not only a channel for them."""
    if "transparency" in image.info:
        return True
    if "A" not in image.getbands():
        return False
    lowest = image.getchannel("A").getextrema()[0]
    return isinstance(lowest, int | float) and lowest < 255


class Sight:
    """What Mado sees in each picture, by its version, worked out once; and the picture last
    decoded at full size, and the canvas last extended, kept for the previews that follow."""

    def __init__(self, ffmpeg: Callable[[], Command | None]) -> None:
        self._ffmpeg = ffmpeg
        self._seen: dict[tuple[str, str], Seen] = {}
        self._decoded: tuple[tuple[str, str], Image.Image] | None = None
        self._extended: tuple[tuple[object, ...], tuple[Pixels, Box, tuple[int, int]]] | None = None
        self._lock = threading.Lock()

    def picture(self, picture: Picture, version: str) -> Image.Image:
        """The picture decoded at full size, upright. Raises what decoding raises."""
        key = (str(picture.path).casefold(), version)
        with self._lock:
            if self._decoded is not None and self._decoded[0] == key:
                return self._decoded[1]
        image = decode(picture.path, picture.kind, longest=None, ffmpeg=self._ffmpeg())
        with self._lock:
            self._decoded = (key, image)
        return image

    def of(self, picture: Picture, version: str) -> Seen:
        """What Mado sees in the picture."""
        key = (str(picture.path).casefold(), version)
        with self._lock:
            found = self._seen.get(key)
        if found is not None:
            return found
        found = see(self.picture(picture, version), picture)
        with self._lock:
            if len(self._seen) > 200:
                self._seen.clear()
            self._seen[key] = found
        return found

    def extended(
        self, picture: Picture, version: str, canvas: Box, fill: Callable[[], Filler]
    ) -> tuple[Pixels, Box, tuple[int, int]]:
        """The picture on an extended canvas, its new edges drawn by LaMa: the last one kept."""
        key = (str(picture.path).casefold(), version, canvas)
        with self._lock:
            if self._extended is not None and self._extended[0] == key:
                return self._extended[1]
        pixels: Pixels = np.asarray(self.picture(picture, version).convert("RGB"))
        made = extended(pixels, canvas, fill())
        with self._lock:
            self._extended = (key, made)
        return made


def planned(
    recipe: Recipe, seen: Seen, starts_on: dict[Literal["photo", "drawing"], Quality]
) -> Plan:
    """The plan for a recipe, from what Mado sees in the picture."""
    return plan(
        recipe,
        seen.width,
        seen.height,
        guessed_kind=seen.kind,
        found_focus=seen.focus,
        starts_on=starts_on,
    )


def make(
    image: Image.Image,
    made: Plan,
    ai: Ai,
    *,
    report: Report,
    stop: Callable[[], bool],
    timer: Timer | None = None,
) -> Image.Image:
    """The picture made to its plan, from the picture decoded at full size and upright. Its
    colour profile comes with it. Raises StoppedError when stopped, ModelError when a model
    can't run."""
    profile = image.info.get("icc_profile")
    grey = image.mode in ("L", "I", "I;16", "1", "F")
    if image.mode in ("P", "PA", "La", "RGBa") or "transparency" in image.info:
        image = image.convert("RGBA")  # see-through parts as a channel of their own
    alpha = image.getchannel("A") if "A" in image.getbands() else None
    pixels: Pixels = np.asarray(image.convert("RGB"))
    if alpha is not None:
        pixels = bled(pixels, np.asarray(alpha))
    kept = made.frame.kept
    target = (made.width, made.height)
    if made.frame.shape == "extend" and made.frame.sides != "none":
        report("shaping", 0.0)
        fill = ai.filler()  # LaMa's time apart: the timer learns the upscaler's pace
        pixels, kept, at = extended(
            pixels,
            made.frame.canvas,
            fill,
            told=lambda done, total: report("shaping", done / total),
            stop=stop,
        )
        if alpha is not None:
            alpha = _extended_alpha(alpha, pixels.shape[1], pixels.shape[0], at)
    report("making", 0.0)
    match made.method:
        case "ai":
            assert made.model is not None  # noqa: S101 - the plan names one for "ai"
            tiling = ai.tiling(made.model, timer)
            out = through_model(
                pixels,
                kept,
                target,
                tiling,
                told=lambda done, total: report("making", done / total),
                stop=stop,
            )
        case "pixels":
            out = by_pixels(pixels, kept, target)
        case "smooth":
            out = smoothly(pixels, kept, target)
        case "shrink":
            out = smaller(pixels, kept, target)
    result = Image.fromarray(out)
    if alpha is not None:
        result.putalpha(Image.fromarray(resize_alpha(np.asarray(alpha), kept, target)))
    elif grey:
        result = result.convert("L")
    if isinstance(profile, bytes):
        result.info["icc_profile"] = profile
    return result


def keep(
    result: Image.Image,
    picture: Picture,
    made: Plan,
    size: Size,
    saving: Saving,
    *,
    conn: sqlite3.Connection,
    quarantine: Quarantine,
    now: datetime,
    job_id: int | None,
    writing: Callable[[Path], None] = lambda _path: None,
) -> Saved:
    """Saves a picture made for `size`: as a new picture, or in its original's place. `writing`
    hears the file it's written to first, so a job cut short knows what to clear away. History's
    line is written before any picture moves, so a job cut short while saving can be finished
    or taken back from it (mado/jobs.py). Raises SavingError."""
    label = size.label
    extension = EXTENSIONS[saving.format]
    original = picture.path
    profile = result.info.get("icc_profile")
    kept_profile = profile if isinstance(profile, bytes) else None
    image = result
    if kept_profile is not None and not saving.keep_colours:
        image, kept_profile = encode.in_srgb(result, kept_profile), None
    dpi = DPI if size.purpose == "print" else None
    exif = encode.prepared_exif(
        read_exif(original, picture.kind),
        keep_camera=saving.keep_camera,
        keep_location=saving.keep_location,
        size=(made.width, made.height),
        dpi=dpi,
    )
    if saving.how == "new":
        folder = saving.folder or original.parent
        name = new_name(original.stem, label, extension, lambda each: (folder / each).exists())
        target = folder / name
    else:
        folder = original.parent
        name = replacement_name(original.name, extension)
        target = folder / name
        if target != original and target.exists():  # another picture has that name
            name = aside_name(name, lambda each: (folder / each).exists())
            target = folder / name
    partial = target.with_name(target.name + PARTIAL)
    writing(partial)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        encode.save(
            image,
            partial,
            saving.format,
            saving.quality,
            exif=exif,
            profile=kept_profile,
            dpi=dpi,
        )
        encode.check(partial, (made.width, made.height))
        written = partial.stat().st_size
    except encode.SaveError as error:
        partial.unlink(missing_ok=True)
        raise SavingError(str(error)) from None
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise SavingError(_unsaved(folder, error)) from None
    if saving.how == "new":
        entry = history.made(
            conn,
            now=now,
            job_id=job_id,
            name=original.name,
            made_for=label,
            original=original,
            result=target,
        )
        try:
            target = _into_place(
                partial,
                target,
                (original.stem, label, extension),
                lambda moved: history.renamed(conn, entry, moved),
            )
        except MoveError as error:
            partial.unlink(missing_ok=True)
            history.forget(conn, entry)
            raise SavingError(str(error)) from None
        return Saved(target, entry, written)
    aside = quarantine.place(original, now)
    entry = history.replaced(
        conn,
        now=now,
        job_id=job_id,
        name=original.name,
        made_for=label,
        original=original,
        result=target,
        aside=aside,
    )
    _replacing(
        partial, target, original, aside, quarantine, now, lambda: history.forget(conn, entry)
    )
    return Saved(target, entry, written)


def _into_place(
    partial: Path,
    target: Path,
    naming: tuple[str, str, str],
    renamed: Callable[[Path], None],
) -> Path:
    """A new picture from beside its place into it; the next number when the name was taken
    meanwhile, `renamed` hearing it first. `naming` is the original's stem, what it was made for
    and the extension."""
    for _ in range(50):
        try:
            move(partial, target)
            return target
        except MoveError:
            if not target.exists():
                raise
            target = target.parent / new_name(*naming, _taken_in(target.parent))
            renamed(target)
    raise MoveError(f"Mado couldn't find a free name for it in {target.parent}.")


def _taken_in(folder: Path) -> Callable[[str], bool]:
    """Whether a name is taken in a folder."""
    return lambda name: (folder / name).exists()


def _replacing(
    partial: Path,
    target: Path,
    original: Path,
    aside: Path,
    quarantine: Quarantine,
    now: datetime,
    forget: Callable[[], None],
) -> None:
    """The original into quarantine at `aside`, the made picture into its place; the original
    back if that doesn't work, and History's line forgotten (`forget`). Raises SavingError."""
    try:
        quarantine.set_aside(original, now, to=aside)
    except MoveError as error:
        partial.unlink(missing_ok=True)
        forget()
        raise SavingError(str(error)) from None
    try:
        move(partial, target)
    except MoveError as error:
        partial.unlink(missing_ok=True)
        try:
            quarantine.put_back(aside, original)
        except MoveError:  # the line stays, so History can put it back
            raise SavingError(
                f"{error} The original waits in quarantine, and History puts it back."
            ) from None
        forget()
        raise SavingError(str(error)) from None


def _extended_alpha(
    alpha: Image.Image, width: int, height: int, at: tuple[int, int]
) -> Image.Image:
    """See-through parts on an extended canvas, the picture's at `at`: what's drawn new is as
    see-through as the picture's edge beside it (a sticker's nothing stays nothing, a solid
    picture's new edges are solid)."""
    seen = np.asarray(alpha)
    left, top = at
    right, bottom = width - left - seen.shape[1], height - top - seen.shape[0]
    return Image.fromarray(np.pad(seen, ((top, bottom), (left, right)), mode="edge"), "L")


def _shrunk(image: Image.Image, longest: int, how: Image.Resampling) -> Image.Image:
    scale = longest / max(image.size)
    if scale >= 1:
        return image
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, how)


def _unsaved(folder: Path, error: OSError) -> str:
    if error.errno == 28:  # ENOSPC
        return f"There isn't enough space in {folder} for it. Free some, then try again."
    return f"Mado couldn't save it in {folder}: {error.strerror or error}."


# The jobs' side: what a job's recipe says, how long it should take, and making it.


def recipe_from(data: dict[str, object], screens: list[Screen]) -> Recipe:
    """A recipe as a job keeps it (JSON), the owner's screens naming theirs. Raises SizeError
    for a size Mado can't make."""
    focus = data.get("focus")
    point: tuple[float, float] | None = None
    if isinstance(focus, list):
        values = cast("list[object]", focus)
        if len(values) == 2 and all(isinstance(each, int | float) for each in values):
            point = (float(cast("float", values[0])), float(cast("float", values[1])))
    kind, quality = data.get("kind"), data.get("quality")
    return Recipe(
        size=resolve(str(data.get("size", "")), screens),
        shape="extend" if data.get("shape") == "extend" else "crop",
        focus=point,
        kind=kind if kind in ("photo", "drawing", "pixels", "screenshot") else None,
        quality=quality if quality in ("fast", "best") else None,
        clean=data.get("clean") is not False,
    )


def saving_from(data: dict[str, object]) -> Saving:
    """How a job saves its picture, as it keeps it (JSON)."""
    format_ = data.get("format")
    quality, folder = data.get("quality"), data.get("folder")
    return Saving(
        how="replace" if data.get("how") == "replace" else "new",
        format=format_ if format_ in ("JPEG", "PNG", "WebP", "AVIF") else "JPEG",
        quality=quality if isinstance(quality, int) else None,
        folder=Path(folder) if isinstance(folder, str) and folder else None,
        keep_camera=data.get("keepCamera") is not False,
        keep_colours=data.get("keepColours") is not False,
        keep_location=data.get("keepLocation") is True,
    )


def estimated(made: Plan, here: Here) -> float:
    """How long making a plan takes here, in seconds."""
    pixels = made.width * made.height
    canvas = made.frame.canvas
    seconds = 0.0
    if made.frame.shape == "extend" and made.frame.sides != "none":
        width, height = round(made.frame.kept.width), round(made.frame.kept.height)
        left, top, canvas_width, canvas_height = canvas_around(canvas, width, height)
        drawn = squares_needed(
            (canvas_width, canvas_height), (left, top, left + width, top + height)
        )
        seconds += drawn * _LAMA_SECONDS[here.place]
    if made.method != "ai" or made.model is None:
        return seconds + seconds_for(None, here.place, 0, 0, pixels, here.speeds)
    tile = tile_for(made.model, here.place, here.card)
    tiles = count(ceil(canvas.width), ceil(canvas.height), tile, overlap_for(tile))
    return seconds + seconds_for(made.model.id, here.place, tiles, tile, pixels, here.speeds)


def waiting_for(made: Plan, ai: Ai) -> list[str]:
    """The downloads a plan waits for: the Best photo model, or LaMa to extend edges."""
    found: list[str] = []
    if made.model is not None and made.model.download and ai.file(made.model) is None:
        found.append(made.model.download)
    if made.frame.shape == "extend" and made.frame.sides != "none" and ai.lama_file() is None:
        found.append(LAMA)
    return found


_LAMA_SECONDS: dict[Place, float] = {"card": 0.35, "processor": 3.0}  # a square drawn


class Maker:
    """A job's work: reading its picture, making it to its recipe, saving it as the owner chose,
    and learning this PC's speed from it."""

    def __init__(
        self,
        ai: Ai,
        quarantine: Quarantine,
        ffmpeg: Callable[[], Command | None],
        *,
        now: Callable[[], datetime],
    ) -> None:
        self._ai = ai
        self._quarantine = quarantine
        self._ffmpeg = ffmpeg
        self._now = now

    def __call__(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        report: Report,
        stop: Callable[[], bool],
        expect: Callable[[float], None],
    ) -> Path:
        order = cast("dict[str, dict[str, object]]", json.loads(row["recipe"]))
        try:
            recipe = recipe_from(order["recipe"], screens_kept(conn))
        except SizeError as error:
            raise JobError(str(error)) from None
        saving = saving_from(order["saving"])
        picture = picture_of(conn, row["picture_id"], Path(row["source"]))
        report("reading", 0.0)
        try:
            image = decode(picture.path, picture.kind, longest=None, ffmpeg=self._ffmpeg())
        except (UnreadableError, PictureGoneError, NeedsFfmpegError) as error:
            raise JobError(str(error)) from None
        here = self._ai.where()
        made = planned(recipe, see(image, picture), self._ai.starts_on(here))
        if waiting_for(made, self._ai):
            raise JobError(
                "It needs a model Mado downloads the first time it's asked for. Download it on "
                "the Size tab, then save again."
            )
        expect(estimated(made, here))
        timer = Timer()
        if stop():  # cancelled while it was read: a way without a model never asks again
            raise StoppedError
        try:
            result = make(image, made, self._ai, report=report, stop=stop, timer=timer)
        except ModelError as error:
            raise JobError(f"{error} Nothing was saved; the original is as it was.") from None
        if stop():  # cancelled as its last tile was made
            raise StoppedError
        report("saving", 0.0)  # past cancelling from here: a picture half moved helps no one
        job_id: int = row["id"]
        try:
            saved = keep(
                result,
                picture,
                made,
                recipe.size,
                saving,
                conn=conn,
                quarantine=self._quarantine,
                now=self._now(),
                job_id=job_id,
                writing=lambda partial: note_writing(conn, job_id, partial),
            )
        except SavingError as error:
            raise JobError(str(error)) from None
        pace = timer.per_megapixel
        if made.model is not None and pace is not None:
            hardware.learn(conn, made.model.id, here.place, pace, self._now())
        report("saving", 1.0)
        return saved.path


def picture_of(conn: sqlite3.Connection, picture_id: int | None, source: Path) -> Picture:
    """The picture a job makes from: as the library has it, or its file as it was asked for."""
    row = (
        conn.execute("SELECT * FROM pictures WHERE id = ?", (picture_id,)).fetchone()
        if picture_id is not None
        else None
    )
    if row is None:
        return Picture(source, kind_of(source.name) or "picture", None, None)
    path = Path(row["path"])
    return Picture(path, kind_of(path.name) or "picture", row["format"], row["camera"])


def screens_kept(conn: sqlite3.Connection) -> list[Screen]:
    """The owner's screens Mado remembers (mado/api/making.py keeps them)."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'screens'").fetchone()
    try:
        kept: object = json.loads(row["value"]) if row else []
    except ValueError:
        return []
    found: list[Screen] = []
    for each in cast("list[object]", kept) if isinstance(kept, list) else []:
        if isinstance(each, dict):
            screen = cast("dict[str, object]", each)
            name, width, height = screen.get("name"), screen.get("width"), screen.get("height")
            if isinstance(name, str) and isinstance(width, int) and isinstance(height, int):
                found.append(Screen(name, width, height))
    return found
