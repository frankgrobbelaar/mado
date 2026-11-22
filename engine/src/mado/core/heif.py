"""Reading a HEIF file's layout (a phone's HEIC): how big its picture is, which way up it goes,
where its Exif is and the colour profile its picture is in. HEIF is ISO base media: boxes inside
boxes, each a length and a four-letter kind. Only the boxes these need are read; ffmpeg decodes
the picture itself (mado/pictures.py)."""

import struct
from collections.abc import Iterator
from dataclasses import dataclass

# A turn or a mirror as a matrix on a picture's (x, y), x to the right and y down: (a, b, c, d)
# is [[a, b], [c, d]]. Each EXIF orientation is one of the eight.
type Matrix = tuple[int, int, int, int]
_ORIENTATIONS: dict[Matrix, int] = {
    (1, 0, 0, 1): 1,
    (-1, 0, 0, 1): 2,  # mirrored left to right
    (-1, 0, 0, -1): 3,  # turned half round
    (1, 0, 0, -1): 4,  # mirrored top to bottom
    (0, 1, 1, 0): 5,
    (0, -1, 1, 0): 6,  # turned a quarter clockwise
    (0, -1, -1, 0): 7,
    (0, 1, -1, 0): 8,  # turned a quarter anticlockwise
}
_ANTICLOCKWISE: Matrix = (0, 1, -1, 0)
_MIRRORS: dict[int, Matrix] = {0: (-1, 0, 0, 1), 1: (1, 0, 0, -1)}  # imir's axis: 0 vertical
_TIFF = (b"II*\x00", b"MM\x00*")


class HeifError(ValueError):
    """Not a HEIF layout Mado can read."""


@dataclass(frozen=True)
class Extent:
    offset: int  # from the start of the file
    length: int


@dataclass(frozen=True)
class Layout:
    width: int | None  # the picture as stored, before it's turned
    height: int | None
    orientation: int  # how it's turned and mirrored to be shown, as EXIF numbers it
    exif: tuple[Extent, ...]  # where its Exif item is in the file; () when it has none there
    exif_inline: bytes | None  # its Exif item, when the layout keeps it itself
    profile: bytes | None = None  # its colours' ICC profile (a phone's Display P3), when it has one


def box_header(data: bytes) -> tuple[bytes, int, int | None]:
    """A box's kind, how long its header is, and how long it is in all (None: to the file's
    end), from the 16 bytes it starts with (8 do, unless it's longer than 4 GB)."""
    if len(data) < 8:
        raise HeifError("it ends partway through a box")
    size, kind = struct.unpack_from(">I4s", data)
    if size == 1:
        if len(data) < 16:
            raise HeifError("it ends partway through a box")
        return kind, 16, struct.unpack_from(">Q", data, 8)[0]
    return kind, 8, None if size == 0 else size


def top_boxes(data: bytes) -> Iterator[tuple[bytes, int, int]]:
    """Each box at the top of a file: its kind, and where its payload starts and ends."""
    yield from _boxes(data, 0, len(data))


def meta_layout(meta: bytes) -> Layout:
    """The layout a HEIF's top-level meta box holds: `meta` is the box's payload, starting with
    its version and flags."""
    children = {kind: (start, end) for kind, start, end in _boxes(meta, 4, len(meta))}
    if b"pitm" not in children:
        raise HeifError("it doesn't say which of its pictures is the picture")
    primary = _primary(meta, *children[b"pitm"])
    kinds = _item_kinds(meta, *children[b"iinf"]) if b"iinf" in children else {}
    places = _locations(meta, *children[b"iloc"]) if b"iloc" in children else {}
    properties, associated = (
        _properties(meta, *children[b"iprp"]) if b"iprp" in children else ([], {})
    )
    described = _described(meta, *children[b"iref"]) if b"iref" in children else {}

    width = height = None
    profile: bytes | None = None
    turn: Matrix = (1, 0, 0, 1)
    for index in associated.get(primary, []):
        if not 1 <= index <= len(properties):
            continue
        kind, start, end = properties[index - 1]
        if kind == b"ispe":
            width, height = _unpack(">II", meta, start + 4, end)
        elif kind == b"irot":
            for _ in range(_unpack(">B", meta, start, end)[0] & 0b11):
                turn = _then(turn, _ANTICLOCKWISE)
        elif kind == b"imir":
            turn = _then(turn, _MIRRORS[_unpack(">B", meta, start, end)[0] & 1])
        elif kind == b"colr" and meta[start : start + 4] in (b"prof", b"rICC") and end > start + 4:
            profile = meta[start + 4 : end]  # an ICC profile, as it is

    exif_items = [item for item, kind in kinds.items() if kind == b"Exif"]
    exif_items.sort(key=lambda item: primary not in described.get(item, ()))
    exif: tuple[Extent, ...] = ()
    inline = None
    if exif_items and exif_items[0] in places:
        method, extents = places[exif_items[0]]
        if method == 0:
            exif = tuple(Extent(offset, length) for offset, length in extents)
        elif method == 1 and b"idat" in children:
            start, end = children[b"idat"]
            inline = b"".join(meta[start + at : start + at + length] for at, length in extents)
    return Layout(width, height, _ORIENTATIONS[turn], exif, inline, profile)


def exif_tiff(item: bytes) -> bytes | None:
    """The TIFF data an Exif item holds, past the field saying where it starts. None when the
    item is too short to hold any."""
    if len(item) < 4:
        return None
    start = 4 + struct.unpack_from(">I", item)[0]
    data = item[start:]
    data = data.removeprefix(b"Exif\x00\x00")
    return data if data.startswith(_TIFF) else None


def _boxes(data: bytes, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    at = start
    while at + 8 <= end:
        kind, header, size = box_header(data[at : at + 16])
        size = end - at if size is None else size
        if size < header or at + size > end:
            raise HeifError(f"a {kind.decode('latin-1')} box runs past its end")
        yield kind, at + header, at + size
        at += size


def _unpack(form: str, data: bytes, start: int, end: int) -> tuple[int, ...]:
    if start + struct.calcsize(form) > end:
        raise HeifError("a box is shorter than what it should hold")
    return struct.unpack_from(form, data, start)


class _Reader:
    """Reads the numbers in one box, one after another, never past its end."""

    def __init__(self, data: bytes, start: int, end: int) -> None:
        self.data, self.at, self.end = data, start, end

    def number(self, size: int) -> int:
        if size == 0:
            return 0
        form = {1: ">B", 2: ">H", 4: ">I", 8: ">Q"}.get(size)
        if form is None:
            raise HeifError(f"a box holds a number {size} bytes long")
        (value,) = _unpack(form, self.data, self.at, self.end)
        self.at += size
        return value

    def kind(self) -> bytes:
        if self.at + 4 > self.end:
            raise HeifError("a box is shorter than what it should hold")
        self.at += 4
        return self.data[self.at - 4 : self.at]

    def version(self) -> tuple[int, int]:
        """A full box's version and flags."""
        return self.number(1), self.number(1) << 16 | self.number(2)


def _primary(data: bytes, start: int, end: int) -> int:
    read = _Reader(data, start, end)
    version, _ = read.version()
    return read.number(2 if version == 0 else 4)


def _item_kinds(data: bytes, start: int, end: int) -> dict[int, bytes]:
    """Each item's kind ("hvc1", "grid", "Exif"), by its number."""
    read = _Reader(data, start, end)
    version, _ = read.version()
    read.number(2 if version == 0 else 4)  # how many: the boxes after say for themselves
    kinds: dict[int, bytes] = {}
    for kind, entry, entry_end in _boxes(data, read.at, end):
        if kind != b"infe":
            continue
        info = _Reader(data, entry, entry_end)
        entry_version, _ = info.version()
        if entry_version < 2:
            continue  # the oldest form names no kind
        item = info.number(2 if entry_version == 2 else 4)
        info.number(2)  # protection
        kinds[item] = info.kind()
    return kinds


def _locations(data: bytes, start: int, end: int) -> dict[int, tuple[int, list[tuple[int, int]]]]:
    """Where each item's bytes are: how they're found (0 in the file, 1 in the layout's idat)
    and their extents."""
    read = _Reader(data, start, end)
    version, _ = read.version()
    sizes = read.number(1)
    offset_size, length_size = sizes >> 4, sizes & 0xF
    more = read.number(1)
    base_size, index_size = more >> 4, (more & 0xF) if version in (1, 2) else 0
    places: dict[int, tuple[int, list[tuple[int, int]]]] = {}
    for _ in range(read.number(2 if version < 2 else 4)):
        item = read.number(2 if version < 2 else 4)
        method = read.number(2) & 0xF if version in (1, 2) else 0
        read.number(2)  # which file: always this one
        base = read.number(base_size)
        extents: list[tuple[int, int]] = []
        count = read.number(2)
        # Each extent has to take room in the box, or a few bytes could ask for billions.
        if count > 1 and index_size + offset_size + length_size == 0:
            raise HeifError("its layout lists pieces of the picture that take no room")
        for _ in range(count):
            read.number(index_size)
            offset = read.number(offset_size)
            extents.append((base + offset, read.number(length_size)))
        places[item] = (method, extents)
    return places


def _properties(
    data: bytes, start: int, end: int
) -> tuple[list[tuple[bytes, int, int]], dict[int, list[int]]]:
    """The properties (each box in ipco, numbered from 1), and which each item has, in order."""
    children = {kind: (at, to) for kind, at, to in _boxes(data, start, end)}
    properties = list(_boxes(data, *children[b"ipco"])) if b"ipco" in children else []
    associated: dict[int, list[int]] = {}
    if b"ipma" in children:
        read = _Reader(data, *children[b"ipma"])
        version, flags = read.version()
        for _ in range(read.number(4)):
            item = read.number(2 if version < 1 else 4)
            wide = flags & 1
            associated[item] = [
                read.number(2 if wide else 1) & (0x7FFF if wide else 0x7F)
                for _ in range(read.number(1))
            ]
    return properties, associated


def _described(data: bytes, start: int, end: int) -> dict[int, tuple[int, ...]]:
    """The items each item describes (its cdsc references: an Exif item's picture)."""
    read = _Reader(data, start, end)
    version, _ = read.version()
    size = 2 if version == 0 else 4
    described: dict[int, tuple[int, ...]] = {}
    for kind, at, to in _boxes(data, read.at, end):
        if kind != b"cdsc":
            continue
        refs = _Reader(data, at, to)
        item = refs.number(size)
        described[item] = tuple(refs.number(size) for _ in range(refs.number(2)))
    return described


def _then(first: Matrix, then: Matrix) -> Matrix:
    """`first`, then `then`: the matrix product then × first."""
    a1, b1, c1, d1 = first
    a2, b2, c2, d2 = then
    return (a2 * a1 + b2 * c1, a2 * b1 + b2 * d1, c2 * a1 + d2 * c1, c2 * b1 + d2 * d1)
