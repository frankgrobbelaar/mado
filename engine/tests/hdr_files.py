"""Made-up HDR photos, written by code, never real ones: a scene drawn by Pillow with a gain map
saying its sun and its lit windows go brighter on an HDR screen.

- Ultra HDR JPEGs, as Android writes them (Adobe's XMP, ISO 21496-1's numbers and MPF), or with
  only some of those pieces, as other writers do;
- HEICs with Apple's gain map (an auxiliary image, its headroom in its XMP or its MakerNote) or
  ISO 21496-1's (a tmap item), their pictures coded as AV1 by Pillow's libavif, as no GPL-free
  HEVC encoder is at hand: so Pillow decodes each item the way ffmpeg decodes a phone's;
- AVIFs with a gain map, as Mado writes them.
"""

import io
import re
import struct

import numpy as np
from PIL import Image, ImageDraw

from mado.core.gainmap import (
    APPLE_AUX,
    APPLE_NAMESPACE,
    ISO_URN,
    ISO_VERSIONS,
    Channel,
    Floats,
    GainMap,
    Info,
    encoded_of,
    iso_numbers,
)
from mado.core.heif import Property, items_of, top_boxes
from mado.core.heif_writer import Entry, avif_with_gain_map, heif_file
from mado.core.jpegs import (
    head,
    mpf_payload,
    segment,
    segments,
    ultra_hdr,
    with_segments,
    without_hdr,
)

INFO = Info((Channel(0.0, 3.0, 1.0, 1 / 64, 1 / 64),), 0.0, 3.0)
_XMP = b"http://ns.adobe.com/xap/1.0/\x00"


def scene(size: tuple[int, int] = (320, 240)) -> Image.Image:
    """A dusk scene: a sky, a dark hill, a sun top left and three lit windows."""
    width, height = size
    image = Image.new("RGB", size, (70, 90, 140))
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(0, height), (0, height * 2 // 3), (width, height // 2), (width, height)],
        fill=(30, 45, 35),
    )
    draw.ellipse([width // 16, height // 16, width // 16 + width // 6, height // 16 + width // 6],
                 fill=(255, 240, 200))  # fmt: skip
    for at in range(3):
        left = width // 2 + at * width // 10
        draw.rectangle([left, height * 3 // 4, left + width // 20, height * 3 // 4 + height // 16],
                       fill=(255, 210, 120))  # fmt: skip
    return image


def gains_for(image: Image.Image, fraction: float = 0.25, most: float = 3.0) -> Floats:
    """Gains in stops for a scene, `fraction` of its size: up to `most` where it's brightest (the
    sun, the windows), none in the dark, smooth as a phone's are."""
    width, height = image.size
    small = image.convert("L").resize(
        (max(1, round(width * fraction)), max(1, round(height * fraction))), Image.Resampling.BOX
    )
    light = np.asarray(small, np.float32) / 255.0
    return np.clip((light - 0.5) / 0.5, 0.0, 1.0).astype(np.float32) * most


def jpeg(image: Image.Image, **options: object) -> bytes:
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=92, **options)
    return out.getvalue()


def ultra_hdr_jpeg(
    size: tuple[int, int] = (320, 240),
    *,
    fraction: float = 0.25,
    orientation: int | None = None,
    info: Info = INFO,
    colour: bool = False,
    pieces: tuple[str, ...] = ("xmp", "iso", "mpf"),
    version: str | None = None,
    exif: Image.Exif | None = None,
) -> bytes:
    """An Ultra HDR JPEG of `scene`: its gain map `fraction` of its size (a colour one when
    asked), stored turned as `orientation` says (its EXIF saying so), with the pieces asked for
    (Adobe's XMP, ISO 21496-1's numbers, MPF); `version` writes another hdrgm version."""
    picture = scene(size)
    gains = gains_for(picture, fraction, info.alternate_headroom)
    if colour:
        gains = np.stack([gains, gains * 0.8, gains * 0.5], axis=2).astype(np.float32)
    values, written = encoded_of(gains, info)
    made = exif if exif is not None else Image.Exif()
    stored_picture, stored_values = picture, values
    if orientation is not None and orientation != 1:
        made[0x0112] = orientation
        stored_picture = _stored(picture, orientation)
        stored_values = np.asarray(_stored(Image.fromarray(values), orientation))
    first = jpeg(stored_picture, exif=made.tobytes())
    second = jpeg(Image.fromarray(stored_values, "RGB" if colour else "L"))
    data = ultra_hdr(first, second, written)
    if version is not None:
        data = data.replace(b'hdrgm:Version="1.0"', f'hdrgm:Version="{version}"'.encode())
    return _only(data, pieces)


def _only(data: bytes, pieces: tuple[str, ...]) -> bytes:
    """An Ultra HDR JPEG with only some of its pieces: what other writers leave out."""
    found = head(data)
    start = found.parts[1].start
    first, second = data[:start], data[start:]

    def keep(jpeg_: bytes) -> bytes:
        out = bytearray(jpeg_[:2])
        at = 2
        for each in segments(jpeg_):
            payload = jpeg_[each.payload]
            dropped = (
                ("xmp" not in pieces and each.marker == 0xE1 and payload.startswith(_XMP))
                or ("iso" not in pieces and each.marker == 0xE2 and payload.startswith(ISO_URN))
                or ("mpf" not in pieces and each.marker == 0xE2 and payload.startswith(b"MPF\x00"))
            )
            if not dropped:
                out += jpeg_[each.start : each.end]
            at = each.end
            if each.marker == 0xDA:
                break
        return bytes(out) + jpeg_[at:]

    if set(pieces) == {"xmp", "iso", "mpf"}:
        return data
    if "mpf" in pieces:
        raise ValueError("leaving pieces out moves the gain map: MPF's offsets would be wrong")
    kept_first, kept_second = keep(first), keep(second)
    # The directory says how long the gain map is: as it is now.
    told = re.search(
        rb'Item:Semantic="GainMap" Item:Mime="image/jpeg" Item:Length="(\d+)"', kept_first
    )
    if told is not None:
        kept_first = kept_first.replace(
            told.group(0), told.group(0).replace(told.group(1), str(len(kept_second)).encode())
        )
        # Its segment's length changes with the digits.
        kept_first = _fixed_lengths(kept_first)
    return kept_first + kept_second


def _fixed_lengths(jpeg_: bytes) -> bytes:
    """A JPEG whose XMP segment's text changed length, its segment length said again."""
    out = bytearray(jpeg_[:2])
    at = 2
    while at < len(jpeg_):
        marker = jpeg_[at + 1]
        if marker == 0xE1 and jpeg_[at + 4 : at + 4 + len(_XMP)] == _XMP:
            end = jpeg_.index(b"</x:xmpmeta>", at) + len(b"</x:xmpmeta>")
            payload = jpeg_[at + 4 : end]
            out += bytes([0xFF, 0xE1]) + (len(payload) + 2).to_bytes(2, "big") + payload
            at = end
            continue
        length = int.from_bytes(jpeg_[at + 2 : at + 4], "big")
        out += jpeg_[at : at + 2 + length]
        if marker == 0xDA:
            return bytes(out) + jpeg_[at + 2 + length :]
        at += 2 + length
    return bytes(out)


def _stored(image: Image.Image, orientation: int) -> Image.Image:
    """A picture as a camera stores one EXIF's `orientation` turns to show: the turn undone."""
    undo = {
        2: Image.Transpose.FLIP_LEFT_RIGHT,
        3: Image.Transpose.ROTATE_180,
        4: Image.Transpose.FLIP_TOP_BOTTOM,
        5: Image.Transpose.TRANSPOSE,
        6: Image.Transpose.ROTATE_90,
        7: Image.Transpose.TRANSVERSE,
        8: Image.Transpose.ROTATE_270,
    }
    return image.transpose(undo[orientation])


def iso_only_jpeg(size: tuple[int, int] = (320, 240), *, fraction: float = 0.25) -> bytes:
    """An HDR JPEG with ISO 21496-1's numbers and MPF, and no XMP, as some writers make one."""
    picture = scene(size)
    values, written = encoded_of(gains_for(picture, fraction, 3.0), INFO)
    second = with_segments(
        jpeg(Image.fromarray(values, "L")), segment(0xE2, ISO_URN + iso_numbers(written))
    )
    first = with_segments(jpeg(picture), segment(0xE2, ISO_URN + ISO_VERSIONS))
    placeholder = segment(0xE2, b"MPF\x00" + mpf_payload(0, 0, 0))
    first = with_segments(first, placeholder)
    header = first.index(placeholder) + 8  # past the marker, the length and "MPF\0"
    mpf = segment(0xE2, b"MPF\x00" + mpf_payload(len(first), len(second), len(first) - header))
    return first.replace(placeholder, mpf) + second


def phone_style(data: bytes, xmp: bytes) -> bytes:
    """An Ultra HDR JPEG whose gain map carries `xmp` (as a phone writes it) and no ISO numbers,
    built again from its two pictures so its parts' lengths and offsets stay right."""
    found = head(data)
    start = found.parts[1].start
    second = with_segments(without_hdr(data[start:]), segment(0xE1, _XMP + xmp))
    return ultra_hdr(data[:start], second, None)


# HEICs and AVIFs.


def av1(image: Image.Image) -> tuple[bytes, tuple[Property, ...]]:
    """A picture coded as AV1 by Pillow's libavif: its item's bytes and its properties."""
    out = io.BytesIO()
    image.save(out, format="AVIF", quality=95)
    data = out.getvalue()
    meta = next((start, end) for kind, start, end in top_boxes(data) if kind == b"meta")
    found = items_of(data[meta[0] : meta[1]])
    item = found.items[found.primary]
    picked = b"".join(data[at : at + length] for at, length in item.extents)
    return picked, item.properties


def apple_makernote(maker33: float, maker48: float) -> bytes:
    """Apple's MakerNote with its tags 33 and 48, as signed fractions, offsets from its start."""
    head = b"Apple iOS\x00" + b"\x00\x01" + b"MM"
    entries = 2
    values_at = len(head) + 2 + 12 * entries + 4
    body = struct.pack(">H", entries)
    values = b""
    for at, (tag, value) in enumerate(((33, maker33), (48, maker48))):
        body += struct.pack(">HHII", tag, 10, 1, values_at + 8 * at)
        values += struct.pack(">ii", round(value * 1_000_000), 1_000_000)
    return head + body + bytes(4) + values


def heic_with_gain_map(
    kind: str = "apple",
    size: tuple[int, int] = (320, 240),
    *,
    fraction: float = 0.5,
    picture_turn: int | None = None,
    gain_turn: int | None = None,
    headroom: float = 4.0,
    xmp_headroom: bool = True,
    makernote: tuple[float, float] | None = None,
    info: Info = INFO,
) -> bytes:
    """A HEIC of `scene` with Apple's gain map (an auxiliary image beside the picture, its headroom
    in an XMP item describing it, or in its Exif's MakerNote) or ISO 21496-1's (a tmap item). Its
    pictures are AV1, so Pillow decodes each as ffmpeg decodes a phone's; `picture_turn` and
    `gain_turn` are irot values on the picture and the gain map."""
    picture = scene(size)
    picture_data, picture_props = av1(picture)
    stops = gains_for(picture, fraction, float(np.log2(headroom)))
    if kind == "apple":  # linear: the light is the base's times 1 + (headroom - 1) × value
        linear = (np.exp2(stops) - 1.0) / (headroom - 1.0)
        stored = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)
        values = np.clip(stored * 255 + 0.5, 0, 255).astype(np.uint8)
        written = info
    else:
        values, written = encoded_of(stops, info)
    gain_data, gain_props = av1(Image.fromarray(values, "L"))
    turn = (Property(b"irot", bytes([picture_turn]), True),) if picture_turn else ()
    gain_own = (Property(b"irot", bytes([gain_turn]), True),) if gain_turn else ()
    entries = [Entry(1, b"av01", False, picture_props + turn, picture_data)]
    refs: dict[bytes, dict[int, tuple[int, ...]]] = {}
    groups: tuple[tuple[bytes, tuple[int, ...]], ...] = ()
    if kind == "apple":
        aux = Property(b"auxC", bytes(4) + APPLE_AUX + b"\x00", False)
        entries.append(Entry(2, b"av01", True, (*gain_props, aux, *gain_own), gain_data))
        refs[b"auxl"] = {2: (1,)}
        if xmp_headroom:
            xmp = (
                f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/'
                f'1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:HDRGainMap="{APPLE_NAMESPACE}"'
                f' HDRGainMap:HDRGainMapVersion="65536" HDRGainMap:HDRGainMapHeadroom='
                f'"{headroom}"/></rdf:RDF></x:xmpmeta>'
            ).encode()
            entries.append(Entry(3, b"mime", False, (), xmp, content_type="application/rdf+xml"))
            refs[b"cdsc"] = {3: (2,)}
        if makernote is not None:
            exif = Image.Exif()
            exif.get_ifd(0x8769)[0x927C] = apple_makernote(*makernote)
            entries.append(Entry(4, b"Exif", False, (), struct.pack(">I", 6) + exif.tobytes()))
            refs.setdefault(b"cdsc", {})[4] = (1,)
    else:
        entries.append(Entry(2, b"av01", True, gain_props + gain_own, gain_data))
        size_prop = next(each for each in picture_props if each.kind == b"ispe")
        entries.append(
            Entry(3, b"tmap", False, (size_prop, *turn), b"\x00" + iso_numbers(written), True)
        )
        refs[b"dimg"] = {3: (1, 2)}
        groups = ((b"altr", (3, 1)),)
    return heif_file((b"heic", (b"mif1", b"heic")), 1, entries, refs, groups)


def avif_hdr(
    size: tuple[int, int] = (320, 240), *, fraction: float = 0.25, info: Info = INFO
) -> bytes:
    """An AVIF of `scene` with its gain map, as Mado writes one (a tmap item)."""
    picture = scene(size)
    values, written = encoded_of(gains_for(picture, fraction, info.alternate_headroom), info)
    base, gain = io.BytesIO(), io.BytesIO()
    picture.save(base, format="AVIF", quality=90)
    Image.fromarray(values, "L").save(gain, format="AVIF", quality=95)
    return avif_with_gain_map(base.getvalue(), gain.getvalue(), written)


def damaged_avif() -> bytes:
    """An AVIF with its gain map, the gain map's coded picture garbage of the same length: its
    boxes whole, its pixels not (Pillow's AVIF reader raises RuntimeError or SyntaxError)."""
    picture = scene((320, 240))
    values, written = encoded_of(gains_for(picture, 0.25, 3.0), INFO)
    base, gain = io.BytesIO(), io.BytesIO()
    picture.save(base, format="AVIF", quality=90)
    Image.fromarray(values, "L").save(gain, format="AVIF", quality=95)
    coded = bytearray(gain.getvalue())
    at = coded.rindex(b"mdat") + 4
    coded[at:] = bytes((at * 7 + n * 13) % 256 for n in range(len(coded) - at))
    return avif_with_gain_map(base.getvalue(), bytes(coded), written)


def hdr_jpeg_of(picture: Image.Image, *, quality: int = 92, info: Info = INFO) -> bytes:
    """An Ultra HDR JPEG of any made-up picture, its gain map `gains_for` it, a quarter of its
    size, written as Mado writes one."""
    from mado.encode import with_gain_map

    gains = gains_for(picture, 0.25, info.alternate_headroom)
    options: dict[str, object] = {"quality": quality, "subsampling": 0}
    return with_gain_map(picture.convert("RGB"), "JPEG", options, GainMap(gains, info))
