"""HDR photos' gain maps, as Mado reads, keeps and writes them. Pure.

A recent phone's HDR photo is an ordinary picture (its base) and a gain map: a smaller picture,
grey or in colour, saying how many times brighter each part of the base may go on an HDR screen.
A screen with all the photo's headroom shows the whole gain; one with less shows part of it, by
the weight its own headroom gives (`weight`); an ordinary screen shows the base. Mado keeps a
gain map as numbers of its own: each place's gain in stops (log2 of how many times brighter the
HDR rendition is there than the ordinary one), with what the gain map says beside them (`Info`):
how far each rendition goes past ordinary white, the offsets that keep black from dividing, and
whether the gains apply in the base's colours. The base is usually the ordinary rendition; when
it's the HDR one, its ordinary rendition divides by the gains, as ISO 21496-1 has it (Chromium
draws it so: checked in Edge).

They come written three ways, each read here into the same `Info`:
- Adobe's gain map XMP (`hdrgm`), which Google's Ultra HDR JPEGs carry;
- ISO 21496-1's numbers, in a JPEG's APP2 segment or a HEIF's or AVIF's `tmap` item;
- Apple's: a gain map whose values are linear, and a headroom (its XMP, or its MakerNote's).
A gain map of a version Mado doesn't know raises GainMapError, and its picture is shown and
saved as it is, without its HDR.

Mado writes a gain map as Adobe's XMP and ISO 21496-1's numbers together (Android, Chromium and
Windows read one or the other), from the gains it kept: their least and most made afresh from
what's there, the curve straight (gamma 1), the headroom and offsets as the photo had them.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Literal

import numpy as np
import numpy.typing as npt

type Floats = npt.NDArray[np.float32]
type Bytes = npt.NDArray[np.uint8]

XMP_NAMESPACE = "http://ns.adobe.com/hdr-gain-map/1.0/"
ISO_URN = b"urn:iso:std:iso:ts:21496:-1\x00"  # what a JPEG's APP2 with ISO 21496-1 starts with
APPLE_AUX = b"urn:com:apple:photo:2020:aux:hdrgainmap"  # Apple's gain map, as its HEIF names it
APPLE_NAMESPACE = "http://ns.apple.com/HDRGainMap/1.0/"
VERSION = "1.0"  # the hdrgm version Mado reads and writes
DEFAULT_OFFSET = 1 / 64  # Adobe's, for an offset the XMP doesn't give
LUMA = (0.2126, 0.7152, 0.0722)  # each colour's share of light (Rec. 709, sRGB's primaries)
_DENOMINATOR = 1_000_000  # ISO 21496-1's fractions, written: to a millionth
_LEAST_SPREAD = 1 / 256  # stops between a gain map's least and most, at the very least
_INT32 = 2**31
_FLAGS = {"colour": 0x80, "base_colours": 0x40, "common": 0x08, "backward": 0x04}


class GainMapError(ValueError):
    """A gain map Mado can't read: a version it doesn't know, or numbers that make no sense, with
    a sentence saying why (said after "Its gain map")."""


@dataclass(frozen=True)
class Channel:
    """How one channel's values are gains: its least and most (in stops), the curve between
    them, and the offsets added to each rendition's light before the gain is taken."""

    low: float  # stops: the gain a value of 0 says
    high: float  # stops: the gain a value of 1 (255) says
    gamma: float = 1.0
    base_offset: float = DEFAULT_OFFSET
    alternate_offset: float = DEFAULT_OFFSET


@dataclass(frozen=True)
class Info:
    """What a gain map says."""

    channels: tuple[Channel, ...]  # one, or red, green and blue
    base_headroom: float  # stops past ordinary white the base reaches: 0 for an ordinary base
    alternate_headroom: float  # stops the other rendition reaches
    base_colours: bool = True  # the gains apply in the base's colour space

    @property
    def base_is_hdr(self) -> bool:
        """The base is the HDR rendition, and the gains make the ordinary one."""
        return self.base_headroom > self.alternate_headroom

    @property
    def stops(self) -> float:
        """How many stops past ordinary white the HDR rendition goes."""
        return max(self.base_headroom, self.alternate_headroom)

    @property
    def colour(self) -> bool:
        return len(self.channels) == 3


@dataclass(frozen=True)
class GainMap:
    """A gain map as Mado works on it: each place's gain in stops, how much brighter the HDR
    rendition is there (height × width, or × 3 for a colour gain map), and what it says."""

    gains: Floats
    info: Info

    @property
    def size(self) -> tuple[int, int]:
        """Width and height."""
        return int(self.gains.shape[1]), int(self.gains.shape[0])


# Adobe's XMP (hdrgm), as Ultra HDR JPEGs carry it.


def xmp_version(packet: bytes) -> str | None:
    """The hdrgm version an XMP packet names (a primary picture's says only that, beside the
    directory of its parts); None when it names none."""
    text = _text(packet)
    prefix = _prefix(text, XMP_NAMESPACE)
    if prefix is None:
        return None
    found = _values(text, prefix, "Version")
    return found[0] if found else None


def from_xmp(packet: bytes) -> Info | None:
    """What a gain map's own hdrgm XMP says; None when it says no gain map's numbers (a primary
    picture's, naming only its version). Raises GainMapError for a version Mado doesn't know, or
    numbers that make no sense."""
    text = _text(packet)
    prefix = _prefix(text, XMP_NAMESPACE)
    if prefix is None:
        return None
    version = (_values(text, prefix, "Version") or [None])[0]
    if version is not None and version.strip() != VERSION:
        raise GainMapError(f"is version {version.strip()[:12]}, which Mado doesn't know yet")
    highs = _numbers(text, prefix, "GainMapMax")
    most = _numbers(text, prefix, "HDRCapacityMax")
    if not highs or not most:
        return None
    lows = _numbers(text, prefix, "GainMapMin") or [0.0]
    gammas = _numbers(text, prefix, "Gamma") or [1.0]
    sdr_offsets = _numbers(text, prefix, "OffsetSDR") or [DEFAULT_OFFSET]
    hdr_offsets = _numbers(text, prefix, "OffsetHDR") or [DEFAULT_OFFSET]
    least = (_numbers(text, prefix, "HDRCapacityMin") or [0.0])[0]
    base_hdr = (_values(text, prefix, "BaseRenditionIsHDR") or ["False"])[0].strip() == "True"
    count = max(len(each) for each in (lows, highs, gammas, sdr_offsets, hdr_offsets))
    if count not in (1, 3) or any(
        len(each) not in (1, count) for each in (lows, highs, gammas, sdr_offsets, hdr_offsets)
    ):
        raise GainMapError("gives its numbers for a number of colours Mado doesn't know")
    channels = tuple(
        Channel(
            low=_at(lows, c),
            high=_at(highs, c),
            gamma=_at(gammas, c),
            base_offset=_at(hdr_offsets if base_hdr else sdr_offsets, c),
            alternate_offset=_at(sdr_offsets if base_hdr else hdr_offsets, c),
        )
        for c in range(count)
    )
    return _checked(
        Info(
            channels=channels,
            base_headroom=most[0] if base_hdr else least,
            alternate_headroom=least if base_hdr else most[0],
        )
    )


def gain_map_xmp(info: Info) -> bytes:
    """The XMP a gain map picture of Mado's carries: Adobe's hdrgm numbers."""
    base_hdr = info.base_is_hdr
    sdr = [c.alternate_offset if base_hdr else c.base_offset for c in info.channels]
    hdr = [c.base_offset if base_hdr else c.alternate_offset for c in info.channels]
    least = min(info.base_headroom, info.alternate_headroom)
    fields: list[tuple[str, list[str]]] = [
        ("Version", [VERSION]),
        ("GainMapMin", [_said(c.low) for c in info.channels]),
        ("GainMapMax", [_said(c.high) for c in info.channels]),
        ("Gamma", [_said(c.gamma) for c in info.channels]),
        ("OffsetSDR", [_said(each) for each in sdr]),
        ("OffsetHDR", [_said(each) for each in hdr]),
        ("HDRCapacityMin", [_said(least)]),
        ("HDRCapacityMax", [_said(info.stops)]),
        ("BaseRenditionIsHDR", ["True" if base_hdr else "False"]),
    ]
    # One value is an attribute; a colour gain map's three are a list (rdf:Seq) in an element.
    attributes = "".join(
        f'\n     hdrgm:{name}="{values[0]}"' for name, values in fields if len(values) == 1
    )
    elements = "".join(
        f"\n      <hdrgm:{name}><rdf:Seq>"
        + "".join(f"<rdf:li>{each}</rdf:li>" for each in values)
        + f"</rdf:Seq></hdrgm:{name}>"
        for name, values in fields
        if len(values) > 1
    )
    return _packet(
        f'<rdf:Description rdf:about=""\n     xmlns:hdrgm="{XMP_NAMESPACE}"{attributes}'
        + (f">{elements}\n    </rdf:Description>" if elements else "/>")
    )


def primary_xmp(gain_map_length: int) -> bytes:
    """The XMP an Ultra HDR JPEG's primary picture carries: the hdrgm version, and the directory
    of its parts (itself, then its gain map, `gain_map_length` bytes, right after it)."""
    container = "http://ns.google.com/photos/1.0/container/"
    item = "http://ns.google.com/photos/1.0/container/item/"
    return _packet(
        f'<rdf:Description rdf:about=""\n     xmlns:Container="{container}"'
        f'\n     xmlns:Item="{item}"\n     xmlns:hdrgm="{XMP_NAMESPACE}"'
        f'\n     hdrgm:Version="{VERSION}">'
        "\n      <Container:Directory><rdf:Seq>"
        '\n        <rdf:li rdf:parseType="Resource"><Container:Item Item:Semantic="Primary"'
        ' Item:Mime="image/jpeg"/></rdf:li>'
        '\n        <rdf:li rdf:parseType="Resource"><Container:Item Item:Semantic="GainMap"'
        f' Item:Mime="image/jpeg" Item:Length="{gain_map_length}"/></rdf:li>'
        "\n      </rdf:Seq></Container:Directory>"
        "\n    </rdf:Description>"
    )


def container_length(packet: bytes) -> int | None:
    """How long a primary picture's XMP directory says its gain map is: Ultra HDR's way of finding
    it when a JPEG has no MPF. None when it doesn't say."""
    text = _text(packet)
    for item in re.finditer(r"<(\w+):Item\b([^>]*)>", text):
        attributes = item.group(2)
        semantic = re.search(r'\b\w+:Semantic\s*=\s*["\']([^"\']*)', attributes)
        length = re.search(r'\b\w+:Length\s*=\s*["\'](\d+)', attributes)
        if semantic and semantic.group(1) == "GainMap" and length:
            return int(length.group(1))
    return None


def apple_xmp_headroom(packet: bytes) -> float | None:
    """The headroom Apple's gain map XMP gives (HDRGainMap:HDRGainMapHeadroom, times brighter);
    None when it gives none."""
    text = _text(packet)
    prefix = _prefix(text, APPLE_NAMESPACE)
    if prefix is None:
        return None
    found = _numbers(text, prefix, "HDRGainMapHeadroom")
    return found[0] if found and found[0] >= 1.0 else None


# ISO 21496-1's numbers.


def iso_version_only(data: bytes) -> bool:
    """Whether ISO 21496-1's numbers in a primary picture's APP2 (past its URN) are only the
    versions, as a base picture's are: the gain map picture holds the rest."""
    return len(data) >= 4 and _u16(data, 0) == 0 and len(data) < 9


def from_iso(data: bytes) -> Info:
    """ISO 21496-1's numbers (past a JPEG APP2's URN, or past a tmap item's version byte).
    Raises GainMapError for a version Mado doesn't know, or numbers that don't add up."""
    if len(data) < 5:
        raise GainMapError("is cut short")
    minimum = _u16(data, 0)
    if minimum != 0:
        raise GainMapError(f"is version {minimum}, which Mado doesn't know yet")
    flags = data[4]
    if flags & _FLAGS["backward"]:
        raise GainMapError("is made backwards from the HDR picture, which Mado doesn't keep yet")
    count = 3 if flags & _FLAGS["colour"] else 1
    at = 5

    def fraction(signed: bool, denominator: int | None = None) -> Fraction:
        nonlocal at
        if denominator is None:
            if at + 8 > len(data):
                raise GainMapError("is cut short")
            top = _s32(data, at) if signed else _u32(data, at)
            bottom = _u32(data, at + 4)
            at += 8
        else:
            if at + 4 > len(data):
                raise GainMapError("is cut short")
            top = _s32(data, at) if signed else _u32(data, at)
            bottom = denominator
            at += 4
        if bottom == 0:
            raise GainMapError("divides by nought")
        return Fraction(top, bottom)

    common: int | None = None
    if flags & _FLAGS["common"]:
        if at + 4 > len(data):
            raise GainMapError("is cut short")
        common = _u32(data, at)
        at += 4
    base_headroom = fraction(False, common)
    alternate_headroom = fraction(False, common)
    channels: list[Channel] = []
    for _ in range(count):
        low = fraction(True, common)
        high = fraction(True, common)
        gamma = fraction(False, common)
        base_offset = fraction(True, common)
        alternate_offset = fraction(True, common)
        channels.append(
            Channel(
                float(low), float(high), float(gamma), float(base_offset), float(alternate_offset)
            )
        )
    return _checked(
        Info(
            channels=tuple(channels),
            base_headroom=float(base_headroom),
            alternate_headroom=float(alternate_headroom),
            base_colours=bool(flags & _FLAGS["base_colours"]),
        )
    )


ISO_VERSIONS = b"\x00\x00\x00\x00"  # what a base picture's APP2 says: minimum and writer version 0


def iso_numbers(info: Info) -> bytes:
    """ISO 21496-1's numbers for a gain map, as Mado writes them: version 0, each value a
    fraction of its own (a millionth), never the shared denominator."""
    flags = (_FLAGS["colour"] if info.colour else 0) | (
        _FLAGS["base_colours"] if info.base_colours else 0
    )
    out = bytearray(ISO_VERSIONS)
    out.append(flags)
    for value in (info.base_headroom, info.alternate_headroom):
        out += _fraction(value, signed=False)
    for channel in info.channels:
        out += _fraction(channel.low, signed=True)
        out += _fraction(channel.high, signed=True)
        out += _fraction(channel.gamma, signed=False)
        out += _fraction(channel.base_offset, signed=True)
        out += _fraction(channel.alternate_offset, signed=True)
    return bytes(out)


# Apple's gain map.


def apple_headroom(maker33: float | None, maker48: float | None) -> float | None:
    """The headroom (times brighter) Apple's MakerNote gives, from its tags 33 and 48, as Apple's
    "Applying Apple HDR effect to your photos" works it out; None without them."""
    if maker33 is None or maker48 is None:
        return None
    if maker33 < 1.0:
        stops = -20.0 * maker48 + 1.8 if maker48 <= 0.01 else -0.101 * maker48 + 1.601
    else:
        stops = -70.0 * maker48 + 3.0 if maker48 <= 0.01 else -0.303 * maker48 + 2.303
    return float(2.0 ** max(stops, 0.0))


def apple_makernote(data: bytes) -> tuple[float | None, float | None]:
    """Tags 33 and 48 of Apple's MakerNote (its EXIF's 0x927C), as `apple_headroom` takes them:
    "Apple iOS", its version and byte order, then a directory whose values sit at offsets from
    the MakerNote's start. Nothing for a MakerNote that isn't Apple's."""
    if not data.startswith(b"Apple iOS\x00") or len(data) < 16:
        return None, None
    order: Literal["big", "little"] = "big" if data[12:14] == b"MM" else "little"
    count = int.from_bytes(data[14:16], order)
    found: dict[int, float] = {}
    for index in range(min(count, 256)):
        at = 16 + 12 * index
        if at + 12 > len(data):
            break
        tag = int.from_bytes(data[at : at + 2], order)
        kind = int.from_bytes(data[at + 2 : at + 4], order)
        if tag not in (33, 48) or int.from_bytes(data[at + 4 : at + 8], order) != 1:
            continue
        if kind in (5, 10):  # a fraction, signed or not, at an offset
            offset = int.from_bytes(data[at + 8 : at + 12], order)
            if offset + 8 > len(data):
                continue
            top = int.from_bytes(data[offset : offset + 4], order, signed=kind == 10)
            bottom = int.from_bytes(data[offset + 4 : offset + 8], order, signed=kind == 10)
            if bottom:
                found[tag] = top / bottom
        elif kind == 11:  # a float, in place
            found[tag] = float(
                np.frombuffer(data[at + 8 : at + 12], ">f4" if order == "big" else "<f4")[0]
            )
    return found.get(33), found.get(48)


def apple_info(headroom: float) -> Info:
    """What Apple's gain map says, as Mado keeps it: gains from none to the headroom, on an
    ordinary base, no offsets (Apple's light is the base's times 1 + (headroom - 1) × value)."""
    stops = float(np.log2(max(headroom, 1.0)))
    return Info(
        channels=(Channel(0.0, max(stops, _LEAST_SPREAD), 1.0, 0.0, 0.0),),
        base_headroom=0.0,
        alternate_headroom=stops,
    )


def apple_gains(encoded: Bytes, headroom: float) -> Floats:
    """Apple's gain map values as gains in stops: each value is linear once taken off sRGB's
    curve, and the light it makes is the base's times 1 + (headroom - 1) × value."""
    linear = _SRGB_TO_LINEAR[encoded]
    return np.log2(1.0 + (max(headroom, 1.0) - 1.0) * linear).astype(np.float32)


# The values, as gains in stops.


def gains_of(encoded: Bytes, info: Info) -> Floats:
    """A gain map's values (height × width, or × 3) as gains in stops, by what it says: one
    channel's numbers for a grey gain map, each colour's for a colour one."""
    values = encoded.astype(np.float32) / 255.0
    if values.ndim == 3 and values.shape[2] == 1:
        values = values[..., 0]
    colour = info.colour or values.ndim == 3
    if not colour:
        return _gains(values, info.channels[0])
    planes = values if values.ndim == 3 else np.repeat(values[..., None], 3, axis=2)
    out = np.empty((*planes.shape[:2], 3), np.float32)
    for c in range(3):
        out[..., c] = _gains(planes[..., c], info.channels[c if info.colour else 0])
    return out


def encoded_of(gains: Floats, info: Info) -> tuple[Bytes, Info]:
    """Gains in stops as a gain map's values and what it says: each channel's least and most made
    afresh from what's there (a little apart at the least), the curve straight, the headroom and
    offsets as `info` had them (its first channel's for every one when `gains` has fewer)."""
    planes = gains[..., None] if gains.ndim == 2 else gains
    channels: list[Channel] = []
    out = np.empty(planes.shape, np.uint8)
    for c in range(planes.shape[2]):
        plane = planes[..., c]
        low, high = _quantised(float(plane.min())), _quantised(float(plane.max()))
        if high - low < _LEAST_SPREAD:
            high = _quantised(low + _LEAST_SPREAD)
        model = info.channels[c] if c < len(info.channels) else info.channels[0]
        channels.append(Channel(low, high, 1.0, model.base_offset, model.alternate_offset))
        scaled = (plane - low) / (high - low)
        out[..., c] = np.clip(scaled * 255.0 + 0.5, 0, 255).astype(np.uint8)
    made = replace(info, channels=tuple(channels))
    return (out[..., 0] if out.shape[2] == 1 else out), made


def weight(info: Info, headroom: float) -> float:
    """How much of the gain a screen with `headroom` stops past ordinary white shows: none at
    the base's own headroom, all at the other rendition's, in between by stops."""
    span = info.alternate_headroom - info.base_headroom
    if abs(span) < 1e-6:
        return 0.0
    return float(np.clip((headroom - info.base_headroom) / span, 0.0, 1.0))


def alternate(base: Floats, gains: Floats, info: Info, amount: float = 1.0) -> Floats:
    """The other rendition (linear light, height × width × 3) from the base's linear light and
    the gains at its size, `amount` of the way (a screen's weight): ISO 21496-1's sum, the gains
    divided by for an HDR base."""
    stops = gains[..., None] if gains.ndim == 2 else gains
    base_offsets = np.array(_per_colour(info, "base_offset"), np.float32)
    alternate_offsets = np.array(_per_colour(info, "alternate_offset"), np.float32)
    lit = (base + base_offsets) * np.exp2(stops * amount * _way(info)) - alternate_offsets
    return lit.astype(np.float32)


def stops_between(base: Floats, other: Floats, info: Info, colour: bool) -> Floats:
    """The gains that make `other` (linear light) from `base`, as `alternate` takes them: per
    colour for a colour gain map, else by their light (each colour's share of it)."""
    base_offsets = np.array(_per_colour(info, "base_offset"), np.float32)
    alternate_offsets = np.array(_per_colour(info, "alternate_offset"), np.float32)
    if colour:
        ratio = (other + alternate_offsets) / np.maximum(base + base_offsets, 1e-6)
        return (np.log2(np.maximum(ratio, 1e-6)) * _way(info)).astype(np.float32)
    luma = np.array(LUMA, np.float32)
    lit = (other + alternate_offsets) @ luma
    seen = (base + base_offsets) @ luma
    found = np.log2(np.maximum(lit, 1e-6) / np.maximum(seen, 1e-6)) * _way(info)
    return found.astype(np.float32)


def _way(info: Info) -> float:
    """Which way the gains go from the base: brighter from an ordinary one, dimmer (divided by)
    from an HDR one."""
    return -1.0 if info.base_is_hdr else 1.0


# What the tools do to the gains.


def single(gains: Floats) -> Floats:
    """A colour gain map as one channel, each colour's gain by its share of light, so the HDR
    rendition keeps the ordinary one's colours (a look's, say); a grey one as it is."""
    if gains.ndim == 2:
        return gains
    return (gains @ np.array(LUMA, np.float32)).astype(np.float32)


def scaled(gains: Floats, by: float | Floats) -> Floats:
    """Gains toward none (`by` 0) or as they are (1), everywhere or place by place (height ×
    width)."""
    factor = np.asarray(by, np.float32)
    if gains.ndim == 3 and factor.ndim == 2:
        factor = factor[..., None]
    return (gains * factor).astype(np.float32)


def filled(gains: Floats, hole: Floats) -> Floats:
    """Gains filled smoothly where `hole` (height × width, 0 to 1) says, from what's round it:
    each level of a pyramid fills its gaps from the coarser one (pull-push), so a gap of any size
    takes the light round it, and a part half in the hole half keeps its own."""
    keep = np.clip(1.0 - hole, 0.0, 1.0).astype(np.float32)
    planes = gains[..., None] if gains.ndim == 2 else gains
    out = np.empty_like(planes)
    for c in range(planes.shape[2]):
        out[..., c] = _pull_push(planes[..., c], keep)
    return out[..., 0] if gains.ndim == 2 else out


def _pull_push(values: Floats, keep: Floats) -> Floats:
    if values.size <= 1 or min(values.shape) <= 1:
        total = float(keep.sum())
        mean = float((values * keep).sum() / total) if total > 1e-6 else float(values.mean())
        return (keep * values + (1.0 - keep) * mean).astype(np.float32)
    height, width = values.shape
    rows, columns = -(-height // 2), -(-width // 2)
    pad = ((0, rows * 2 - height), (0, columns * 2 - width))
    weighted = np.pad(values * keep, pad, mode="edge").reshape(rows, 2, columns, 2).sum(axis=(1, 3))
    weights = np.pad(keep, pad, mode="edge").reshape(rows, 2, columns, 2).sum(axis=(1, 3))
    coarse_values = np.where(weights > 1e-6, weighted / np.maximum(weights, 1e-6), 0.0).astype(
        np.float32
    )
    coarse_keep = np.clip(weights, 0.0, 1.0).astype(np.float32)
    coarse = _pull_push(coarse_values, coarse_keep)
    up = np.repeat(np.repeat(coarse, 2, axis=0), 2, axis=1)[:height, :width]
    return (keep * values + (1.0 - keep) * up).astype(np.float32)


def size_for(made: tuple[int, int], fraction: tuple[float, float], most: int) -> tuple[int, int]:
    """The size a gain map is kept at beside a picture `made` big: the same share of it as the
    photo's had (`fraction`, its width and height of the picture's), no more than `most` pixels
    on its longer side, and a pixel at least."""
    width = made[0] * fraction[0]
    height = made[1] * fraction[1]
    scale = min(1.0, most / max(width, height, 1.0))
    return max(1, round(width * scale)), max(1, round(height * scale))


def turned(gains: Floats, orientation: int) -> Floats:
    """Gains laid out as a picture stored with EXIF's `orientation` is shown: the gain map is
    stored as its picture is, and turned with it."""
    match orientation:
        case 2:
            out = gains[:, ::-1]
        case 3:
            out = gains[::-1, ::-1]
        case 4:
            out = gains[::-1, :]
        case 5:
            out = np.swapaxes(gains, 0, 1)
        case 6:
            out = np.rot90(gains, -1)
        case 7:
            out = np.rot90(np.swapaxes(gains, 0, 1), 2)
        case 8:
            out = np.rot90(gains, 1)
        case _:
            out = gains
    return np.ascontiguousarray(out, np.float32)


# The pieces.

_XMP_HEAD = (
    '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Mado">\n'
    '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n    '
)
_XMP_FOOT = "\n  </rdf:RDF>\n</x:xmpmeta>"
_SRGB_TO_LINEAR = np.where(
    np.arange(256) / 255.0 <= 0.04045,
    np.arange(256) / 255.0 / 12.92,
    ((np.arange(256) / 255.0 + 0.055) / 1.055) ** 2.4,
).astype(np.float32)


def _packet(description: str) -> bytes:
    return (_XMP_HEAD + description + _XMP_FOOT).encode("utf-8")


def _text(packet: bytes) -> str:
    return packet.decode("utf-8", "replace")


def _prefix(text: str, namespace: str) -> str | None:
    found = re.search(r'xmlns:(\w+)\s*=\s*["\']' + re.escape(namespace) + r'["\']', text)
    return found.group(1) if found else None


def _values(text: str, prefix: str, name: str) -> list[str]:
    """A field's value or values: an attribute, an element, or an element's list (rdf:Seq)."""
    tag = re.escape(f"{prefix}:{name}")
    attribute = re.search(rf"\b{tag}\s*=\s*\"([^\"]*)\"|\b{tag}\s*=\s*'([^']*)'", text)
    if attribute:
        return [attribute.group(1) if attribute.group(1) is not None else attribute.group(2)]
    element = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}\s*>", text, re.DOTALL)
    if element is None:
        return []
    inner = element.group(1)
    listed = re.findall(r"<\w+:li\b[^>]*>([^<]*)</\w+:li\s*>", inner)
    return listed or [inner.strip()]


def _numbers(text: str, prefix: str, name: str) -> list[float]:
    found: list[float] = []
    for each in _values(text, prefix, name):
        try:
            value = float(each.strip())
        except ValueError:
            raise GainMapError(f"says {name} is “{each.strip()[:20]}”, not a number") from None
        if not np.isfinite(value):
            raise GainMapError(f"says {name} is no number at all")
        found.append(value)
    return found


def _at(values: Sequence[float], channel: int) -> float:
    return values[channel] if len(values) > 1 else values[0]


def _said(value: str | float) -> str:
    if isinstance(value, str):
        return value
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _checked(info: Info) -> Info:
    for channel in info.channels:
        if channel.high < channel.low:
            raise GainMapError("says its most gain is less than its least")
        if channel.gamma <= 0:
            raise GainMapError("has a curve that isn't one")
        values = (channel.low, channel.high, channel.base_offset, channel.alternate_offset)
        if not all(np.isfinite(each) and abs(each) < 64 for each in values):
            raise GainMapError("gives numbers far beyond any photo's")
    if not all(abs(each) < 64 for each in (info.base_headroom, info.alternate_headroom)):
        raise GainMapError("gives a headroom far beyond any screen's")
    return info


def _gains(values: Floats, channel: Channel) -> Floats:
    curved = values if channel.gamma == 1.0 else np.power(values, 1.0 / channel.gamma)
    return (channel.low + (channel.high - channel.low) * curved).astype(np.float32)


def _per_colour(info: Info, field: str) -> list[float]:
    values = [float(getattr(channel, field)) for channel in info.channels]
    return values * 3 if len(values) == 1 else values


def _quantised(value: float) -> float:
    return round(value * _DENOMINATOR) / _DENOMINATOR


def _fraction(value: float, *, signed: bool) -> bytes:
    top = round(value * _DENOMINATOR)
    if signed:
        top = int(np.clip(top, -_INT32, _INT32 - 1))
        return top.to_bytes(4, "big", signed=True) + _DENOMINATOR.to_bytes(4, "big")
    top = int(np.clip(top, 0, 2 * _INT32 - 1))
    return top.to_bytes(4, "big") + _DENOMINATOR.to_bytes(4, "big")


def _u16(data: bytes, at: int) -> int:
    return int.from_bytes(data[at : at + 2], "big")


def _u32(data: bytes, at: int) -> int:
    return int.from_bytes(data[at : at + 4], "big")


def _s32(data: bytes, at: int) -> int:
    return int.from_bytes(data[at : at + 4], "big", signed=True)
