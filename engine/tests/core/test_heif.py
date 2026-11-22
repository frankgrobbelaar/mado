"""Reading a HEIF file's layout: its size, which way up it goes, and where its Exif is."""

import struct

import pytest
from PIL import Image

from mado.core.heif import HeifError, exif_tiff, meta_layout, top_boxes
from tests.heif_files import exif_item, full_box, heif


def layout_of(data: bytes):
    meta = next((start, end) for kind, start, end in top_boxes(data) if kind == b"meta")
    return meta_layout(data[meta[0] : meta[1]])


def made_up_exif() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "Pixelworks"
    return exif_item(exif)


def test_a_heif_says_how_big_its_picture_is():
    found = layout_of(heif(width=4032, height=3024))

    assert (found.width, found.height, found.orientation) == (4032, 3024, 1)
    assert found.exif == ()
    assert found.exif_inline is None


@pytest.mark.parametrize(
    ("transforms", "orientation"),
    [
        (((b"irot", 1),), 8),  # 90 degrees anticlockwise
        (((b"irot", 2),), 3),
        (((b"irot", 3),), 6),  # 270 anticlockwise: 90 clockwise
        (((b"imir", 0),), 2),  # mirrored left to right
        (((b"imir", 1),), 4),  # top to bottom
        (((b"imir", 0), (b"irot", 1)), 5),  # mirrored, then turned anticlockwise
        (((b"imir", 0), (b"irot", 3)), 7),
        (((b"irot", 2), (b"imir", 1)), 2),
    ],
)
def test_a_heif_turned_or_mirrored_says_so_as_exif_numbers_it(
    transforms: tuple[tuple[bytes, int], ...], orientation: int
):
    assert layout_of(heif(transforms=transforms)).orientation == orientation


def test_a_heif_says_where_its_exif_is_in_the_file():
    item = made_up_exif()
    data = heif(exif=item)

    [extent] = layout_of(data).exif

    assert data[extent.offset : extent.offset + extent.length] == item


def test_a_heif_may_keep_its_exif_inside_its_layout():
    item = made_up_exif()

    found = layout_of(heif(exif=item, exif_in_meta=True))

    assert found.exif == ()
    assert found.exif_inline == item


def test_properties_listed_two_bytes_each_are_read_too():
    found = layout_of(heif(transforms=((b"irot", 3),), wide_associations=True))

    assert (found.width, found.height, found.orientation) == (4032, 3024, 6)


def test_the_tiff_inside_an_exif_item_is_found_past_its_header():
    exif = Image.Exif()
    exif[0x010F] = "Pixelworks"

    tiff = exif_tiff(exif_item(exif))

    assert tiff is not None
    assert tiff.startswith((b"II*\x00", b"MM\x00*"))


def test_an_exif_item_too_short_to_hold_any_says_nothing():
    assert exif_tiff(b"\x00\x00") is None
    assert exif_tiff(b"\x00\x00\x00\xff" + b"short") is None


def test_something_that_isnt_a_heif_layout_is_refused():
    with pytest.raises(HeifError):
        meta_layout(b"\x00\x00\x00\x00" + b"\x00\x00\x00\x30iinf")  # a box running past the end
    with pytest.raises(HeifError):
        meta_layout(b"\x00\x00\x00\x00")  # no primary item at all


def test_a_layout_whose_pieces_take_no_room_is_refused_rather_than_counted():
    # Offsets, lengths and indexes all 0 bytes wide: each piece would cost nothing to read, so
    # a few hundred bytes could ask for billions of them.
    pitm = full_box(b"pitm", 0, 0, struct.pack(">H", 1))
    items = [struct.pack(">HHHH", item, 0, 0, 65535) for item in (1, 2)]
    iloc = full_box(b"iloc", 1, 0, bytes([0x00, 0x00]) + struct.pack(">H", 2) + b"".join(items))

    with pytest.raises(HeifError):
        meta_layout(bytes(4) + pitm + iloc)


def test_top_level_boxes_are_listed_with_where_each_payload_is():
    data = heif()

    kinds = [kind for kind, _, _ in top_boxes(data)]

    assert kinds == [b"ftyp", b"meta", b"mdat"]
