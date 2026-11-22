"""Made-up HEIF files, built box by box: the parts Mado reads (its layout and its Exif), around
a few bytes standing in for the picture, which only ffmpeg would decode."""

import struct

from PIL import Image

PICTURE = b"\x00\x00\x00\x01made-up picture data"


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def full_box(kind: bytes, version: int, flags: int, payload: bytes) -> bytes:
    return box(kind, bytes([version]) + flags.to_bytes(3, "big") + payload)


def exif_item(exif: Image.Exif) -> bytes:
    """An Exif item as HEIF keeps it: where its TIFF header starts, then "Exif\\0\\0" and TIFF."""
    return struct.pack(">I", 6) + exif.tobytes()


def heif(
    *,
    width: int = 4032,
    height: int = 3024,
    transforms: tuple[tuple[bytes, int], ...] = (),
    exif: bytes | None = None,
    exif_in_meta: bool = False,
    wide_associations: bool = False,
) -> bytes:
    """A HEIF file whose primary item is `width` by `height`, turned by `transforms` (("irot",
    1) turns it 90 degrees anticlockwise, ("imir", 0) mirrors it left to right) in that order,
    with `exif` as its Exif item, kept in the meta box's idat or after it in mdat."""
    ftyp = box(b"ftyp", b"heic" + struct.pack(">I", 0) + b"mif1heic")
    meta = _meta(width, height, transforms, exif, exif_in_meta, wide_associations, mdat_at=0)
    mdat_at = len(ftyp) + len(meta) + 8  # where mdat's payload starts
    meta = _meta(width, height, transforms, exif, exif_in_meta, wide_associations, mdat_at)
    data = PICTURE if exif is None or exif_in_meta else exif + PICTURE
    return ftyp + meta + box(b"mdat", data)


def _meta(
    width: int,
    height: int,
    transforms: tuple[tuple[bytes, int], ...],
    exif: bytes | None,
    exif_in_meta: bool,
    wide_associations: bool,
    mdat_at: int,
) -> bytes:
    hdlr = full_box(b"hdlr", 0, 0, struct.pack(">I", 0) + b"pict" + bytes(12) + b"\x00")
    pitm = full_box(b"pitm", 0, 0, struct.pack(">H", 1))
    entries = [_infe(1, b"hvc1")] + ([_infe(2, b"Exif")] if exif is not None else [])
    iinf = full_box(b"iinf", 0, 0, struct.pack(">H", len(entries)) + b"".join(entries))
    properties = [full_box(b"ispe", 0, 0, struct.pack(">II", width, height))]
    properties += [box(kind, bytes([value])) for kind, value in transforms]
    ipco = box(b"ipco", b"".join(properties))
    indexes = range(1, len(properties) + 1)
    if wide_associations:  # flags 1: each association in two bytes
        associations = b"".join(struct.pack(">H", 0x8000 | index) for index in indexes)
    else:
        associations = bytes(0x80 | index for index in indexes)
    ipma = full_box(
        b"ipma",
        0,
        1 if wide_associations else 0,
        struct.pack(">IHB", 1, 1, len(properties)) + associations,
    )
    iprp = box(b"iprp", ipco + ipma)
    picture_at = mdat_at + (len(exif) if exif is not None and not exif_in_meta else 0)
    locations = [(1, 0, picture_at, len(PICTURE))]
    parts = [hdlr, pitm, iinf]
    if exif is not None:
        locations.append((2, 1, 0, len(exif)) if exif_in_meta else (2, 0, mdat_at, len(exif)))
        parts.append(full_box(b"iref", 0, 0, box(b"cdsc", struct.pack(">HHH", 2, 1, 1))))
    iloc = full_box(
        b"iloc",
        1,
        0,
        bytes([0x44, 0x00])
        + struct.pack(">H", len(locations))
        + b"".join(
            struct.pack(">HHHHII", item, method, 0, 1, offset, length)
            for item, method, offset, length in locations
        ),
    )
    parts += [iprp, iloc]
    if exif is not None and exif_in_meta:
        parts.append(box(b"idat", exif))
    return full_box(b"meta", 0, 0, b"".join(parts))


def _infe(item: int, kind: bytes) -> bytes:
    return full_box(b"infe", 2, 0, struct.pack(">HH", item, 0) + kind + b"\x00")
