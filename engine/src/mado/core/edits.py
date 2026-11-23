"""Editing by clicking, by its rules: the parts picked (a click or a few on the picture, and which
of the selecting model's three answers), the brush's strokes, and the edits made with them in
order: erase, cut out, blur what's behind, and cut out the subject. Together they're a recipe's
first step, made before its size and its look by the same Save. Pure.

A part is kept as the clicks that picked it, as fractions of the picture, so Save can pick it
again at full size from the picture as it was then; the masks the window showed are only kept to
save time (mado/editing.py). A part is picked on the picture as the edits before it left it. The
edits of a picture are tied to its version: once its file changes, they're for another picture.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

type Quality = Literal["fast", "best"]
type Behind = Literal["nothing", "colour", "blurred"]

CHOICES = 3  # the selecting model's answers for each part, smallest first
WHITE = (255, 255, 255)


class EditError(ValueError):
    """Edits Mado can't make as they're kept, with a sentence saying why."""


@dataclass(frozen=True)
class Click:
    x: float  # across the picture, 0 to 1
    y: float  # down it
    keep: bool = True  # False: Alt-click, taking that away


@dataclass(frozen=True)
class Part:
    clicks: tuple[Click, ...]
    choice: int | None = None  # which of the three, smallest first; None: as Mado picks


@dataclass(frozen=True)
class Stroke:
    points: tuple[tuple[float, float], ...]  # fractions of the picture
    size: float  # the brush's width, as a fraction of the picture's shorter side
    take: bool = False  # Alt: takes away what was painted


@dataclass(frozen=True)
class Erase:
    parts: tuple[Part, ...] = ()
    strokes: tuple[Stroke, ...] = ()
    quality: Quality = "fast"


@dataclass(frozen=True)
class CutOut:
    parts: tuple[Part, ...]
    behind: Behind = "nothing"
    colour: tuple[int, int, int] = WHITE


@dataclass(frozen=True)
class Blur:
    """What's behind the parts blurred, as a big camera lens would."""

    parts: tuple[Part, ...]


@dataclass(frozen=True)
class Subject:
    """The picture's subject cut out, found without a click."""

    quality: Quality | None = None  # None: as this PC suits
    behind: Behind = "nothing"
    colour: tuple[int, int, int] = WHITE


type Edit = Erase | CutOut | Blur | Subject


@dataclass(frozen=True)
class Editing:
    edits: tuple[Edit, ...]
    version: str | None = None  # the picture's version they were made on; None: any (a batch's)


def see_through(editing: Editing | None) -> bool:
    """Whether the edits leave the picture with see-through parts: a cut-out with nothing behind
    it."""
    if editing is None:
        return False
    return any(
        isinstance(edit, CutOut | Subject) and edit.behind == "nothing" for edit in editing.edits
    )


def label(editing: Editing | None) -> str | None:
    """What a new picture's name says of the edits: "Erased", "Cut out", "Blurred", or "Edited"
    for more than one kind."""
    if editing is None or not editing.edits:
        return None
    kinds = {_kind(edit) for edit in editing.edits}
    if len(kinds) > 1:
        return "Edited"
    return {"erase": "Erased", "cut": "Cut out", "blur": "Blurred"}[kinds.pop()]


def phrase(editing: Editing | None) -> str | None:
    """The edits as History and Save say them: "erased 2 parts, cut out the subject"."""
    if editing is None or not editing.edits:
        return None
    said: list[str] = []
    for edit in editing.edits:
        match edit:
            case Erase(parts=parts, strokes=strokes):
                count = len(parts) + (1 if strokes else 0)
                said.append("erased a part" if count <= 1 else f"erased {count} parts")
            case CutOut(parts=parts, behind=behind):
                said.append(_cut("cut out a part" if len(parts) <= 1 else "cut out parts", behind))
            case Blur():
                said.append("blurred what's behind a part")
            case Subject(behind=behind):
                said.append(_cut("cut out the subject", behind))
    return ", ".join(said)


def _cut(said: str, behind: Behind) -> str:
    match behind:
        case "nothing":
            return said
        case "colour":
            return f"{said} onto a colour"
        case "blurred":
            return f"{said} over the rest, blurred"


def _kind(edit: Edit) -> Literal["erase", "cut", "blur"]:
    match edit:
        case Erase():
            return "erase"
        case CutOut() | Subject():
            return "cut"
        case Blur():
            return "blur"


CLOSE = 0.1  # how near SAM's sureness of a bigger answer to its best one for the bigger to go first


def first_choice(scores: Sequence[float], areas: Sequence[float]) -> int:
    """Which of a part's three answers (smallest first) Mado shows first: the one SAM is surest
    of, unless a bigger one is nearly as sure (a click on a boat's hull picks the boat, not the
    hull), as one click most often means the whole thing. The owner goes bigger or smaller from
    there."""
    best = max(range(len(scores)), key=lambda at: scores[at])
    for at in range(len(scores) - 1, best, -1):
        if areas[at] > areas[best] and scores[at] >= scores[best] - CLOSE:
            return at
    return best


def parts_named(count: int) -> list[str]:
    """What the parts are called, as picked: "Part 1", "Part 2". Mado never guesses what a part
    is."""
    return [f"Part {at + 1}" for at in range(count)]


def models_for(editing: Editing | None, *, cut_quality: Quality) -> set[str]:
    """What the edits need: "select" for parts, "erase-fast" or "erase-best", "cut-fast" or
    "cut-best" for the subject (`cut_quality` when it's left to this PC)."""
    needs: set[str] = set()
    if editing is None:
        return needs
    for edit in editing.edits:
        if isinstance(edit, Erase | CutOut | Blur) and edit.parts:
            needs.add("select")
        if isinstance(edit, Erase):
            needs.add(f"erase-{edit.quality}")
        if isinstance(edit, Subject):
            needs.add(f"cut-{edit.quality or cut_quality}")
    return needs


def editing_from(data: object) -> Editing | None:
    """An edit step as a job or a request keeps it (JSON), or None for none. Raises EditError
    for one Mado can't make."""
    if data is None:
        return None
    if not isinstance(data, dict):
        raise EditError(_UNKNOWN)
    kept = cast("dict[str, object]", data)
    listed = kept.get("edits")
    if not isinstance(listed, list):
        raise EditError(_UNKNOWN)
    edits = tuple(_edit(each) for each in cast("list[object]", listed))
    version = kept.get("version")
    return Editing(edits, version if isinstance(version, str) and version else None)


def parts_from(data: object) -> tuple[Part, ...]:
    """Parts as they're kept (JSON): each its clicks and its choice."""
    if not isinstance(data, list):
        return ()
    return tuple(_part(each) for each in cast("list[object]", data))


def _edit(data: object) -> Edit:
    if not isinstance(data, dict):
        raise EditError(_UNKNOWN)
    kept = cast("dict[str, object]", data)
    match kept.get("kind"):
        case "erase":
            edit: Edit = Erase(
                parts_from(kept.get("parts")),
                _strokes(kept.get("strokes")),
                _quality(kept.get("quality")) or "fast",
            )
            if not edit.parts and not edit.strokes:
                raise EditError("An erase needs a part picked or painted: pick one first.")
            return edit
        case "cutout":
            parts = parts_from(kept.get("parts"))
            if not parts:
                raise EditError("A cut-out needs a part picked: pick one first.")
            return CutOut(parts, _behind(kept.get("behind")), _colour(kept.get("colour")))
        case "blur":
            parts = parts_from(kept.get("parts"))
            if not parts:
                raise EditError("Blurring what's behind needs a part picked: pick one first.")
            return Blur(parts)
        case "subject":
            return Subject(
                _quality(kept.get("quality")),
                _behind(kept.get("behind")),
                _colour(kept.get("colour")),
            )
        case _:
            raise EditError(_UNKNOWN)


def _part(data: object) -> Part:
    if not isinstance(data, dict):
        raise EditError(_UNKNOWN)
    kept = cast("dict[str, object]", data)
    listed = kept.get("clicks")
    clicks = tuple(_click(each) for each in cast("list[object]", listed or []))
    if not clicks or not any(click.keep for click in clicks):
        raise EditError("A part needs a click on the picture to pick it.")
    choice = kept.get("choice")
    return Part(
        clicks,
        min(max(int(choice), 0), CHOICES - 1) if isinstance(choice, int | float) else None,
    )


def _click(data: object) -> Click:
    if not isinstance(data, dict):
        raise EditError(_UNKNOWN)
    kept = cast("dict[str, object]", data)
    x, y = kept.get("x"), kept.get("y")
    if not isinstance(x, int | float) or not isinstance(y, int | float):
        raise EditError(_UNKNOWN)
    return Click(_fraction(x), _fraction(y), kept.get("keep") is not False)


def _strokes(data: object) -> tuple[Stroke, ...]:
    if not isinstance(data, list):
        return ()
    found: list[Stroke] = []
    for each in cast("list[object]", data):
        if not isinstance(each, dict):
            raise EditError(_UNKNOWN)
        kept = cast("dict[str, object]", each)
        points = kept.get("points")
        size = kept.get("size")
        if not isinstance(points, list) or not isinstance(size, int | float) or size <= 0:
            raise EditError(_UNKNOWN)
        found.append(
            Stroke(
                tuple(_point(point) for point in cast("list[object]", points)),
                min(float(size), 1.0),
                kept.get("take") is True,
            )
        )
    return tuple(found)


def _point(data: object) -> tuple[float, float]:
    if isinstance(data, list) and len(cast("list[object]", data)) == 2:
        x, y = cast("list[object]", data)
        if isinstance(x, int | float) and isinstance(y, int | float):
            return _fraction(x), _fraction(y)
    raise EditError(_UNKNOWN)


def _fraction(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _quality(value: object) -> Quality | None:
    match value:
        case "fast":
            return "fast"
        case "best":
            return "best"
        case _:
            return None


def _behind(value: object) -> Behind:
    match value:
        case "colour":
            return "colour"
        case "blurred":
            return "blurred"
        case _:
            return "nothing"


def _colour(value: object) -> tuple[int, int, int]:
    """A colour as "#rrggbb"; white for anything else."""
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
        except ValueError:
            return WHITE
    return WHITE


def colour_text(colour: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour)


def as_json(editing: Editing) -> dict[str, object]:
    """An edit step as a job keeps it."""
    return {"version": editing.version, "edits": [edit_json(edit) for edit in editing.edits]}


def edit_json(edit: Edit) -> dict[str, object]:
    match edit:
        case Erase(parts=parts, strokes=strokes, quality=quality):
            return {
                "kind": "erase",
                "parts": parts_json(parts),
                "strokes": [
                    {"points": [list(p) for p in s.points], "size": s.size, "take": s.take}
                    for s in strokes
                ],
                "quality": quality,
            }
        case CutOut(parts=parts, behind=behind, colour=colour):
            return {
                "kind": "cutout",
                "parts": parts_json(parts),
                "behind": behind,
                "colour": colour_text(colour),
            }
        case Blur(parts=parts):
            return {"kind": "blur", "parts": parts_json(parts)}
        case Subject(quality=quality, behind=behind, colour=colour):
            return {
                "kind": "subject",
                "quality": quality,
                "behind": behind,
                "colour": colour_text(colour),
            }


def parts_json(parts: Sequence[Part]) -> list[dict[str, object]]:
    return [
        {
            "clicks": [{"x": c.x, "y": c.y, "keep": c.keep} for c in part.clicks],
            "choice": part.choice,
        }
        for part in parts
    ]


_UNKNOWN = "This Mado doesn't know one of the edits, so it can't make them: update Mado."
