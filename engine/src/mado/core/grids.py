"""A look as a table of colours (a 3D LUT): for each point on a grid through the cube of red,
green and blue, the colour it becomes; a colour between points is mixed from the eight around it
(trilinear), as Pillow's Color3DLUT mixes them. Pure.

A grid is float32, (n, n, n, 3), indexed [blue][green][red], every value 0 to 1: red changes
fastest, the order .cube files list their rows in and Pillow takes. Mado's own looks are 33
points a side; Pillow takes at most 65, so a bigger table is sampled down to that.
"""

import zlib

import numpy as np
import numpy.typing as npt

type Grid = npt.NDArray[np.float32]  # (n, n, n, 3): [blue][green][red] -> red, green, blue
type Colours = npt.NDArray[np.float32]  # (..., 3): red, green, blue, 0 to 1

SIDE = 33  # points a side for Mado's own looks
MOST = 65  # the most Pillow's Color3DLUT takes
_STEPS = 65535  # a kept value's 16-bit steps


def identity(n: int = SIDE) -> Grid:
    """The grid that leaves every colour as it was."""
    axis = np.linspace(0.0, 1.0, n, dtype=np.float32)
    blue, green, red = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.stack([red, green, blue], axis=-1)


def blended(grid: Grid, strength: float) -> Grid:
    """A look at `strength` (0 to 1): mixed with the colours as they were. For a look that only
    changes colours, that's the same as mixing the pictures it makes."""
    plain = identity(grid.shape[0])
    return (plain + (grid - plain) * np.float32(strength)).astype(np.float32)


def sample(grid: Grid, colours: Colours) -> Colours:
    """The colours `colours` become through `grid`, each mixed from the eight points around it."""
    n = grid.shape[0]
    place = np.clip(colours, 0.0, 1.0) * np.float32(n - 1)
    low = np.minimum(np.floor(place).astype(np.intp), n - 2)
    part = (place - low).astype(np.float32)
    red, green, blue = low[..., 0], low[..., 1], low[..., 2]
    across, up, deep = part[..., 0:1], part[..., 1:2], part[..., 2:3]

    def at(db: int, dg: int, dr: int) -> Colours:
        return grid[blue + db, green + dg, red + dr]

    near = (at(0, 0, 0) * (1 - across) + at(0, 0, 1) * across) * (1 - up)
    near += (at(0, 1, 0) * (1 - across) + at(0, 1, 1) * across) * up
    far = (at(1, 0, 0) * (1 - across) + at(1, 0, 1) * across) * (1 - up)
    far += (at(1, 1, 0) * (1 - across) + at(1, 1, 1) * across) * up
    return (near * (1 - deep) + far * deep).astype(np.float32)


def resized(grid: Grid, n: int) -> Grid:
    """The same look on a grid of `n` points a side."""
    if grid.shape[0] == n:
        return grid
    return sample(grid, identity(n))


def packed(grid: Grid) -> bytes:
    """A grid in few bytes, for the database: each value in 16-bit steps, kept as its difference
    from the one before it along red, which a look keeps small, so zlib packs them tight."""
    steps = np.round(np.clip(grid, 0.0, 1.0) * _STEPS).astype(np.int64)
    differences = np.diff(steps, axis=2, prepend=0) % (_STEPS + 1)
    return zlib.compress(differences.astype("<u2").tobytes(), 9)


def unpacked(data: bytes, n: int) -> Grid:
    """A grid kept by `packed`, `n` points a side. Raises ValueError for bytes that aren't one."""
    try:
        raw = zlib.decompress(data)
    except zlib.error:
        raw = b""
    if len(raw) != n**3 * 3 * 2:
        raise ValueError(f"It isn't a {n}-point table.")
    differences = np.frombuffer(raw, "<u2").reshape(n, n, n, 3)
    steps = np.cumsum(differences, axis=2, dtype=np.uint16)  # wraps round, as it was kept
    return (steps.astype(np.float32) / np.float32(_STEPS)).astype(np.float32)
