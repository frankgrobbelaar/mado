"""Reading the words in a picture at Best: the pure half of PP-OCRv6 small, its detector and its
recogniser (mado/ocr.py runs them, docs/stack/search.md has what was measured).

The detector sees the picture fitted into a canvas of a fixed size, so the graphics card compiles
it once, and answers with a map of how likely each pixel is to be text. The lines are the blobs
of that map: each one's smallest turned rectangle, kept when the map is sure enough over it, then
grown a little, as text's edges fade in the map. Each line is cut out of the picture straight,
48 pixels high, and read by the recogniser, which answers, for each column, how likely each of
its characters is: the likeliest, with repeats and blanks taken out, are the line's words (CTC).

The steps and their numbers are RapidOCR's (Apache-2.0, LICENSE-RapidOCR.txt beside this file),
itself PaddleOCR's: the map read at 0.3 and a line kept where it averages 0.5, grown by 1.6 times
its area over its outline (DB's "unclip", through pyclipper), lines read 48 pixels high and kept
when the recogniser averages 0.5 over their letters, the angle classifier left out. Ported to
NumPy: OpenCV's contours are runs of text pixels joined row to row, its smallest rectangle the
turn of the blob's hull that needs the least room. Pure: arrays come in and go out.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import pyclipper
from PIL import Image

type Map = npt.NDArray[np.float32]  # the detector's answer: how likely each pixel is text, 0 to 1
type Pixels = npt.NDArray[np.uint8]  # a picture's RGB, height × width × 3
type Point = tuple[float, float]

THRESHOLD = 0.3  # a pixel is text where the map says more than this
BOX_SCORE = 0.5  # a line is kept where the map averages at least this over it
UNCLIP = 1.6  # how much a line grows: this times its area, over its outline
MIN_SIDE = 3  # pixels: a blob narrower than this isn't a line
MOST_LINES = 1000  # lines looked at in one picture, at most
# On a thumbnail, a line thicker than this share of the picture's shorter side isn't words: the
# detector takes a plain sky or wall for text there (docs/stack/search.md).
TALLEST = 0.25
LINE_HEIGHT = 48  # the recogniser reads a line this many pixels high
LINE_WIDTH = 320  # and at least this wide
MIN_LETTERS = 2  # a line read is kept with this many letters or digits at least
WORD_SCORE = 0.5  # a line's words are kept when the recogniser averages this over its letters
SAME_ROW = 10  # pixels: lines whose tops are nearer than this are read as one row, left first
_TALL = 1.5  # a line this many times taller than wide is turned to be read


@dataclass(frozen=True)
class Placed:
    """A picture fitted into the detector's canvas: the canvas, and how much the picture was
    scaled to fit it (its top-left corner at the canvas's; the rest padded)."""

    width: int
    height: int
    scale: float


@dataclass(frozen=True)
class Line:
    """A line of text found in a picture: its four corners in the picture's pixels, top-left
    first and clockwise, and how sure the detector was of it."""

    corners: tuple[Point, Point, Point, Point]
    score: float


@dataclass(frozen=True)
class Words:
    """What the recogniser read on a line, and how sure it was."""

    text: str
    score: float


def placed(width: int, height: int, canvases: Sequence[tuple[int, int]]) -> Placed:
    """The canvas a picture is read on: of those the detector's sessions take, the one it fills
    most once fitted inside (the smaller on a tie), never grown past its own size more than
    twice, as a small picture's letters wouldn't get clearer."""
    best: Placed | None = None
    best_filled = -1.0
    for canvas_width, canvas_height in canvases:
        scale = min(canvas_width / width, canvas_height / height, 2.0)
        filled = (width * scale * height * scale) / (canvas_width * canvas_height)
        bigger = best is not None and canvas_width * canvas_height > best.width * best.height
        if filled > best_filled + 1e-9 or (abs(filled - best_filled) <= 1e-9 and not bigger):
            best, best_filled = Placed(canvas_width, canvas_height, scale), filled
    if best is None:
        raise ValueError("The detector needs at least one canvas.")
    return best


def on_white(picture: Image.Image) -> Image.Image:
    """A picture as the readers of words see it, in red, green and blue: what's see-through laid
    on white, as a page or a screen shows it (dark words on a see-through PNG would otherwise
    vanish into black)."""
    if picture.mode in ("RGBA", "LA", "PA") or "transparency" in picture.info:
        rgba = picture.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, rgba).convert("RGB")
    return picture.convert("RGB")


def detector_input(pixels: Pixels, canvas: Placed) -> npt.NDArray[np.float32]:
    """A picture (red, green and blue), already scaled to fit, as the detector takes it: its
    colours from -1 to 1 as blue, green and red (as OpenCV reads a picture, and PaddleOCR's
    models were trained) in the canvas's top-left corner, the rest black, as
    1 × 3 × height × width."""
    height, width = pixels.shape[:2]
    if height > canvas.height or width > canvas.width:
        raise ValueError("The picture is bigger than its canvas: scale it first.")
    tensor = np.full((3, canvas.height, canvas.width), -1.0, np.float32)
    bgr = pixels[:, :, 2::-1].transpose(2, 0, 1)
    tensor[:, :height, :width] = bgr.astype(np.float32) / 127.5 - 1.0
    return tensor[None]


def lines(
    found: Map, canvas: Placed, width: int, height: int, *, tallest: float | None = None
) -> list[Line]:
    """The lines of text in the detector's map, in the picture's pixels (`width` × `height`),
    in reading order: top to bottom, then left to right within a row."""
    mask = _dilated(found > THRESHOLD)
    kept: list[Line] = []
    for points in _blobs(mask)[:MOST_LINES]:
        box, short = _smallest_box(points)
        if short < MIN_SIDE:
            continue
        score = _mean_inside(found, box)
        if score < BOX_SCORE:
            continue
        grown, short = _smallest_box(_unclipped(box))
        if short < MIN_SIDE + 2:
            continue
        corners = _in_picture(grown / canvas.scale, width, height)
        across, down = _side(corners[0], corners[1]), _side(corners[0], corners[3])
        thick = tallest is not None and min(across, down) > tallest * min(width, height)
        if min(across, down) <= MIN_SIDE or thick:
            continue
        kept.append(Line(corners, score))
    return reading_order(kept)


def reading_order(found: Sequence[Line]) -> list[Line]:
    """Lines top to bottom, those whose tops are within SAME_ROW of the one above read left to
    right, as one row."""
    by_top = sorted(found, key=lambda line: line.corners[0][1])
    rows: list[int] = []
    row = 0
    for at, line in enumerate(by_top):
        if at and line.corners[0][1] - by_top[at - 1].corners[0][1] >= SAME_ROW:
            row += 1
        rows.append(row)
    order = sorted(range(len(by_top)), key=lambda at: (rows[at], by_top[at].corners[0][0]))
    return [by_top[at] for at in order]


def cut_out(picture: Image.Image, line: Line) -> Image.Image | None:
    """A line cut out of the picture straight, as wide and high as its sides; turned when it's
    far taller than wide (letters running down). None for a line with no width or height."""
    top_left, top_right, bottom_right, bottom_left = line.corners
    width = int(max(_side(top_left, top_right), _side(bottom_left, bottom_right)))
    height = int(max(_side(top_left, bottom_left), _side(top_right, bottom_right)))
    if width < 1 or height < 1:
        return None
    quad = (*top_left, *bottom_left, *bottom_right, *top_right)
    straight = picture.transform(
        (width, height), Image.Transform.QUAD, quad, resample=Image.Resampling.BICUBIC
    )
    if height / width >= _TALL:
        straight = straight.transpose(Image.Transpose.ROTATE_90)
    return straight


def line_width(cut: Image.Image, widths: Sequence[int] = ()) -> int:
    """The width a line is read at, LINE_HEIGHT high: as wide as its shape asks (LINE_WIDTH at
    least), or, given the widths the recogniser's sessions take, the smallest that holds it (the
    widest, squeezed, when none does)."""
    wanted = max(LINE_WIDTH, math.ceil(LINE_HEIGHT * cut.width / cut.height))
    if not widths:
        return wanted
    for each in sorted(widths):
        if each >= wanted:
            return each
    return max(widths)


def recogniser_input(cuts: Sequence[Image.Image], width: int) -> npt.NDArray[np.float32]:
    """Lines as the recogniser takes them: each LINE_HEIGHT high and as wide as its shape (no
    wider than `width`), its colours from -1 to 1 as blue, green and red, the rest of `width` 0,
    as N × 3 × 48 × width."""
    batch = np.zeros((len(cuts), 3, LINE_HEIGHT, width), np.float32)
    for at, cut in enumerate(cuts):
        shown = min(width, math.ceil(LINE_HEIGHT * cut.width / cut.height))
        resized = cut.convert("RGB").resize((shown, LINE_HEIGHT), Image.Resampling.BILINEAR)
        bgr = np.asarray(resized, np.float32)[:, :, ::-1]  # as the detector's (above)
        values = bgr.transpose(2, 0, 1) / 127.5 - 1.0
        batch[at, :, :, :shown] = values
    return batch


def decoded(found: npt.NDArray[np.float32], characters: Sequence[str]) -> list[Words]:
    """The recogniser's answer (lines × columns × its characters, a blank first and a space
    last) as words: each column's likeliest character, repeats run together and blanks left
    out, with how sure it was on average over the letters kept."""
    alphabet = ["", *characters, " "]
    best = found.argmax(axis=2)
    sure = found.max(axis=2)
    read: list[Words] = []
    for picks, odds in zip(best, sure, strict=True):
        keep = np.ones(len(picks), bool)
        keep[1:] = picks[1:] != picks[:-1]
        keep &= picks != 0
        indexes: list[int] = picks[keep].tolist()
        letters = "".join(alphabet[index] for index in indexes if index < len(alphabet))
        kept = odds[keep]
        read.append(Words(letters, float(kept.mean()) if kept.size else 0.0))
    return read


def text_of(read: Sequence[Words]) -> str:
    """The words a picture shows, a line of text to a line: those the recogniser was sure of,
    worth keeping."""
    kept = [" ".join(each.text.split()) for each in read if each.score >= WORD_SCORE]
    return "\n".join(each for each in kept if worth_keeping(each))


def worth_keeping(line: str) -> bool:
    """Whether a line read is words worth searching: MIN_LETTERS letters or digits at least.
    A shape in a photo read as one ("1", "O", "人", a dot) is noise, and a search for one letter
    would find too much to help."""
    return sum(letter.isalnum() for letter in line) >= MIN_LETTERS


# The blobs of the map.


def _dilated(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """The mask grown by a 2 × 2 square, as DB's post-processing does: blobs a pixel apart
    join."""
    grown = mask.copy()
    grown[1:, :] |= mask[:-1, :]
    widened = grown.copy()
    widened[:, 1:] |= grown[:, :-1]
    return widened


def _blobs(mask: npt.NDArray[np.bool_]) -> list[npt.NDArray[np.float64]]:
    """Each blob of the mask (pixels touching, corners too) as the centres of the first and last
    pixel of each of its runs along a row: enough for its hull."""
    rows, starts, ends = _runs(mask)
    if rows.size == 0:
        return []
    parent = list(range(rows.size))

    def root(at: int) -> int:
        while parent[at] != at:
            parent[at] = parent[parent[at]]
            at = parent[at]
        return at

    every_row = np.arange(mask.shape[0] + 1, dtype=np.int64)
    first_of = cast("list[int]", np.searchsorted(rows, every_row).tolist())
    for row in range(mask.shape[0] - 1):
        top, middle, bottom = first_of[row], first_of[row + 1], first_of[row + 2]
        if top == middle or middle == bottom:
            continue
        # A run below touches each run above that reaches its first pixel's left neighbour and
        # starts by its last pixel's right neighbour: runs in a row never overlap, so those are
        # a stretch of the row above.
        lows: list[int] = np.searchsorted(
            ends[top:middle], starts[middle:bottom] - 1, side="left"
        ).tolist()
        highs: list[int] = np.searchsorted(
            starts[top:middle], ends[middle:bottom] + 1, side="right"
        ).tolist()
        for offset, (low, high) in enumerate(zip(lows, highs, strict=True)):
            for each in range(low, high):
                a, b = root(top + each), root(middle + offset)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    owners = np.array([root(at) for at in range(rows.size)])
    order = np.argsort(owners, kind="stable")
    splits = np.flatnonzero(np.diff(owners[order])) + 1
    found: list[npt.NDArray[np.float64]] = []
    for members in np.split(order, splits):
        ys = rows[members].astype(np.float64)
        points = np.concatenate(
            [np.stack([starts[members], ys], axis=1), np.stack([ends[members], ys], axis=1)]
        )
        found.append(points.astype(np.float64))
    return found


def _runs(
    mask: npt.NDArray[np.bool_],
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    """Every run of set pixels along a row: its row, its first and its last column, row by row
    and left to right."""
    height, width = mask.shape
    padded = np.zeros((height, width + 2), np.int8)
    padded[:, 1:-1] = mask
    steps = np.diff(padded, axis=1)
    rows, starts = np.nonzero(steps == 1)
    _, after = np.nonzero(steps == -1)
    return rows.astype(np.int64), starts.astype(np.int64), after.astype(np.int64) - 1


def _hull(points: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """The convex hull of some points, anticlockwise (Andrew's monotone chain)."""
    unique = np.unique(points, axis=0)
    if len(unique) <= 2:
        return unique
    ordered = [tuple(each) for each in unique.tolist()]

    def turn(o: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, ...]] = []
    for point in ordered:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, ...]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return np.array(lower[:-1] + upper[:-1], np.float64)


def _smallest_box(points: npt.NDArray[np.float64]) -> tuple[npt.NDArray[np.float64], float]:
    """The smallest rectangle, turned any way, round some points (OpenCV's minAreaRect): its
    corners, clockwise from the top-left, and its shorter side."""
    hull = _hull(points)
    if len(hull) == 1:
        corner = hull[0]
        return np.array([corner, corner, corner, corner]), 0.0
    edges = np.roll(hull, -1, axis=0) - hull
    angles = np.unique(np.mod(np.arctan2(edges[:, 1], edges[:, 0]), np.pi / 2))
    cos, sin = np.cos(angles), np.sin(angles)
    # Each turn's frame: the hull's points along the turned x and y.
    along = hull[None, :, 0] * cos[:, None] + hull[None, :, 1] * sin[:, None]
    across = -hull[None, :, 0] * sin[:, None] + hull[None, :, 1] * cos[:, None]
    low_x, high_x = along.min(axis=1), along.max(axis=1)
    low_y, high_y = across.min(axis=1), across.max(axis=1)
    best = int(np.argmin((high_x - low_x) * (high_y - low_y)))
    c, s = cos[best], sin[best]
    frame = [
        (low_x[best], low_y[best]),
        (high_x[best], low_y[best]),
        (high_x[best], high_y[best]),
        (low_x[best], high_y[best]),
    ]
    corners = np.array([(x * c - y * s, x * s + y * c) for x, y in frame], np.float64)
    short = float(min(high_x[best] - low_x[best], high_y[best] - low_y[best]))
    return _clockwise(corners), short


def _clockwise(corners: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Four corners as top-left, top-right, bottom-right, bottom-left: the two leftmost by height
    for the left side, the two rightmost for the right."""
    by_x = corners[np.argsort(corners[:, 0], kind="stable")]
    left = by_x[:2][np.argsort(by_x[:2, 1], kind="stable")]
    right = by_x[2:][np.argsort(by_x[2:, 1], kind="stable")]
    return np.array([left[0], right[0], right[1], left[1]], np.float64)


def _mean_inside(found: Map, box: npt.NDArray[np.float64]) -> float:
    """The map's average over the pixels inside a box (their centres inside its four sides)."""
    height, width = found.shape
    low_x = int(np.clip(np.floor(box[:, 0].min()), 0, width - 1))
    high_x = int(np.clip(np.ceil(box[:, 0].max()), 0, width - 1))
    low_y = int(np.clip(np.floor(box[:, 1].min()), 0, height - 1))
    high_y = int(np.clip(np.ceil(box[:, 1].max()), 0, height - 1))
    ys, xs = np.mgrid[low_y : high_y + 1, low_x : high_x + 1]
    signs: list[npt.NDArray[np.float64]] = []
    for at in range(4):
        (x0, y0), (x1, y1) = box[at], box[(at + 1) % 4]
        signs.append((x1 - x0) * (ys - y0) - (y1 - y0) * (xs - x0))
    inside = np.all([each >= -0.5 for each in signs], axis=0) | np.all(
        [each <= 0.5 for each in signs], axis=0
    )
    window = found[low_y : high_y + 1, low_x : high_x + 1]
    if not inside.any():
        return float(window.mean())
    return float(window[inside].mean())


def _unclipped(box: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """A box grown out by UNCLIP times its area over its outline, its corners rounded."""
    area = _side(box[0], box[1]) * _side(box[1], box[2])
    outline = 2 * (_side(box[0], box[1]) + _side(box[1], box[2]))
    if outline <= 0:
        return box
    offset = pyclipper.PyclipperOffset()
    offset.AddPath(box.tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    grown = offset.Execute(area * UNCLIP / outline)
    if not grown:
        return box
    return np.array(grown[0], np.float64)


def _in_picture(
    corners: npt.NDArray[np.float64], width: int, height: int
) -> tuple[Point, Point, Point, Point]:
    """Corners rounded to whole pixels and kept inside the picture."""
    xs = np.clip(np.round(corners[:, 0]), 0, width - 1)
    ys = np.clip(np.round(corners[:, 1]), 0, height - 1)
    ordered = _clockwise(np.stack([xs, ys], axis=1))
    return (
        (float(ordered[0, 0]), float(ordered[0, 1])),
        (float(ordered[1, 0]), float(ordered[1, 1])),
        (float(ordered[2, 0]), float(ordered[2, 1])),
        (float(ordered[3, 0]), float(ordered[3, 1])),
    )


def _side(
    a: Sequence[float] | npt.NDArray[np.float64], b: Sequence[float] | npt.NDArray[np.float64]
) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))
