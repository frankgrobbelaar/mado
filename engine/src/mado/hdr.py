"""HDR photos on the PC: whether a picture carries a gain map Mado reads, from its headers alone
(quick enough for every picture a scan reads), and the gain map itself, decoded and turned the
way its picture is shown, as gains in stops (mado/core/gainmap.py).

- A JPEG's (Ultra HDR, or ISO 21496-1's): its MPF segment, or else its XMP's directory, says
  where its gain map picture is; that picture's XMP or APP2 gives its numbers, ISO's first.
- A HEIC's or an AVIF's: its tmap item (ISO 21496-1), or Apple's auxiliary image with its
  headroom in an XMP item or the picture's MakerNote. The gain map item is written into a file
  of its own (mado/core/heif_writer.py) and decoded as a picture: by Pillow for AV1, by ffmpeg
  for HEVC, in the data folder's cache, never beside the picture.

A gain map is decoded no bigger than 4096 pixels on its longer side, as every copy of it Mado
keeps is (mado/core/gains.py): a huge photo's full-size gain map is smooth. Nothing here writes
to a picture: files are only opened to read.
"""

import io
import logging
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
from PIL import Image

from mado.core import gainmap, heif, jpegs
from mado.core.gainmap import GainMap, GainMapError, Info
from mado.core.gains import MOST
from mado.core.heif_writer import one_item
from mado.pictures import Command, meta_box

log = logging.getLogger(__name__)

type State = Literal["none", "hdr", "unreadable"]

_HEAD = 64 << 10  # bytes read first of a picture's or its gain map's header
_MOST_HEAD = 4 << 20  # a header longer than this isn't one
_ORIENTATION = 0x0112
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DECODE_TIMEOUT = 120


@dataclass(frozen=True)
class Found:
    """Whether a picture carries a gain map, and what it says."""

    state: State
    info: Info | None = None  # its numbers, when Mado reads them
    why: str | None = None  # why Mado can't keep it, said after "Its gain map"
    size: tuple[int, int] | None = None  # the gain map as stored, before it's turned
    where: tuple[str, int, int] | None = None  # how to find it: a JPEG's part, or a HEIF item


NONE = Found("none")


def facts(path: Path) -> Found:
    """Whether the picture at `path` carries a gain map Mado reads, from its headers alone: a
    JPEG's first segments and its gain map picture's, or a HEIF's layout. One that can't be read
    is said with why; a file that can't be opened says nothing (its own reading says why)."""
    try:
        with path.open("rb") as file:
            start = file.read(12)
            if start.startswith(jpegs.SOI):
                return _jpeg_facts(file)
            if start[4:8] == b"ftyp":
                return _heif_facts(file)
    except (OSError, jpegs.JpegError, heif.HeifError, ValueError) as error:
        log.debug("Mado couldn't look for a gain map in %s: %s", path, error)
    return NONE


def read(path: Path, *, ffmpeg: Command | None, scratch: Path | None) -> GainMap | None:
    """The picture's gain map as gains in stops, turned the way its picture is shown; None for a
    picture without one, or one Mado can't read (its picture is then kept as it is). `scratch`:
    a folder of Mado's own for a HEIC's gain map on its way to ffmpeg."""
    found = facts(path)
    if found.state != "hdr" or found.info is None or found.where is None:
        return None
    kind, at, length = found.where
    try:
        with path.open("rb") as file:
            if kind == "jpeg":
                values, turn = _jpeg_values(file, at, length)
            else:
                values, turn = _heif_values(file, at, ffmpeg, scratch, found.info)
    except Exception as error:  # whatever its decoder raised, its picture is kept as it is
        log.warning("Mado couldn't read the gain map of %s: %s", path, error)
        return None
    if found.size is not None and not _whole(values, found.size):
        log.warning("The gain map of %s came out another shape than its own", path)
        return None
    info = found.info
    values = _at_most(values, MOST)
    if kind == "apple":
        headroom = float(np.exp2(info.alternate_headroom))
        gains = gainmap.apple_gains(values if values.ndim == 2 else values[..., 0], headroom)
    else:
        if not info.colour and values.ndim == 3:
            values = values[..., 0]
        gains = gainmap.gains_of(values, info)
    return GainMap(gainmap.turned(gains, turn), info)


def _whole(values: np.ndarray, size: tuple[int, int]) -> bool:
    """Whether a gain map decoded is the whole of it as its headers size it (decoded smaller or
    not), not a part, as one tile of a grid would be: the same shape, give or take a pixel."""
    height, width = values.shape[:2]
    across, down = width / size[0], height / size[1]
    return abs(across - down) <= 0.02 * max(across, down) + 1 / min(size)


def _at_most(values: np.ndarray, most: int) -> np.ndarray:
    """A gain map's values no bigger than `most` on their longer side: a huge photo's full-size
    gain map is smooth, and every copy of it Mado keeps is at most that."""
    height, width = values.shape[:2]
    if max(width, height) <= most:
        return values
    scale = most / max(width, height)
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return np.asarray(Image.fromarray(values).resize(size, Image.Resampling.BOX))


# A JPEG's.


def _jpeg_facts(file: BinaryIO) -> Found:
    data = _head(file, 0)
    primary = jpegs.head(data)
    version = gainmap.xmp_version(primary.xmp) if primary.xmp else None
    if version is None and primary.iso is None:
        return NONE  # an ordinary JPEG (an MPO of a camera's, say): nothing more read
    if version is not None and version.strip() != gainmap.VERSION:
        return Found(
            "unreadable", why=f"is version {version.strip()[:12]}, which Mado doesn't know yet"
        )
    if (
        primary.iso is not None
        and len(primary.iso) >= 2
        and primary.iso[:2] != b"\x00\x00"
        and version is None
    ):
        level = int.from_bytes(primary.iso[:2], "big")
        return Found("unreadable", why=f"is version {level}, which Mado doesn't know yet")
    file.seek(0, io.SEEK_END)
    size = file.tell()
    # Where its MPF says the gain map is; else (or where that isn't a picture) where its XMP's
    # directory says: the file's last part, its length given.
    places = [(part.start, part.length) for part in primary.parts[1:]]
    if primary.xmp is not None:
        length = gainmap.container_length(primary.xmp)
        if length is not None and 0 < length < size and (size - length, length) not in places:
            places.append((size - length, length))
    problem: str | None = None
    seen = False  # a picture where it was said to be
    for start, length in places:
        if start <= 0 or start >= size:
            continue
        own = _head(file, start)
        if not own.startswith(jpegs.SOI):
            continue
        seen = True
        found = jpegs.head(own)
        info, said = _numbers(found)
        if info is not None:
            return Found("hdr", info, None, jpegs.size_of(own), ("jpeg", start, length))
        problem = problem or said
    if problem is None:
        problem = (
            "doesn't say how much brighter it goes"
            if seen
            else "isn't where its picture says it is"
        )
    return Found("unreadable", why=problem)


def _numbers(found: jpegs.Head) -> tuple[Info | None, str | None]:
    """A gain map picture's numbers: ISO 21496-1's, else Adobe's XMP; and why neither reads."""
    problem: str | None = None
    if found.iso is not None and not gainmap.iso_version_only(found.iso):
        try:
            return gainmap.from_iso(found.iso), None
        except GainMapError as error:
            problem = str(error)
    if found.xmp is not None:
        try:
            info = gainmap.from_xmp(found.xmp)
        except GainMapError as error:
            return None, problem or str(error)
        if info is not None:
            return info, None
    return None, problem


def _jpeg_values(file: BinaryIO, at: int, length: int) -> tuple[np.ndarray, int]:
    file.seek(0)
    with Image.open(file) as picture:
        turn = picture.getexif().get(_ORIENTATION)
    file.seek(at)
    data = file.read(length)
    with Image.open(io.BytesIO(data)) as opened:
        opened.draft(opened.mode, (MOST, MOST))  # a huge one decodes at a smaller scale first
        opened.load()
        values = np.asarray(opened.convert("L" if len(opened.getbands()) == 1 else "RGB"))
    return values, turn if isinstance(turn, int) and 1 <= turn <= 8 else 1


# A HEIF's (a HEIC, or an AVIF).


def _heif_facts(file: BinaryIO) -> Found:
    file.seek(0)
    meta = meta_box(file)
    found = heif.items_of(meta)
    place = heif.gain_map_place(found)
    if place is None:
        return NONE
    item = found.items.get(place.item)
    if item is None:
        return Found("unreadable", why="isn't among its pictures")

    def read(at: int, length: int) -> bytes:
        file.seek(at)
        return file.read(length)

    size = heif.size_of(item)
    if place.kind == "iso" and place.numbers is not None:
        data = heif.bytes_of(found, found.items[place.numbers], read)
        if not data or data[0] != 0:
            return Found("unreadable", why="is a kind Mado doesn't know yet")
        try:
            info = gainmap.from_iso(data[1:])
        except GainMapError as error:
            return Found("unreadable", why=str(error))
        return Found("hdr", info, None, size, ("iso", place.item, 0))
    headroom: float | None = None
    for each in place.xmp:
        headroom = headroom or gainmap.apple_xmp_headroom(
            heif.bytes_of(found, found.items[each], read)
        )
    if headroom is None:
        headroom = _makernote_headroom(meta, read)
    if headroom is None:
        return Found("unreadable", why="doesn't say how much brighter it goes")
    return Found("hdr", gainmap.apple_info(headroom), None, size, ("apple", place.item, 0))


def _makernote_headroom(meta: bytes, read: heif.Reader) -> float | None:
    """Apple's headroom from the picture's Exif MakerNote (its tags 33 and 48)."""
    layout = heif.meta_layout(meta)
    item = layout.exif_inline or b"".join(read(each.offset, each.length) for each in layout.exif)
    tiff = heif.exif_tiff(item) if item else None
    if tiff is None:
        return None
    exif = Image.Exif()
    try:
        exif.load(tiff)
        note = exif.get_ifd(0x8769).get(0x927C)
    except OSError, SyntaxError, ValueError:
        return None
    if not isinstance(note, bytes):
        return None
    return gainmap.apple_headroom(*gainmap.apple_makernote(note))


def _heif_values(
    file: BinaryIO, item_id: int, ffmpeg: Command | None, scratch: Path | None, info: Info
) -> tuple[np.ndarray, int]:
    file.seek(0)
    found = heif.items_of(meta_box(file))
    place = heif.gain_map_place(found)
    if place is None or place.item != item_id:
        raise heif.HeifError("its gain map moved as it was read")

    def read(at: int, length: int) -> bytes:
        file.seek(at)
        return file.read(length)

    alone = one_item(found, item_id, read)
    item = found.items[item_id]
    tiles = found.refs.get(b"dimg", {}).get(item_id, ())
    av1 = item.kind == b"av01" or any(
        found.items[each].kind == b"av01" for each in tiles if each in found.items
    )
    if av1:
        with Image.open(io.BytesIO(alone)) as opened:
            opened.load()
            values = np.asarray(opened.convert("RGB" if info.colour else "L"))
        return values, place.orientation
    return _decoded_by_ffmpeg(alone, ffmpeg, scratch), place.orientation


def _decoded_by_ffmpeg(data: bytes, ffmpeg: Command | None, scratch: Path | None) -> np.ndarray:
    """A one-item HEIF decoded by ffmpeg, as stored, from a file of Mado's own in `scratch`."""
    if ffmpeg is None or scratch is None:
        raise ValueError("Mado needs ffmpeg, and a folder of its own, to read a HEIC's gain map")
    scratch.mkdir(parents=True, exist_ok=True)
    alone = scratch / f"gain-map-{secrets.token_hex(6)}.heic"
    alone.write_bytes(data)
    command = [str(ffmpeg)] if isinstance(ffmpeg, Path) else list(ffmpeg)
    try:
        done = subprocess.run(  # noqa: S603 - Mado's own ffmpeg, and a path, never a shell
            [
                *command,
                *("-v", "error", "-nostdin", "-noautorotate", "-i", str(alone)),
                *("-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-pix_fmt", "rgb24", "-"),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_DECODE_TIMEOUT,
            creationflags=_NO_WINDOW,
            check=False,
        )
    finally:
        alone.unlink(missing_ok=True)
    if done.returncode != 0 or not done.stdout:
        said = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ValueError(
            f"ffmpeg couldn't decode its gain map ({said[-1] if said else done.returncode})"
        )
    with Image.open(io.BytesIO(done.stdout)) as opened:
        opened.load()
        return np.asarray(opened.convert("RGB"))


def _head(file: BinaryIO, start: int) -> bytes:
    """A JPEG's segments up to its picture, from `start`: 64 KB first, more while it's cut short."""
    want = _HEAD
    while True:
        file.seek(start)
        data = file.read(want)
        try:
            if jpegs.head(data).whole or len(data) < want or want >= _MOST_HEAD:
                return data
        except jpegs.JpegError:
            return data
        want *= 4
