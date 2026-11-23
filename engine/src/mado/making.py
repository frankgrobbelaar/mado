"""Making a picture to its recipe, and saving it: the work of a job (mado/jobs.py).

1. Reading: the picture decoded at full size, as the library reads it, turned upright.
2. Editing: its edits made in order at its own size (mado/editing.py): parts erased, cut out or
   blurred behind, as the Edit tab picked them, or its subject cut out.
3. Shaping: cropped around its subject (the crop is the part kept, resized from exactly), or its
   edges extended by LaMa (mado/extend.py).
4. Making: four times bigger through the AI model a tile at a time, then resized exactly, or
   without AI for pixel art, screenshots and a picture already big enough (mado/upscale.py).
   With no size, the picture keeps its pixels.
5. Looking: its look and finishing touches (mado/looks.py), at the size made, so grain and dust
   never grow into blobs; only on a part, through its mask placed as the picture is.
6. Saving: as a new picture beside the original (or in a folder the owner chose), named after
   it with what it was made for and with, or in the original's place, the original going into
   quarantine; either way written beside first, checked, then put in place, and in History.

What Mado sees in a picture (what it is, where its subject is, its colours) is worked out once
a picture and kept for the engine's life, so the tabs and the job agree.
"""

import json
import logging
import shutil
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado import encode, hardware, history, own_looks
from mado.ai import BIREFNET, LAMA, MIGAN, SAM, Ai, Timer
from mado.core.edits import (
    Blur,
    CutOut,
    EditError,
    Erase,
    Subject,
    editing_from,
    models_for,
    parts_from,
)
from mado.core.estimate import seconds_for
from mado.core.files import Kind as FileKind
from mado.core.files import kind_of
from mado.core.framing import Box, subject
from mado.core.hardware import Place, overlap_for, tile_for
from mado.core.kind import Kind, guess
from mado.core.looks import Look
from mado.core.models import Quality
from mado.core.naming import EXTENSIONS, aside_name, new_name, replacement_name
from mado.core.quality import Format
from mado.core.recipe import Plan, Recipe, Sizing, Styling, plan
from mado.core.sizes import DPI, Screen, SizeError, resolve
from mado.core.tiles import count
from mado.core.touches import named
from mado.directml import ModelError
from mado.editing import EditingError, Editor, cut_quality, picture_key
from mado.extend import Filler, canvas_around, extended, squares_needed
from mado.hardware import Here
from mado.jobs import (
    PARTIAL,
    DriveGoneError,
    HeldError,
    JobError,
    NoRoomError,
    Stage,
    drive_of,
    drive_there,
    note_writing,
)
from mado.libraw import Reader
from mado.looks import seed_of, styled
from mado.pictures import (
    Command,
    InUseError,
    NeedsFfmpegError,
    NeedsReaderError,
    PictureGoneError,
    UnreadableError,
    decode,
    read_exif,
)
from mado.quarantine import InUseMoveError, MoveError, Quarantine, movable, move
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


class InUseSavingError(SavingError):
    """The original couldn't be replaced: another app has it open. Nothing was saved."""


class FullError(SavingError):
    """The drive a picture was being saved to filled up."""

    def __init__(self, folder: Path) -> None:
        drive = folder.drive or folder.anchor or str(folder)
        super().__init__(
            f"There isn't enough space on {drive} for it, so nothing was saved and the original "
            "is as it was. Free some there, then try again."
        )
        self.drive = drive


@dataclass(frozen=True)
class Naming:
    """What a picture made is called, and what History says of it."""

    width: int
    height: int
    named: str  # what its name says it was made for and with: "TV 8K, Warm film"
    made_for: str | None
    look: str | None
    edit: str | None = None  # what was edited: "erased a part"

    @classmethod
    def of(cls, made: Plan) -> Naming:
        return cls(made.width, made.height, made.named, made.made_for, made.look, made.edit)


class MissingLookError(ValueError):
    """A recipe's look that isn't there any more (the owner deleted it), with a sentence."""

    def __init__(self) -> None:
        super().__init__(
            "Its look isn't in your looks any more, so nothing was made and the original is as "
            "it was. Pick another look, then save again."
        )


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
    decoded at full size, the canvas last extended and the picture last made small for a preview,
    kept for the previews that follow. Each is made under a lock of its own, so two asking at once
    (the Looks tab's picture with its look and without) wait for one making, not make it twice."""

    def __init__(self, ffmpeg: Callable[[], Command | None], reader: Reader | None = None) -> None:
        self._ffmpeg = ffmpeg
        self.reader = reader  # camera RAW's, once it's there
        self._seen: dict[tuple[str, str], Seen] = {}
        self._decoded: tuple[tuple[str, str], Image.Image] | None = None
        self._extended: tuple[tuple[object, ...], tuple[Pixels, Box, tuple[int, int]]] | None = None
        self._fitted: tuple[tuple[object, ...], Image.Image] | None = None
        self._lock = threading.Lock()  # what's kept
        self._decoding = threading.Lock()
        self._extending = threading.Lock()
        self._fitting = threading.Lock()

    def fitted(self, key: tuple[object, ...], make: Callable[[], Image.Image]) -> Image.Image:
        """The picture made small for a preview (`key` says which picture, shape and size), the
        last one kept: the next look tried on it takes moments."""
        with self._fitting:
            with self._lock:
                if self._fitted is not None and self._fitted[0] == key:
                    return self._fitted[1]
            image = make()
            with self._lock:
                self._fitted = (key, image)
            return image

    def picture(self, picture: Picture, version: str) -> Image.Image:
        """The picture decoded at full size, upright. Raises what decoding raises."""
        key = (str(picture.path).casefold(), version)
        with self._decoding:
            with self._lock:
                if self._decoded is not None and self._decoded[0] == key:
                    return self._decoded[1]
            image = decode(
                picture.path,
                picture.kind,
                longest=None,
                ffmpeg=self._ffmpeg(),
                reader=self.reader,
            )
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
        self,
        picture: Picture,
        version: str,
        canvas: Box,
        fill: Callable[[], Filler],
        *,
        image: Image.Image | None = None,
        also: object = None,
    ) -> tuple[Pixels, Box, tuple[int, int]]:
        """The picture (or `image`, the picture as its edits left it, which `also` names) on an
        extended canvas, its new edges drawn by LaMa: the last one kept. A picture with
        see-through parts comes with them as a fourth channel, carried onto the canvas as Save
        carries them."""
        key = (str(picture.path).casefold(), version, canvas, also)
        with self._extending:
            with self._lock:
                if self._extended is not None and self._extended[0] == key:
                    return self._extended[1]
            shown = image if image is not None else self.picture(picture, version)
            colours, clear = split_alpha(shown)
            pixels, kept, at = extended(colours, canvas, fill())
            if clear is not None:
                spread = _extended_alpha(clear, pixels.shape[1], pixels.shape[0], at)
                pixels = np.dstack([pixels, spread])
            made = (pixels, kept, at)
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
    seed: int = 0,
    editor: Editor | None = None,
    key: str = "",
    keep: bool = True,
) -> Image.Image:
    """The picture made to its plan, from the picture decoded at full size and upright: its
    edits (by `editor`, `key` naming the picture and its version, keeping their masks unless
    it's a batch's picture, made once), its size, then its look and touches at that size (`seed`
    grows them), only on a part when the look says so. Its colour profile comes with it. Raises
    StoppedError when stopped, ModelError when a model can't run, EditingError for edits Mado
    can't make."""
    edits = made.editing.edits if made.editing else ()
    parts = made.styling.parts if made.styling else ()
    if (edits or parts) and editor is None:
        raise EditingError("Mado can't make edits here.")
    edited = image
    if edits and editor is not None:
        report("editing", 0.0)
        edited = editor.state(
            image,
            key,
            edits,
            stop=stop,
            report=lambda done: report("editing", done / len(edits)),
            keep=keep,
        )
    sized = edited if made.method == "keep" else _sized(edited, made, ai, report, stop, timer)
    if made.styling is None:
        return sized
    report("looking", 0.0)
    looked = styled(sized, made.styling, seed=seed, stop=stop)
    if parts and editor is not None:
        mask = editor.look_mask(image, key, edits, parts, keep=keep)
        looked = only_on(looked, sized, placed(mask, made, looked.size))
    report("looking", 1.0)
    return looked


def placed(mask: npt.NDArray[np.uint8], made: Plan, size: tuple[int, int]) -> Image.Image:
    """A mask at the picture's own size, placed as the size step places the picture (cropped, or
    on its extended canvas, where what's at the picture's edge carries on), `size` big."""
    height, width = mask.shape
    frame = made.frame
    if frame.shape == "extend" and frame.sides != "none":
        left, top, canvas_width, canvas_height = canvas_around(frame.canvas, width, height)
        padded = np.pad(
            mask,
            ((top, canvas_height - top - height), (left, canvas_width - left - width)),
            mode="edge",
        )
        kept = Box(
            frame.canvas.x + left, frame.canvas.y + top, frame.canvas.width, frame.canvas.height
        )
        shown = Image.fromarray(padded, "L")
    else:
        kept = frame.kept
        shown = Image.fromarray(mask, "L")
    box = (kept.x, kept.y, kept.x + kept.width, kept.y + kept.height)
    return shown.resize(size, Image.Resampling.BILINEAR, box=box)


def only_on(looked: Image.Image, plain: Image.Image, mask: Image.Image) -> Image.Image:
    """A look only where the mask says, the picture as it was elsewhere."""
    profile = looked.info.get("icc_profile")
    joined = Image.composite(looked, plain.convert(looked.mode), mask)
    if isinstance(profile, bytes):
        joined.info["icc_profile"] = profile
    return joined


def _sized(
    image: Image.Image,
    made: Plan,
    ai: Ai,
    report: Report,
    stop: Callable[[], bool],
    timer: Timer | None,
) -> Image.Image:
    """The picture cropped or extended, and made the size its plan says."""
    profile = image.info.get("icc_profile")
    grey = image.mode in ("L", "I", "I;16", "1", "F")
    pixels, alpha = split_alpha(image)
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
        case "shrink" | "keep":
            out = smaller(pixels, kept, target)
    result = Image.fromarray(out)
    if alpha is not None:
        result.putalpha(Image.fromarray(resize_alpha(alpha, kept, target)))
    elif grey:
        result = result.convert("L")
    if isinstance(profile, bytes):
        result.info["icc_profile"] = profile
    return result


def write(
    result: Image.Image,
    picture: Picture,
    size: tuple[int, int],
    saving: Saving,
    path: Path,
    *,
    dpi: int | None,
    reader: Reader | None = None,
) -> int:
    """Writes a picture made to `path` as Save would (its format and quality, and what's kept of
    its original: a camera RAW's by `reader`), checks it, and says how many bytes it came to.
    Raises encode.SaveError."""
    profile = result.info.get("icc_profile")
    kept_profile = profile if isinstance(profile, bytes) else None
    image = result
    if kept_profile is not None and not saving.keep_colours:
        image, kept_profile = encode.in_srgb(result, kept_profile), None
    exif = encode.prepared_exif(
        read_exif(picture.path, picture.kind, reader),
        keep_camera=saving.keep_camera,
        keep_location=saving.keep_location,
        size=size,
        dpi=dpi,
    )
    encode.save(
        image, path, saving.format, saving.quality, exif=exif, profile=kept_profile, dpi=dpi
    )
    encode.check(path, size)
    return path.stat().st_size


def into(saving: Saving, original: Path) -> Path:
    """The folder a picture made is saved in: beside its original (or in its place), a folder by
    name beside it ("Edited"), or a folder of its own."""
    if saving.how == "replace" or saving.folder is None:
        return original.parent
    return saving.folder if saving.folder.is_absolute() else original.parent / saving.folder


def keep(
    written: Callable[[Path], int],
    picture: Picture,
    naming: Naming,
    saving: Saving,
    *,
    conn: sqlite3.Connection,
    quarantine: Quarantine,
    now: datetime,
    job_id: int | None,
    writing: Callable[[Path], None] = lambda _path: None,
) -> Saved:
    """Saves a picture made: as a new picture named after what it was made for and with, or in
    its original's place. `written` writes it to the file it's given and says how big it came
    out (`write`, or a copy of one See it first made); `writing` hears that file first, so a job
    cut short knows what to clear away. History's line is written before any picture moves, so a
    job cut short while saving can be finished or taken back from it (mado/jobs.py). Raises
    SavingError (FullError when the drive filled up)."""
    label = naming.named
    extension = EXTENSIONS[saving.format]
    original = picture.path
    folder = into(saving, original)
    if saving.how == "new":
        name = new_name(original.stem, label, extension, lambda each: (folder / each).exists())
        target = folder / name
    else:
        name = replacement_name(original.name, extension)
        target = folder / name
        if target != original and target.exists():  # another picture has that name
            name = aside_name(name, lambda each: (folder / each).exists())
            target = folder / name
    partial = target.with_name(target.name + PARTIAL)
    writing(partial)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        size = written(partial)
    except encode.SaveError as error:
        partial.unlink(missing_ok=True)
        if error.full:
            raise FullError(folder) from None
        raise SavingError(str(error)) from None
    except OSError as error:
        partial.unlink(missing_ok=True)
        if encode.full(error):
            raise FullError(folder) from None
        raise SavingError(_unsaved(folder, error)) from None
    with history.MOVES:  # an undo waits till the picture is in place
        if saving.how == "new":
            entry = history.made(
                conn,
                now=now,
                job_id=job_id,
                name=original.name,
                made_for=naming.made_for,
                look=naming.look,
                original=original,
                result=target,
                edit=naming.edit,
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
            return Saved(target, entry, size)
        aside = quarantine.place(original, now)
        entry = history.replaced(
            conn,
            now=now,
            job_id=job_id,
            name=original.name,
            made_for=naming.made_for,
            look=naming.look,
            original=original,
            result=target,
            aside=aside,
            edit=naming.edit,
        )
        _replacing(
            partial, target, original, aside, quarantine, now, lambda: history.forget(conn, entry)
        )
        return Saved(target, entry, size)


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
        if isinstance(error, InUseMoveError):
            raise InUseSavingError(str(error)) from None
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


def split_alpha(image: Image.Image) -> tuple[Pixels, npt.NDArray[np.uint8] | None]:
    """A picture's colours, with what its see-through parts hide carried in from what shows (so
    making it bigger brings in no dark fringe), and its see-through parts apart: None for a solid
    picture."""
    if image.mode in ("P", "PA", "La", "RGBa") or "transparency" in image.info:
        image = image.convert("RGBA")  # see-through parts as a channel of their own
    pixels: Pixels = np.asarray(image.convert("RGB"))
    if "A" not in image.getbands():
        return pixels, None
    alpha = np.asarray(image.getchannel("A"))
    return bled(pixels, alpha), alpha


def _extended_alpha(
    seen: npt.NDArray[np.uint8], width: int, height: int, at: tuple[int, int]
) -> npt.NDArray[np.uint8]:
    """See-through parts on an extended canvas, the picture's at `at`: what's drawn new is as
    see-through as the picture's edge beside it (a sticker's nothing stays nothing, a solid
    picture's new edges are solid)."""
    left, top = at
    right, bottom = width - left - seen.shape[1], height - top - seen.shape[0]
    return np.pad(seen, ((top, bottom), (left, right)), mode="edge")


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


def recipe_from(
    data: dict[str, object], screens: list[Screen], looks: Callable[[str], Look | None]
) -> Recipe:
    """A recipe as a job keeps it (JSON: its edit step, its size step and its look step, any of
    them none), the owner's screens naming theirs and `looks` finding a look by its id. A job
    Mado 0.1 kept is its size step alone, flat. Raises SizeError for a size Mado can't make,
    MissingLookError for a look that isn't there any more, EditError for edits it can't make."""
    if isinstance(data.get("size"), str):  # Mado 0.1's: the size step's fields, flat
        return Recipe(sizing=_sizing_from(data, screens))
    size, look = data.get("size"), data.get("look")
    sizing = (
        _sizing_from(cast("dict[str, object]", size), screens) if isinstance(size, dict) else None
    )
    styling: Styling | None = None
    if isinstance(look, dict):
        asked = cast("dict[str, object]", look)
        found = looks(str(asked.get("look", "")))
        if found is None:
            raise MissingLookError
        strength, amounts = asked.get("strength"), asked.get("touches")
        styling = Styling(
            look=found,
            strength=min(max(float(strength), 0.0), 1.0)
            if isinstance(strength, int | float)
            else 1.0,
            touches=named(cast("dict[str, int]", amounts) if isinstance(amounts, dict) else {}),
            parts=parts_from(asked.get("parts")),
        )
    return Recipe(sizing=sizing, styling=styling, editing=editing_from(data.get("edit")))


def _sizing_from(data: dict[str, object], screens: list[Screen]) -> Sizing:
    """The size step as a job keeps it."""
    focus = data.get("focus")
    point: tuple[float, float] | None = None
    if isinstance(focus, list):
        values = cast("list[object]", focus)
        if len(values) == 2 and all(isinstance(each, int | float) for each in values):
            point = (float(cast("float", values[0])), float(cast("float", values[1])))
    kind, quality = data.get("kind"), data.get("quality")
    return Sizing(
        size=resolve(str(data.get("size", "")), screens),
        shape="extend" if data.get("shape") == "extend" else "crop",
        focus=point,
        kind=kind if kind in ("photo", "drawing", "pixels", "screenshot") else None,
        quality=quality if quality in ("fast", "best") else None,
        clean=data.get("clean") is not False,
    )


def dpi_of(recipe: Recipe) -> int | None:
    """The dots to the inch a picture made to `recipe` says: a print's 300."""
    return DPI if recipe.sizing is not None and recipe.sizing.size.purpose == "print" else None


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


def estimated(made: Plan, here: Here, cut_on: Place | None = None) -> float:
    """How long making a plan takes here, in seconds. `cut_on`: where cutting out a subject at
    its best runs (on the processor, unless the card has a great deal of room)."""
    pixels = made.width * made.height
    canvas = made.frame.canvas
    seconds = _edit_seconds(made, here.place, cut_on or "processor")
    if made.styling is not None:
        drawn = made.styling.touches.spatial()
        seconds += pixels / 1e6 * (_LOOK_SECONDS + (_TOUCHES_SECONDS if drawn else 0.0))
        if made.styling.parts:
            seconds += _EDIT_SECONDS["mask"] * pixels / 1e6
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


def _edit_seconds(made: Plan, place: Place, cut_on: Place) -> float:
    """About how long a plan's edits take, at the picture's own size."""
    if made.editing is None:
        return 0.0
    megapixels = made.frame.kept.width * made.frame.kept.height / 1e6
    seconds = 0.0
    for edit in made.editing.edits:
        seconds += _EDIT_SECONDS["mask"] * megapixels
        match edit:
            case Erase(parts=parts, quality=quality):
                seconds += (_READ_SECONDS[place] if parts else 0.0) + _ERASE_SECONDS[
                    (quality, place)
                ]
            case CutOut():
                seconds += _READ_SECONDS[place]
            case Blur():
                seconds += _READ_SECONDS[place] + _EDIT_SECONDS["blur"] * megapixels
            case Subject(quality=quality):
                seconds += _CUT_SECONDS[cut_on] if quality == "best" else _CUT_SECONDS["fast"]
    return seconds


# What the edits take on the owner's PC (docs/stack/editing.md): SAM reading a picture, each
# erase's model (Fast, Best) and cutting out a subject (Fast on the processor, Best where it
# runs), and per megapixel, making a mask the picture's size and blurring behind a part.
_READ_SECONDS: dict[Place, float] = {"card": 0.4, "processor": 1.8}
_ERASE_SECONDS: dict[tuple[str, Place], float] = {
    ("fast", "card"): 0.15,
    ("fast", "processor"): 1.2,
    ("best", "card"): 0.45,
    ("best", "processor"): 3.2,
}
_CUT_SECONDS: dict[str, float] = {"fast": 0.3, "card": 3.0, "processor": 9.5}
_EDIT_SECONDS = {"mask": 0.1, "blur": 0.05}


def waiting_for(made: Plan, ai: Ai) -> list[str]:
    """The downloads a plan waits for: the Best photo model, LaMa to extend edges or erase at its
    best, and the editing models its edits and its look's part use."""
    found: list[str] = []
    if made.model is not None and made.model.download and ai.file(made.model) is None:
        found.append(made.model.download)
    edits = models_for(made.editing, cut_quality=cut_quality(ai))
    if made.styling is not None and made.styling.parts:
        edits.add("select")
    extending = made.frame.shape == "extend" and made.frame.sides != "none"
    if (extending or "erase-best" in edits) and ai.lama_file() is None:
        found.append(LAMA)
    wanted = {
        "select": (SAM, "vision_encoder.onnx"),
        "erase-fast": (MIGAN, "migan-pipeline-v2.onnx"),
    }
    wanted["cut-best"] = (BIREFNET, "birefnet-lite.onnx")
    for need, (download, file) in wanted.items():
        if need in edits and ai.edit_file(download, file) is None:
            found.append(download)
    return found


_LAMA_SECONDS: dict[Place, float] = {"card": 0.35, "processor": 3.0}  # a square drawn
# Seconds a megapixel takes through a look's table, and for its touches drawn across it: the
# owner's i5-9600K (docs/stack/looks.md).
_LOOK_SECONDS = 0.02
_TOUCHES_SECONDS = 0.1


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
        kept: Path | None = None,
        editor: Editor | None = None,
        reader: Reader | None = None,
    ) -> None:
        """`kept`: where See it first's pictures wait for their jobs; one is let go once its
        job has saved it. `editor` makes a recipe's edits (and a look's part); `reader` reads
        camera RAW."""
        self._ai = ai
        self._quarantine = quarantine
        self._ffmpeg = ffmpeg
        self._reader = reader
        self._now = now
        self._kept = kept
        self._editor = editor

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
            recipe = recipe_from(
                order["recipe"], screens_kept(conn), lambda look: own_looks.resolve(conn, look)
            )
        except (SizeError, MissingLookError, EditError) as error:
            raise JobError(str(error)) from None
        saving = saving_from(order["saving"])
        picture = picture_of(conn, row["picture_id"], Path(row["source"]))
        if saving.how == "replace" and picture.kind == "raw":
            raise JobError(NO_RAW_REPLACE)  # Mado can't write RAW: never one put in its place
        job_id: int = row["id"]
        seen_first = _seen_first(order.get("made"), picture)
        if seen_first is not None:  # See it first made this one already, just as it's asked for
            sample, naming = seen_first
            report("saving", 0.0)
            saved = self._keep(
                lambda partial: _copied(sample, partial, (naming.width, naming.height)),
                picture,
                naming,
                saving,
                conn=conn,
                job_id=job_id,
            )
            self._let_go(sample)
            report("saving", 1.0)
            return saved.path
        report("reading", 0.0)
        if saving.how == "replace" and not movable(picture.path):
            raise HeldError(picture.path.name, "replace")  # asked first: not made for nothing
        try:
            image = decode(
                picture.path,
                picture.kind,
                longest=None,
                ffmpeg=self._ffmpeg(),
                reader=self._reader,
            )
        except InUseError:  # waits, and is tried again by itself
            raise HeldError(picture.path.name, "read") from None
        except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
            raise _drive_gone(picture.path) or JobError(str(error)) from None
        now_version = _file_version(picture.path)
        edited_on = recipe.editing.version if recipe.editing else None
        if edited_on is not None and edited_on != now_version:
            raise JobError(_CHANGED.format(name=picture.path.name))
        here = self._ai.where()
        made = planned(recipe, see(image, picture), self._ai.starts_on(here))
        if made.empty and not order.get("as_is"):  # a paste saved as it is is something to save
            raise JobError(
                "There was nothing to make: no size, and no look that changes it. Nothing was "
                "saved, and the original is as it was."
            )
        if waiting_for(made, self._ai):
            raise JobError(
                "It needs a model Mado downloads the first time it's asked for. Download it on "
                "the tab that asked for it, then save again."
            )
        if made.see_through and saving.format not in ("PNG", "WebP"):
            saving = replace(saving, format="PNG", quality=None)  # a cut-out keeps its nothing
        expect(estimated(made, here, self._ai.edit_place(BIREFNET)))
        timer = Timer()
        if stop():  # cancelled while it was read: a way without a model never asks again
            raise StoppedError
        try:
            result = make(
                image,
                made,
                self._ai,
                report=report,
                stop=stop,
                timer=timer,
                seed=seed_of(picture.path),
                editor=self._editor,
                key=picture_key(picture.path, now_version or ""),
                keep=edited_on is not None,  # a batch's picture is made once: nothing kept
            )
        except ModelError as error:
            raise JobError(f"{error} Nothing was saved; the original is as it was.") from None
        except EditingError as error:
            raise JobError(str(error)) from None
        if stop():  # cancelled as its last tile was made
            raise StoppedError
        report("saving", 0.0)  # past cancelling from here: a picture half moved helps no one
        dpi = dpi_of(recipe)
        saved = self._keep(
            lambda partial: write(
                result,
                picture,
                (made.width, made.height),
                saving,
                partial,
                dpi=dpi,
                reader=self._reader,
            ),
            picture,
            Naming.of(made),
            saving,
            conn=conn,
            job_id=job_id,
        )
        pace = timer.per_megapixel
        if made.model is not None and pace is not None:
            hardware.learn(conn, made.model.id, here.place, pace, self._now())
        report("saving", 1.0)
        return saved.path

    def _let_go(self, sample: Path) -> None:
        """See it first's picture, saved: it goes, when it's one Mado keeps for its jobs."""
        if self._kept is None or sample.parent != self._kept:
            return
        try:
            sample.unlink(missing_ok=True)
        except OSError as error:
            log.warning("Mado couldn't let go of %s: %s", sample, error)

    def _keep(
        self,
        written: Callable[[Path], int],
        picture: Picture,
        naming: Naming,
        saving: Saving,
        *,
        conn: sqlite3.Connection,
        job_id: int,
    ) -> Saved:
        """Saves a job's picture: a drive that filled up is the queue's to wait for room on."""
        try:
            return keep(
                written,
                picture,
                naming,
                saving,
                conn=conn,
                quarantine=self._quarantine,
                now=self._now(),
                job_id=job_id,
                writing=lambda partial: note_writing(conn, job_id, partial),
            )
        except FullError as error:
            raise NoRoomError(error.drive, str(error)) from None
        except InUseSavingError:  # waits, and is tried again by itself
            raise HeldError(picture.path.name, "replace") from None
        except SavingError as error:
            gone = _drive_gone(picture.path, into(saving, picture.path))
            if gone is not None and history.for_job(conn, job_id) is None:  # nothing moved
                raise gone from None
            raise JobError(str(error)) from None


_CHANGED = (
    "{name} changed since you edited it, so the parts you picked may not be where they were. "
    "Nothing was saved, and the picture is as it is now. Open it and edit it again."
)
NO_RAW_REPLACE = (
    "Mado can't write camera RAW, so it saves a new picture beside it: the RAW stays exactly as "
    "it is."
)


def _file_version(path: Path) -> str | None:
    """A picture's version as its file is now (mado/previews.py names its copies by it)."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return f"{stat.st_mtime_ns:x}-{stat.st_size:x}"


def _drive_gone(*paths: Path) -> DriveGoneError | None:
    """The drive of the first of these paths that isn't connected any more: a batch's picture
    waits in line for it rather than failing."""
    for path in paths:
        if not drive_there(path):
            return DriveGoneError(drive_of(path))
    return None


def _seen_first(found: object, picture: Picture) -> tuple[Path, Naming] | None:
    """A picture See it first made for this job, as it's asked for now, when it's still there
    and its original hasn't changed since: what it was written to, and what it's called."""
    if not isinstance(found, dict):
        return None
    made = cast("dict[str, object]", found)
    source = made.get("source")
    if not isinstance(source, str) or source.casefold() != str(picture.path).casefold():
        return None  # made from another picture: this one's made afresh
    path, version_ = made.get("path"), made.get("version")
    width, height, named = made.get("width"), made.get("height"), made.get("named")
    if not (
        isinstance(path, str)
        and isinstance(version_, str)
        and isinstance(width, int)
        and isinstance(height, int)
        and isinstance(named, str)
    ):
        return None
    try:
        stat = picture.path.stat()
    except OSError:
        return None
    if f"{stat.st_mtime_ns:x}-{stat.st_size:x}" != version_ or not Path(path).is_file():
        return None
    made_for, look, edit = made.get("madeFor"), made.get("look"), made.get("edit")
    return Path(path), Naming(
        width,
        height,
        named,
        made_for if isinstance(made_for, str) else None,
        look if isinstance(look, str) else None,
        edit if isinstance(edit, str) else None,
    )


def _copied(sample: Path, partial: Path, size: tuple[int, int]) -> int:
    """A picture See it first made, copied to where a job writes its picture, and checked."""
    shutil.copyfile(sample, partial)
    encode.check(partial, size)
    return partial.stat().st_size


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
