"""Writing HEIF files, box by box, for an HDR photo: a file of one item (its gain map alone, so
ffmpeg or Pillow decodes it as a picture of its own), and an AVIF with its gain map, as ISO
21496-1 keeps one in HEIF: a hidden gain map item, and a `tmap` item made from the picture and
the gain map, holding ISO's numbers, the two named alternatives (`altr`, the HDR one first).
The picture stays the primary item, so an app that knows no gain maps shows it. Pure.
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass

from mado.core.gainmap import Info, iso_numbers
from mado.core.heif import HeifError, Items, Property, Reader, bytes_of, items_of, top_boxes

# Properties an item decoded alone leaves behind: Mado turns what it decodes itself, and the
# gain map isn't an auxiliary image once it's a file's own picture.
_LEFT_OUT = {b"irot", b"imir", b"clap", b"auxC"}


@dataclass(frozen=True)
class Entry:
    id: int
    kind: bytes
    hidden: bool
    properties: tuple[Property, ...]
    data: bytes
    in_meta: bool = False  # kept in the meta box's idat (a tmap's few numbers), not in mdat
    content_type: str = ""  # a mime item's ("application/rdf+xml")


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def full_box(kind: bytes, version: int, flags: int, payload: bytes) -> bytes:
    return box(kind, bytes([version]) + flags.to_bytes(3, "big") + payload)


def one_item(found: Items, item_id: int, read: Reader) -> bytes:
    """A HEIF (an AVIF, for AV1) whose picture is item `item_id` of `found`, its tiles with it
    when it's a grid, as stored: never turned, mirrored or cropped. Raises HeifError when the
    item isn't there."""
    item = found.items.get(item_id)
    if item is None:
        raise HeifError("its gain map isn't among its pictures")
    tiles = found.refs.get(b"dimg", {}).get(item_id, ()) if item.kind == b"grid" else ()
    members = [item, *(found.items[each] for each in tiles if each in found.items)]
    if len(members) != 1 + len(tiles):
        raise HeifError("its gain map's tiles aren't all there")
    numbering = {member.id: at + 1 for at, member in enumerate(members)}
    entries = [
        Entry(
            numbering[member.id],
            member.kind,
            member is not item,  # a grid's tiles stay hidden, as they were: only it's the picture
            tuple(each for each in member.properties if each.kind not in _LEFT_OUT),
            bytes_of(found, member, read),
        )
        for member in members
    ]
    refs = {b"dimg": {1: tuple(numbering[each] for each in tiles)}} if tiles else {}
    av1 = any(member.kind == b"av01" for member in members)
    brands = (b"avif", (b"mif1", b"avif", b"miaf")) if av1 else (b"heic", (b"mif1", b"heic"))
    return heif_file(brands, 1, entries, refs, ())


def avif_with_gain_map(picture: bytes, gain_map: bytes, info: Info) -> bytes:
    """An AVIF of `picture` (an AVIF Pillow wrote) with `gain_map` (another, of the gain map's
    values) as its gain map: the picture's items as they were (its Exif and XMP still describing
    it), the gain map hidden, and a tmap item made from both with ISO 21496-1's numbers. Raises
    HeifError for an AVIF it can't read."""
    base, base_read = _parsed(picture)
    gain, gain_read = _parsed(gain_map)
    gain_item = gain.items[gain.primary]
    if gain_item.kind != b"av01" or base.items[base.primary].kind != b"av01":
        raise HeifError("it isn't one AV1 picture as Pillow writes one")
    others = sorted(each for each in base.items if each != base.primary)
    numbering = {base.primary: 1} | {each: at + 2 for at, each in enumerate(others)}
    entries = [
        Entry(numbering[item.id], item.kind, item.hidden, item.properties, data)
        for item, data in ((each, bytes_of(base, each, base_read)) for each in base.items.values())
    ]
    gain_id = len(numbering) + 1
    tmap_id = gain_id + 1
    entries.append(
        Entry(gain_id, b"av01", True, gain_item.properties, bytes_of(gain, gain_item, gain_read))
    )
    size = base.items[base.primary].property(b"ispe")
    if size is None:
        raise HeifError("its picture doesn't say how big it is")
    entries.append(Entry(tmap_id, b"tmap", False, (size,), b"\x00" + iso_numbers(info), True))
    refs: dict[bytes, dict[int, tuple[int, ...]]] = {}
    for kind, listed in base.refs.items():
        for source, targets in listed.items():
            if source in numbering:
                refs.setdefault(kind, {})[numbering[source]] = tuple(
                    numbering[each] for each in targets if each in numbering
                )
    refs.setdefault(b"dimg", {})[tmap_id] = (1, gain_id)
    groups = ((b"altr", (tmap_id, 1)),)
    brands = (b"avif", (b"avif", b"mif1", b"miaf", b"tmap"))  # no AV1 profile claimed
    return heif_file(brands, 1, entries, refs, groups)


def _parsed(data: bytes) -> tuple[Items, Reader]:
    meta = next(((start, end) for kind, start, end in top_boxes(data) if kind == b"meta"), None)
    if meta is None:
        raise HeifError("it has no layout saying what it holds")
    return items_of(data[meta[0] : meta[1]]), lambda at, length: data[at : at + length]


def heif_file(
    brands: tuple[bytes, Sequence[bytes]],
    primary: int,
    entries: Sequence[Entry],
    refs: dict[bytes, dict[int, tuple[int, ...]]],
    groups: Sequence[tuple[bytes, tuple[int, ...]]],
) -> bytes:
    major, compatible = brands
    ftyp = box(b"ftyp", major + struct.pack(">I", 0) + b"".join(compatible))
    meta = _meta(primary, entries, refs, groups, mdat_at=0)
    mdat_at = len(ftyp) + len(meta) + 8  # where mdat's payload starts
    meta = _meta(primary, entries, refs, groups, mdat_at=mdat_at)
    mdat = b"".join(each.data for each in entries if not each.in_meta)
    return ftyp + meta + box(b"mdat", mdat)


def _meta(
    primary: int,
    entries: Sequence[Entry],
    refs: dict[bytes, dict[int, tuple[int, ...]]],
    groups: Sequence[tuple[bytes, tuple[int, ...]]],
    *,
    mdat_at: int,
) -> bytes:
    hdlr = full_box(b"hdlr", 0, 0, bytes(4) + b"pict" + bytes(12) + b"\x00")
    wide = max([primary, *(each.id for each in entries)]) > 0xFFFF
    pitm = full_box(b"pitm", 1 if wide else 0, 0, primary.to_bytes(4 if wide else 2, "big"))
    infes = [
        full_box(
            b"infe",
            3 if wide else 2,
            1 if each.hidden else 0,
            each.id.to_bytes(4 if wide else 2, "big")
            + bytes(2)  # protection: none
            + each.kind
            + b"\x00"  # its name: none
            + (each.content_type.encode("latin-1") + b"\x00" if each.kind == b"mime" else b""),
        )
        for each in entries
    ]
    iinf = full_box(
        b"iinf", 1 if wide else 0, 0, len(infes).to_bytes(4 if wide else 2, "big") + b"".join(infes)
    )
    # Each property once, every item naming those it has.
    unique: list[tuple[bytes, bytes]] = []
    associations: list[tuple[int, list[tuple[int, bool]]]] = []
    for each in entries:
        listed: list[tuple[int, bool]] = []
        for prop in each.properties:
            key = (prop.kind, prop.data)
            if key not in unique:
                unique.append(key)
            listed.append((unique.index(key) + 1, prop.essential))
        associations.append((each.id, listed))
    ipco = box(b"ipco", b"".join(box(kind, data) for kind, data in unique))
    big = len(unique) > 0x7F
    ipma_body = bytearray(len(associations).to_bytes(4, "big"))
    for item, listed in associations:
        ipma_body += item.to_bytes(4 if wide else 2, "big") + bytes([len(listed)])
        for index, essential in listed:
            if big:
                ipma_body += ((0x8000 if essential else 0) | index).to_bytes(2, "big")
            else:
                ipma_body.append((0x80 if essential else 0) | index)
    ipma = full_box(b"ipma", 1 if wide else 0, 1 if big else 0, bytes(ipma_body))
    iprp = box(b"iprp", ipco + ipma)
    # Where each item's bytes are: in mdat, one after another, or the meta box's idat.
    places = bytearray()
    in_mdat = mdat_at
    in_idat = 0
    for each in entries:
        if each.in_meta:
            method, offset = 1, in_idat
            in_idat += len(each.data)
        else:
            method, offset = 0, in_mdat
            in_mdat += len(each.data)
        places += each.id.to_bytes(4 if wide else 2, "big")
        places += method.to_bytes(2, "big") + bytes(2)  # construction method; this file
        places += (
            (1).to_bytes(2, "big") + offset.to_bytes(4, "big") + len(each.data).to_bytes(4, "big")
        )
    iloc = full_box(
        b"iloc",
        2 if wide else 1,
        0,
        bytes([0x44, 0x00]) + len(entries).to_bytes(4 if wide else 2, "big") + bytes(places),
    )
    parts = [hdlr, pitm, iloc, iinf]
    if refs:
        children = b"".join(
            box(
                kind,
                source.to_bytes(4 if wide else 2, "big")
                + len(targets).to_bytes(2, "big")
                + b"".join(target.to_bytes(4 if wide else 2, "big") for target in targets),
            )
            for kind, listed in refs.items()
            for source, targets in listed.items()
        )
        parts.append(full_box(b"iref", 1 if wide else 0, 0, children))
    parts.append(iprp)
    idat = b"".join(each.data for each in entries if each.in_meta)
    if idat:
        parts.append(box(b"idat", idat))
    if groups:
        first_free = max(each.id for each in entries) + 1
        parts.append(
            box(
                b"grpl",
                b"".join(
                    full_box(
                        kind,
                        0,
                        0,
                        (first_free + at).to_bytes(4, "big")
                        + len(members).to_bytes(4, "big")
                        + b"".join(member.to_bytes(4, "big") for member in members),
                    )
                    for at, (kind, members) in enumerate(groups)
                ),
            )
        )
    return full_box(b"meta", 0, 0, b"".join(parts))
