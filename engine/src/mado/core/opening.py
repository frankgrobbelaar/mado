"""Pictures from anywhere: what paths open as (one picture its page; several, or a folder, Many
at once), the words for what can't be opened, and a pasted picture's name. Pure."""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Literal

# The formats Mado reads, as a sentence says them.
READS = "JPEG, PNG, HEIC, WebP, AVIF, TIFF, BMP and GIF"

type Found = Literal["folder", "picture", "other", "missing"]
type Opens = Literal["page", "many", "nothing"]


@dataclass(frozen=True)
class Entry:
    """A path as it was found: a folder, a picture by its name, another file, or not there."""

    path: str
    found: Found


def what_opens(entries: Sequence[Entry]) -> Opens:
    """One picture opens its page; several, or a folder, open Many at once; none, nothing."""
    if any(entry.found == "folder" for entry in entries):
        return "many"
    pictures = sum(entry.found == "picture" for entry in entries)
    if pictures == 1:
        return "page"
    return "many" if pictures else "nothing"


def not_a_picture(name: str) -> str:
    """Why a file that isn't a picture Mado reads didn't open."""
    return f"{name} isn't a picture Mado reads. It reads {READS}, and lists camera RAW."


def not_there(path: str, drive_there: bool) -> str:
    """Why a path that isn't there didn't open: its drive isn't connected, or it went."""
    name = PureWindowsPath(path).name or path
    drive = PureWindowsPath(path).drive
    if not drive_there and drive:
        return f"{name} is on {drive}, which isn't connected. Connect it, then open it again."
    return f"{name} isn't there any more: it was moved or deleted."


def nothing_to_open(
    left: Sequence[tuple[str, str]],
    entries: Sequence[Entry] = (),
    *,
    unplugged_drives: Collection[str] = (),
) -> str:
    """What's said when nothing of what was given opens: why, for one; for several not there,
    the drive they're on that isn't connected, or that they went; else the formats."""
    if len(left) == 1:
        return left[0][1]
    if entries and all(entry.found == "missing" for entry in entries):
        drives = {PureWindowsPath(entry.path).drive.upper() for entry in entries}
        unplugged = {drive.upper() for drive in unplugged_drives}
        if len(drives) == 1 and drives <= unplugged:
            drive = next(iter(drives))
            return f"Those are on {drive}, which isn't connected. Connect it, then open them again."
        return "None of those are there any more: they were moved or deleted."
    return f"None of those are pictures Mado reads: {READS}."


def long_form(path: str) -> str:
    r"""A path in Windows' long form, which reaches paths longer than 260 letters on a PC where
    long paths aren't turned on: D:\x as \\?\D:\x, and \\server\share\x as \\?\UNC\server\share\x.
    A path in that form already stays as it is."""
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def pasted_name(now: datetime, taken: Callable[[str], bool]) -> str:
    """A pasted picture's file name, by when it was pasted: "Pasted 2026-11-23 14.05.png", with
    "(2)" when another was pasted in the same minute."""
    base = f"Pasted {now:%Y-%m-%d %H.%M}"
    name = f"{base}.png"
    number = 2
    while taken(name):
        name = f"{base} ({number}).png"
        number += 1
    return name
