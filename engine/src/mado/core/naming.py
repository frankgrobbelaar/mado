"""Names: a new picture's, after its original and what it was made for ("Harbour at dusk (TV
8K).jpg", "(2)" when that's taken), and where a picture set aside waits in quarantine. Pure.

The quarantine is a folder at the top of each drive, "Mado quarantine", a folder a day inside
it, so setting a picture aside is a rename on its own drive, never a copy. Only a file in one
day's folder there is ever the clear-out's to delete, whatever a record says.
"""

from collections.abc import Callable
from datetime import date
from pathlib import PurePath, PureWindowsPath

QUARANTINE = "Mado quarantine"
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WebP": ".webp", "AVIF": ".avif"}
_UNSAFE = str.maketrans(dict.fromkeys('<>:"/\\|?*', "-"))


def new_name(stem: str, label: str, extension: str, taken: Callable[[str], bool]) -> str:
    """A new picture's file name: its original's, with what it was made for ("Harbour at dusk
    (TV 8K).jpg"), and "(2)", "(3)"… when that's taken (`taken` says whether a name is, in any
    case). With nothing to say of what made it (a paste saved as it is), its original's own."""
    base = f"{stem} ({label.translate(_UNSAFE)})" if label else stem
    name = f"{base}{extension}"
    number = 2
    while taken(name):
        name = f"{base} ({number}){extension}"
        number += 1
    return name


def replacement_name(original: str, extension: str) -> str:
    """The name a replaced picture takes: its original's, with the extension of the format it's
    saved in now ("Harbour at dusk.heic" saved as JPEG is "Harbour at dusk.jpg")."""
    path = PureWindowsPath(original)
    if path.suffix.casefold() in _SAME.get(extension, (extension,)):
        return original
    return f"{path.stem}{extension}"


_SAME = {".jpg": (".jpg", ".jpeg", ".jpe", ".jfif"), ".avif": (".avif",), ".png": (".png",),
         ".webp": (".webp",)}  # fmt: skip


def quarantine_root[P: PurePath](source: P) -> P:
    r"""The quarantine on a picture's own drive: D:\Mado quarantine."""
    return type(source)(source.anchor) / QUARANTINE


def aside_name(name: str, taken: Callable[[str], bool]) -> str:
    """A name in a day's quarantine folder: the picture's own, or with "(2)" when another of
    that name was set aside the same day."""
    path = PureWindowsPath(name)
    found = name
    number = 2
    while taken(found):
        found = f"{path.stem} ({number}){path.suffix}"
        number += 1
    return found


def in_quarantine(path: PurePath, root: PurePath) -> bool:
    """Whether a path is a picture set aside, in one day's folder of the quarantine `root` (its
    drive's): only such a file is the clear-out's to delete."""
    day, folder = path.parent, path.parent.parent
    if path.name in ("", ".", ".."):
        return False
    try:
        date.fromisoformat(day.name)
    except ValueError:
        return False
    return str(folder).casefold() == str(root).casefold()
