"""Reading how near each part of a picture is, and making the depth tools with it: portrait blur,
fog and tilt-shift (docs/stack/depth.md; the rules are mado/core/depth.py).

Depth Anything V2 Small reads a picture once, the whole of it squeezed to its 518 square (on the
card when it has room, else the processor), and what it read is kept: in memory for the last few
pictures, and in the data folder's cache (`cache/depth`, a folder for each picture and its
version, as the edits' masks are) as a 16-bit picture of its nearness, so the previews and Save,
made later by the queue or after Mado restarts, use the same depth. A picture as its edits leave
it is read as that. Nothing here touches the picture's file.

The tools are made on a picture at any size (a preview, or the picture made at full size): the
blurs are worked out on a copy 1024 pixels on its longer side (a blurred place has no fine detail
to lose), the depth's edges made to follow that copy's (a guided filter), the subject's mask
keeping its own edges; then joined with the picture itself a band of rows at a time, the picture's
own pixels kept where it's in focus.
"""

import hashlib
import logging
import shutil
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image, PngImagePlugin

from mado.ai import Ai, Timer
from mado.core import depth as rules
from mado.core.depth import (
    READ,
    WORK,
    Depthing,
    Floats,
    at_point,
    behind_subject,
    f_radius,
    firm,
    flat_reading,
    fogged,
    in_focus,
    joined,
    lens_blur,
    lifted,
    linear_to_stored,
    middle_of,
    nearness,
    on_canvas,
    own_haze,
    placed,
    span_of,
    stack_blur,
    subject_near,
    subject_only,
    tilt_radius,
    to_bytes,
    to_linear,
    with_subject,
)
from mado.core.edits import Edit
from mado.core.gainmap import GainMap, alternate, stops_between
from mado.core.gains import resized
from mado.core.hardware import Place
from mado.core.masks import guided, guided_coefficients, running
from mado.editing import Editor, edits_key
from mado.selecting import flat
from mado.upscale import StoppedError

log = logging.getLogger(__name__)

type Pixels = npt.NDArray[np.uint8]
type Mask = npt.NDArray[np.uint8]

_KEPT = 16  # pictures' depth kept in memory
_DAYS = 30  # a picture's depth goes once it hasn't been used for this long
_BAND = 256  # rows joined at a time
_EDGE_RADIUS = 4  # the depth's edges follow the copy's over this many of its pixels
_EDGE_EPS = 4e-4  # how much a flat place smooths the depth rather than follows the picture
_AGREE = 17  # pixels of the copy across which the subject's mask is held past where it's as near
_SPREAD = "spread"  # the PNG texts that keep how deep the picture is
_EDGES = "edges"


@dataclass(frozen=True)
class Reading:
    """What the model read of a picture: its nearness at the model's square (0, the farthest, to
    1, the nearest) and how deep the picture is; where it ran, how long it took and how long it
    waited for the card (none of them, when it was kept)."""

    near: Floats
    spread: float
    edges: float
    place: Place | None = None
    seconds: float = 0.0
    waited: float = 0.0

    @property
    def flat(self) -> bool:
        """A flat picture (a scan, a screenshot): no depth to speak of."""
        return flat_reading(self.spread, self.edges)


class Depths:
    def __init__(self, ai: Ai, editor: Editor, folder: Path) -> None:
        """`folder`: where each picture's depth is kept (the data folder's `cache/depth`)."""
        self._ai = ai
        self._editor = editor
        self._folder = folder
        self._lock = threading.Lock()
        self._reading = threading.Lock()  # one read at a time: the same picture isn't read twice
        self._kept: OrderedDict[str, Reading] = OrderedDict()

    @property
    def ai(self) -> Ai:
        return self._ai

    def read(
        self,
        image: Image.Image,
        key: str,
        edits: tuple[Edit, ...] = (),
        *,
        keep: bool = True,
        timer: Timer | None = None,
        edited: Image.Image | None = None,
    ) -> Reading:
        """How near each part of the picture is (`image`, decoded or a copy of it; `key` names it
        and its version), as the edits leave it (`edited`, when they're made already): kept, or
        read now. Without `keep` (a batch's picture, made once) nothing is kept. Raises
        ModelError when the model isn't downloaded or can't run, and what making the edits
        raises."""
        name = edits_key(key, edits)
        found = self._found(name, key)
        if found is not None:
            return found
        with self._reading:
            found = self._found(name, key)
            if found is not None:
                return found
            state = (
                edited
                if edited is not None
                else self._editor.state(image, key, edits, keep=keep)
                if edits
                else image
            )
            clock = timer or Timer()
            reader, place = self._ai.depth_reader(clock)
            began = time.perf_counter()
            squeezed = flat(state).resize((READ, READ), Image.Resampling.BICUBIC, reducing_gap=3.0)
            raw = reader(rules.readable(np.asarray(squeezed)))
            seen = nearness(raw)
            made = Reading(
                seen.near,
                seen.spread,
                seen.edges,
                place,
                time.perf_counter() - began,
                clock.waited,
            )
            if keep:
                self._store(name, key, made)
            return made

    def kept(self, image_key: str, edits: tuple[Edit, ...] = ()) -> Reading | None:
        """The depth kept for a picture as the edits leave it, without reading it."""
        name = edits_key(image_key, edits)
        return self._found(name, image_key)

    def tidy(self) -> None:
        """As the engine starts: the depth of pictures not used for a month goes."""
        cutoff = time.time() - _DAYS * 86400
        try:
            pictures = list(self._folder.iterdir())
        except OSError:
            return
        for picture in pictures:
            try:
                for each in list(picture.iterdir()):
                    # A depth read is touched each time it's used: the newest file says when.
                    used = max(
                        (inner.stat().st_mtime for inner in each.iterdir()),
                        default=each.stat().st_mtime,
                    )
                    if used < cutoff:
                        shutil.rmtree(each, ignore_errors=True)
                if not any(picture.iterdir()):
                    picture.rmdir()
            except OSError as error:
                log.warning("Mado couldn't tidy %s: %s", picture, error)

    def _found(self, name: str, key: str) -> Reading | None:
        with self._lock:
            kept = self._kept.get(name)
            if kept is not None:
                self._kept.move_to_end(name)
                return Reading(kept.near, kept.spread, kept.edges)
        path = self._path(name, key)
        try:
            with Image.open(path) as stored:
                spread = float(stored.info.get(_SPREAD, "nan"))
                edges = float(stored.info.get(_EDGES, "nan"))
                values = np.asarray(stored, np.float32)
            path.touch()
        except OSError, ValueError:
            return None
        if values.shape != (READ, READ) or not (np.isfinite(spread) and np.isfinite(edges)):
            return None  # read again
        found = Reading((values / 65535.0).astype(np.float32), spread, edges)
        with self._lock:
            self._remember(name, found)
        return found

    def _store(self, name: str, key: str, made: Reading) -> None:
        with self._lock:
            self._remember(name, Reading(made.near, made.spread, made.edges))
        path = self._path(name, key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + ".partial")
            values = (np.clip(made.near, 0, 1) * 65535 + 0.5).astype(np.uint16)
            told = PngImagePlugin.PngInfo()
            told.add_text(_SPREAD, f"{made.spread:.6f}")
            told.add_text(_EDGES, f"{made.edges:.6f}")
            Image.fromarray(values).save(partial, format="PNG", pnginfo=told)  # 16-bit grey
            partial.replace(path)
        except OSError as error:  # kept in memory all the same; it can be read again
            log.warning("Mado couldn't keep a picture's depth in %s: %s", path.parent, error)

    def _remember(self, name: str, found: Reading) -> None:
        self._kept[name] = found
        self._kept.move_to_end(name)
        while len(self._kept) > _KEPT:
            self._kept.popitem(last=False)

    def _path(self, name: str, key: str) -> Path:
        picture, _, version = key.rpartition("|")
        folder = hashlib.sha256(picture.encode()).hexdigest()[:16]
        return self._folder / folder / version / f"{name}.png"


@dataclass(frozen=True)
class Depthed:
    """A picture with its depth tools made, where it was in focus (fractions of it) and whether
    a subject was kept sharp by its own edges."""

    image: Image.Image
    focus: tuple[float, float] | None
    subject: bool


@dataclass(frozen=True)
class Worked:
    """The depth tools worked out on a copy of the whole picture made (`small`, its width and
    height), to be joined with the picture itself, or any part of it, at its own size: the
    nearness on the copy of what's behind the subject, where the subject's mask is the subject,
    the subject's own nearness, the fog's light, the lens blur and what it's focused at, and
    tilt-shift's blurred copy."""

    depthing: Depthing
    small: tuple[int, int]
    short: int  # the copy's shorter side: the circles are in its pixels
    agree: Floats | None  # where the subject's mask is the subject, not a far part of it
    behind: Floats
    at_subject: float | None
    focus_point: tuple[float, float] | None
    focus: float
    haze: Floats | None
    lens: tuple[Floats, Floats, Floats] | None  # behind and front (as stored), and nearer
    most: float
    tilted: Floats | None  # as stored
    span: tuple[float, float]  # what's made of the picture, down it: where the band is placed


def depthed(
    image: Image.Image,
    depthing: Depthing,
    near: Floats,
    canvas: tuple[float, float, float, float],
    picture: tuple[int, int],
    *,
    mask: Mask | None = None,
    found_focus: tuple[float, float] = (0.5, 0.5),
    stop: Callable[[], bool] = lambda: False,
) -> Depthed:
    """The picture made (`image`: a preview, or the picture at full size) with its depth tools:
    fog first (it's in the scene), then portrait blur (the lens), then tilt-shift. `near` is the
    whole picture's nearness (the picture `picture` big, as its edits leave it), `canvas` the
    part of it `image` shows (x, y, width, height in its pixels), `mask` its subject at
    `image`'s size (None: no subject), `found_focus` where Mado found the subject (fractions of
    the picture), for portrait blur's focus when there's no mask and no click. See-through parts
    stay as they are; a grey picture stays grey unless the fog colours it. Raises StoppedError
    when stopped between bands."""
    worked = work_out(image, depthing, near, canvas, picture, mask=mask, found_focus=found_focus)
    made = joined_on(image, (0, 0, image.width, image.height), worked, mask=mask, stop=stop)
    return Depthed(made, worked.focus_point, worked.at_subject is not None)


def work_out(
    whole: Image.Image,
    depthing: Depthing,
    near: Floats,
    canvas: tuple[float, float, float, float],
    picture: tuple[int, int],
    *,
    mask: Mask | None = None,
    found_focus: tuple[float, float] = (0.5, 0.5),
) -> Worked:
    """The depth tools worked out on a copy of `whole`, the whole picture made (at any size: a
    preview's, or its own), as `depthed` takes them; `mask` the subject at `whole`'s size."""
    setting = _setting(whole, depthing, near, canvas, picture, mask=mask, found_focus=found_focus)
    lin = setting.lin
    if depthing.fog is not None and setting.haze is not None:
        lin = fogged(lin, setting.near, depthing.fog.density, setting.haze)
    lens = None
    if depthing.portrait is not None:
        blurred = lens_blur(lin, setting.near, setting.focus, setting.most)
        behind_seen = linear_to_stored(blurred.behind)
        front_seen = linear_to_stored(blurred.front)
        lens = (behind_seen, front_seen, blurred.nearer)
        sharp = in_focus((np.abs(setting.near - setting.focus) * setting.most).astype(np.float32))
        lin = _linear_of(
            joined(linear_to_stored(lin), sharp, behind_seen, front_seen, blurred.nearer)
        )
    tilted = None
    if depthing.tilt is not None:
        small = setting.small
        radius = tilt_radius(small[1], small[0], depthing.tilt, setting.short, setting.span)
        tilted = linear_to_stored(stack_blur(lin, radius))
    return Worked(
        depthing,
        setting.small,
        setting.short,
        setting.agree,
        setting.behind,
        setting.at_subject,
        setting.focus_point,
        setting.focus,
        setting.haze,
        lens,
        setting.most,
        tilted,
        setting.span,
    )


@dataclass(frozen=True)
class _Setting:
    """What the depth tools are worked out from on a copy of the picture made: its size, the
    copy in linear light, how near each point is (the subject's own nearness inside its mask,
    what's behind it round it), what's in focus, the fog's light and the lens's circle."""

    small: tuple[int, int]
    short: int
    lin: Floats
    near: Floats
    agree: Floats | None
    behind: Floats
    at_subject: float | None
    focus_point: tuple[float, float] | None
    focus: float
    haze: Floats | None
    most: float
    span: tuple[float, float]


def gains_depthed(
    gain: GainMap,
    sized: Image.Image,
    depthing: Depthing,
    near: Floats,
    canvas: tuple[float, float, float, float],
    picture: tuple[int, int],
    *,
    mask: Mask | None = None,
    found_focus: tuple[float, float] = (0.5, 0.5),
) -> GainMap:
    """An HDR photo's gain map once its picture is given its depth tools, made again from both
    renditions given the same tools: the picture made (`sized`, before its depth tools) and its
    HDR rendition, each fogged, blurred as a lens or tilt-shifted as `depthed` does them, at the
    gain map's size (at most the copy the tools are worked out on), and the gain between them
    taken again. So fog thins the gain with distance as it thins the light, and a light blurred
    into a disc glows as a disc. `near`, `canvas`, `picture`, `mask` (the subject at `sized`'s
    size) and `found_focus` as `depthed` takes them."""
    width, height = gain.size
    scale = min(WORK / max(width, height), 1.0)
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    gains = resized(gain, size).gains
    small = sized.convert("RGB").resize(size, Image.Resampling.BOX)
    small_mask = (
        np.asarray(Image.fromarray(mask, "L").resize(size, Image.Resampling.BILINEAR))
        if mask is not None
        else None
    )
    setting = _setting(
        small, depthing, near, canvas, picture, mask=small_mask, found_focus=found_focus
    )
    base = setting.lin
    other = alternate(base, gains, gain.info)
    made_base = _tools_in_light(base, depthing, setting)
    made_other = _tools_in_light(np.maximum(other, 0.0), depthing, setting)
    return GainMap(
        stops_between(made_base, made_other, gain.info, colour=gains.ndim == 3), gain.info
    )


def _tools_in_light(lin: Floats, depthing: Depthing, setting: _Setting) -> Floats:
    """The depth tools on a copy in linear light (an HDR rendition's above 1 too), joined in
    light, so both renditions are given exactly the same."""
    if depthing.fog is not None and setting.haze is not None:
        lin = fogged(lin, setting.near, depthing.fog.density, setting.haze)
    if depthing.portrait is not None:
        blurred = lens_blur(lin, setting.near, setting.focus, setting.most)
        sharp = in_focus((np.abs(setting.near - setting.focus) * setting.most).astype(np.float32))
        keep = (sharp * (1.0 - blurred.nearer))[..., None]
        seen = sharp[..., None] * blurred.front + (1.0 - sharp)[..., None] * blurred.behind
        lin = (keep * lin + (1.0 - keep) * seen).astype(np.float32)
    if depthing.tilt is not None:
        small = setting.small
        radius = tilt_radius(small[1], small[0], depthing.tilt, setting.short, setting.span)
        blurred_rows = stack_blur(lin, radius)
        sharp_rows = in_focus(radius[:, :1])[..., None]
        lin = (sharp_rows * lin + (1.0 - sharp_rows) * blurred_rows).astype(np.float32)
    return lin


def _setting(
    whole: Image.Image,
    depthing: Depthing,
    near: Floats,
    canvas: tuple[float, float, float, float],
    picture: tuple[int, int],
    *,
    mask: Mask | None,
    found_focus: tuple[float, float],
) -> _Setting:
    rgb = flat(whole) if "A" not in whole.getbands() else whole.convert("RGB")
    width, height = rgb.size
    scale = min(WORK / max(width, height), 1.0)
    small = (max(1, round(width * scale)), max(1, round(height * scale)))
    copy = rgb.resize(small, Image.Resampling.BOX) if scale < 1 else rgb
    copy_pixels = np.asarray(copy)
    lin = to_linear(copy_pixels)
    near_w = _edges(placed(near, canvas, picture, small), copy_pixels)
    mask_w = _small_mask(mask, small)
    short = min(small)

    # The subject: its own nearness inside its mask (what isn't as near as it taken out), what's
    # behind it round it.
    portrait = depthing.portrait
    at_subject = subject_near(near_w, mask_w) if mask_w is not None else None
    agree: Floats | None = None
    if mask_w is not None and at_subject is not None:
        # Where the mask is as near as the subject, held a little past its edge, so the mask's own
        # crisp edge stays and only a far part of it (a sun) goes.
        alike = subject_only(near_w, np.ones_like(mask_w), at_subject)
        agree = running(alike, _AGREE, np.maximum)
        mask_w = mask_w * agree
        at_subject = subject_near(near_w, mask_w)
    if mask_w is None or at_subject is None:
        mask_w, at_subject, agree = None, None, None
    behind = behind_subject(near_w, mask_w) if mask_w is not None else near_w
    # On the copy, a pixel the subject's edge crosses is all the subject's, so none of its colour
    # is blurred into what's behind it (a dark halo round it); the edge itself is the mask's,
    # joined at full size.
    near_ref = (
        with_subject(behind, (mask_w > 0).astype(np.float32), at_subject)
        if mask_w is not None and at_subject is not None
        else near_w
    )
    focus_point: tuple[float, float] | None = None
    focus = 0.0
    if portrait is not None:
        if portrait.focus is not None:
            focus_point = on_canvas(portrait.focus, canvas, picture)
            focus = at_point(near_ref, focus_point)
        elif at_subject is not None and mask_w is not None:
            focus = at_subject
            focus_point = middle_of(mask_w)
        else:
            focus_point = on_canvas(found_focus, canvas, picture)
            focus = at_point(near_ref, focus_point)

    # The fog's light (the picture's own haze, or the colour chosen) and the lens's circle.
    haze = None
    if depthing.fog is not None:
        haze = (
            to_linear(np.array([depthing.fog.colour], np.uint8))[0]
            if depthing.fog.colour is not None
            else own_haze(lin, near_ref)
        )
    most = f_radius(portrait.aperture, short) if portrait is not None else 0.0
    return _Setting(
        small,
        short,
        lin,
        near_ref,
        agree,
        behind,
        at_subject,
        focus_point,
        focus,
        haze,
        most,
        span_of(canvas, picture),
    )


def joined_on(
    image: Image.Image,
    at: tuple[int, int, int, int],
    worked: Worked,
    *,
    mask: Mask | None = None,
    stop: Callable[[], bool] = lambda: False,
) -> Image.Image:
    """`image`, the whole picture made or a part of it (`at`: its left and top in the picture
    made, and the picture made's width and height), with the depth tools `worked` out on a copy
    of the whole: a band of rows at a time, at its own size, its own pixels kept where it's in
    focus; `mask` is the subject on `image`, at its size. Raises StoppedError when stopped
    between bands."""
    depthing = worked.depthing
    profile = image.info.get("icc_profile")
    grey = image.mode in ("L", "LA", "I", "I;16", "1", "F")
    alpha = image.getchannel("A") if "A" in image.getbands() else None
    rgb = flat(image) if alpha is None else image.convert("RGB")
    width, height = rgb.size
    full = np.asarray(rgb)
    out = np.empty_like(full)
    grow = _Grower(worked.small, at, (width, height))
    subject = mask is not None and worked.at_subject is not None and worked.agree is not None
    agree_layer = grow.layer(worked.agree) if subject and worked.agree is not None else None
    behind_layer = grow.layer(worked.behind)
    lens_layers = (
        (grow.layers(worked.lens[0]), grow.layers(worked.lens[1]), grow.layer(worked.lens[2]))
        if worked.lens is not None
        else None
    )
    tilt_layers = grow.layers(worked.tilted) if worked.tilted is not None else None
    # Tilt-shift's circle by row of the picture made, in the copy's pixels, as it was blurred.
    tilt_rows = (
        tilt_radius(at[3], 1, depthing.tilt, worked.short, worked.span)[at[1] : at[1] + height, 0]
        if depthing.tilt is not None
        else None
    )
    for top in range(0, height, _BAND):
        if stop():
            raise StoppedError
        bottom = min(top + _BAND, height)
        band = full[top:bottom].astype(np.float32) / 255.0
        near_here = grow.band(behind_layer, top, bottom)
        if mask is not None and agree_layer is not None and worked.at_subject is not None:
            shown = firm(mask[top:bottom].astype(np.float32) / 255.0) * grow.band(
                agree_layer, top, bottom
            )
            near_here = with_subject(near_here, shown, worked.at_subject)
        if worked.haze is not None and depthing.fog is not None:
            lin = fogged(to_linear(full[top:bottom]), near_here, depthing.fog.density, worked.haze)
            band = linear_to_stored(lin)
        if lens_layers is not None:
            behind_seen, front_seen, nearer_seen = lens_layers
            sharp = in_focus((np.abs(near_here - worked.focus) * worked.most).astype(np.float32))
            band = joined(
                band,
                sharp,
                grow.bands(behind_seen, top, bottom),
                grow.bands(front_seen, top, bottom),
                grow.band(nearer_seen, top, bottom),
            )
        if tilt_layers is not None and tilt_rows is not None:
            sharp_rows = in_focus(tilt_rows[top:bottom])[:, None, None]
            seen = grow.bands(tilt_layers, top, bottom)
            mixed = (sharp_rows * band + (1.0 - sharp_rows) * seen).astype(np.float32)
            band = linear_to_stored(lifted(_linear_of(mixed)))
        out[top:bottom] = to_bytes(band)
    made = Image.fromarray(out)
    if alpha is not None:
        made.putalpha(alpha)
    elif grey and (depthing.fog is None or depthing.fog.colour is None) and depthing.tilt is None:
        made = made.convert("L")
    if isinstance(profile, bytes):
        made.info["icc_profile"] = profile
    return made


class _Grower:
    """What was worked out on the copy (`small`, width and height) made the size of the picture
    made, for a part of it (`at`: its left and top, and the picture made's width and height;
    `size`, the part's width and height), a band of rows at a time, smoothly (Pillow's
    bilinear)."""

    def __init__(
        self, small: tuple[int, int], at: tuple[int, int, int, int], size: tuple[int, int]
    ) -> None:
        self._small = small
        self._at = at
        self._size = size

    def layer(self, values: Floats) -> Image.Image:
        return Image.fromarray(np.ascontiguousarray(values, np.float32), "F")

    def layers(self, values: Floats) -> list[Image.Image]:
        return [self.layer(values[..., channel]) for channel in range(values.shape[2])]

    def band(self, layer: Image.Image, top: int, bottom: int) -> Floats:
        left, first, across, down = self._at
        kx, ky = self._small[0] / across, self._small[1] / down
        box = (
            left * kx,
            (first + top) * ky,
            (left + self._size[0]) * kx,
            (first + bottom) * ky,
        )
        grown = layer.resize((self._size[0], bottom - top), Image.Resampling.BILINEAR, box=box)
        return np.asarray(grown, np.float32)

    def bands(self, layers: list[Image.Image], top: int, bottom: int) -> Floats:
        return np.stack([self.band(each, top, bottom) for each in layers], axis=-1)


def subject_at(near: Floats, mask: Mask | None) -> float | None:
    """How near the subject (`mask`, at the nearness's size) is, what isn't as near as it left
    out; None without one."""
    if mask is None or not mask.any():
        return None
    soft = mask.astype(np.float32) / 255.0
    found = subject_near(near, soft)
    if found is None:
        return None
    return subject_near(near, subject_only(near, soft, found))


def edges_of(near: Floats, guide: Pixels) -> Floats:
    """The depth's edges made to follow the picture's own (`guide`, the same size)."""
    return _edges(near, guide)


def _edges(near: Floats, guide: Pixels) -> Floats:
    """The depth's edges made to follow the picture's own (`guide`, the same size), as a cut-out's
    mask is: crisp where the picture is, smooth where it's flat."""
    values = guide.astype(np.float32) / 255.0
    slope, offset = guided_coefficients(values, near, _EDGE_RADIUS, _EDGE_EPS)
    return guided(values, slope, offset).astype(np.float32)


def _small_mask(mask: Mask | None, size: tuple[int, int]) -> Floats | None:
    """The subject's mask on the copy blurred, 0 to 1, made firm."""
    if mask is None or not mask.any():
        return None
    small = Image.fromarray(mask, "L").resize(size, Image.Resampling.BILINEAR)
    return firm(np.asarray(small, np.float32) / 255.0)


def _linear_of(stored: Floats) -> Floats:
    """Stored values (0 to 1) in linear light."""
    return to_linear(to_bytes(stored))
