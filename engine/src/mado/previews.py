"""The smaller copies of each picture the window shows, kept in the data folder's cache: a
thumbnail about 512 pixels for the grid, a view the size of a screen for a picture's page, and a
copy at full size for a format the window can't show itself (TIFF, HEIC).

Each is made the first time it's asked for (a scan makes the thumbnails as it reads) and named
after its picture's version, so a picture that changes gets new ones. They're WebP, with the
picture's own colour profile, so wide colours stay wide. Anything in the cache can go: it's
made again.
"""

import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from mado.config import DataPaths
from mado.core.files import Kind, kind_of
from mado.pictures import Command, PictureGoneError, UnreadableError, decode

THUMBNAIL = 512  # pixels on its longer side
VIEW = 2560
FULL_KEPT = 8  # full-size copies kept: each is as big as its picture, and only one is looked at
_LOCKS = 64  # copies being made at once, each with a lock of its own among these
# Formats the window shows as they are, at full size.
SHOWN_AS_IS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WebP": "image/webp",
    "AVIF": "image/avif",
    "GIF": "image/gif",
    "BMP": "image/bmp",
}


@dataclass(frozen=True)
class Source:
    """A picture, as much as making its copies needs."""

    id: int
    path: Path
    kind: Kind
    format: str | None
    version: str  # changes when its file does
    problem: str | None = None  # why it won't open

    @classmethod
    def of(cls, row: sqlite3.Row) -> Source:
        """From a row of the pictures table."""
        return cls(
            id=row["id"],
            path=Path(row["path"]),
            kind=kind_of(row["name"]) or "picture",
            format=row["format"],
            version=version(row["modified"], row["size"]),
            problem=row["problem"],
        )


def version(modified: int, size: int) -> str:
    """What names a picture's copies: it changes when its file does."""
    return f"{modified:x}-{size:x}"


class Previews:
    def __init__(self, paths: DataPaths, ffmpeg: Callable[[], Command | None]) -> None:
        self._root = paths.cache / "pictures"
        self._full = paths.cache / "full"
        self._ffmpeg = ffmpeg
        # A copy asked for twice at once (a look's small copies, all at once) is made once: each
        # copy's own lock among a few, so copies of other pictures don't wait for it.
        self._making = [threading.Lock() for _ in range(_LOCKS)]

    def _lock_for(self, target: Path) -> threading.Lock:
        return self._making[hash(str(target).casefold()) % _LOCKS]

    def thumbnail(self, picture: Source) -> Path:
        """Its thumbnail, made now if it hasn't been."""
        return self._copy(picture, "thumbnail", THUMBNAIL, quality=80)

    def view(self, picture: Source) -> Path:
        """Its view the size of a screen, made now if it hasn't been."""
        return self._copy(picture, "view", VIEW, quality=88)

    def full(self, picture: Source) -> tuple[Path, str]:
        """The picture at full size, and what kind of file that is: the picture itself when the
        window can show its format, else a copy it can (PNG), made now if it hasn't been."""
        self._readable(picture)
        shown = SHOWN_AS_IS.get(picture.format or "")
        if picture.kind == "picture" and shown is not None:
            if not picture.path.is_file():
                raise PictureGoneError(picture.path)
            return picture.path, shown
        target = self._full / f"{picture.id}-{picture.version}.png"
        if target.is_file():
            return target, "image/png"
        with self._lock_for(target):
            if not target.is_file():
                image = decode(picture.path, picture.kind, longest=None, ffmpeg=self._ffmpeg())
                save_copy(image, target, "PNG", compress_level=1)
                self._prune()
        return target, "image/png"

    def forget(self, ids: Iterable[int]) -> None:
        """Takes away the copies of these pictures (forgotten, or changed since): each of their
        cache's folders listed once, however many pictures a folder taken out held."""
        wanted = {str(picture_id) for picture_id in ids}
        folders = {self._root / _shelf(int(picture_id)) for picture_id in wanted}
        for folder in [*folders, self._full] if wanted else []:
            try:
                names = [each.name for each in folder.iterdir()]
            except OSError:
                continue  # no copies there
            for name in names:
                if name.split("-", 1)[0] in wanted:
                    _remove(folder / name)

    def _copy(self, picture: Source, purpose: str, longest: int, *, quality: int) -> Path:
        self._readable(picture)
        target = self._root / _shelf(picture.id) / f"{picture.id}-{picture.version}-{purpose}.webp"
        if target.is_file():
            return target
        with self._lock_for(target):
            if not target.is_file():  # made meanwhile, by the ask that held the lock
                image = decode(picture.path, picture.kind, longest=longest, ffmpeg=self._ffmpeg())
                save_copy(image, target, "WEBP", quality=quality, method=4)
        return target

    @staticmethod
    def _readable(picture: Source) -> None:
        if picture.problem:
            raise UnreadableError(picture.problem)
        if picture.kind == "raw":
            raise UnreadableError("Mado can't read camera RAW yet: it lists them as they are.")

    def _prune(self) -> None:
        """Keeps the newest few full-size copies."""
        copies = sorted(self._full.glob("*.png"), key=_made, reverse=True)
        for old in copies[FULL_KEPT:]:
            _remove(old)


def _shelf(picture_id: int) -> str:
    """The cache's folder for a picture's copies: a thousand pictures to a folder."""
    return str(picture_id // 1000)


def _made(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def save_copy(image: Image.Image, target: Path, format_: str, **options: object) -> None:
    """Saves a copy whole or not at all: written beside, then put in place in one step, so a
    copy another thread asks for at the same time is never half there. When Windows won't put it
    in place because the window is reading the copy already there (made at the same moment for
    the same version), that one stays."""
    target.parent.mkdir(parents=True, exist_ok=True)
    profile = image.info.get("icc_profile")
    if isinstance(profile, bytes):
        options["icc_profile"] = profile
    writing = target.with_name(f"{target.name}.{secrets.token_hex(4)}.part")
    try:
        image.save(writing, format=format_, **options)
        try:
            writing.replace(target)
        except PermissionError:
            if not target.is_file():
                raise
    finally:
        writing.unlink(missing_ok=True)


def _remove(path: Path) -> None:
    """Takes a copy away, unless the window is reading it: a copy left behind is harmless, as
    its name says which version of its picture it is."""
    with suppress(OSError):
        path.unlink(missing_ok=True)
