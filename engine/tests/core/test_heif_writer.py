"""Writing HEIF files box by box: a gain map item alone, as Mado hands it to a decoder, and an
AVIF with its gain map."""

import struct

from mado.core.heif import Items, Property, Reader, items_of, top_boxes
from mado.core.heif_writer import Entry, heif_file, one_item
from tests.hdr_files import avif_hdr


def test_an_avif_with_its_gain_map_claims_only_the_brands_it_keeps_to():
    # Pillow's AVIFs aren't always AV1's baseline profile (4:4:4, or past 8K): no MA1B.
    data = avif_hdr((320, 240))
    start, end = next((start, end) for kind, start, end in top_boxes(data) if kind == b"ftyp")
    ftyp = data[start:end]
    major, compatible = ftyp[:4], {ftyp[at : at + 4] for at in range(8, len(ftyp), 4)}
    assert major == b"avif"
    assert compatible == {b"avif", b"mif1", b"miaf", b"tmap"}


def _size(width: int, height: int) -> Property:
    return Property(b"ispe", bytes(4) + struct.pack(">II", width, height), False)


def _parsed(data: bytes) -> Items:
    start, end = next((start, end) for kind, start, end in top_boxes(data) if kind == b"meta")
    return items_of(data[start:end])


def _reader(data: bytes) -> Reader:
    def read(at: int, length: int) -> bytes:
        return data[at : at + length]

    return read


def test_a_grid_gain_map_alone_keeps_its_tiles_hidden_and_itself_the_picture():
    # A phone's gain map is often a grid of tiles, each hidden: only the grid is a picture.
    grid = bytes([0, 0, 0, 1]) + struct.pack(">HH", 128, 64)  # 1 row, 2 columns, 128 × 64
    entries = [
        Entry(1, b"hvc1", False, (_size(256, 128),), b"picture"),
        Entry(2, b"grid", True, (_size(128, 64),), grid),
        Entry(3, b"hvc1", True, (_size(64, 64),), b"left tile"),
        Entry(4, b"hvc1", True, (_size(64, 64),), b"right tile"),
    ]
    data = heif_file((b"heic", (b"mif1", b"heic")), 1, entries, {b"dimg": {2: (3, 4)}}, ())
    found = _parsed(data)

    alone = one_item(found, 2, _reader(data))

    made = _parsed(alone)
    assert made.primary == 1
    assert made.items[1].kind == b"grid"
    assert not made.items[1].hidden
    tiles = made.refs[b"dimg"][1]
    assert [made.items[each].hidden for each in tiles] == [True, True]
    assert [made.items[each].kind for each in tiles] == [b"hvc1", b"hvc1"]
