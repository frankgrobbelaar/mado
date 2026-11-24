"""What Mado's tools do to an HDR photo's gain map, so the picture made keeps its HDR. Pure.

A gain map says how much brighter each place may go; it's smooth, so it follows the picture by
plain resampling, and the AI models work on the picture alone. What each tool does to it:

- Size: cropped, its edges extended (the gain at the edge carried on) and resized with the
  picture, kept at the same share of the picture as the photo's was (a quarter stays a quarter),
  4096 pixels on its longer side at most.
- Edit: where a part is erased, the gain map is filled from round it (the wall's gain, not the
  lamp's); behind a cut-out on a colour it's none (a flat colour is the same on any screen);
  behind a part blurred (a cut-out on the rest blurred, or Blur what's behind it) it's blurred
  the same way. A cut-out on nothing saves as PNG or WebP, which hold no gain map.
- Looks: a look grades the ordinary picture and the gain map is kept, so the HDR rendition is the
  graded picture made brighter where it was; a colour gain map is made one channel first, as its
  colours would bring back what the look took out (a black and white look stays black and white).
- Painting styles: a painter's or a picture's style, oil paint and cartoon keep the photo's light
  where it was, so the gain map is kept (a lamp painted still glows); a pencil sketch, coloured
  or not, is paper and lines, so the gain fades with the style's strength, and at full strength
  there's no HDR left.
- Fixes (noise, blur, JPEG blocks, brightening, local contrast) clean or brighten the ordinary
  picture and keep the gain map as it is: brightening's curve holds the highlights below white,
  and the gain map opens them up again on an HDR screen.
- Restoring: where scratches and dust are filled, the gain map is filled from round them as an
  erase's is (a white scratch on a photographed print would glow on again on an HDR screen);
  colouring a black and white picture, or bringing faded colours back, keeps it, one channel, as
  a look does: the light was where it was.
- Depth tools: made again from both renditions given the same tool (mado/depth.py).
"""

from collections.abc import Sequence

import numpy as np
from PIL import Image

from mado.core.depth import spread
from mado.core.edits import Blur, CutOut, Edit, Erase, Subject
from mado.core.framing import Frame
from mado.core.gainmap import Floats, GainMap, filled, scaled, single, size_for
from mado.core.masks import Mask
from mado.core.painting import Painting

MOST = 4096  # a gain map kept beside a picture is no bigger than this on its longer side
_PENCILS = ("pencil", "coloured-pencil")  # paper and lines: no light to brighten
_LENS = 0.006  # Blur what's behind it: a disc this much of the shorter side out (cutting.py)
_BACKDROP = 0.01  # a cut-out on the rest blurred: this much of the shorter side out
_FLAT = 1e-3  # gains this close to none everywhere are no HDR left


def sized(gain: GainMap, frame: Frame, picture: tuple[int, int], made: tuple[int, int]) -> GainMap:
    """The gain map of a picture `picture` big (width, height, as shown) made `made` big by a
    plan's `frame`: what it keeps cropped out (or its canvas, past the picture's edges when
    extending, the gain at each edge carried on), resized to the same share of the picture made
    as it had of the photo, `MOST` at most."""
    width, height = gain.size
    sx, sy = width / picture[0], height / picture[1]
    extending = frame.shape == "extend" and frame.sides != "none"
    part = frame.canvas if extending else frame.kept
    left, top = part.x * sx, part.y * sy
    right, bottom = (part.x + part.width) * sx, (part.y + part.height) * sy
    # Past the gain map's edges (an extended canvas): its edges carried on.
    pad_left = max(0, int(np.ceil(-left)) + 1)
    pad_top = max(0, int(np.ceil(-top)) + 1)
    pad_right = max(0, int(np.ceil(right - width)) + 1)
    pad_bottom = max(0, int(np.ceil(bottom - height)) + 1)
    planes = gain.gains[..., None] if gain.gains.ndim == 2 else gain.gains
    padded = np.pad(
        planes, ((pad_top, pad_bottom), (pad_left, pad_right), (0, 0)), mode="edge"
    ).astype(np.float32)
    box = (left + pad_left, top + pad_top, right + pad_left, bottom + pad_top)
    size = size_for(made, (sx, sy), MOST)
    out = np.empty((size[1], size[0], planes.shape[2]), np.float32)
    for c in range(planes.shape[2]):
        plane = Image.fromarray(np.ascontiguousarray(padded[..., c]), "F")
        out[..., c] = np.asarray(plane.resize(size, Image.Resampling.BILINEAR, box=box))
    return GainMap(out[..., 0] if gain.gains.ndim == 2 else out, gain.info)


def resized(gain: GainMap, size: tuple[int, int]) -> GainMap:
    """The gain map `size` big (width, height), smoothly."""
    if gain.size == size:
        return gain
    planes = gain.gains[..., None] if gain.gains.ndim == 2 else gain.gains
    out = np.empty((size[1], size[0], planes.shape[2]), np.float32)
    for c in range(planes.shape[2]):
        plane = Image.fromarray(np.ascontiguousarray(planes[..., c]), "F")
        out[..., c] = np.asarray(plane.resize(size, Image.Resampling.BILINEAR))
    return GainMap(out[..., 0] if gain.gains.ndim == 2 else out, gain.info)


def shown_with(gain: GainMap, picture: tuple[int, int], shown: tuple[int, int]) -> GainMap:
    """The gain map of a picture `picture` big, for a copy of it `shown` big: the same share of
    the copy as of the picture, `MOST` at most."""
    width, height = gain.size
    return resized(gain, size_for(shown, (width / picture[0], height / picture[1]), MOST))


def edited(gain: GainMap, steps: Sequence[tuple[Edit, Mask]]) -> GainMap | None:
    """The gain map as the edits leave it, each with its mask (at the picture's size): erased
    parts filled from round them, a cut-out's ground none or blurred as its picture's is. None
    once a cut-out leaves nothing behind it: its see-through parts save only as PNG or WebP."""
    gains = gain.gains
    height, width = gains.shape[:2]
    short = min(width, height)
    for edit, mask in steps:
        inside = _shrunk(mask, (width, height))
        match edit:
            case Erase():
                gains = filled(gains, inside)
            case CutOut(behind="nothing") | Subject(behind="nothing"):
                return None
            case CutOut(behind="colour") | Subject(behind="colour"):
                gains = scaled(gains, inside)
            case CutOut() | Subject():
                gains = _behind(gains, inside, short * _BACKDROP)
            case Blur():
                gains = _behind(gains, inside, short * _LENS)
    return GainMap(gains, gain.info)


def painted(gain: GainMap, painting: Painting, where: Floats | None = None) -> GainMap | None:
    """The gain map once its picture is painted in a style (everywhere, or `where` says, 0 to 1
    at the gain map's size, for a style on a part): kept, but for a pencil sketch, whose gain
    fades as much as the style shows; None with none of it left."""
    if painting.style.id not in _PENCILS:
        return gain
    shows = painting.strength if where is None else painting.strength * where
    made = GainMap(scaled(gain.gains, 1.0 - np.asarray(shows, np.float32)), gain.info)
    return None if flat(made) else made


def looked(gain: GainMap) -> GainMap:
    """The gain map once its picture is given a look: one channel, so the HDR rendition keeps the
    look's colours."""
    return GainMap(single(gain.gains), gain.info)


def restored(gain: GainMap, filled_mask: Mask | None, *, recoloured: bool) -> GainMap:
    """The gain map once its picture is restored: where its scratches and dust were filled
    (`filled_mask`, at the picture's size; None when none were), filled from round them as an
    erase's is; coloured, or its faded colours brought back (`recoloured`), one channel, as a
    look's."""
    gains = gain.gains
    if filled_mask is not None:
        height, width = gains.shape[:2]
        gains = filled(gains, _shrunk(filled_mask, (width, height)))
    made = GainMap(gains, gain.info)
    return looked(made) if recoloured else made


def flat(gain: GainMap) -> bool:
    """Whether a gain map brightens nothing anywhere, so there's no HDR to keep."""
    return float(np.abs(gain.gains).max(initial=0.0)) <= _FLAT


def _shrunk(mask: Mask, size: tuple[int, int]) -> Floats:
    """A mask at the picture's size, 0 to 1, at the gain map's."""
    picture = Image.fromarray(mask, "L")
    if picture.size != size:
        picture = picture.resize(size, Image.Resampling.BOX)
    return (np.asarray(picture, np.float32) / 255.0).astype(np.float32)


def _behind(gains: Floats, inside: Floats, radius: float) -> Floats:
    """Gains blurred by a disc `radius` pixels out where the part isn't, the part's own left out
    of the blur so it doesn't spread into what's round it, joined softly at its edge."""
    outside = (1.0 - inside).astype(np.float32)
    planes = gains[..., None] if gains.ndim == 2 else gains
    weight = spread(outside, radius)
    blurred = spread((planes * outside[..., None]).astype(np.float32), radius)
    ground = np.where(
        weight[..., None] > 1e-3, blurred / np.maximum(weight[..., None], 1e-3), planes
    )
    joined = inside[..., None] * planes + outside[..., None] * ground
    return (joined[..., 0] if gains.ndim == 2 else joined).astype(np.float32)
