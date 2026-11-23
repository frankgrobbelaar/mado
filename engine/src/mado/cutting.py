"""Cutting a part out, and blurring what's behind it (docs/stack/editing.md).

A part's mask comes from a model at its own size (SAM's 256 square, U²-Net's 320, BiRefNet's
1024), so its edge is a few of the picture's pixels off. It's made to follow the picture's own
edges at full size by a guided filter: worked out on a copy 1024 across, then laid on the picture
itself a band of rows at a time, and only along the mask's unsure edge, so a 50-megapixel picture
needs little more memory than its mask.
What's cut out then sits on nothing (see-through, saved as PNG or WebP), on a colour, or on the
rest of the picture blurred. "Blur what's behind it" blurs everything outside the part as a big
camera lens does, a disc rather than a haze, in light rather than in the picture's numbers (so
bright things bloom), the part itself kept out of the blur so its colour never bleeds round it,
then joined with a soft edge.
"""

from collections.abc import Callable

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado.core.edits import Behind
from mado.core.masks import Floats, Mask, box, feathered, guided, guided_coefficients
from mado.selecting import flat, grid_size

type Pixels = npt.NDArray[np.uint8]

_WORK = 1024  # the guided filter is worked out on a copy this big on its long side
_RADIUS = 4  # its reach, in pixels of that copy
_SURE = 0.02  # a mask this near 0 or 1 is sure: nothing to refine there
_EPS = 2e-3  # how much a flat place smooths the mask rather than follows the picture
_BAND = 256  # rows of the picture at a time
_LENS = 0.012  # the lens's blur, a disc this much of the picture's shorter side across
_EDGE = 0.004  # the soft edge between a part and its blurred background, of the shorter side
_BACKDROP = 0.02  # the rest blurred behind a cut-out: a haze this much of the shorter side
_GAMMA = 2.2  # light from a picture's numbers, near enough, so bright places bloom when blurred


def refined(image: Image.Image, mask: Floats) -> Mask:
    """A soft mask (0 to 1, at any size) made the picture's size and made to follow the
    picture's own edges: crisp where the picture is, soft where it is (fur, a blurred edge). Only
    the mask's unsure edge is worked out at full size; where it's sure, it stays as it is."""
    width, height = image.size
    scale = min(_WORK / max(width, height), 1.0)
    work = (max(1, round(width * scale)), max(1, round(height * scale)))
    rgb = flat(image)
    guide = np.asarray(rgb.resize(work, Image.Resampling.BOX), np.float32) / 255.0
    small = np.clip(
        np.asarray(
            Image.fromarray(np.ascontiguousarray(mask, np.float32), "F").resize(
                work, Image.Resampling.BILINEAR
            ),
            np.float32,
        ),
        0,
        1,
    )
    slope, offset = guided_coefficients(guide, small, _RADIUS, _EPS)
    layers = [Image.fromarray(np.ascontiguousarray(slope[..., c]), "F") for c in range(3)]
    layers.append(Image.fromarray(np.ascontiguousarray(offset), "F"))
    unsure = box(((small > _SURE) & (small < 1 - _SURE)).astype(np.float32), _RADIUS + 2) > 0
    plain = Image.fromarray((small * 255 + 0.5).astype(np.uint8), "L").resize(
        (width, height), Image.Resampling.BILINEAR
    )
    found = np.array(plain, np.uint8)
    pixels = np.asarray(rgb)
    across, down = work[0] / width, work[1] / height
    for top in range(0, height, _BAND):
        bottom = min(top + _BAND, height)
        rows = unsure[int(top * down) : min(int(np.ceil(bottom * down)) + 1, work[1])]
        columns = np.flatnonzero(rows.any(axis=0))
        if columns.size == 0:
            continue  # all sure here: the mask as it is
        left = max(int(columns[0] / across) - 2, 0)
        right = min(int(np.ceil((columns[-1] + 1) / across)) + 2, width)
        box_ = (left * across, top * down, right * across, bottom * down)
        grown = [
            np.asarray(
                layer.resize((right - left, bottom - top), Image.Resampling.BILINEAR, box=box_),
                np.float32,
            )
            for layer in layers
        ]
        here = pixels[top:bottom, left:right].astype(np.float32) / 255.0
        made = guided(here, np.stack(grown[:3], axis=-1), grown[3])
        found[top:bottom, left:right] = (made * 255 + 0.5).astype(np.uint8)
    return found


def cut(
    image: Image.Image, mask: Mask, behind: Behind, colour: tuple[int, int, int]
) -> Image.Image:
    """A part cut out of the picture: on nothing (its see-through parts the mask's, the picture
    kept whole underneath), on a colour, or on the rest blurred. Where the picture is
    see-through itself, the colour shows through it; on the rest blurred, it stays see-through."""
    profile = image.info.get("icc_profile")
    clear = image.getchannel("A") if "A" in image.getbands() else None
    if behind == "nothing":
        made = image.convert("RGBA")
        alpha = np.minimum(np.asarray(made.getchannel("A")), mask)
        made.putalpha(Image.fromarray(alpha, "L"))
    elif behind == "colour":
        shown, rgb = mask, flat(image)
        if clear is not None:  # its own colours, each as much as it shows
            seen = mask.astype(np.uint16) * np.asarray(clear, np.uint16)
            shown = ((seen + 127) // 255).astype(np.uint8)
            rgb = image.convert("RGB")
        made = Image.composite(rgb, Image.new("RGB", rgb.size, colour), Image.fromarray(shown, "L"))
    else:
        ground = _blurred(flat(image), mask, lambda short: _gaussian(short * _BACKDROP / 2))
        rgb = image.convert("RGB") if clear is not None else flat(image)  # its own colours
        made = Image.composite(rgb, ground, Image.fromarray(mask, "L"))
        if clear is not None:
            made.putalpha(clear)
    if isinstance(profile, bytes):
        made.info["icc_profile"] = profile
    return made


def lens_blurred(image: Image.Image, mask: Mask) -> Image.Image:
    """Everything outside the part blurred as a big camera lens would, joined to it softly."""
    profile = image.info.get("icc_profile")
    rgb = flat(image)
    short = min(rgb.size)
    ground = _blurred(rgb, mask, lambda small: _disc(small * _LENS / 2))
    edge = feathered(mask, max(2, round(short * _EDGE)))
    made = Image.composite(rgb, ground, Image.fromarray(edge, "L"))
    if image.mode == "RGBA":
        made.putalpha(image.getchannel("A"))
    if isinstance(profile, bytes):
        made.info["icc_profile"] = profile
    return made


def _blurred(rgb: Image.Image, mask: Mask, kernel: Callable[[float], Floats]) -> Image.Image:
    """The picture blurred by `kernel` (made from the shorter side of a copy 1024 across), in
    light, with what's in the mask left out of the blur so it doesn't bleed into what's round it;
    made the picture's size again."""
    work = grid_size(rgb.size)
    small = np.asarray(rgb.resize(work, Image.Resampling.BOX), np.float32) / 255.0
    light = small**_GAMMA
    outside = 1.0 - (
        np.asarray(Image.fromarray(mask, "L").resize(work, Image.Resampling.BILINEAR), np.float32)
        / 255.0
    )
    shape = kernel(min(work))
    weight = convolved(outside, shape)
    spread = convolved((light * outside[..., None]).astype(np.float32), shape)
    made = np.where(weight[..., None] > 1e-3, spread / np.maximum(weight[..., None], 1e-3), light)
    back = np.clip(made, 0, 1) ** (1 / _GAMMA)
    smaller = Image.fromarray((back * 255 + 0.5).astype(np.uint8))
    return smaller.resize(rgb.size, Image.Resampling.BICUBIC)


def _disc(radius: float) -> Floats:
    """A lens's blur: a disc `radius` pixels across each way, its edge smooth to a pixel."""
    reach = max(1, int(np.ceil(radius)))
    ys, xs = np.mgrid[-reach : reach + 1, -reach : reach + 1].astype(np.float32)
    disc = np.clip(radius + 0.5 - np.hypot(xs, ys), 0, 1)
    return (disc / disc.sum()).astype(np.float32)


def _gaussian(sigma: float) -> Floats:
    """A haze: a bell's curve `sigma` pixels wide."""
    sigma = max(sigma, 0.5)
    reach = max(1, int(np.ceil(sigma * 3)))
    ys, xs = np.mgrid[-reach : reach + 1, -reach : reach + 1].astype(np.float32)
    bell = np.exp(-(xs * xs + ys * ys) / (2 * sigma * sigma))
    return (bell / bell.sum()).astype(np.float32)


def convolved(values: Floats, kernel: Floats) -> Floats:
    """Values spread by a kernel (its middle at its middle), by the fast Fourier transform, the
    edges mirrored so nothing wraps round."""
    reach = kernel.shape[0] // 2
    pad = [(reach, reach), (reach, reach)] + [(0, 0)] * (values.ndim - 2)
    padded = np.pad(values, pad, mode="reflect")
    height, width = padded.shape[:2]
    placed = np.zeros((height, width), np.float32)
    placed[: kernel.shape[0], : kernel.shape[1]] = kernel
    placed = np.roll(placed, (-reach, -reach), axis=(0, 1))
    shape = np.fft.rfft2(placed)
    if values.ndim == 3:
        shape = shape[..., None]
    spread = np.fft.irfft2(
        np.fft.rfft2(padded, axes=(0, 1)) * shape, s=(height, width), axes=(0, 1)
    )
    return spread[reach : reach + values.shape[0], reach : reach + values.shape[1]].astype(
        np.float32
    )
