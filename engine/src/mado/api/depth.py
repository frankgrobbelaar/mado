"""Depth, as the Depth tab, a batch's steps and a recipe ask for it (docs/stack/depth.md): the
depth step's choices (portrait blur, fog and tilt-shift, each off or at its settings), and what
Mado reads of a picture's depth for the tab (`POST /pictures/{id}/depth`): whether it's flat,
where its subject is and where the model runs. The plan, previews and Save are
mado/api/making.py's; a 3D photo is mado/api/motion.py's."""

import time
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, status
from pydantic import Field

from mado.ai import DEPTH, DEPTH_FILE
from mado.api.common import ApiModel, Database, Depthing, Editors, Models, Seeing, Toolbox
from mado.api.edits import EditIn, edits_of
from mado.core.depth import APERTURE, APERTURES, depthing_from, middle_of
from mado.core.depth import Depthing as DepthStep
from mado.core.edits import EditError
from mado.directml import ModelError
from mado.editing import MOST_PIXELS, EditingError, picture_key
from mado.making import picture_of
from mado.pictures import NeedsFfmpegError, NeedsReaderError, PictureGoneError, UnreadableError
from mado.previews import version

router = APIRouter()

type Quality = Literal["fast", "best"]


class PortraitIn(ApiModel):
    """Portrait blur: in focus at a point (fractions across and down; null, the subject), as a
    lens at `aperture` (f/1.4 to f/16), the subject's edges at Fast or Best (null: as this PC
    suits)."""

    focus: Annotated[list[float], Field(min_length=2, max_length=2)] | None = None
    aperture: float = Field(default=APERTURE, ge=APERTURES[0], le=APERTURES[-1])
    quality: Quality | None = None


class FogIn(ApiModel):
    """Fog: how thick, 0 to 1, and its colour ("#rrggbb"; null, the picture's own haze)."""

    density: float = Field(default=0.5, ge=0, le=1)
    colour: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class TiltIn(ApiModel):
    """Tilt-shift: the band in focus (its middle and height, fractions of the picture's height)
    and how much blur grows away from it, 0 to 1."""

    centre: float = Field(default=0.55, ge=0, le=1)
    height: float = Field(default=0.2, ge=0.02, le=0.9)
    strength: float = Field(default=0.6, ge=0, le=1)


class DepthStepIn(ApiModel):
    """The depth tools: portrait blur, fog and tilt-shift, each null (off) or its settings."""

    portrait: PortraitIn | None = None
    fog: FogIn | None = None
    tilt: TiltIn | None = None


def depthing_of(step: DepthStepIn | None) -> DepthStep | None:
    """The depth step asked for, None with no tool on."""
    return depthing_from(step.model_dump()) if step is not None else None


class DepthAsk(ApiModel):
    """The picture as the window has it, and the edits made on it: its depth is read as they
    leave it."""

    version: str
    edits: Annotated[list[EditIn], Field(default_factory=list[EditIn], max_length=64)]


class DepthNeed(ApiModel):
    id: str
    name: str
    size: int  # bytes


class DepthOut(ApiModel):
    """What Mado read of a picture's depth, for the Depth tab."""

    needs: list[DepthNeed]  # the depth model, while it isn't downloaded: nothing else is read
    read: bool  # its depth was read (or kept)
    flat: bool  # no depth to speak of: a scan, a screenshot
    place: Literal["card", "processor"]  # where the depth model runs
    seconds: float | None  # what reading it took, when this asked it to be read
    waited: float  # of which waiting for the graphics card, while the queue's picture had it
    subject: bool  # Mado found a subject (u2netp), which portrait blur keeps sharp
    focus: list[float] | None  # where portrait blur is in focus without a click: its subject
    see_through: bool  # its see-through parts stay as they are
    grey: bool
    megapixels: float
    too_big: bool  # past what Mado edits: the Size tab makes a smaller copy first


@router.post("/pictures/{picture_id}/depth")
def depth_of(
    picture_id: int,
    body: DepthAsk,
    conn: Database,
    sight: Seeing,
    ai: Models,
    toolbox: Toolbox,
    depths: Depthing,
    editor: Editors,
) -> DepthOut:
    """Reads how near each part of the picture is (as its edits leave it), the first time it's
    asked for (about a tenth of a second on the card, half a second on the processor), and finds
    its subject: what the Depth tab says of it. While the depth model isn't downloaded, says so
    and reads nothing."""
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That picture isn't in your library any more."
        )
    picture = picture_of(conn, picture_id, Path(row["path"]))
    now = version(row["modified"], row["size"])
    if body.version != now:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{picture.path.name} changed since Mado read it: it's read again as it is now.",
        )
    try:
        edits = edits_of(body.edits, now).edits
        seen = sight.of(picture, now)
    except EditError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    too_big = seen.width * seen.height > MOST_PIXELS
    place = ai.depth_place()
    megapixels = round(seen.width * seen.height / 1e6, 1)
    needs: list[DepthNeed] = []
    if ai.edit_file(DEPTH, DEPTH_FILE) is None:
        tool = next((item for item, _ in toolbox.status() if item.id == DEPTH), None)
        if tool is not None:
            needs.append(DepthNeed(id=DEPTH, name=tool.name, size=tool.size or 0))
    if needs or too_big:
        return DepthOut(
            needs=needs,
            read=False,
            flat=False,
            place=place,
            seconds=None,
            waited=0.0,
            subject=False,
            focus=None,
            see_through=seen.alpha,
            grey=seen.grey,
            megapixels=megapixels,
            too_big=too_big,
        )
    key = picture_key(picture.path, now)
    began = time.perf_counter()
    try:
        whole = sight.picture(picture, now)
        kept = depths.kept(key, edits)
        reading = kept if kept is not None else depths.read(whole, key, edits)
        mask, _where = editor.subject(whole, key, edits, "fast")
    except ModelError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except EditingError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    focus = middle_of(np.asarray(mask, np.float32) / 255.0) if mask.any() else None
    return DepthOut(
        needs=[],
        read=True,
        flat=reading.flat or seen.kind in ("screenshot", "pixels"),
        place=place,
        seconds=None if kept is not None else round(time.perf_counter() - began, 2),
        waited=round(reading.waited, 2),
        subject=focus is not None,
        focus=[focus[0], focus[1]] if focus is not None else None,
        see_through=seen.alpha,
        grey=seen.grey,
        megapixels=megapixels,
        too_big=False,
    )


def _refused(error: Exception) -> HTTPException:
    if isinstance(error, PictureGoneError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, NeedsFfmpegError | NeedsReaderError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
