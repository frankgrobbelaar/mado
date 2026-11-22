"""Reading a .cube file, the look format Adobe and DaVinci Resolve write: a title, the table's
size and the range its inputs cover, then a row of red, green and blue for each point, red
changing fastest. Pure: the caller reads the file and passes its text.

What Mado reads: 3D tables of 2 to 256 points a side, as the format allows, in a file of up to
100 MB, which holds about 129 (one bigger than 65 is sampled down to 65, the most Pillow's filter
takes), 1D tables of 2 to 65,536 points (made a 3D table of 65), the
range of their inputs (DOMAIN_MIN and DOMAIN_MAX, or Resolve's LUT_3D_INPUT_RANGE and
LUT_1D_INPUT_RANGE), comments, and values outside 0 to 1, held to it after sampling, as Mado's
pictures are 8 bits a channel. Not a file with a 1D table before a 3D one (Resolve's shaper),
nor keywords it doesn't know: each says so in a sentence.
"""

from array import array
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from mado.core.grids import MOST, Grid, identity, resized, sample

MOST_BYTES = 100 * 1024 * 1024  # the biggest file read: a 129-point table is about 60 MB
_SIDES_3D = (2, 256)  # points a side the format allows
_POINTS_1D = (2, 65536)
_KNOWN = frozenset(
    {
        "TITLE",
        "LUT_3D_SIZE",
        "LUT_1D_SIZE",
        "DOMAIN_MIN",
        "DOMAIN_MAX",
        "LUT_3D_INPUT_RANGE",
        "LUT_1D_INPUT_RANGE",
    }
)
_NOT_ONE = "It isn't a .cube file: it has no table of colours in it."

type Floats = npt.NDArray[np.float64]


class CubeError(ValueError):
    """A .cube file Mado can't use, with a sentence saying why."""


@dataclass(frozen=True, eq=False)
class Cube:
    title: str | None
    points: int  # as the file has it: a side of a 3D table, or a 1D table's length
    one_d: bool
    grid: Grid  # as Mado uses it: 3D, at most 65 points a side, values 0 to 1


def too_big(size: int) -> str | None:
    """Why a file `size` bytes big isn't read; None when it's small enough."""
    if size <= MOST_BYTES:
        return None
    return (
        f"It's {size / 1024**2:,.0f} MB, bigger than any look Mado reads: up to "
        f"{MOST_BYTES // 1024**2} MB, which holds a 129-point table."
    )


def read(text: str) -> Cube:
    """The look a .cube file's `text` holds. Raises CubeError."""
    header: dict[str, str] = {}
    unknown: list[str] = []
    late: tuple[int, str] | None = None  # a keyword after the rows began: its line and word
    rows: list[str] = []
    lines = array("I")  # each row's line in the file
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line[0].isalpha():
            rows.append(line)
            lines.append(number)
            continue
        word, *rest = line.split(None, 1)  # a space or a tab after the keyword
        value = rest[0] if rest else ""
        if rows and late is None:
            late = (number, word)
        if word in _KNOWN:
            header[word] = value.strip()
        else:
            unknown.append(word)
    if not rows and "LUT_3D_SIZE" not in header and "LUT_1D_SIZE" not in header:
        raise CubeError(_NOT_ONE)
    if unknown:
        raise CubeError(f"It uses something Mado doesn't read yet: “{unknown[0]}”.")
    if late is not None:
        raise CubeError(
            f"Line {late[0]} says “{late[1]}” after the table's rows began, where Mado can't "
            "tell what it means."
        )
    if "LUT_3D_SIZE" in header and "LUT_1D_SIZE" in header:
        raise CubeError(
            "It has two tables, a 1D one before a 3D one, which Mado doesn't read yet. Export "
            "it from your app as one 3D table."
        )
    one_d = "LUT_1D_SIZE" in header
    if not one_d and "LUT_3D_SIZE" not in header:
        raise CubeError("It doesn't say how big its table is (LUT_3D_SIZE), so it can't be read.")
    keyword = "LUT_1D_SIZE" if one_d else "LUT_3D_SIZE"
    points = _count(keyword, header[keyword], _POINTS_1D if one_d else _SIDES_3D)
    wanted = points if one_d else points**3
    if len(rows) != wanted:
        table = f"a 1D table of {points:,} points" if one_d else f"a {points}-point table"
        raise CubeError(
            f"It's damaged or cut short: {table} has {wanted:,} rows, and it has {len(rows):,}."
        )
    values = _numbers(rows, lines)
    low, high = _domain(header, one_d)
    grid = _one_d(values, low, high) if one_d else _three_d(values, points, low, high)
    title = header.get("TITLE", "").strip().strip('"').strip() or None
    return Cube(title, points, one_d, np.clip(grid, 0.0, 1.0).astype(np.float32))


def _count(keyword: str, value: str, allowed: tuple[int, int]) -> int:
    try:
        points = int(value)
    except ValueError:
        raise CubeError(f"{keyword} says “{value}”, not a number of points.") from None
    if not allowed[0] <= points <= allowed[1]:
        if keyword == "LUT_1D_SIZE":
            raise CubeError(
                f"Its 1D table has {points:,} points; a .cube file's have {allowed[0]} to "
                f"{allowed[1]:,}."
            )
        unit = "point" if points == 1 else "points"
        raise CubeError(
            f"Its table is {points} {unit} a side; a .cube file's are {allowed[0]} to {allowed[1]}."
        )
    return points


def _numbers(rows: list[str], lines: array[int]) -> Floats:
    """The rows as numbers, three to a row; the first row that isn't said by its line."""
    try:
        values = np.loadtxt(rows, dtype=np.float64, ndmin=2, comments=None)
    except ValueError:
        values = np.zeros((0, 0))
    if values.shape != (len(rows), 3):
        for row, number in zip(rows, lines, strict=True):
            parts = row.split()
            if len(parts) != 3 or not all(_is_number(part) for part in parts):
                raise CubeError(f"Line {number} isn't three numbers: “{row}”.")
        raise CubeError(_NOT_ONE)  # loadtxt and the rows disagree: never seen
    finite = np.isfinite(values).all(axis=1)
    if not finite.all():
        first = int(np.argmin(finite))
        raise CubeError(f"Line {lines[first]} has a number Mado can't use: “{rows[first]}”.")
    return values


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _domain(header: dict[str, str], one_d: bool) -> tuple[Floats, Floats]:
    """The range the table's inputs cover, for each of red, green and blue."""
    low, high = np.zeros(3), np.ones(3)
    ranged = header.get("LUT_1D_INPUT_RANGE" if one_d else "LUT_3D_INPUT_RANGE")
    if ranged is not None:
        ends = _floats("LUT_3D_INPUT_RANGE" if not one_d else "LUT_1D_INPUT_RANGE", ranged, 2)
        low, high = np.full(3, ends[0]), np.full(3, ends[1])
    if "DOMAIN_MIN" in header:
        low = _floats("DOMAIN_MIN", header["DOMAIN_MIN"], 3)
    if "DOMAIN_MAX" in header:
        high = _floats("DOMAIN_MAX", header["DOMAIN_MAX"], 3)
    if not (low < high).all():
        raise CubeError("Its DOMAIN_MIN isn't below its DOMAIN_MAX, so it can't be used.")
    return low, high


def _floats(keyword: str, value: str, count: int) -> Floats:
    parts = value.split()
    if len(parts) != count or not all(_is_number(part) for part in parts):
        raise CubeError(f"{keyword} says “{value}”, not {count} numbers.")
    found = np.array([float(part) for part in parts])
    if not np.isfinite(found).all():
        raise CubeError(f"{keyword} says “{value}”, not {count} numbers.")
    return found


def _three_d(values: Floats, points: int, low: Floats, high: Floats) -> Grid:
    """A 3D table on Mado's grid: as it is, or sampled to cover 0 to 1 in at most 65 points."""
    grid = values.reshape(points, points, points, 3).astype(np.float32)
    if (low == 0).all() and (high == 1).all():
        return resized(grid, min(points, MOST))
    # Inputs outside the table's range take its edge, as the format says.
    inputs = (identity(MOST) - low.astype(np.float32)) / (high - low).astype(np.float32)
    return sample(grid, inputs.astype(np.float32))


def _one_d(values: Floats, low: Floats, high: Floats) -> Grid:
    """A 1D table (a curve for each of red, green and blue) as a 3D table of 65 points."""
    axis = np.linspace(0.0, 1.0, MOST)
    points = values.shape[0]

    def curve(channel: int) -> Floats:
        ends = np.linspace(float(low[channel]), float(high[channel]), points)
        return np.interp(axis, ends, values[:, channel]).astype(np.float64)

    red, green, blue = curve(0), curve(1), curve(2)
    grid = np.empty((MOST, MOST, MOST, 3), np.float32)
    grid[..., 0] = red[None, None, :]
    grid[..., 1] = green[None, :, None]
    grid[..., 2] = blue[:, None, None]
    return grid
