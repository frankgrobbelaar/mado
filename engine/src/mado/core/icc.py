"""Mado's own Display P3 colour profile, written by code: the colours a camera RAW is developed
into (mado/libraw.py), carried in every copy and picture made from it, so a camera's wide
colours stay wide and every app shows them as they are. Pure.

An ICC v4 profile of a screen: Display P3's primaries (DCI-P3's, around D65's white), seen in
D50 as ICC's colour space is, and sRGB's curve, which Display P3 shares.
"""

import struct
from functools import cache

type Matrix = tuple[tuple[float, ...], ...]
type Vector = tuple[float, ...]

_PRIMARIES = ((0.680, 0.320), (0.265, 0.690), (0.150, 0.060))  # red, green, blue (x, y)
_D65 = (0.3127, 0.3290)
_D50: Vector = (0.9642, 1.0, 0.8249)  # ICC's own white
_BRADFORD: Matrix = (
    (0.8951, 0.2664, -0.1614),
    (-0.7502, 1.7135, 0.0367),
    (0.0389, -0.0685, 1.0296),
)
_SRGB_CURVE = (2.4, 1 / 1.055, 0.055 / 1.055, 1 / 12.92, 0.04045)  # g, a, b, c, d


@cache
def display_p3() -> bytes:
    """The profile's bytes."""
    to_xyz = _rgb_to_xyz(_PRIMARIES, _D65)
    adapt = _bradford(_xyz(_D65), _D50)
    seen = _times(adapt, to_xyz)
    columns = [tuple(seen[row][column] for row in range(3)) for column in range(3)]
    curve = b"para" + bytes(4) + struct.pack(">HH", 3, 0) + _fixed(*_SRGB_CURVE)
    tags: list[tuple[bytes, bytes]] = [
        (b"desc", _text("Display P3")),
        (b"cprt", _text("No copyright: made by Mado, free to use")),
        (b"wtpt", _xyz_tag(_D50)),
        (b"chad", b"sf32" + bytes(4) + _fixed(*(value for row in adapt for value in row))),
        (b"rXYZ", _xyz_tag(columns[0])),
        (b"gXYZ", _xyz_tag(columns[1])),
        (b"bXYZ", _xyz_tag(columns[2])),
        (b"rTRC", curve),
        (b"gTRC", curve),
        (b"bTRC", curve),
    ]
    table_end = 128 + 4 + 12 * len(tags)
    entries = bytearray(struct.pack(">I", len(tags)))
    body = bytearray()
    placed: dict[bytes, int] = {}  # the curve is written once and shared by all three
    for signature, data in tags:
        if data not in placed:
            placed[data] = table_end + len(body)
            body.extend(data + bytes(-len(data) % 4))
        entries.extend(struct.pack(">4sII", signature, placed[data], len(data)))
    size = table_end + len(body)
    header = struct.pack(
        ">I4sI4s4s4s6H4s4sI4s4s8sI12s4s16s28s",
        size,
        b"\x00\x00\x00\x00",
        0x04300000,  # version 4.3
        b"mntr",
        b"RGB ",
        b"XYZ ",
        2026,
        11,
        23,
        0,
        0,
        0,
        b"acsp",
        b"\x00\x00\x00\x00",
        0,
        b"\x00\x00\x00\x00",
        b"\x00\x00\x00\x00",
        bytes(8),
        0,  # perceptual
        _fixed(*_D50),
        b"\x00\x00\x00\x00",
        bytes(16),
        bytes(28),
    )
    return header + bytes(entries) + bytes(body)


def _xyz(xy: tuple[float, float]) -> Vector:
    x, y = xy
    return (x / y, 1.0, (1 - x - y) / y)


def _rgb_to_xyz(primaries: tuple[tuple[float, float], ...], white: tuple[float, float]) -> Matrix:
    """The matrix from linear RGB to XYZ for these primaries around this white."""
    columns = [_xyz(each) for each in primaries]
    m = tuple(tuple(columns[column][row] for column in range(3)) for row in range(3))
    s = _apply(_inverse(m), _xyz(white))
    return tuple(tuple(m[row][column] * s[column] for column in range(3)) for row in range(3))


def _bradford(source: Vector, target: Vector) -> Matrix:
    """Bradford's chromatic adaptation from one white to another."""
    cone_source, cone_target = _apply(_BRADFORD, source), _apply(_BRADFORD, target)
    scale = tuple(cone_target[at] / cone_source[at] for at in range(3))
    scaled = tuple(
        tuple(_BRADFORD[row][column] * scale[row] for column in range(3)) for row in range(3)
    )
    return _times(_inverse(_BRADFORD), scaled)


def _times(a: Matrix, b: Matrix) -> Matrix:
    return tuple(
        tuple(sum(a[row][k] * b[k][column] for k in range(3)) for column in range(3))
        for row in range(3)
    )


def _apply(m: Matrix, v: Vector) -> Vector:
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def _inverse(m: Matrix) -> Matrix:
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return (
        ((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det),
        ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det),
        ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det),
    )


def _fixed(*values: float) -> bytes:
    """ICC's s15Fixed16Number: each value in 16ths of 16 bits."""
    return b"".join(struct.pack(">i", round(value * 65536)) for value in values)


def _xyz_tag(xyz: Vector) -> bytes:
    return b"XYZ " + bytes(4) + _fixed(*xyz)


def _text(words: str) -> bytes:
    """A multiLocalizedUnicodeType holding one English string."""
    encoded = words.encode("utf-16-be")
    return (
        b"mluc"
        + bytes(4)
        + struct.pack(">II", 1, 12)
        + struct.pack(">2s2sII", b"en", b"US", len(encoded), 28)
        + encoded
    )


DISPLAY_P3 = display_p3()
