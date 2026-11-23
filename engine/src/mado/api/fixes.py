"""The quick fixes as the Fix tab, a batch's steps and a recipe ask for them: each fix off (null)
or on at its one setting (docs/stack/fixes.md). What Mado suggests fixing in a picture is
`GET /pictures/{id}/fixes`, beside the plan and previews in mado/api/making.py."""

from pydantic import Field

from mado.api.common import ApiModel
from mado.core.fixes import Fixing, Quality, fixing_from


class StrengthIn(ApiModel):
    """How much of the model's change is kept, 0 to 1."""

    strength: float = Field(default=1.0, ge=0, le=1)


class JpegIn(ApiModel):
    """JPEG blocks: at Fast (SCUNet) or Best (FBCNN), null as this PC has them; how hard, 0 to 1
    (at Best, FBCNN's quality setting: 0.7 takes it for a JPEG saved at 30), or null as hard as
    each JPEG was squeezed (a batch's, a picture that isn't a JPEG left as it is)."""

    quality: Quality | None = None
    strength: float | None = Field(default=0.6, ge=0, le=1)


class DarkIn(ApiModel):
    """A dark photo, brightened as it measures: how much local contrast is laid on after, 0 to
    1."""

    contrast: float = Field(default=0.0, ge=0, le=1)


class FixStepIn(ApiModel):
    """The fixes: noise, blur from a shaking camera or a moving subject, JPEG blocks and a dark
    photo, each null (off) or its setting."""

    noise: StrengthIn | None = None
    blur: StrengthIn | None = None
    jpeg: JpegIn | None = None
    dark: DarkIn | None = None


def fixing_of(step: FixStepIn | None) -> Fixing | None:
    """The fix step asked for, None with no fix on."""
    return fixing_from(step.model_dump()) if step is not None else None


class FixesOut(ApiModel):
    """What Mado measures of a picture, for the Fix tab: only what it can measure cheaply and
    reliably (docs/stack/fixes.md says how often each suggestion was right)."""

    jpeg_quality: int | None  # a JPEG's own quality, from its tables; None for any other file
    blocks: bool  # Mado suggests taking its JPEG blocks out
    stops: float  # how many stops brighter the dark photo fix makes it: 0 when it isn't dark
    dark: bool  # Mado suggests brightening it
    grey: bool  # black and white: the fixes keep it so
    see_through: bool  # its see-through parts stay as they are
    colour: str  # its colours, kept: "sRGB", "Display P3"
    megapixels: float
