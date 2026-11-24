"""The smaller copies of each picture the window shows, kept in the data folder's cache: a
thumbnail about 512 pixels for the grid, a view the size of a screen for a picture's page, and a
copy at full size for a format the window can't show itself (TIFF, HEIC, camera RAW).

Each is made the first time it's asked for (a scan makes the thumbnails as it reads) and named
after its picture's version, so a picture that changes gets new ones. They're WebP, with the
picture's own colour profile, so wide colours stay wide. Anything in the cache can go: it's
made again. A camera RAW's thumbnail comes from the preview its camera kept inside it; its view
and full size are developed, so its page shows the picture Save makes (mado/core/raw.py).
"""

import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from mado import hdr
from mado.config import DataPaths
from mado.core.files import Kind, kind_of
from mado.core.gains import shown_with
from mado.encode import with_gain_map
from mado.libraw import Reader
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
    hdr: bool = False  # an HDR photo whose gain map Mado reads: its view keeps it
    size: tuple[int, int] | None = None  # as it's shown

    @classmethod
    def of(cls, row: sqlite3.Row) -> Source:
        """From a row of the pictures table."""
        width, height = row["width"], row["height"]
        return cls(
            id=row["id"],
            path=Path(row["path"]),
            kind=kind_of(row["name"]) or "picture",
            format=row["format"],
            version=version(row["modified"], row["size"]),
            problem=row["problem"],
            hdr=row["hdr"] == 1,
            size=(width, height) if width and height else None,
        )


def version(modified: int, size: int) -> str:
    """What names a picture's copies: it changes when its file does."""
    return f"{modified:x}-{size:x}"


class Previews:
    def __init__(
        self,
        paths: DataPaths,
        ffmpeg: Callable[[], Command | None],
        reader: Reader | None = None,
    ) -> None:
        self._root = paths.cache / "pictures"
        self._full = paths.cache / "full"
        self._scratch = paths.cache / "hdr"  # a HEIC's gain map on its way to ffmpeg
        self._ffmpeg = ffmpeg
        self.reader = reader  # camera RAW's, once it's there
        # Pictures (by number and version) whose gain map didn't read: shown as they are from
        # then on, not tried again on every copy asked for.
        self._unread: set[tuple[int, str]] = set()
        # A copy asked for twice at once (a look's small copies, all at once) is made once: each
        # copy's own lock among a few, so copies of other pictures don't wait for it.
        self._making = [threading.Lock() for _ in range(_LOCKS)]

    def _lock_for(self, target: Path) -> threading.Lock:
        return self._making[hash(str(target).casefold()) % _LOCKS]

    def tidy(self) -> None:
        """As the engine starts: a HEIC's gain map a stop left on its way to ffmpeg goes."""
        for left in self._scratch.glob("gain-map-*.heic") if self._scratch.is_dir() else ():
            left.unlink(missing_ok=True)

    def thumbnail(self, picture: Source) -> Path:
        """Its thumbnail, made now if it hasn't been."""
        return self._copy(picture, "thumbnail", THUMBNAIL, quality=80)

    def kept_thumbnail(self, picture: Source) -> Path | None:
        """Its thumbnail when the cache holds it; None, rather than making one."""
        target = self._root / _shelf(picture.id) / f"{picture.id}-{picture.version}-thumbnail.webp"
        return target if target.is_file() else None

    def view(self, picture: Source) -> Path:
        """Its view the size of a screen, made now if it hasn't been: an HDR photo's as an Ultra
        HDR JPEG, its gain map with it, so an HDR screen shows it in HDR (an ordinary screen
        shows its picture, as it shows any other's)."""
        if picture.hdr:
            made = self._hdr_copy(picture, "view", VIEW, quality=88)
            if made is not None:
                return made
        return self._copy(picture, "view", VIEW, quality=88)

    def full(self, picture: Source) -> tuple[Path, str]:
        """The picture at full size, and what kind of file that is: the picture itself when the
        window can show its format, else a copy it can (PNG; an HDR HEIC's an Ultra HDR JPEG),
        made now if it hasn't been."""
        self._readable(picture)
        shown = SHOWN_AS_IS.get(picture.format or "")
        if picture.kind == "picture" and shown is not None:
            if not picture.path.is_file():
                raise PictureGoneError(picture.path)
            return picture.path, shown
        if picture.hdr and picture.kind == "heif":
            made = self._hdr_copy(picture, "full", None, quality=95)
            if made is not None:
                return made, "image/jpeg"
        target = self._full / f"{picture.id}-{picture.version}.png"
        if target.is_file():
            return target, "image/png"
        with self._lock_for(target):
            if not target.is_file():
                image = decode(
                    picture.path,
                    picture.kind,
                    longest=None,
                    ffmpeg=self._ffmpeg(),
                    reader=self.reader,
                )
                save_copy(image, target, "PNG", compress_level=1)
                self._prune()
        return target, "image/png"

    def _hdr_copy(
        self, picture: Source, purpose: str, longest: int | None, *, quality: int
    ) -> Path | None:
        """An HDR photo's copy as an Ultra HDR JPEG: its picture, and its gain map made the same
        share of it; None when its gain map won't read now (an ordinary copy then)."""
        self._readable(picture)
        folder = self._full if longest is None else self._root / _shelf(picture.id)
        name = f"{picture.id}-{picture.version}{'' if longest is None else f'-{purpose}'}.jpg"
        target = folder / name
        if target.is_file():
            return target
        if (picture.id, picture.version) in self._unread:
            return None
        with self._lock_for(target):
            if target.is_file():
                return target
            gain = hdr.read(picture.path, ffmpeg=self._ffmpeg(), scratch=self._scratch)
            if gain is None or picture.size is None:
                self._unread.add((picture.id, picture.version))
                return None
            image = decode(
                picture.path, picture.kind, longest=longest, ffmpeg=self._ffmpeg(), reader=None
            )
            shown_gain = shown_with(gain, picture.size, image.size)
            options: dict[str, object] = {"quality": quality, "subsampling": 0}
            profile = image.info.get("icc_profile")
            if isinstance(profile, bytes):
                options["icc_profile"] = profile
            rgb = image if image.mode in ("RGB", "L") else image.convert("RGB")
            data = with_gain_map(rgb, "JPEG", options, shown_gain)
            target.parent.mkdir(parents=True, exist_ok=True)
            writing = target.with_name(f"{target.name}.{secrets.token_hex(4)}.part")
            try:
                writing.write_bytes(data)
                try:
                    writing.replace(target)
                except PermissionError:
                    if not target.is_file():
                        raise
            finally:
                writing.unlink(missing_ok=True)
            if longest is None:
                self._prune()
        return target

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
                image = decode(
                    picture.path,
                    picture.kind,
                    longest=longest,
                    ffmpeg=self._ffmpeg(),
                    reader=self.reader,
                )
                save_copy(image, target, "WEBP", quality=quality, method=4)
        return target

    @staticmethod
    def _readable(picture: Source) -> None:
        if picture.problem:
            raise UnreadableError(picture.problem)

    def _prune(self) -> None:
        """Keeps the newest few full-size copies."""
        copies = sorted(
            [*self._full.glob("*.png"), *self._full.glob("*.jpg")], key=_made, reverse=True
        )
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
