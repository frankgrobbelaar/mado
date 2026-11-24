"""Many at once: the pictures a batch is made of (ticked in the library, a folder, what a search
found, or files and folders dropped on the window or picked), what it takes (time, space and the
room on the drive, by this PC's speeds and what See it first found), and putting it in the
queue (mado/jobs.py), a picture's job each. Pictures outside the library are made as well as
those in it: a job takes its file's path. docs/stack/queue.md has how batches run.
"""

import json
import logging
import os
import shutil
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Literal, cast

from mado import own_looks, own_styles
from mado.ai import BIREFNET, COLOURER, DETECTOR, Ai
from mado.core.batch import (
    KEPT_SECONDS,
    SPACE_HELD,
    Starts,
    StepError,
    calibrated,
    cutout_detail,
    fits,
    folder_words,
    look_chip,
    paint_detail,
    recipe_of,
    saving_chip,
    size_chip,
    size_detail,
    steps_in_order,
)
from mado.core.depth import DepthError, depthing_from
from mado.core.depth import detail as depth_detail
from mado.core.depth import phrase as depth_phrase
from mado.core.edits import phrase as edit_phrase
from mado.core.estimate import key
from mado.core.files import kind_of, skipped_folder
from mado.core.fixes import BLOCKY, FixError, fixing_from
from mado.core.fixes import detail as fix_detail
from mado.core.fixes import phrase as fix_phrase
from mado.core.looks import phrase
from mado.core.naming import EXTENSIONS, QUARANTINE
from mado.core.painting import Painting
from mado.core.quality import Format, about_bytes
from mado.core.recipe import Plan, Recipe, Styling, plan, said_with
from mado.core.restore import RestoreError, Restoring, restoring_from
from mado.core.restore import detail as restore_detail
from mado.core.restore import phrase as restore_phrase
from mado.core.sizes import Purpose, SizeError
from mado.core.touches import named as named_touches
from mado.core.touches import words as touch_words
from mado.jobs import Jobs, NewBatch, destination
from mado.libraw import Reader
from mado.making import (
    MissingLookError,
    MissingStyleError,
    estimated,
    recipe_from,
    screens_kept,
    waiting_for,
)
from mado.pictures import NeedsReaderError, PictureGoneError, UnreadableError, read_facts
from mado.previews import version

log = logging.getLogger(__name__)

type How = Literal[
    "ticked", "folder", "search", "favourites", "dropped", "picked", "pasted", "opened"
]

MOST = 10_000  # pictures a batch holds at most
_WALKED = 50_000  # files looked at in folders dropped, at most
_FOCUS = (0.5, 0.5)  # where a picture's subject is reckoned to be, for what it takes
_JPEGS = (".jpg", ".jpeg", ".jpe", ".jfif")  # a JPEG's names, for what its fixes take


class BatchError(ValueError):
    """A batch that can't be made as asked, with a sentence saying why."""


@dataclass(frozen=True)
class Picture:
    """One of a batch's pictures."""

    id: int | None  # in the library; None for one outside it
    path: Path
    name: str
    size: int  # bytes
    width: int
    height: int
    version: str


@dataclass(frozen=True)
class Picked:
    pictures: list[Picture]
    source: str  # where they're from: "Holiday"
    shared: str | None  # the folder they share, when they do
    words: str  # "ticked in Holiday", "in Holiday", "found by “beach”", "from Desktop"
    left_out: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])


@dataclass(frozen=True)
class Takes:
    """What a batch takes."""

    seconds: float
    bytes: int
    each: list[tuple[float, int]]  # each picture's seconds and bytes, reckoned
    free: int | None  # bytes free where most of them are saved
    drive: str | None  # that drive: "D:"
    fits: bool
    measured: bool  # the times are this PC's own, not a guess
    reckoned: bool  # moved by what See it first found
    needs: list[str]  # downloads it waits for
    plan: Plan  # the first picture's, for the words


def from_ids(conn: sqlite3.Connection, ids: Sequence[int]) -> Picked:
    """Pictures ticked in the library, in the order they were ticked from."""
    rows = _rows(conn, "p.id IN (SELECT value FROM json_each(?))", [json.dumps(list(ids))])
    order = {picture_id: at for at, picture_id in enumerate(ids)}
    rows.sort(key=lambda row: order.get(row["id"], len(order)))
    return _picked(rows, "ticked", None)


def from_folder(conn: sqlite3.Connection, folder_id: int, inside: str) -> Picked:
    """Every picture in a library folder (or a folder inside it), newest first."""
    clause, values = _in_folder(folder_id, inside)
    rows = _rows(conn, clause, values)
    return _picked(rows, "folder", _folder_name(conn, folder_id, inside))


def from_search(
    conn: sqlite3.Connection,
    folder_id: int | None,
    inside: str,
    words: str,
    found_ids: Sequence[int],
) -> Picked:
    """What a Library search found (`found_ids`, in the order its results show them: by the words
    in a picture, what it shows and its name), in a folder or anywhere; or, with no words, the
    pictures More like this found."""
    rows = _rows(conn, "p.id IN (SELECT value FROM json_each(?))", [json.dumps(list(found_ids))])
    order = {picture_id: at for at, picture_id in enumerate(found_ids)}
    rows.sort(key=lambda row: order.get(row["id"], len(order)))
    where = _folder_name(conn, folder_id, inside) if folder_id is not None else None
    if words.strip():
        found = f"found by “{words.strip()}”" + (f" in {where}" if where else "")
    else:
        found = "like the picture you chose"
    picked = _picked(rows, "search", where)
    return Picked(picked.pictures, picked.source, picked.shared, found, picked.left_out)


def from_favourites(
    conn: sqlite3.Connection, words: str = "", found_ids: Sequence[int] | None = None
) -> Picked:
    """The owner's favourites, in the library or from outside it, newest first; with `words`,
    those a search of them found (`found_ids`, in the order its results show them)."""
    clause = "p.id IN (SELECT picture_id FROM favourites)"
    values: list[object] = []
    if found_ids is not None:
        clause += " AND p.id IN (SELECT value FROM json_each(?))"
        values.append(json.dumps(list(found_ids)))
    rows = conn.execute(
        f"""SELECT p.id, p.path, p.name, p.size, p.width, p.height, p.modified, p.raw,
                   p.problem, p.read_at, p.dir, p.folder_id
            FROM pictures AS p WHERE p.gone_at IS NULL AND {clause}
            ORDER BY p.taken_at DESC, p.id DESC""",  # noqa: S608 - built of fixed pieces
        values,
    ).fetchall()
    if found_ids is not None:
        order = {picture_id: at for at, picture_id in enumerate(found_ids)}
        rows.sort(key=lambda row: order.get(row["id"], len(order)))
    pictures: list[Picture] = []
    left: list[tuple[str, str]] = []
    for row in rows:
        found = _from_row(row)
        if found is None:
            left.append((row["name"], _why(row)))
        elif row["folder_id"] is None:  # from outside the library: known by its path alone
            pictures.append(replace(found, id=None))
        else:
            pictures.append(found)
    shared = _shared([picture.path for picture in pictures])
    said = f"found by “{words.strip()}” in your favourites" if words.strip() else "your favourites"
    return Picked(_most(pictures, left), "Favourites", str(shared) if shared else None, said, left)


def from_paths(
    conn: sqlite3.Connection, paths: Sequence[str], how: How, reader: Reader | None = None
) -> Picked:
    """Files and folders dropped on the window, picked, pasted or opened from File Explorer:
    every picture in them, those in the library as it knows them, any other read now (a camera
    RAW by `reader`). A folder's own folders are looked in too, but never a quarantine."""
    files: list[Path] = []
    left: list[tuple[str, str]] = []
    for each in paths:
        path = Path(each)
        if path.is_dir():
            walked, cut = _walked(path)
            files.extend(walked)
            if cut:
                left.append(
                    (
                        f"The rest of {_name_of(path)}",
                        f"Mado looks through {_WALKED:,} files at most in a folder dropped or "
                        "picked: drop the folders inside it one at a time.",
                    )
                )
        elif path.is_file():
            files.append(path)
        else:
            left.append((path.name or each, "It isn't there any more."))
    known = _known(conn, files)
    pictures: list[Picture] = []
    for path in dict.fromkeys(files):
        kind = kind_of(path.name)
        if kind is None:
            left.append((path.name, "It isn't a picture Mado makes."))
            continue
        row = known.get(str(path).casefold())
        if row is not None:
            found = _from_row(row)
            if found is None:
                left.append((path.name, _why(row)))
            else:
                pictures.append(found)
            continue
        try:
            facts = read_facts(path, kind, reader)
            stat = path.stat()
        except NeedsReaderError:
            left.append((path.name, WAITS_FOR_READER))
            continue
        except (UnreadableError, PictureGoneError, OSError) as error:
            left.append((path.name, str(error)))
            continue
        pictures.append(
            Picture(
                None,
                path,
                path.name,
                stat.st_size,
                facts.width,
                facts.height,
                version(stat.st_mtime_ns, stat.st_size),
            )
        )
    shared = _shared([picture.path for picture in pictures])
    source = _name_of(shared) if shared else "several folders"
    words = f"{how if how in ('dropped', 'pasted', 'opened') else 'picked'} from {source}"
    return Picked(_most(pictures, left), source, str(shared) if shared else None, words, left)


def kept_key(path: Path) -> str:
    """How a picture's file is known among See it first's: its path, whatever its case."""
    return str(path).casefold()


def takes(
    conn: sqlite3.Connection,
    pictures: Sequence[Picture],
    recipe: Recipe,
    saving: dict[str, object],
    ai: Ai,
    found: Sequence[tuple[str, float, float, int, int]] = (),
) -> Takes:
    """What a batch takes: each picture's time and size made as its steps say, by this PC's
    speeds (and what's free where they're saved), moved by how See it first's went against
    their guesses (`found`: each one's file, guessed and measured seconds, then bytes). See it
    first's own pictures are kept rather than made again: moments each."""
    if not pictures:
        raise BatchError("There are no pictures to make.")
    here = ai.where()
    starts = ai.starts_on(here)
    fix_starts = ai.fix_starts_on()
    cut_on = ai.edit_place(BIREFNET)
    format_ = saving.get("format")
    quality = saving.get("quality")
    chosen: Format = cast("Format", format_) if format_ in EXTENSIONS else "JPEG"
    level = quality if isinstance(quality, int) else None
    each: list[tuple[float, int]] = []
    first: Plan | None = None
    # Its style paints in the same place for every picture, as the depth model reads.
    paint_on = ai.painter.place(recipe.painting.style) if recipe.painting else None
    depth_on = ai.depth_place() if recipe.depthing else None
    restore_on = (ai.restore_place(DETECTOR), ai.restore_place(COLOURER))
    # Restoring each picture as it needs (coloured, or its colours back) isn't known till each is
    # read: reckoned as if each needs all it asks, and waiting for all of their models.
    asked = recipe
    if recipe.restoring is not None and recipe.restoring.each:
        asked = replace(recipe, restoring=replace(recipe.restoring, each=False))
    for picture in pictures:
        made = plan(
            asked,
            picture.width,
            picture.height,
            guessed_kind="photo",
            found_focus=_FOCUS,
            starts_on=starts,
            fix_starts_on=fix_starts,
            # A JPEG's blocks take as long however hard they come out: any quality will do here.
            jpeg_saved_at=BLOCKY if picture.path.suffix.casefold() in _JPEGS else None,
        )
        first = first or made
        bytes_ = about_bytes(chosen, level, "photo", made.width * made.height)
        seconds = estimated(
            made, here, cut_on, paint_on=paint_on, depth_on=depth_on, restore_on=restore_on
        )
        each.append((seconds, bytes_))
    assert first is not None  # noqa: S101 - there's a picture
    times = [(guess, took) for _at, guess, took, _b, _m in found]
    sizes = [(float(guessed), float(made)) for _at, _g, _t, guessed, made in found]
    ratio_s = calibrated([1.0], times)
    ratio_b = calibrated([1.0], sizes, held=SPACE_HELD)
    reckoned = [(s * ratio_s, round(b * ratio_b)) for s, b in each]
    places = {kept_key(each.path): at for at, each in enumerate(pictures)}
    for source, _guess, _took, _guessed, made in found:
        at = places.get(kept_key(Path(source)))
        if at is not None:  # made already, as it's asked for: kept, not made again
            reckoned[at] = (KEPT_SECONDS, made)
    seconds = sum(s for s, _ in reckoned)
    size = sum(b for _, b in reckoned)
    drive, free = _room(pictures, saving)
    measured = first.model is None or key(first.model.id, here.place) in here.speeds
    return Takes(
        seconds=seconds,
        bytes=size,
        each=reckoned,
        free=free,
        drive=drive,
        fits=free is None or fits(size, free),
        measured=measured,
        reckoned=bool(found),
        needs=waiting_for(first, ai),
        plan=first,
    )


def recipe_from_steps(conn: sqlite3.Connection, steps: Sequence[dict[str, object]]) -> Recipe:
    """The recipe a batch's steps make. Raises BatchError for steps Mado can't make."""
    try:
        return recipe_from(
            recipe_of(steps),
            screens_kept(conn),
            lambda look: own_looks.resolve(conn, look),
            lambda asked: own_styles.resolve(conn, asked),
        )
    except (
        StepError,
        SizeError,
        MissingLookError,
        MissingStyleError,
        FixError,
        DepthError,
        RestoreError,
    ) as error:
        raise BatchError(str(error)) from None


def put_in(
    conn: sqlite3.Connection,
    jobs: Jobs,
    ai: Ai,
    *,
    name: str,
    source: str,
    shared: str | None,
    pictures: Sequence[Picture],
    steps: Sequence[dict[str, object]],
    saving: dict[str, object],
    starts: Starts,
    now: datetime,
    recipe_id: int | None = None,
    watch_id: int | None = None,
    found: Sequence[tuple[str, float, float, int, int]] = (),
    made: dict[str, dict[str, object]] | None = None,
    seen_first: bool = False,
) -> int:
    """Puts a batch in the queue, a picture's job each, and says its number. `made`: what See it
    first made already, by each picture's file (`kept_key`), to be kept rather than made again.
    Raises BatchError."""
    if len(pictures) > MOST:
        raise BatchError(f"That's more than {MOST:,} pictures: make them in a few batches.")
    ordered = steps_in_order(steps)
    orders = _orders(conn, ai, pictures, ordered, saving, found, made or {})
    batch_id = jobs.add_batch(
        conn,
        NewBatch(
            name=name,
            source=source,
            shared=shared,
            steps={"steps": list(ordered), "saving": saving},
            starts=starts,
            recipe_id=recipe_id,
            watch_id=watch_id,
            seen_first=seen_first,
        ),
        orders,
    )
    if recipe_id is not None:
        with conn:
            conn.execute(
                "UPDATE recipes SET used = used + 1, used_at = ? WHERE id = ?",
                (now.isoformat(timespec="seconds"), recipe_id),
            )
    return batch_id


def join(
    conn: sqlite3.Connection,
    jobs: Jobs,
    ai: Ai,
    batch_id: int,
    pictures: Sequence[Picture],
) -> None:
    """More pictures for a batch not yet done, made as it says (a watch folder's)."""
    row = conn.execute("SELECT steps FROM batches WHERE id = ?", (batch_id,)).fetchone()
    steps, saving = kept_steps(row["steps"] if row else "{}")
    jobs.join(conn, batch_id, _orders(conn, ai, pictures, steps, saving, (), {}))


def order_of(text: str) -> dict[str, object]:
    """A job's order as the jobs table keeps it (JSON): what to make and how to save it."""
    try:
        found: object = json.loads(text)
    except ValueError:
        return {}
    return cast("dict[str, object]", found) if isinstance(found, dict) else {}


def first_order(conn: sqlite3.Connection, batch_id: int) -> dict[str, object]:
    """A batch's first picture's order, which says what all of them are made for and with."""
    row = conn.execute(
        "SELECT recipe FROM jobs WHERE batch_id = ? ORDER BY position LIMIT 1", (batch_id,)
    ).fetchone()
    return order_of(row["recipe"]) if row else {}


def kept_steps(text: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """A batch's steps and how it saves, as the batches table keeps them (JSON)."""
    try:
        kept: object = json.loads(text)
    except ValueError:
        kept = {}
    found = cast("dict[str, object]", kept) if isinstance(kept, dict) else {}
    steps, saving = found.get("steps"), found.get("saving")
    return (
        [
            cast("dict[str, object]", each)
            for each in (cast("list[object]", steps) if isinstance(steps, list) else [])
            if isinstance(each, dict)
        ],
        cast("dict[str, object]", saving) if isinstance(saving, dict) else {},
    )


def _orders(
    conn: sqlite3.Connection,
    ai: Ai,
    pictures: Sequence[Picture],
    steps: Sequence[dict[str, object]],
    saving: dict[str, object],
    found: Sequence[tuple[str, float, float, int, int]],
    made: dict[str, dict[str, object]],
) -> list[tuple[int | None, Path, int, dict[str, object]]]:
    """Each picture's job: what to make and how to save it, about how long it takes and how big
    it comes out, and what See it first made of it already. Raises BatchError."""
    recipe = recipe_from_steps(conn, steps)
    reckoned = takes(conn, pictures, recipe, saving, ai, found)
    if reckoned.needs:
        raise BatchError(
            "It needs a model Mado downloads the first time it's asked for: download it first."
        )
    words = _made_words(recipe)
    orders: list[tuple[int | None, Path, int, dict[str, object]]] = []
    for picture, (seconds, bytes_) in zip(pictures, reckoned.each, strict=True):
        order: dict[str, object] = {
            "recipe": recipe_of(steps),
            "saving": saving,
            "label": words[0],
            "look": words[1],
            "edit": words[2],
            "fix": words[3],
            "depth": words[4],
            "restore": words[5],
            "seconds": round(seconds, 2),
            "bytes": bytes_,
        }
        kept = made.get(kept_key(picture.path))
        if kept is not None:
            order["made"] = kept
        orders.append((picture.id, picture.path, picture.size, order))
    return orders


def words_for(
    conn: sqlite3.Connection, steps: Sequence[dict[str, object]], saving: dict[str, object]
) -> list[tuple[str, str, str, str, str | None]]:
    """A batch's steps, then its save, as its steps and a recipe's line say them: each one's
    kind, title, detail, chip and amount ("Warm film", "60"). A step this Mado doesn't know is
    said as best it can."""
    found: list[tuple[str, str, str, str, str | None]] = []
    for step in steps_in_order(steps):
        kind = str(step.get("step"))
        if kind == "cutout":
            quality, behind = step.get("quality"), step.get("behind")
            found.append(
                (
                    "cutout",
                    "Cut out the subject",
                    cutout_detail(
                        quality if isinstance(quality, str) else None,
                        behind if isinstance(behind, str) else "nothing",
                    ),
                    "Cut out the subject",
                    None,
                )
            )
        elif kind == "restore":
            asked = {k: v for k, v in step.items() if k != "step"}
            try:
                restoring = restoring_from({**asked, "each": True})
            except RestoreError:
                restoring = None
            if restoring is None:
                found.append(("restore", "Restore", "Restoring Mado can't read", "?", None))
                continue
            found.append(
                ("restore", "Restore", restore_detail(restoring), _restore_chip(restoring), None)
            )
        elif kind == "fix":
            try:
                fixing = fixing_from({k: v for k, v in step.items() if k != "step"})
            except FixError:
                fixing = None
            if fixing is None:
                found.append(("fix", "Fix", "Fixes Mado can't read", "?", None))
                continue
            found.append(
                (
                    "fix",
                    "Fix",
                    fix_detail(fixing, fixing.jpeg_quality),
                    _fix_chip(fixing.on),
                    None,
                )
            )
        elif kind == "depth":
            try:
                depthing = depthing_from({k: v for k, v in step.items() if k != "step"})
            except DepthError:
                depthing = None
            if depthing is None:
                found.append(("depth", "Depth", "Depth tools Mado can't read", "?", None))
                continue
            found.append(("depth", "Depth", depth_detail(depthing), _depth_chip(depthing.on), None))
        elif kind == "size":
            try:
                recipe = recipe_from(
                    {"size": _fields(step), "look": None}, screens_kept(conn), _no_look
                )
            except SizeError, MissingLookError:
                found.append(
                    ("size", "Make it for a screen", "A size Mado doesn't know", "?", None)
                )
                continue
            assert recipe.sizing is not None  # noqa: S101 - asked for
            sizing = recipe.sizing
            found.append(
                (
                    "size",
                    "Make it for a screen",
                    size_detail(sizing.size, sizing.shape, sizing.quality),
                    size_chip(sizing.size),
                    None,
                )
            )
        elif kind == "paint":
            found.append(_paint_words(conn, step))
        elif kind == "look":
            look_id = str(step.get("look", ""))
            look = own_looks.resolve(conn, look_id)
            strength = step.get("strength")
            amount = float(strength) if isinstance(strength, int | float) else 1.0
            if look is None:
                found.append(
                    ("look", "A look", "A look that isn't in your looks any more", "?", None)
                )
                continue
            touches = step.get("touches")
            amounts = cast("dict[str, int]", touches) if isinstance(touches, dict) else {}
            styling = Styling(look, min(max(amount, 0.0), 1.0), named_touches(amounts))
            chip, percent = look_chip(look.name, styling.strength)
            found.append(("look", "A look", _look_detail(styling), chip, percent))
        else:
            found.append(
                (kind, "A step this Mado doesn't know", "Update Mado to make it", kind, None)
            )
    how = "replace" if saving.get("how") == "replace" else "new"
    format_ = str(saving.get("format") or "JPEG")
    quality = saving.get("quality")
    level = quality if isinstance(quality, int) else None
    folder = saving.get("folder")
    folder_ = folder if isinstance(folder, str) and folder else None
    found.append(
        (
            "save",
            "Save",
            _save_detail(how, format_, level, folder_),
            saving_chip(how, format_, level, folder_),
            None,
        )
    )
    return found


def into_words(saving: dict[str, object], shared: str | None) -> str:
    """Where a batch's new pictures go, as Saving says it."""
    if saving.get("how") == "replace":
        return "in place of the originals"
    folder = saving.get("folder")
    return folder_words(folder if isinstance(folder, str) and folder else None, shared)


def folder_of(saving: dict[str, object], shared: str | None) -> str | None:
    """The one folder a batch's new pictures went to, to open: when its pictures share a folder,
    or it saved into one of its own."""
    folder = saving.get("folder")
    if saving.get("how") != "replace" and isinstance(folder, str) and folder:
        if Path(folder).is_absolute():
            return folder
        return str(Path(shared) / folder) if shared else None
    return shared


def purpose_of(conn: sqlite3.Connection, steps: Sequence[dict[str, object]]) -> Purpose | None:
    """What a batch's size step makes its pictures for: "tv"; None without one."""
    for step in steps:
        if step.get("step") == "size":
            try:
                recipe = recipe_from(
                    {"size": _fields(step), "look": None}, screens_kept(conn), _no_look
                )
            except SizeError, MissingLookError:
                return None
            return recipe.sizing.size.purpose if recipe.sizing else None
    return None


def _made_words(
    recipe: Recipe,
) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    """What a batch's pictures are made for and with, what's edited first, what the fixes do,
    the depth tools and restoring, as a job and History say them."""
    made_for = recipe.sizing.size.label if recipe.sizing else None
    look = said_with(recipe.painting, recipe.styling)
    return (
        made_for,
        look,
        edit_phrase(recipe.editing),
        fix_phrase(recipe.fixing),
        depth_phrase(recipe.depthing),
        restore_phrase(recipe.restoring),
    )


def _restore_chip(restoring: Restoring) -> str:
    """Restoring as a recipe's line says it: "Coloured", "Faded colours back", "Restored"."""
    if restoring.colour is not None and restoring.faded is not None:
        return "Coloured or colours back"
    return "Coloured" if restoring.colour is not None else "Faded colours back"


def _depth_chip(on: tuple[str, ...]) -> str:
    """The depth tools as a recipe's line says them: "Portrait blur and fog"."""
    names = {"portrait": "portrait blur", "fog": "fog", "tilt": "tilt-shift"}
    said = [names[kind] for kind in on]
    joined = said[0] if len(said) == 1 else f"{', '.join(said[:-1])} and {said[-1]}"
    return joined[:1].upper() + joined[1:]


def _paint_words(
    conn: sqlite3.Connection, step: dict[str, object]
) -> tuple[str, str, str, str, str | None]:
    """A painting style as a batch's steps and a recipe's line say it: "After Hokusai", "80"."""
    style = own_styles.resolve(conn, step)
    if style is None:
        return (
            "paint",
            "A painting style",
            "A style that isn't in your styles any more",
            "?",
            None,
        )
    strength = step.get("strength")
    amount = min(max(float(strength), 0.0), 1.0) if isinstance(strength, int | float) else 1.0
    setting = step.get("setting")
    painting = Painting(
        style,
        amount,
        colours=step.get("colours") is True,
        setting=int(setting) if isinstance(setting, int | float) else None,
    )
    said = (style.setting, painting.amount) if style.kind == "classic" and style.setting else None
    chip, percent = look_chip(style.name, amount)
    return (
        "paint",
        "A painting style",
        paint_detail(style.name, amount, painting.keeps_colours, said),
        chip,
        percent,
    )


def _fix_chip(on: tuple[str, ...]) -> str:
    """The fixes as a recipe's line says them: "Noise and JPEG blocks", "Dark photo"."""
    names = {"noise": "noise", "blur": "blur", "jpeg": "JPEG blocks", "dark": "dark photo"}
    said = [names[kind] for kind in on]
    joined = said[0] if len(said) == 1 else f"{', '.join(said[:-1])} and {said[-1]}"
    return joined[:1].upper() + joined[1:]


def _look_detail(styling: Styling) -> str:
    """A look as a batch's steps say it: "Warm film at 60%, grain 20"."""
    said = phrase(styling.look, styling.strength, styling.touches)
    touched = touch_words(styling.touches)
    said = said[0].upper() + said[1:] if said else said
    return f"{said}, {touched}" if touched and styling.look.grid is not None else said


def _save_detail(how: str, format_: str, quality: int | None, folder: str | None) -> str:
    kind = f"{format_} {quality}" if quality else format_
    if how == "replace":
        return f"In place of the originals, {kind}; each original waits in quarantine for 30 days"
    where = folder_words(folder, None) if folder else "beside the originals"
    if folder and not Path(folder).is_absolute():
        where = f"into a folder called {folder} beside each"
    elif folder:
        where = f"into {folder}"
    return f"As new pictures, {kind}, {where}"


def _no_look(_look_id: str) -> None:
    return None


def _fields(step: dict[str, object]) -> dict[str, object]:
    return {name: value for name, value in step.items() if name != "step"}


_SELECT = """SELECT p.id, p.path, p.name, p.size, p.width, p.height, p.modified, p.raw,
                    p.problem, p.read_at, p.dir, p.folder_id
             FROM pictures AS p WHERE p.gone_at IS NULL AND p.folder_id IS NOT NULL AND """


def _rows(conn: sqlite3.Connection, clause: str, values: list[object]) -> list[sqlite3.Row]:
    return conn.execute(
        f"{_SELECT}{clause} ORDER BY p.taken_at DESC, p.id DESC",
        values,
    ).fetchall()


def _in_folder(folder_id: int | None, inside: str) -> tuple[str, list[object]]:
    clause = "p.folder_id = ?"
    values: list[object] = [folder_id]
    inside = inside.strip("/")
    if inside:
        clause += " AND (p.dir = ? OR substr(p.dir, 1, ?) = ?)"
        values += [inside, len(inside) + 1, f"{inside}/"]
    return clause, values


def _folder_name(conn: sqlite3.Connection, folder_id: int | None, inside: str) -> str | None:
    if inside.strip("/"):
        return inside.strip("/").split("/")[-1]
    row = conn.execute("SELECT path FROM folders WHERE id = ?", (folder_id,)).fetchone()
    return _name_of(Path(row["path"])) if row else None


def _picked(rows: list[sqlite3.Row], how: How, where: str | None) -> Picked:
    pictures: list[Picture] = []
    left: list[tuple[str, str]] = []
    for row in rows:
        found = _from_row(row)
        if found is None:
            left.append((row["name"], _why(row)))
        else:
            pictures.append(found)
    shared = _shared([picture.path for picture in pictures])
    source = where or (_name_of(shared) if shared else "your library")
    words = {"ticked": f"ticked in {source}", "folder": f"in {source}"}.get(how, source)
    return Picked(_most(pictures, left), source, str(shared) if shared else None, words, left)


def _from_row(row: sqlite3.Row) -> Picture | None:
    """A library picture a batch can make: read (a camera RAW by Mado's RAW reader), opening."""
    if row["problem"] or row["read_at"] is None or not row["width"]:
        return None
    return Picture(
        row["id"],
        Path(row["path"]),
        row["name"],
        row["size"],
        row["width"],
        row["height"],
        version(row["modified"], row["size"]),
    )


def _why(row: sqlite3.Row) -> str:
    if row["problem"]:
        return f"It won't open: {row['problem']}"
    if row["raw"] and row["read_at"] is not None:
        return WAITS_FOR_READER
    return "Mado is still reading it."


# A camera RAW left out of a batch while Mado's RAW reader comes.
WAITS_FOR_READER = (
    "It's a camera RAW, and Mado is getting its RAW reader: it joins once that's here."
)
# One left out once the reader's here, till the scan has read it.
BEING_READ = "It's a camera RAW Mado is reading now: it joins once it's read."


def _known(conn: sqlite3.Connection, files: Iterable[Path]) -> dict[str, sqlite3.Row]:
    """The library's pictures among some files, by their paths."""
    wanted = [str(path) for path in files]
    found: dict[str, sqlite3.Row] = {}
    for start in range(0, len(wanted), 500):
        chunk = wanted[start : start + 500]
        for row in conn.execute(
            f"{_SELECT}p.path IN (SELECT value FROM json_each(?))",  # noqa: S608 - fixed pieces
            [json.dumps(chunk)],
        ):
            found[str(row["path"]).casefold()] = row
    return found


def _walked(folder: Path) -> tuple[list[Path], bool]:
    """The pictures in a folder and the folders in it, a quarantine and Windows' own left out;
    and whether there were more files than Mado looks through."""
    found: list[Path] = []
    looked = 0
    for here, folders, files in os.walk(folder):
        folders[:] = sorted(
            name for name in folders if name != QUARANTINE and not skipped_folder(name)
        )
        for name in sorted(files):
            looked += 1
            if looked > _WALKED:
                return found, True
            if kind_of(name) is not None:
                found.append(Path(here) / name)
    return found, False


def _shared(paths: Sequence[Path]) -> Path | None:
    """The folder pictures share, when they're all under one."""
    if not paths:
        return None
    try:
        return Path(os.path.commonpath([str(path.parent) for path in paths]))
    except ValueError:  # on different drives
        return None


def _name_of(folder: Path) -> str:
    return folder.name or PureWindowsPath(folder).drive or str(folder)


def _most(pictures: list[Picture], left: list[tuple[str, str]]) -> list[Picture]:
    """As many pictures as a batch holds; those past it said in `left`."""
    more = len(pictures) - MOST
    if more > 0:
        said = "1 more picture" if more == 1 else f"{more:,} more pictures"
        them = "it" if more == 1 else "them"
        left.append((said, f"A batch holds {MOST:,} at most: make {them} in another."))
    return pictures[:MOST]


def _room(pictures: Sequence[Picture], saving: dict[str, object]) -> tuple[str | None, int | None]:
    """The drive most of a batch's pictures are saved on, and what's free there."""
    counts: dict[str, tuple[int, Path]] = {}
    for picture in pictures:
        into = destination({"saving": saving}, picture.path)
        drive = (PureWindowsPath(into).drive or str(into.anchor)).upper()
        seen, _ = counts.get(drive, (0, into))
        counts[drive] = (seen + 1, into)
    if not counts:
        return None, None
    drive, (_, into) = max(counts.items(), key=lambda each: each[1][0])
    here = into
    while not here.exists() and here.parent != here:
        here = here.parent
    try:
        return drive, shutil.disk_usage(here).free
    except OSError:
        return drive, None
