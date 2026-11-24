"""3D photos, by their rules: a short video of a picture with the view moving gently through it by
its depth (a slow push in, a sway or a circle), looping. The view's path, how each point moves
by how near it is, where each frame's pixels come from, what the moving view uncovers behind
near things, the video's size and length, and the encoders that make it. Pure: numpy only.

A point a nearness `d` moves by `(d - pivot)` times the view's shift and grows by as much times
its push, so what's as near as the pivot (the subject) stays put, nearer things move one way and
farther ones the other; the whole is made a little bigger, so the frame's edges never show past
the picture. Each frame is found backwards, a point of the frame at a time: where in the picture
it came from, found again a few times as the nearness there says (docs/stack/depth.md).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, pi, sin
from typing import Literal

import numpy as np
import numpy.typing as npt

from mado.core.masks import box, running

type Floats = npt.NDArray[np.float32]
type Motion = Literal["push", "sway", "circle"]
type Fill = Literal["fast", "best"]
type Size = Literal["1080p", "4k"]
type Format = Literal["mp4", "webp"]

MOTIONS: tuple[Motion, ...] = ("push", "sway", "circle")
FPS = 30
SECONDS = (3, 5, 8)  # the lengths a 3D photo can be
LENGTH = 5  # seconds, at first
SHIFT = 0.035  # at full amount, a point a whole nearness from the pivot moves this much of the
# picture's shorter side
PUSH = 0.1  # and grows by this much, pushing in
AMOUNT = 0.5  # how much the view moves, 0 to 1, at first
SIDES: dict[Size, int] = {"1080p": 1920, "4k": 3840}  # a video's longer side at most
WEBP_SIDE = 1280  # an animated WebP's longer side at most: its files grow fast
_ITERATIONS = 3  # where a frame's point came from, found again this many times
_JUMP = 0.08  # nearness that changes this much within the view's reach is an edge to fill behind
_STRETCHED = (0.25, 0.6)  # a frame's area from less than this of its own in the picture shows
# the background layer, more than the second the picture itself, between them a mix
_MISSED = 0.75  # pixels a point found backwards may miss where it came from by and still count
_FILLED = 3  # the layer behind is filled over this many times the view's reach inside a near
# thing's edge, so what fills the part it uncovers is nearer what's farther than the near thing
# H.264 encoders that come with their licence, in the order Mado tries them: Windows' own (Media
# Foundation's) first, then the graphics cards'. OpenH264 is never used: Cisco's patent licence
# for it covers only the builds Cisco publishes.
ENCODERS: dict[str, str] = {
    "h264_mf": "Windows' own video encoder",
    "h264_nvenc": "NVIDIA's encoder (NVENC)",
    "h264_amf": "AMD's encoder (AMF)",
    "h264_qsv": "Intel Quick Sync",
}


@dataclass(frozen=True)
class Moving:
    """A 3D photo as the owner asks for it."""

    motion: Motion = "push"
    seconds: int = LENGTH
    amount: float = AMOUNT  # 0 to 1
    fill: Fill = "fast"  # what's uncovered: stretched from beside it, or drawn by LaMa
    size: Size = "1080p"
    format: Format = "mp4"


@dataclass(frozen=True)
class View:
    """Where the view is in a frame: its shift (pixels across and down, for a whole nearness from
    the pivot) and its push (how much a whole nearness nearer grows)."""

    across: float
    down: float
    push: float


def view(motion: Motion, t: float, shift: float, push: float) -> View:
    """The view at `t` (0 to 1 round the loop; 1 is 0 again, so it loops without a seam): a slow
    push in and back out, a sway from side to side, or a circle. `shift` is the most it moves in
    pixels, `push` the most it pushes in."""
    turn = 2 * pi * t
    match motion:
        case "push":
            return View(0.0, -0.15 * shift * sin(turn), push * (1 - cos(turn)) / 2)
        case "sway":
            return View(shift * sin(turn), 0.0, 0.25 * push * (1 - cos(2 * turn)) / 2)
        case "circle":
            return View(shift * cos(turn), 0.6 * shift * sin(turn), 0.2 * push)


def path(moving: Moving, short: int) -> list[View]:
    """Every frame's view, once round the loop, for a video `short` pixels on its shorter side."""
    frames = max(2, moving.seconds * FPS)
    shift = SHIFT * moving.amount * short
    push = PUSH * moving.amount
    return [view(moving.motion, at / frames, shift, push) for at in range(frames)]


def margin(views: Sequence[View], size: tuple[int, int], pivot: float) -> float:
    """How much bigger the whole is made so a frame's edges never show past the picture: enough
    for the farthest any point moves out from its place on any frame."""
    width, height = size
    reach = max(pivot, 1.0 - pivot)  # the most a point's nearness differs from the pivot's
    most = 1.0
    for each in views:
        for half, moved in ((width / 2, abs(each.across)), (height / 2, abs(each.down))):
            grown = half * (1 - abs(each.push) * reach) - moved * reach
            most = max(most, half / max(grown, half * 0.5))
    return most


def sources(
    near: Floats,
    at: View,
    pivot: float,
    scale: float,
    grid: tuple[Floats, Floats],
    size: tuple[int, int],
) -> tuple[Floats, Floats, Floats]:
    """Where each point of a frame (`grid`: its places across and down, in the frame's pixels;
    `size` the frame's width and height) came from in the picture, as the nearness (`near`, the
    frame's size) says: found backwards, again and again, each time by the nearness where it was
    last found. Also how far each missed (pixels): a point that never settles is behind
    something near that moved away."""
    width, height = size
    cx, cy = (width - 1) / 2, (height - 1) / 2
    qx, qy = grid
    bx, by = (qx - cx) / scale, (qy - cy) / scale  # the frame's point, before its push and shift
    px, py = bx + cx, by + cy
    for _ in range(_ITERATIONS):
        offset = sample(near, px, py) - pivot
        grow = 1.0 + at.push * offset
        px = cx + (bx - at.across * offset) / grow
        py = cy + (by - at.down * offset) / grow
    offset = sample(near, px, py) - pivot
    grow = 1.0 + at.push * offset
    landed_x = (px - cx) * grow + at.across * offset
    landed_y = (py - cy) * grow + at.down * offset
    missed = np.hypot(landed_x - bx, landed_y - by) * scale
    return px.astype(np.float32), py.astype(np.float32), missed.astype(np.float32)


def sample(values: npt.NDArray[np.generic], xs: Floats, ys: Floats) -> Floats:
    """Values (height × width, or × channels; any number type) at fractional places, each
    between its four nearest, the edges held; as 32-bit floats. The places can be any shape."""
    height, width = values.shape[:2]
    x = np.clip(xs, 0, width - 1)
    y = np.clip(ys, 0, height - 1)
    x0 = np.minimum(x.astype(np.int32), max(width - 2, 0))
    y0 = np.minimum(y.astype(np.int32), max(height - 2, 0))
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    flat: npt.NDArray[np.generic] = values.reshape(height * width, -1)
    here = y0 * width + x0
    right = np.minimum(here + 1, height * width - 1)
    below = np.minimum(here + width, height * width - 1)
    corner = np.minimum(here + width + 1, height * width - 1)
    a: Floats = np.take(flat, here, axis=0).astype(np.float32)
    b: Floats = np.take(flat, right, axis=0).astype(np.float32)
    c: Floats = np.take(flat, below, axis=0).astype(np.float32)
    d: Floats = np.take(flat, corner, axis=0).astype(np.float32)
    across, down = fx[..., None], fy[..., None]
    # In place, as a frame's colours are millions of values: a becomes the top's, c the bottom's,
    # then a the place's.
    b -= a
    b *= across
    a += b
    d -= c
    d *= across
    c += d
    c -= a
    c *= down
    a += c
    return a[..., 0] if values.ndim == 2 else a


def own_share(xs: Floats, ys: Floats, scale: float, step: int = 1) -> Floats:
    """How much of its own area each point of a frame takes from the picture (`xs`, `ys`: where
    the frame's points `step` pixels apart came from; 1 as the picture is, made `scale` bigger):
    far less where the view stretches the picture over what it uncovered."""
    dxx = np.gradient(xs, axis=1)
    dyy = np.gradient(ys, axis=0)
    dxy = np.gradient(xs, axis=0)
    dyx = np.gradient(ys, axis=1)
    area = np.abs(dxx * dyy - dxy * dyx) * (scale / step) ** 2
    return area.astype(np.float32)


def shown(share: Floats, missed: Floats) -> Floats:
    """How much of each point of a frame is the picture itself (near and far as they are), not
    the layer behind it: none where it's stretched over what the view uncovered, or never found
    where it came from."""
    low, high = _STRETCHED
    kept = np.clip((share - low) / (high - low), 0.0, 1.0)
    found = np.clip(1.0 - (missed - _MISSED) / _MISSED, 0.0, 1.0)
    return box((kept * found).astype(np.float32), 1)


def behind(near: Floats, reach: int) -> tuple[Floats, Floats]:
    """What the moving view can uncover: the parts of near things within `reach` pixels of
    something farther (by `_JUMP` or more), 0 to 1; and the nearness behind them, what's farther
    carried in, so the layer behind moves as the background does."""
    window = 2 * reach + 1
    farthest = running(near, window, np.minimum)
    uncovers = np.clip((near - farthest - _JUMP) / _JUMP, 0.0, 1.0).astype(np.float32)
    back = (uncovers * farthest + (1.0 - uncovers) * near).astype(np.float32)
    return uncovers, box(back, 2)


def to_fill(near: Floats, reach: int) -> npt.NDArray[np.bool_]:
    """What's filled for the layer behind: near things within three times the view's `reach` of
    something farther, so the part the view can uncover (within its reach) is filled from what's
    farther, which is nearer it, never from the near thing's own colours."""
    farthest = running(near, 2 * _FILLED * reach + 1, np.minimum)
    return near - farthest > 1.5 * _JUMP  # where `behind` says it uncovers more than half


def pivot_of(near: Floats, subject: float | None) -> float:
    """What stays put as the view moves: the subject's nearness, or the middle of the picture's
    without one."""
    if subject is not None:
        return subject
    return float(np.median(near))


def video_size(width: int, height: int, size: Size) -> tuple[int, int]:
    """A video's width and height from a picture's: its shape, its longer side `SIDES[size]` at
    most (never bigger than the picture), each even, as H.264 asks."""
    longest = SIDES[size]
    scale = min(longest / max(width, height), 1.0)
    return _even(width * scale), _even(height * scale)


def webp_size(width: int, height: int) -> tuple[int, int]:
    scale = min(WEBP_SIDE / max(width, height), 1.0)
    return _even(width * scale), _even(height * scale)


def _even(value: float) -> int:
    """A side made even, as H.264 asks, never past what it was."""
    return max(2, int(value) // 2 * 2)


def bitrate(width: int, height: int) -> int:
    """The bits a second a video is made at: plenty for a picture's detail moving slowly (12 Mb/s
    at 1080p, 40 at 4K)."""
    return int(max(2_000_000, min(40_000_000, 12_000_000 * width * height / (1920 * 1080))))


def about_bytes(moving: Moving, width: int, height: int) -> int:
    """About how big a 3D photo comes out: its bits a second for an MP4; an animated WebP's
    frames at about a sixth of a byte a pixel."""
    if moving.format == "mp4":
        return bitrate(width, height) * moving.seconds // 8
    return int(width * height * 0.16 * moving.seconds * FPS)


def encoder_args(encoder: str, width: int, height: int) -> list[str]:
    """What ffmpeg is told to make H.264 with each encoder, at this size's bits a second."""
    rate = str(bitrate(width, height))
    match encoder:
        case "h264_mf":
            return ["-c:v", "h264_mf", "-rate_control", "pc_vbr", "-b:v", rate, "-g", "60"]
        case "h264_nvenc":
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-b:v", rate, "-g", "60"]
        case "h264_amf":
            return ["-c:v", "h264_amf", "-quality", "quality", "-b:v", rate, "-g", "60"]
        case "h264_qsv":
            return ["-c:v", "h264_qsv", "-preset", "slower", "-b:v", rate, "-g", "60"]
        case _:
            raise ValueError(encoder)


def check_command(ffmpeg: Sequence[str], encoder: str) -> list[str]:
    """ffmpeg making a fifth of a second of grey with `encoder`: whether it works on this PC."""
    return [
        *ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=gray:s=320x240:r=30:d=0.2",
        "-pix_fmt",
        "yuv420p",
        *encoder_args(encoder, 320, 240),
        "-f",
        "null",
        "-",
    ]


def encode_command(
    ffmpeg: Sequence[str], encoder: str, width: int, height: int, out: str
) -> list[str]:
    """ffmpeg taking a video's frames (RGB in sRGB, one after another) and writing them as an MP4
    with `encoder`, ready to play as it loads: turned to video's colours by HD's own matrix, and
    tagged so, so a player shows them as they were rather than guessing."""
    return [
        *ffmpeg,
        "-hide_banner",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-vf",
        "scale=out_color_matrix=bt709:out_range=tv",
        "-pix_fmt",
        "yuv420p",
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "iec61966-2-1",
        *encoder_args(encoder, width, height),
        # Written into the video itself, as not every encoder writes them: HD's primaries and
        # matrix, sRGB's curve, video's range.
        "-bsf:v",
        "h264_metadata=colour_primaries=1:transfer_characteristics=13:matrix_coefficients=1"
        ":video_full_range_flag=0",
        "-movflags",
        "+faststart",
        "-an",
        "-y",
        out,
    ]


MOTION_WORDS = "into a 3D photo"  # how History's words for a 3D photo start


def moving_words(moving: Moving) -> str:
    """A 3D photo as History says it: "into a 3D photo, pushing in for 5 s"."""
    how = {"push": "pushing in", "sway": "swaying", "circle": "circling"}[moving.motion]
    return f"{MOTION_WORDS}, {how} for {moving.seconds} s"
