"""How long making a picture takes. Pure.

The AI model's work grows with the pixels it's given, so each model's speed is in seconds for a
megapixel of tiles, on the graphics card or the processor. Until Mado has timed this PC, it goes
by the owner's GTX 1660 Super and i5-9600K (docs/stack/upscaling.md, 2026-11-22); every picture
made then moves the time kept for its model a little (mado/hardware.py), so the times become
this PC's own.
"""

from collections.abc import Mapping
from typing import Literal

type Place = Literal["card", "processor"]

# Seconds for a megapixel of tiles, by model and place, as the owner's PC ran them: 512 tiles
# of the general model in 0.15 s on the card, 256 tiles of x4plus in 0.49 s, of its drawing
# model in 0.16 s; on the processor 0.8 s, 8.3 s and 2.5 s a 256 tile.
GUESS: dict[str, float] = {
    "realesr-general-x4v3@card": 0.59,
    "realesr-general-wdn-x4v3@card": 0.59,
    "realesrgan-x4plus@card": 7.5,
    "realesrgan-x4plus-anime-6b@card": 2.5,
    "realesr-general-x4v3@processor": 12.6,
    "realesr-general-wdn-x4v3@processor": 12.6,
    "realesrgan-x4plus@processor": 128.0,
    "realesrgan-x4plus-anime-6b@processor": 38.0,
    # The fixes' models, in 384 tiles, as a 12-megapixel photo fixed measured them on the owner's
    # PC (docs/stack/fixes.md).
    "scunet@card": 1.42,
    "fbcnn@card": 0.95,
    "nafnet@card": 0.38,
    "scunet@processor": 31.2,
    "fbcnn@processor": 17.7,
    "nafnet@processor": 5.5,
}
_START = 0.5  # seconds: reading the picture and setting out
_PER_MEGAPIXEL = 0.06  # seconds for each megapixel made: resizing, fading in and saving
_PER_TILE = 0.02  # seconds each tile's result takes to resize and lay in place


def key(model: str, place: Place) -> str:
    """How a speed is kept: "realesr-general-x4v3@card"."""
    return f"{model}@{place}"


def speed(model: str, place: Place, speeds: Mapping[str, float]) -> float:
    """Seconds for a megapixel of tiles: as measured on this PC, else the guess."""
    measured = speeds.get(key(model, place))
    if measured is not None and measured > 0:
        return measured
    return GUESS.get(key(model, place), GUESS[key("realesrgan-x4plus", place)])


def seconds_for(
    model: str | None,
    place: Place,
    tiles: int,
    tile: int,
    made_pixels: int,
    speeds: Mapping[str, float],
) -> float:
    """How long making a picture takes: `tiles` tiles of `tile` pixels through `model` (None
    when no AI touches it), then resizing to `made_pixels` and saving."""
    work = _START + made_pixels / 1e6 * _PER_MEGAPIXEL
    if model is None:
        return work
    megapixels = tiles * tile * tile / 1e6
    return work + megapixels * speed(model, place, speeds) + tiles * _PER_TILE


def blended(old: float | None, measured: float, share: float = 0.3) -> float:
    """A speed kept, moved `share` of the way to one just measured."""
    return measured if old is None else old * (1 - share) + measured * share
