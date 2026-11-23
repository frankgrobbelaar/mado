"""What a file is by its name: a picture Pillow reads, a HEIF (a phone's HEIC, read with ffmpeg's
help), a camera RAW (read by LibRaw, which Mado downloads the first time it reads one), or
something else; and the folders a scan never looks into."""

from pathlib import PureWindowsPath
from typing import Literal

type Kind = Literal["picture", "heif", "raw"]

# What Pillow reads by itself.
PICTURES = frozenset(
    {
        ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".avif", ".tif", ".tiff", ".bmp",
        ".dib", ".gif",
    }
)  # fmt: skip
HEIF = frozenset({".heic", ".heif", ".hif"})
# Cameras' own formats, read by LibRaw (mado/libraw.py).
RAW = frozenset(
    {
        ".3fr", ".arw", ".cr2", ".cr3", ".crw", ".dng", ".erf", ".iiq", ".kdc", ".mos", ".mrw",
        ".nef", ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2", ".rwl", ".sr2", ".srf", ".srw",
        ".x3f",
    }
)  # fmt: skip

# Mado's own quarantine, the folders Windows keeps on every drive, and a network drive's own
# thumbnails.
_SKIPPED = frozenset(
    name.casefold()
    for name in (
        "Mado quarantine",
        "$RECYCLE.BIN",
        "RECYCLER",
        "System Volume Information",
        "@eaDir",
    )
)


def kind_of(name: str) -> Kind | None:
    """A picture by its extension, in any case; None for anything else. Hidden files aren't
    pictures, such as the "._IMG_2041.JPG" a Mac leaves beside each picture on a shared drive."""
    if name.startswith("."):
        return None
    extension = PureWindowsPath(name).suffix.casefold()
    if extension in PICTURES:
        return "picture"
    if extension in HEIF:
        return "heif"
    if extension in RAW:
        return "raw"
    return None


def skipped_folder(name: str) -> bool:
    """Folders a scan never looks into: Mado's quarantine, Windows' own, a network drive's
    thumbnails, and hidden ones."""
    folded = name.casefold()
    return folded in _SKIPPED or folded.startswith(".")
