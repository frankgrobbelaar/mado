"""Masks, by their maths: a part of a picture as numbers from 0 (not in it) to 255 (all in it), one
for each of the picture's pixels. Parts put together and taken away, the brush's strokes drawn,
an edge grown or made soft (feathered), a soft mask made to follow the picture's own edges (a
guided filter), the outline the window draws round what's picked, and how much fine detail a
place has (an erase that left a smear). Pure: numpy only.
"""

import itertools
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

type Mask = npt.NDArray[np.uint8]  # height × width, 0 to 255
type Floats = npt.NDArray[np.float32]
type Line = list[tuple[float, float]]  # an outline's points, in the grid's pixels

_EDGE = 1e-6


@dataclass(frozen=True)
class Brush:
    """A stroke of the brush in the picture's own pixels: its points, how wide it is, and whether
    it takes away (Alt) rather than paints."""

    points: tuple[tuple[float, float], ...]
    width: float
    take: bool = False


def together(masks: Iterable[Mask], shape: tuple[int, int]) -> Mask:
    """Every part as one: a pixel is in it as much as it's in the part it's most in."""
    found = np.zeros(shape, np.uint8)
    for mask in masks:
        np.maximum(found, mask, out=found)
    return found


def without(mask: Mask, taken: Mask) -> Mask:
    """A mask with another taken out of it."""
    return np.minimum(mask, 255 - taken)


def area(mask: Mask) -> float:
    """How much of the picture a mask covers, 0 to 1."""
    return float(np.count_nonzero(mask >= 128)) / max(mask.size, 1)


def box(values: Floats, radius: int) -> Floats:
    """The mean of each value's square of neighbours `radius` out each way (the edges count
    themselves again), by running sums: as quick for a big square as a small one."""
    if radius <= 0:
        return values.astype(np.float32, copy=True)
    out = _box_along(values.astype(np.float32, copy=False), radius, 0)
    return _box_along(out, radius, 1)


def _box_along(values: Floats, radius: int, axis: int) -> Floats:
    moved = np.moveaxis(values, axis, 0)
    padded = np.pad(moved, [(radius, radius)] + [(0, 0)] * (moved.ndim - 1), mode="edge")
    # Running sums in 32 bits: a window with nothing new in it subtracts two equal sums, exactly 0.
    sums = np.cumsum(padded, axis=0, dtype=np.float32)
    sums = np.concatenate([np.zeros((1, *sums.shape[1:]), np.float32), sums], axis=0)
    width = 2 * radius + 1
    spread = (sums[width:] - sums[:-width]) * np.float32(1 / width)
    return np.ascontiguousarray(np.moveaxis(spread, 0, axis), dtype=np.float32)


def running(values: Floats, window: int, pick: np.ufunc) -> Floats:
    """Each value's highest or lowest (`pick`: np.maximum, np.minimum) over its square of
    neighbours `window` across, the edges repeating outward: by doubling runs, so as quick for a
    wide square as a small one."""
    out = values
    for axis in (0, 1):
        moved = np.moveaxis(out, axis, 0)
        count = moved.shape[0]
        before = window // 2
        padded = np.concatenate(
            [np.repeat(moved[:1], before, 0), moved, np.repeat(moved[-1:], window - 1 - before, 0)]
        )
        span = 1
        while span * 2 <= window:
            padded = pick(padded[:-span], padded[span:])
            span *= 2
        rest = window - span
        if rest:
            padded = pick(padded[: padded.shape[0] - rest], padded[rest:])
        out = np.moveaxis(padded[:count], 0, axis)
    return np.ascontiguousarray(out, np.float32)


def feathered(mask: Mask, radius: int) -> Mask:
    """A mask's edge made soft over about `radius` pixels each way (two passes of a box, close to
    a bell's curve), so what's laid through it fades in rather than steps. Worked out only round
    what's in the mask: nothing reaches further than the radius."""
    if radius <= 0:
        return mask.copy()
    half = max(1, radius // 2)
    return _round_it(mask, 2 * half + 2, lambda part: _softened(part, half))


def _softened(part: Mask, half: int) -> Mask:
    soft = box(box(part.astype(np.float32), half), half)
    return np.clip(soft + 0.5, 0, 255).astype(np.uint8)


def grown(mask: Mask, by: int) -> Mask:
    """A mask grown outward by `by` pixels each way: what's half in it or more, and every pixel
    within `by` of that, all in it. An erase covers the thing picked and its fringe."""
    solid = (mask >= 128).astype(np.uint8) * 255
    if by <= 0:
        return solid
    return _round_it(
        solid,
        by + 1,
        lambda part: ((box(part.astype(np.float32), by) > _EDGE) * 255).astype(np.uint8),
    )


def _round_it(mask: Mask, reach: int, work: Callable[[Mask], Mask]) -> Mask:
    """`work` done on the part of a mask holding all that's in it, `reach` pixels round it; the
    rest stays empty."""
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    found = np.zeros_like(mask)
    if rows.size == 0:
        return found
    top, bottom = max(int(rows[0]) - reach, 0), min(int(rows[-1]) + 1 + reach, mask.shape[0])
    left, right = max(int(columns[0]) - reach, 0), min(int(columns[-1]) + 1 + reach, mask.shape[1])
    found[top:bottom, left:right] = work(mask[top:bottom, left:right])
    return found


def bounds(mask: Mask) -> tuple[int, int, int, int] | None:
    """The smallest box holding what's in a mask, (left, top, right, bottom) with right and
    bottom past its last pixel; None for an empty mask."""
    rows = np.flatnonzero((mask >= 128).any(axis=1))
    columns = np.flatnonzero((mask >= 128).any(axis=0))
    if rows.size == 0 or columns.size == 0:
        return None
    return int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1


def square_around(
    found: tuple[int, int, int, int], size: tuple[int, int], *, least: int, margin: float
) -> tuple[int, int, int, int]:
    """The square an erase is drawn in: the hole's box with `margin` of its longer side around it
    on every side (so the model sees what's around it), `least` pixels a side at least, inside
    the picture where it fits (a picture narrower than the square keeps its whole width)."""
    left, top, right, bottom = found
    width, height = size
    longest = max(right - left, bottom - top)
    side = max(least, round(longest * (1 + 2 * margin)))
    side_x, side_y = min(side, width), min(side, height)
    middle_x, middle_y = (left + right) / 2, (top + bottom) / 2
    x0 = round(min(max(middle_x - side_x / 2, 0), width - side_x))
    y0 = round(min(max(middle_y - side_y / 2, 0), height - side_y))
    return x0, y0, x0 + side_x, y0 + side_y


def stroked(brushes: Sequence[Brush], size: tuple[int, int]) -> Mask:
    """The brush's strokes drawn at a picture's size, in the order they were made: one taking away
    clears what was painted before it, and painting again brings it back. Their edges are smooth
    to a pixel."""
    width, height = size
    found = np.zeros((height, width), np.uint8)
    for brush in brushes:
        drawn = _drawn(brush, width, height)
        if drawn is None:
            continue
        mask, (x0, y0) = drawn
        here = found[y0 : y0 + mask.shape[0], x0 : x0 + mask.shape[1]]
        if brush.take:
            np.minimum(here, 255 - mask, out=here)
        else:
            np.maximum(here, mask, out=here)
    return found


def _drawn(brush: Brush, width: int, height: int) -> tuple[Mask, tuple[int, int]] | None:
    """One stroke, as the part of the picture it touches and where that part starts."""
    if not brush.points or brush.width <= 0:
        return None
    radius = brush.width / 2
    points = np.asarray(brush.points, np.float32)
    x0 = max(int(np.floor(points[:, 0].min() - radius)) - 1, 0)
    y0 = max(int(np.floor(points[:, 1].min() - radius)) - 1, 0)
    x1 = min(int(np.ceil(points[:, 0].max() + radius)) + 2, width)
    y1 = min(int(np.ceil(points[:, 1].max() + radius)) + 2, height)
    if x1 <= x0 or y1 <= y0:
        return None
    nearest = np.full((y1 - y0, x1 - x0), np.inf, np.float32)
    pairs = list(itertools.pairwise(points)) or [(points[0], points[0])]
    for start, end in pairs:
        _nearer(nearest, start, end, radius, (x0, y0))
    cover = np.clip(radius + 0.5 - nearest, 0, 1)
    return (cover * 255 + 0.5).astype(np.uint8), (x0, y0)


def _nearer(
    nearest: Floats,
    start: npt.NDArray[np.float32],
    end: npt.NDArray[np.float32],
    radius: float,
    origin: tuple[int, int],
) -> None:
    """Each pixel's distance to a stroke's segment, where it's nearer than what's kept."""
    x0 = max(int(np.floor(min(start[0], end[0]) - radius)) - 1 - origin[0], 0)
    y0 = max(int(np.floor(min(start[1], end[1]) - radius)) - 1 - origin[1], 0)
    x1 = min(int(np.ceil(max(start[0], end[0]) + radius)) + 2 - origin[0], nearest.shape[1])
    y1 = min(int(np.ceil(max(start[1], end[1]) + radius)) + 2 - origin[1], nearest.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    xs = np.arange(x0, x1, dtype=np.float32) + origin[0] + 0.5
    ys = np.arange(y0, y1, dtype=np.float32) + origin[1] + 0.5
    px, py = np.meshgrid(xs, ys)
    dx, dy = float(end[0] - start[0]), float(end[1] - start[1])
    length = dx * dx + dy * dy
    if length <= _EDGE:
        along = np.zeros_like(px)
    else:
        along = np.clip(((px - start[0]) * dx + (py - start[1]) * dy) / length, 0, 1)
    distance = np.hypot(px - (start[0] + along * dx), py - (start[1] + along * dy))
    here = nearest[y0:y1, x0:x1]
    np.minimum(here, distance, out=here)


def guided_coefficients(
    guide: Floats, soft: Floats, radius: int, eps: float
) -> tuple[Floats, Floats]:
    """A guided filter's two parts (He, Sun and Tang), worked out on small copies: how much of the
    picture's colour (`guide`, height × width × 3, 0 to 1) to take into the mask (`soft`, 0 to 1)
    at each place, and what to add. Laid on the picture at its full size (`guided`), the mask's
    edge follows the picture's own, sharp where the picture is and soft where it is (hair, a
    blurred edge)."""
    red, green, blue = (np.ascontiguousarray(guide[..., c], dtype=np.float32) for c in range(3))
    mean_p = box(soft, radius)
    mr, mg, mb = box(red, radius), box(green, radius), box(blue, radius)
    cr = box(red * soft, radius) - mr * mean_p
    cg = box(green * soft, radius) - mg * mean_p
    cb = box(blue * soft, radius) - mb * mean_p
    e = np.float32(eps)
    a = box(red * red, radius) - mr * mr + e
    b = box(red * green, radius) - mr * mg
    c = box(red * blue, radius) - mr * mb
    d = box(green * green, radius) - mg * mg + e
    f = box(green * blue, radius) - mg * mb
    g = box(blue * blue, radius) - mb * mb + e
    # The colours' spread, a symmetric 3 × 3 at each place, inverted by its cofactors.
    ia, ib, ic = d * g - f * f, c * f - b * g, b * f - c * d
    idd, ie, ig = a * g - c * c, b * c - a * f, a * d - b * b
    det = a * ia + b * ib + c * ic
    det = np.where(np.abs(det) < 1e-12, np.float32(1e-12), det)
    sr = ((ia * cr + ib * cg + ic * cb) / det).astype(np.float32)
    sg = ((ib * cr + idd * cg + ie * cb) / det).astype(np.float32)
    sb = ((ic * cr + ie * cg + ig * cb) / det).astype(np.float32)
    offset = mean_p - sr * mr - sg * mg - sb * mb
    slope = np.stack([box(sr, radius), box(sg, radius), box(sb, radius)], axis=-1)
    return slope.astype(np.float32), box(offset.astype(np.float32), radius)


def guided(guide: Floats, slope: Floats, offset: Floats) -> Floats:
    """A guided filter laid on (part of) the picture: `slope` and `offset` from
    `guided_coefficients`, made as big as `guide` first."""
    return np.clip(np.einsum("hwc,hwc->hw", slope, guide) + offset, 0, 1)


def detail(grey: Floats, where: npt.NDArray[np.bool_]) -> float:
    """How much fine detail a place has: the spread of each pixel's difference from its four
    neighbours, where `where` says."""
    if grey.shape[0] < 3 or grey.shape[1] < 3:
        return 0.0
    middle = grey[1:-1, 1:-1]
    fine = 4 * middle - grey[:-2, 1:-1] - grey[2:, 1:-1] - grey[1:-1, :-2] - grey[1:-1, 2:]
    inside = where[1:-1, 1:-1]
    return float(fine[inside].std()) if np.count_nonzero(inside) > 16 else 0.0


def outline(solid: npt.NDArray[np.bool_], tolerance: float = 0.75) -> list[Line]:
    """The edges of what's picked, as closed lines round each piece and each hole in it (marching
    squares on the pixels' middles, then straightened to within `tolerance` of a pixel)."""
    grid = np.pad(solid.astype(np.uint8), 1)
    cases = grid[:-1, :-1] * 8 + grid[:-1, 1:] * 4 + grid[1:, 1:] * 2 + grid[1:, :-1]
    rows, columns = np.nonzero((cases > 0) & (cases < 15))
    segments: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for row, column in zip(rows.tolist(), columns.tolist(), strict=True):
        for start, end in _SEGMENTS[int(cases[row, column])]:
            segments.append(
                (_edge_point(row, column, start), _edge_point(row, column, end)),
            )
    return [_straightened(line, tolerance) for line in _joined(segments)]


# Each square of four pixels' middles (top left, top right, bottom right, bottom left: 8, 4, 2,
# 1 when in): the edges its outline crosses, as pairs of its sides (0 top, 1 right, 2 bottom,
# 3 left), drawn with what's in on their left.
_SEGMENTS: dict[int, list[tuple[int, int]]] = {
    1: [(3, 2)],
    2: [(2, 1)],
    3: [(3, 1)],
    4: [(1, 0)],
    5: [(3, 0), (1, 2)],
    6: [(2, 0)],
    7: [(3, 0)],
    8: [(0, 3)],
    9: [(0, 2)],
    10: [(0, 1), (2, 3)],
    11: [(0, 1)],
    12: [(1, 3)],
    13: [(1, 2)],
    14: [(2, 3)],
}


def _edge_point(row: int, column: int, side: int) -> tuple[int, int]:
    """The middle of a square's side, in half pixels (so it's whole), from the padded grid."""
    match side:
        case 0:
            return 2 * column + 1, 2 * row
        case 1:
            return 2 * column + 2, 2 * row + 1
        case 2:
            return 2 * column + 1, 2 * row + 2
        case _:
            return 2 * column, 2 * row + 1


def _joined(segments: list[tuple[tuple[int, int], tuple[int, int]]]) -> list[Line]:
    """Segments joined end to end into closed lines, in pixels of the picture's grid."""
    starting: dict[tuple[int, int], list[int]] = {}
    for index, (start, _end) in enumerate(segments):
        starting.setdefault(start, []).append(index)
    used = [False] * len(segments)
    lines: list[Line] = []
    for first in range(len(segments)):
        if used[first]:
            continue
        used[first] = True
        start, end = segments[first]
        points = [start, end]
        while end != start:
            following = [each for each in starting.get(end, []) if not used[each]]
            if not following:
                break
            used[following[0]] = True
            end = segments[following[0]][1]
            points.append(end)
        # Half pixels of the padded grid to the picture's pixels, by their middles: pixel 0's is 0.
        lines.append([((x / 2) - 1, (y / 2) - 1) for x, y in points])
    return lines


def _straightened(line: Line, tolerance: float) -> Line:
    """A closed line with the points it doesn't need left out (Douglas and Peucker), every point
    of the line it stood for still within `tolerance` of it."""
    if len(line) < 4:
        return line
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    far = max(range(len(line)), key=lambda at: _away(line[at], line[0]))
    keep[far] = True
    spans = [(0, far), (far, len(line) - 1)]
    while spans:
        start, end = spans.pop()
        if end - start < 2:
            continue
        a, b = line[start], line[end]
        index, most = start, -1.0
        for at in range(start + 1, end):
            gap = _from_segment(line[at], a, b)
            if gap > most:
                index, most = at, gap
        if most > tolerance:
            keep[index] = True
            spans.extend([(start, index), (index, end)])
    return [point for point, kept in zip(line, keep, strict=True) if kept]


def _away(p: tuple[float, float], q: tuple[float, float]) -> float:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2


def _from_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    if length <= _EDGE:
        return _away(p, a) ** 0.5
    along = min(max(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length, 0.0), 1.0)
    return _away(p, (a[0] + along * dx, a[1] + along * dy)) ** 0.5


def path(lines: Sequence[Line], size: tuple[int, int]) -> str:
    """Outlines as an SVG path in a frame 1000 across and 1000 down, whatever the picture's shape
    (the window stretches it over the picture), each line closed: drawn with the even-odd rule,
    a hole in a piece stays open."""
    width, height = size
    parts: list[str] = []
    for line in lines:
        if len(line) < 3:
            continue
        points = [f"{_place(x, width)} {_place(y, height)}" for x, y in line]
        parts.append("M" + "L".join(points) + "Z")
    return "".join(parts)


def _place(value: float, length: int) -> str:
    """A point on a side `length` pixels long as tenths of the frame's 1000, its pixel's middle
    at its place."""
    at = round((value + 0.5) / length * 1000, 1)
    return f"{at:g}"
