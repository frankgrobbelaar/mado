"""What a file is by its name: a picture Mado reads, a HEIF (a phone's HEIC, read with ffmpeg's
help), a camera RAW it lists but can't read yet, or something else; and the folders a scan never
looks into."""

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
# Cameras' own formats: listed now, readable once Mado has a RAW reader.
RAW = frozenset(
    {
        ".3fr", ".arw", ".cr2", ".cr3", ".crw", ".dng", ".erf", ".iiq", ".kdc", ".mos", ".mrw",
        ".nef", ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2", ".rwl", ".sr2", ".srf", ".srw",
        ".x3f",
    }
)  # fmt: skip

# The folders Windows keeps on every drive, and a network drive's own thumbnails.
_SKIPPED = frozenset(
    name.casefold() for name in ("$RECYCLE.BIN", "RECYCLER", "System Volume Information", "@eaDir")
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
    """Folders a scan never looks into: Windows' own, a network drive's thumbnails, and hidden
    ones."""
    folded = name.casefold()
    return folded in _SKIPPED or folded.startswith(".")
