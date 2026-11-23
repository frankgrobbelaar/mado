"""The library's folders: how they may sit together, where a picture sits inside one, and how
long a scan has left. mado/library.py does the looking."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PureWindowsPath

from mado.core.files import skipped_folder

_MIN_FOR_PACE = 5  # pictures read before a pace is worth going by


@dataclass(frozen=True)
class Covered:
    """The new folder is already in the library, or inside a folder that is."""

    by: PureWindowsPath


@dataclass(frozen=True)
class Holds:
    """The new folder holds folders already in the library, which it takes in."""

    folders: tuple[PureWindowsPath, ...]


def fits(new: PureWindowsPath, existing: Iterable[PureWindowsPath]) -> Covered | Holds | None:
    """How a new library folder sits beside the ones already there. None: on its own."""
    folders = list(existing)
    for folder in folders:
        if new == folder or new.is_relative_to(folder):
            return Covered(folder)
    held = tuple(folder for folder in folders if folder.is_relative_to(new))
    return Holds(held) if held else None


def holding(picture: PureWindowsPath, folders: Iterable[PureWindowsPath]) -> PureWindowsPath | None:
    """The library folder a picture is in, as a scan would find it there: None outside every
    one, or in a folder inside one that a scan never looks into (a quarantine, a hidden one)."""
    for folder in folders:
        if picture.parent == folder or picture.parent.is_relative_to(folder):
            inside = picture.parent.relative_to(folder).parts
            return None if any(skipped_folder(part) for part in inside) else folder
    return None


def inner_folder(root: PureWindowsPath, picture: PureWindowsPath) -> str:
    """The folders between a library folder and a picture in it, as "2026/Holiday"; "" for one
    at the top."""
    return "/".join(picture.parent.relative_to(root).parts)


def time_left(done: int, total: int, elapsed: float) -> float | None:
    """Seconds left at the pace so far, or None until there's enough of a pace to go by."""
    if done >= total:
        return 0.0
    if done < _MIN_FOR_PACE:
        return None
    return (total - done) * elapsed / done
