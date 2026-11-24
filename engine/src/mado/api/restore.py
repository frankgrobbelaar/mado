"""Restoring old photos as the Fix tab, a batch's steps and a recipe ask for it (docs/stack/
restoring.md): scratches and dust (the owner's strokes over what Mado found), a black-and-white
or toned picture coloured, faded colours brought back, each off (null) or on. What the detector
finds on a picture is `POST /pictures/{id}/scratches`, beside the plan and previews in
mado/api/making.py."""

from dataclasses import replace
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import Field

from mado.api.common import ApiModel
from mado.api.edits import StrokeIn
from mado.api.fixes import StrengthIn
from mado.core.restore import Restoring, restoring_from


class ScratchesIn(ApiModel):
    """Scratches and dust filled: what Mado found, with the owner's strokes over it (painting
    adds, Alt takes away)."""

    strokes: Annotated[list[StrokeIn], Field(default_factory=list[StrokeIn], max_length=512)]


class RestoreStepIn(ApiModel):
    """Restoring, each part null (off) or on: scratches and dust filled, a black-and-white or
    toned picture coloured, faded colours brought back. `version`: the picture's, as the strokes
    were painted on it."""

    version: str | None = None
    scratches: ScratchesIn | None = None
    colour: StrengthIn | None = None
    faded: StrengthIn | None = None


def restoring_of(step: RestoreStepIn | None) -> Restoring | None:
    """The restore step asked for, None with nothing on."""
    return restoring_from(step.model_dump()) if step is not None else None


def tied(restoring: Restoring | None, now: str, name: str) -> Restoring | None:
    """Restoring for the picture as it is now (`now`, its version; `name`, its file's): the
    scratches' strokes were painted on it at their version, so once it's changed they're
    refused (409), as edits are; colour and faded colours go by the picture as it is."""
    if restoring is None:
        return None
    if restoring.scratches is None:
        return replace(restoring, version=None)
    if restoring.version is not None and restoring.version != now:
        raise HTTPException(status.HTTP_409_CONFLICT, rechecked(name))
    return replace(restoring, version=now)


def rechecked(name: str) -> str:
    """Why scratches painted on a picture that's changed since aren't used."""
    return (
        f"{name} changed since Mado found its scratches, so the mask may not be where they are. "
        "Check them again on the picture as it is now."
    )
