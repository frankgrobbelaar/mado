"""How a picture made for a size is saved: the format and quality that suit what it's for and
what it is, about how big that comes out, and the words for its colours. Pure.

The format stays as it was when Mado writes it (JPEG, PNG, WebP, AVIF). Otherwise photos are
JPEG, which every screen and print shop takes, a little lighter for a phone and at 95 for a TV or
a print; drawings, pixel art and screenshots are PNG, which keeps flat colour and sharp edges
exactly; and a picture with see-through parts is never JPEG, which can't keep them. The owner
can choose another at Save.
"""

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from mado.core.kind import Kind
from mado.core.sizes import Purpose

type Format = Literal["JPEG", "PNG", "WebP", "AVIF"]

FORMATS: tuple[Format, ...] = ("JPEG", "PNG", "WebP", "AVIF")
WRITES = frozenset(FORMATS)  # what Mado saves in: an original in another keeps its name only
# What keeps an HDR photo's gain map: JPEG as Ultra HDR, AVIF with ISO 21496-1's tmap item.
# PNG and WebP have no room for one.
HDR_FORMATS: frozenset[Format] = frozenset(("JPEG", "AVIF"))

# Bytes a pixel takes, about: photos at JPEG's qualities (between them, in proportion), and
# PNG for each kind of picture.
_JPEG = ((80, 0.22), (90, 0.35), (92, 0.42), (95, 0.55), (100, 1.2))
_WEBP = ((75, 0.12), (85, 0.18), (90, 0.24), (95, 0.36), (100, 0.9))
_AVIF = ((60, 0.07), (75, 0.11), (85, 0.17), (95, 0.3), (100, 0.6))
_PNG: dict[Kind, float] = {"photo": 1.8, "drawing": 0.45, "pixels": 0.05, "screenshot": 0.3}
_LOSSY_DRAWING = 0.5  # a drawing's flat colour takes half a photo's bytes in a lossy format
_FITS: dict[Purpose, str] = {
    "phone": "What every phone shows.",
    "tablet": "What every tablet shows.",
    "laptop": "What every laptop shows.",
    "monitor": "What every screen shows.",
    "ultrawide": "What every screen shows.",
    "tv": "What every TV shows.",
    "print": "What print shops take, at 300 dpi.",
    "screen": "What every screen shows.",
}
_PHRASES: dict[Purpose, str] = {
    "phone": "A phone",
    "tablet": "A tablet",
    "laptop": "A laptop",
    "monitor": "A 4K monitor",
    "ultrawide": "An ultrawide",
    "tv": "A TV",
    "print": "A print",
    "screen": "Your screen",
}


@dataclass(frozen=True)
class Suited:
    format: Format
    quality: int | None  # JPEG, WebP and AVIF's quality; None for PNG
    fits: str  # "What every TV shows."


def suited(purpose: Purpose, kind: Kind, original: str | None, *, alpha: bool = False) -> Suited:
    """The format and quality that suit a picture of `kind` made for `purpose`: its `original`
    format ("PNG", "HEIC"…) when Mado writes it, else what suits it. `alpha`: it has see-through
    parts."""
    kept: Format | None = next((each for each in FORMATS if each == original), None)
    if kept == "JPEG" and alpha:
        kept = None
    match kept:
        case "JPEG":
            return Suited("JPEG", _jpeg_quality(purpose), _FITS[purpose])
        case "WebP":
            return Suited("WebP", 90, _WEBP_FITS)
        case "AVIF":
            return Suited("AVIF", 80, _AVIF_FITS)
        case "PNG":
            return Suited("PNG", None, _png_fits(kind, alpha))
        case None:
            pass
    if kind != "photo" or alpha:
        return Suited("PNG", None, _png_fits(kind, alpha))
    return Suited("JPEG", _jpeg_quality(purpose), _FITS[purpose])


_WEBP_FITS = "Smaller than JPEG; most apps show it, though some TVs and print shops don't."
_AVIF_FITS = "The smallest; newer apps show it, though many TVs and print shops don't."


def _png_fits(kind: Kind, alpha: bool) -> str:
    if alpha:
        return "Kept exactly, its see-through parts too."
    if kind == "photo":
        return "Kept exactly, every pixel as it was made."
    return "Kept exactly: flat colour and sharp edges stay as they are."


def _jpeg_quality(purpose: Purpose) -> int:
    return {"phone": 90, "tablet": 92, "laptop": 92, "tv": 95, "print": 95}.get(purpose, 92)


def phrase(purpose: Purpose, name: str) -> str:
    """What a picture is made for, as a sentence starts with it: "A TV", "An A4 print"."""
    if purpose == "print" and not name[0].isdigit():
        return f"An {name} print" if name[0] in "AEIOU" else f"A {name} print"
    if purpose == "print":
        return f"A {name} print"
    return _PHRASES[purpose]


def about_bytes(format_: Format, quality: int | None, kind: Kind, pixels: int) -> int:
    """About how big a picture of `pixels` comes out."""
    if format_ == "PNG":
        return round(pixels * _PNG[kind])
    curve = {"JPEG": _JPEG, "WebP": _WEBP, "AVIF": _AVIF}[format_]
    per_pixel = _along(curve, quality if quality is not None else 90)
    if kind != "photo":
        per_pixel *= _LOSSY_DRAWING
    return round(pixels * per_pixel)


def colour_words(profile: str | None, keep: bool) -> str:
    """The colours a picture is saved in: its own profile's, when it has one and it's kept
    ("Display P3"), else sRGB, which every screen takes."""
    if keep and profile and "srgb" not in profile.casefold():
        return profile
    return "sRGB"


def _along(curve: tuple[tuple[int, float], ...], quality: int) -> float:
    """A curve's value at `quality`, in proportion between its points."""
    if quality <= curve[0][0]:
        return curve[0][1]
    for (low, low_value), (high, high_value) in pairwise(curve):
        if quality <= high:
            return low_value + (high_value - low_value) * (quality - low) / (high - low)
    return curve[-1][1]
