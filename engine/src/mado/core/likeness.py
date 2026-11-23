"""What a picture looks like, in numbers that tell one picture from another: a fingerprint, a
finer one, and how sharp it is. Pure: the grey copies come in as arrays
(docs/stack/duplicates.md has the measurements behind each).

- The fingerprint is a pHash: a 32 × 32 grey copy's lowest 8 × 8 frequencies (a DCT), each above
  or below their median: 64 bits, kept as a signed integer, as SQLite keeps one. A copy saved
  again at another size, quality or format comes out within a few bits; another scene, about
  half of them apart.
- The finer fingerprint is the same from a 64 × 64 grey copy's lowest 16 × 16 frequencies: 256
  bits (32 bytes). It tells a copy from a crop: cropping a few per cent shifts the finer
  frequencies, and the bits with them, where saving again doesn't.
- Sharpness is the variance of the Laplacian on a grey copy at a fixed size: the sharpest shot of
  a burst is the one to keep.
- Close fingerprints are found in buckets (`near_pairs`): the 64 bits split into enough bands
  that two within the limit share one band exactly, and only pictures sharing a band are
  compared, so a library of 100,000 compares a few million pairs, not five billion.
"""

from collections.abc import Iterator

import numpy as np
import numpy.typing as npt

type Grey = npt.NDArray[np.float32]  # a grey copy, 0 to 255
type Hashes = npt.NDArray[np.int64]

SIDE = 32  # the grey copy the fingerprint is taken from, a side
FINE_SIDE = 64  # the grey copy the finer fingerprint is taken from


def _basis(n: int) -> npt.NDArray[np.float64]:
    """The DCT-II's basis: row u holds frequency u at each of n points."""
    points = np.arange(n, dtype=np.float64)
    return np.cos(np.pi * (2 * points[None, :] + 1) * points[:, None] / (2 * n))


_DCT = {SIDE: _basis(SIDE), FINE_SIDE: _basis(FINE_SIDE)}


def _bits(grey: Grey, side: int, low: int) -> npt.NDArray[np.bool_]:
    """A grey copy's lowest `low` × `low` frequencies, each above their median or not, the
    lowest first. The average (the very first) is left out of the median."""
    if grey.shape != (side, side):
        raise ValueError(f"A fingerprint is taken from a grey copy {side} × {side}.")
    basis = _DCT[side]
    frequencies = basis @ grey.astype(np.float64) @ basis.T
    kept = frequencies[:low, :low].flatten()
    return kept > np.median(kept[1:])


def fingerprint(grey: Grey) -> int:
    """The picture's fingerprint, from its grey copy SIDE × SIDE: 64 bits, the first the lowest
    frequency's, as a signed integer."""
    value = int.from_bytes(np.packbits(_bits(grey, SIDE, 8)).tobytes(), "big")
    return value - (1 << 64) if value >= 1 << 63 else value


def fine(grey: Grey) -> bytes:
    """The picture's finer fingerprint, from its grey copy FINE_SIDE × FINE_SIDE: 256 bits."""
    return np.packbits(_bits(grey, FINE_SIDE, 16)).tobytes()


def apart(first: int, second: int) -> int:
    """How many of two fingerprints' 64 bits differ."""
    return ((first ^ second) & ((1 << 64) - 1)).bit_count()


def fine_apart(first: bytes, second: bytes) -> int:
    """How many of two finer fingerprints' bits differ (all of them, when they can't be told)."""
    if len(first) != len(second) or not first:
        return 8 * max(len(first), len(second), 32)
    a, b = np.frombuffer(first, np.uint8), np.frombuffer(second, np.uint8)
    return int(np.bitwise_count(a ^ b).sum())


def sharpness(grey: Grey) -> float:
    """How sharp a picture is: the variance of the Laplacian of its grey copy. Compare only
    copies made at the same size."""
    if grey.shape[0] < 3 or grey.shape[1] < 3:
        return 0.0
    g = grey.astype(np.float64)
    laplacian = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(laplacian.var())


def near_pairs(hashes: Hashes, within: int) -> Iterator[tuple[int, int, int]]:
    """Every pair of fingerprints (by their places in `hashes`) at most `within` bits apart,
    each once, with how far apart it is."""
    count = len(hashes)
    if count < 2:
        return
    unsigned = hashes.astype(np.int64).view(np.uint64)
    seen: set[tuple[int, int]] = set()
    for shift, width in _bands(within):
        keys = (unsigned >> np.uint64(shift)) & np.uint64((1 << width) - 1)
        order = np.argsort(keys, kind="stable")
        sorted_keys = keys[order]
        starts = np.flatnonzero(np.r_[True, sorted_keys[1:] != sorted_keys[:-1]])
        ends = np.r_[starts[1:], count]
        for start, end in zip(starts.tolist(), ends.tolist(), strict=True):
            if end - start > 1:
                yield from _close_in(order[start:end], unsigned, within, seen)


def _close_in(
    members: npt.NDArray[np.intp],
    unsigned: npt.NDArray[np.uint64],
    within: int,
    seen: set[tuple[int, int]],
) -> Iterator[tuple[int, int, int]]:
    """The pairs in one bucket within the limit, compared a block at a time (a bucket can hold
    thousands of pictures much alike, dark ones say), each pair once however many bands it
    shares."""
    values = unsigned[members]
    for start in range(0, len(members), _BLOCK):
        block = values[start : start + _BLOCK]
        distances = np.bitwise_count(block[:, None] ^ values[None, start:])
        rows, columns = np.nonzero(distances <= within)
        for row, column in zip(rows.tolist(), columns.tolist(), strict=True):
            if column <= row:  # itself, or a pair this block met the other way round
                continue
            a, b = int(members[start + row]), int(members[start + column])
            pair = (a, b) if a < b else (b, a)
            if pair in seen:
                continue
            seen.add(pair)
            yield pair[0], pair[1], int(distances[row, column])


_BLOCK = 512  # a bucket's pictures compared at once


def _bands(within: int) -> list[tuple[int, int]]:
    """The 64 bits split into `within` + 1 bands (each a shift and a width): two fingerprints at
    most `within` apart differ in at most that many bands, so they share at least one exactly."""
    count = min(max(within + 1, 1), 64)
    widths = [64 // count + (1 if at < 64 % count else 0) for at in range(count)]
    bands: list[tuple[int, int]] = []
    shift = 0
    for width in widths:
        bands.append((shift, width))
        shift += width
    return bands
