"""A JPEG's pieces, as an HDR photo needs them: its segments up to its picture, the XMP, ISO
21496-1 and MPF (Multi-Picture Format) segments an Ultra HDR JPEG keeps, where its gain map is,
and an Ultra HDR JPEG put together from a picture and its gain map. Pure.

An Ultra HDR JPEG is two JPEGs one after the other: the picture, then its gain map. The picture
says there's a second in three ways: its MPF segment lists both (where each starts, counted from
the MPF's own header), its XMP names hdrgm's version and lists both in a directory (the gain map
by its length), and an APP2 segment with ISO 21496-1's versions says the gain map's numbers
follow ISO's way. The gain map has its own XMP with Adobe's numbers, and its own APP2 with ISO's.
Mado writes all of it, as Android does, so phones, browsers and Windows read it whichever way
they look; an app that knows none of it shows the picture.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from mado.core.gainmap import ISO_URN, ISO_VERSIONS, Info, gain_map_xmp, iso_numbers, primary_xmp

SOI = b"\xff\xd8"
_XMP = b"http://ns.adobe.com/xap/1.0/\x00"
_MPF = b"MPF\x00"
_SOS, _EOI = 0xDA, 0xD9
_APP1, _APP2 = 0xE1, 0xE2
_STANDALONE = {0x01, *range(0xD0, 0xD8)}  # markers with no length: TEM and the restarts
_MOST_PAYLOAD = 65533  # a segment's payload at most
_MPF_VERSION, _MPF_COUNT, _MPF_ENTRIES = 0xB000, 0xB001, 0xB002
_PRIMARY = 0x030000  # MPF's attribute for the baseline primary picture


class JpegError(ValueError):
    """Not a JPEG as Mado reads one, with why."""


@dataclass(frozen=True)
class Segment:
    marker: int  # 0xE1 for APP1…
    start: int  # where its 0xFF is
    end: int  # just past it

    @property
    def payload(self) -> slice:
        return slice(self.start + 4, self.end)


@dataclass(frozen=True)
class Part:
    """One of the pictures an MPF segment lists: where it starts in the file, and how long it is."""

    start: int
    length: int
    primary: bool


@dataclass(frozen=True)
class Head:
    """What a JPEG's segments before its picture say of an HDR photo."""

    xmp: bytes | None  # its XMP packet
    iso: bytes | None  # its ISO 21496-1 numbers, past the URN
    parts: tuple[Part, ...]  # what its MPF lists, the first being itself
    picture_at: int  # where its picture's data starts: past the segments read
    whole: bool  # the bytes read reached its picture: nothing before it was missed


def segments(data: bytes) -> Iterator[Segment]:
    """Each segment from the start of a JPEG to its picture's data (the start of scan, which it
    stops after). Raises JpegError when it isn't a JPEG, or one ends before its picture does; a
    head `data` cut short of its picture just stops."""
    if not data.startswith(SOI):
        raise JpegError("it doesn't start as a JPEG does")
    at = 2
    while at + 4 <= len(data):
        if data[at] != 0xFF:
            raise JpegError("a segment doesn't start where the one before it ends")
        marker = data[at + 1]
        if marker == 0xFF:  # fill bytes before a marker
            at += 1
            continue
        if marker in _STANDALONE:
            at += 2
            continue
        length = int.from_bytes(data[at + 2 : at + 4], "big")
        if length < 2:
            raise JpegError("a segment says it's shorter than itself")
        segment = Segment(marker, at, at + 2 + length)
        yield segment
        if marker in (_SOS, _EOI):
            return
        at = segment.end


def head(data: bytes) -> Head:
    """What a JPEG's first bytes (its segments, at least up to its picture) say of an HDR photo.
    Raises JpegError."""
    xmp: bytes | None = None
    iso: bytes | None = None
    parts: tuple[Part, ...] = ()
    picture_at = 0
    whole = False
    for found in segments(data):
        if found.end > len(data):
            break  # cut short: the caller reads more
        payload = data[found.payload]
        if found.marker == _APP1 and payload.startswith(_XMP) and xmp is None:
            xmp = payload[len(_XMP) :]
        elif found.marker == _APP2 and payload.startswith(ISO_URN) and iso is None:
            iso = payload[len(ISO_URN) :]
        elif found.marker == _APP2 and payload.startswith(_MPF) and not parts:
            parts = mpf_parts(payload[len(_MPF) :], found.start + 4 + len(_MPF))
        picture_at = found.end
        whole = found.marker == _SOS
    return Head(xmp, iso, parts, picture_at, whole)


def mpf_parts(data: bytes, at: int) -> tuple[Part, ...]:
    """The pictures an MPF segment lists (`data` past its "MPF\\0", whose header is `at` in the
    file): each one's start in the file and length. Nothing when its numbers make no sense."""
    if len(data) < 8 or data[:4] not in (b"II*\x00", b"MM\x00*"):
        return ()
    order = "little" if data[:2] == b"II" else "big"

    def number(offset: int, size: int) -> int:
        if offset + size > len(data):
            raise JpegError("its MPF is cut short")
        return int.from_bytes(data[offset : offset + size], order)

    try:
        directory = number(4, 4)
        count = number(directory, 2)
        entries = 0
        listed = 0
        for index in range(count):
            field = directory + 2 + 12 * index
            tag = number(field, 2)
            if tag == _MPF_COUNT:
                listed = number(field + 8, 4)
            elif tag == _MPF_ENTRIES:
                entries = number(field + 8, 4)
        if not entries or not 1 <= listed <= 16:
            return ()
        found: list[Part] = []
        for index in range(listed):
            entry = entries + 16 * index
            attribute = number(entry, 4)
            length = number(entry + 4, 4)
            offset = number(entry + 8, 4)
            primary = (attribute & 0xFFFFFF) == _PRIMARY or index == 0
            found.append(Part(0 if index == 0 else at + offset, length, primary))
    except JpegError:
        return ()
    return tuple(found)


def size_of(data: bytes) -> tuple[int, int] | None:
    """A JPEG's width and height, from its frame header, as stored (before any EXIF turn); None
    when the bytes read don't reach it."""
    for found in segments(data):
        if found.end > len(data):
            return None
        if 0xC0 <= found.marker <= 0xCF and found.marker not in (0xC4, 0xC8, 0xCC):
            payload = data[found.payload]
            if len(payload) >= 5:
                height = int.from_bytes(payload[1:3], "big")
                width = int.from_bytes(payload[3:5], "big")
                return (width, height) if width and height else None
    return None


def segment(marker: int, payload: bytes) -> bytes:
    """A segment with its marker and length. Raises JpegError past a segment's 64 KB."""
    if len(payload) > _MOST_PAYLOAD:
        raise JpegError("a piece is too big for one JPEG segment")
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def with_segments(jpeg: bytes, added: bytes) -> bytes:
    """A JPEG with segments added after its own APP and comment segments (so JFIF, EXIF and its
    colour profile stay first), before its tables and picture."""
    at = _past_apps(jpeg)
    return jpeg[:at] + added + jpeg[at:]


def _past_apps(jpeg: bytes) -> int:
    at = 2
    for found in segments(jpeg):
        if not (0xE0 <= found.marker <= 0xEF or found.marker == 0xFE):
            break
        at = found.end
    return at


def without_hdr(jpeg: bytes) -> bytes:
    """A JPEG without any XMP, ISO 21496-1 or MPF segment of its own (Pillow keeps none of them,
    but a JPEG handed over might): Mado writes its own."""
    out = bytearray(jpeg[:2])
    at = 2
    for found in segments(jpeg):
        payload = jpeg[found.payload]
        dropped = (found.marker == _APP1 and payload.startswith(_XMP)) or (
            found.marker == _APP2 and (payload.startswith(ISO_URN) or payload.startswith(_MPF))
        )
        if not dropped:
            out += jpeg[found.start : found.end]
        at = found.end
        if found.marker == _SOS:
            break
    return bytes(out) + jpeg[at:]


def ultra_hdr(picture: bytes, gain_map: bytes, info: Info | None) -> bytes:
    """An Ultra HDR JPEG: `picture` (a JPEG) with hdrgm's XMP and its directory, ISO 21496-1's
    versions and an MPF segment listing both, then `gain_map` (a JPEG) with Adobe's numbers in
    its XMP and ISO's in its APP2 (`info` None: the gain map picture as it is, its own pieces
    kept, as another writer's)."""
    second = (
        gain_map
        if info is None
        else with_segments(
            without_hdr(gain_map),
            segment(_APP1, _XMP + gain_map_xmp(info)) + segment(_APP2, ISO_URN + iso_numbers(info)),
        )
    )
    base = without_hdr(picture)
    at = _past_apps(base)
    before = segment(_APP1, _XMP + primary_xmp(len(second))) + segment(
        _APP2, ISO_URN + ISO_VERSIONS
    )
    mpf_length = 4 + len(_MPF) + len(mpf_payload(0, 0, 0))
    first_length = len(base) + len(before) + mpf_length
    header = (
        at + len(before) + 4 + len(_MPF)
    )  # where MPF's own header is: its offsets count from it
    mpf = segment(_APP2, _MPF + mpf_payload(first_length, len(second), first_length - header))
    return base[:at] + before + mpf + base[at:] + second


def mpf_payload(first: int, second: int, second_at: int) -> bytes:
    """MPF's header and index for two pictures, big-endian: its version, how many, and each
    one's attribute, length and start (the first's always 0)."""
    out = bytearray(b"MM\x00*" + (8).to_bytes(4, "big"))
    out += (3).to_bytes(2, "big")
    out += _MPF_VERSION.to_bytes(2, "big") + (7).to_bytes(2, "big") + (4).to_bytes(4, "big")
    out += b"0100"
    out += _MPF_COUNT.to_bytes(2, "big") + (4).to_bytes(2, "big") + (1).to_bytes(4, "big")
    out += (2).to_bytes(4, "big")
    entries = 8 + 2 + 3 * 12 + 4  # past the header, the index and the next index's place (none)
    out += _MPF_ENTRIES.to_bytes(2, "big") + (7).to_bytes(2, "big") + (32).to_bytes(4, "big")
    out += entries.to_bytes(4, "big")
    out += bytes(4)
    for attribute, length, start in ((_PRIMARY, first, 0), (0, second, second_at)):
        out += attribute.to_bytes(4, "big") + length.to_bytes(4, "big") + start.to_bytes(4, "big")
        out += bytes(4)
    return bytes(out)
