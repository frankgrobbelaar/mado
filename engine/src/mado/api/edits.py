"""The edits as the window sends them: the parts picked (their clicks and the answer shown), the
brush's strokes, and each edit, as a recipe's first step (mado/core/edits.py)."""

from typing import Annotated, Literal

from pydantic import Field

from mado.api.common import ApiModel
from mado.core.edits import EditError, Editing, Part, editing_from, parts_from
from mado.core.models import Quality

type Behind = Literal["nothing", "colour", "blurred"]
_COLOUR = r"^#[0-9a-fA-F]{6}$"


class ClickIn(ApiModel):
    """A click on the picture, as fractions of it: one that picks (`keep`) or, with Alt, one that
    takes away."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    keep: bool = True


class PartIn(ApiModel):
    """A part: the clicks that picked it, and which of the three answers (smallest first) is
    shown; none, as Mado picks."""

    clicks: Annotated[list[ClickIn], Field(min_length=1, max_length=32)]
    choice: int | None = Field(default=None, ge=0, le=2)


class StrokeIn(ApiModel):
    """A stroke of the brush: its points as fractions of the picture, its width as a fraction of
    the picture's shorter side, and whether it takes away (Alt)."""

    points: Annotated[
        list[Annotated[list[float], Field(min_length=2, max_length=2)]],
        Field(min_length=1, max_length=4096),
    ]
    size: float = Field(gt=0, le=1)
    take: bool = False


class EraseIn(ApiModel):
    """Erase what's picked or painted, filled from what's around it."""

    kind: Literal["erase"] = "erase"
    parts: Annotated[list[PartIn], Field(default_factory=list[PartIn], max_length=32)]
    strokes: Annotated[list[StrokeIn], Field(default_factory=list[StrokeIn], max_length=256)]
    quality: Quality = "fast"


class CutOutIn(ApiModel):
    """Cut out what's picked: on nothing, a colour, or the rest blurred."""

    kind: Literal["cutout"] = "cutout"
    parts: Annotated[list[PartIn], Field(min_length=1, max_length=32)]
    behind: Behind = "nothing"
    colour: str | None = Field(default=None, pattern=_COLOUR)


class BlurIn(ApiModel):
    """Blur what's behind what's picked, as a big camera lens would."""

    kind: Literal["blur"] = "blur"
    parts: Annotated[list[PartIn], Field(min_length=1, max_length=32)]


class SubjectIn(ApiModel):
    """Cut out the picture's subject, found without a click."""

    kind: Literal["subject"] = "subject"
    quality: Quality | None = None  # None: as this PC suits
    behind: Behind = "nothing"
    colour: str | None = Field(default=None, pattern=_COLOUR)


type EditIn = Annotated[EraseIn | CutOutIn | BlurIn | SubjectIn, Field(discriminator="kind")]


class EditStepIn(ApiModel):
    """The edits, in order, made on the picture as it was at `version`."""

    version: str
    edits: Annotated[list[EditIn], Field(max_length=64)]


def editing_of(step: EditStepIn | None) -> Editing | None:
    """The edit step asked for. Raises EditError for edits Mado can't make."""
    if step is None:
        return None
    return editing_from(step.model_dump(by_alias=True))


def edits_of(edits: list[EditIn], version: str) -> Editing:
    """Edits as the window lists them. Raises EditError."""
    found = editing_from(
        {"version": version, "edits": [edit.model_dump(by_alias=True) for edit in edits]}
    )
    if found is None:
        raise EditError("Those edits can't be made.")
    return found


def picked(parts: list[PartIn]) -> tuple[Part, ...]:
    """Parts as the window lists them."""
    return parts_from([part.model_dump(by_alias=True) for part in parts])
