"""Reading pictures: what each one is (its facts), and decoding it the way it's shown, for the
smaller copies the window shows (mado/previews.py).

Pillow reads most formats by itself. A HEIF (a phone's HEIC) has its facts read from its layout
and Exif (mado/core/heif.py), and its picture decoded by ffmpeg. A camera RAW is read by LibRaw
(mado/libraw.py), downloaded the first time one is read: its facts without developing it, a small
copy from the preview its camera kept inside it, and anything bigger developed (mado/core/raw.py
says which). Nothing here changes a picture: files are only opened to read.
"""

import io
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Literal

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from mado.core import facts, heif, raw
from mado.core.files import Kind
from mado.libraw import (
    LibRaw,
    NeedsReaderError,
    Preview,
    RawError,
    RawFacts,
    Reader,
    opens_to_read,
)

__all__ = ["NeedsReaderError"]  # a RAW waiting for its reader, as callers catch it from here

# Pillow refuses pictures over 89 megapixels, a guard for servers taking strangers' files. The
# owner's own panoramas and scans can be bigger; a gigapixel is about 3 GB to decode.
Image.MAX_IMAGE_PIXELS = 1_000_000_000

type Command = Path | Sequence[str]  # ffmpeg, or a whole command standing in for it in tests

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flashing for each picture
_DECODE_TIMEOUT = 120  # seconds ffmpeg may spend on one picture
_LAYOUT_LIMIT = 16 << 20  # a HEIF layout (its meta box) bigger than this isn't one
_EXIF_LIMIT = 4 << 20
_ORIENTATION, _EXIF_IFD, _GPS_IFD = 0x0112, 0x8769, 0x8825
_MAKE, _MODEL, _TAKEN = 0x010F, 0x0110, 0x9003
_EXPOSURE, _F_NUMBER, _ISO, _FOCAL, _LENS = 0x829A, 0x829D, 0x8827, 0x920A, 0xA434
_NAMES = {"MPO": "JPEG", "WEBP": "WebP", "DIB": "BMP"}  # Pillow's names, as people know them
_TURNS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
_DAMAGED = "The file is damaged or was only half copied"
# Pillow's colour management, whose types are partly unknown to Pyright: called through Any.
_CMS: Any = ImageCms


class UnreadableError(Exception):
    """A picture that won't open, with a sentence saying why."""


class InUseError(UnreadableError):
    """A picture another app has open, so Mado can't read it now: nothing's wrong with it, and it
    opens once that app lets go."""


class ShortOfMemoryError(UnreadableError):
    """A camera RAW too big to develop with the memory free now: nothing's wrong with it, so it's
    never kept as one that won't open."""


class PictureGoneError(Exception):
    """A picture's file isn't where the library says: moved, deleted, or its drive unplugged."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"{path.name} isn't there any more: its drive may be unplugged, or it was moved or "
            "deleted. Mado looks again as it notices changes."
        )


class NeedsFfmpegError(Exception):
    """A HEIF can't be decoded until ffmpeg is there."""

    def __init__(self) -> None:
        super().__init__(
            "Mado needs ffmpeg to show HEIC pictures, and it isn't there. Restart Mado; if it "
            "says the same, reinstall it to fetch ffmpeg again."
        )


@dataclass(frozen=True)
class Facts:
    format: str  # "JPEG", "HEIC", "PNG"…
    width: int  # as it's shown, turned the way its orientation says
    height: int
    orientation: int | None  # EXIF's 1 to 8; None when the picture doesn't say
    taken: datetime | None  # by the camera's clock; None when the picture doesn't say
    camera: str | None
    located: bool  # it carries where it was taken
    # an HDR photo's gain map: "hdr" one Mado reads, "unreadable" one it can't, "none"
    hdr: Literal["none", "hdr", "unreadable"] = "none"


def read_facts(path: Path, kind: Kind, reader: Reader | None = None) -> Facts:
    """What a picture is, read from its header and EXIF, without decoding it (a camera RAW's by
    `reader`, without developing it), and whether it carries a gain map (mado/hdr.py)."""
    if not path.is_file():
        raise PictureGoneError(path)
    if kind == "raw":
        return _raw_facts(path, reader)
    found = _heif_facts(path) if kind == "heif" else _picture_facts(path)
    from mado import hdr  # here, not above: mado/hdr.py reads HEIF layouts with this module

    return replace(found, hdr=hdr.facts(path).state)


def _raw_facts(path: Path, reader: Reader | None) -> Facts:
    found = _raw(path, reader, lambda library: library.facts(path))
    return Facts(
        format=path.suffix[1:].upper(),
        width=found.width,
        height=found.height,
        orientation=raw.orientation(found.flip),
        taken=found.taken,
        camera=facts.camera(found.make, found.model),
        located=found.latitude is not None,
    )


def _picture_facts(path: Path) -> Facts:
    """A picture Pillow reads, from its header and EXIF."""
    try:
        with Image.open(path) as image:
            width, height = image.size
            found = _exif_of(image)
            name = _NAMES.get(image.format or "", image.format or path.suffix[1:].upper())
    except UnidentifiedImageError:
        raise UnreadableError(
            "Mado can't tell what kind of picture it is: it may be damaged, or not a picture at "
            "all."
        ) from None
    except Image.DecompressionBombError:
        raise UnreadableError(_too_big(path)) from None
    except OSError as error:
        _raise_in_use(path, error)
        raise UnreadableError(f"{_DAMAGED}: {error.strerror or error}.") from None
    except (SyntaxError, ValueError) as error:  # a part of it Pillow won't take, as decode says
        raise UnreadableError(f"{_DAMAGED}: {error}.") from None
    return _facts(name, width, height, found)


_LOCKED = (32, 33)  # Windows' sharing and lock violations: another app has the file open


def _raise_in_use(path: Path, error: OSError) -> None:
    """Raises InUseError for a picture another app holds open, so Mado can't read it."""
    if getattr(error, "winerror", None) in _LOCKED:
        raise InUseError(
            f"{path.name} is open in another app, so Mado can't read it. Close it there, then "
            "try again."
        ) from None


def decode(
    path: Path,
    kind: Kind,
    *,
    longest: int | None,
    ffmpeg: Command | None = None,
    reader: Reader | None = None,
) -> Image.Image:
    """The picture, decoded and turned the way it's shown, no longer on its longer side than
    `longest` (None: as big as it is; never made bigger), in pixels the window can show: RGB,
    RGBA or grey."""
    if not path.is_file():
        raise PictureGoneError(path)
    if kind == "heif":
        return _decode_heif(path, longest, ffmpeg)
    if kind == "raw":
        shown = _raw(path, reader, lambda library: _developed(library, path, longest))
        if longest is not None:
            shown.thumbnail((longest, longest), Image.Resampling.LANCZOS)
        return shown
    try:
        with Image.open(path) as image:
            if longest is not None:
                image.draft(None, (longest, longest))  # a JPEG decodes at a smaller scale
            image.load()
            profile = image.info.get("icc_profile")
            shown = _showable(ImageOps.exif_transpose(image), profile)
    except UnidentifiedImageError:
        raise UnreadableError(
            "Mado can't tell what kind of picture it is: it may be damaged, or not a picture at "
            "all."
        ) from None
    except Image.DecompressionBombError:
        raise UnreadableError(_too_big(path)) from None
    except OSError as error:
        _raise_in_use(path, error)
        raise UnreadableError(f"{_DAMAGED}: {error}.") from None
    except (SyntaxError, ValueError) as error:
        raise UnreadableError(f"{_DAMAGED}: {error}.") from None
    if longest is not None:
        shown.thumbnail((longest, longest), Image.Resampling.LANCZOS)
    return shown


def _facts(name: str, width: int, height: int, found: Image.Exif) -> Facts:
    orientation = found.get(_ORIENTATION)
    turned = orientation if isinstance(orientation, int) and 1 <= orientation <= 8 else None
    return _facts_turned(name, width, height, found, turned)


def _facts_turned(
    name: str, width: int, height: int, found: Image.Exif, orientation: int | None
) -> Facts:
    shown_width, shown_height = facts.shown_size(width, height, orientation)
    try:
        taken = facts.taken(_text(found.get_ifd(_EXIF_IFD).get(_TAKEN)))
        camera = facts.camera(_text(found.get(_MAKE)), _text(found.get(_MODEL)))
        located = facts.located(found.get_ifd(_GPS_IFD))
    except Exception:  # damaged EXIF: the picture is still the picture, its facts unknown
        taken, camera, located = None, None, False
    return Facts(
        format=name,
        width=shown_width,
        height=shown_height,
        orientation=orientation,
        taken=taken,
        camera=camera,
        located=located,
    )


def _exif_of(image: Image.Image) -> Image.Exif:
    try:
        return image.getexif()
    except Exception:  # damaged EXIF: the picture is still the picture
        return Image.Exif()


def _text(value: object) -> str | None:
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return value if isinstance(value, str) else None


def _heif_facts(path: Path) -> Facts:
    layout, found = _heif_layout(path)
    if not layout.width or not layout.height:
        raise UnreadableError(f"{_DAMAGED}: it doesn't say how big its picture is.")
    name = "HEIC" if path.suffix.casefold() == ".heic" else "HEIF"
    return _facts_turned(name, layout.width, layout.height, found, layout.orientation)


def _heif_layout(path: Path) -> tuple[heif.Layout, Image.Exif]:
    """A HEIF's layout, and its Exif (empty when it has none, or it's damaged)."""
    try:
        with path.open("rb") as file:
            layout = heif.meta_layout(meta_box(file))
            item = layout.exif_inline or _read_extents(file, layout.exif)
    except heif.HeifError as error:
        raise UnreadableError(f"{_DAMAGED}: {error}.") from None
    except OSError as error:
        _raise_in_use(path, error)
        raise UnreadableError(f"{_DAMAGED}: {error.strerror or error}.") from None
    found = Image.Exif()
    tiff = heif.exif_tiff(item) if item else None
    if tiff is not None:
        try:
            found.load(tiff)
        except OSError, SyntaxError, ValueError:
            found = Image.Exif()  # damaged Exif: the picture is still the picture
    return layout, found


def read_exif(path: Path, kind: Kind, reader: Reader | None = None) -> Image.Exif | None:
    """A picture's EXIF as it is, every part of it read in, to carry over to a picture made from
    it; None when it has none, or it can't be read. A camera RAW's is written from what its
    reader read of it: the camera, when it was taken, how, and where."""
    if kind == "raw":
        try:
            return _raw_exif(_raw(path, reader, lambda library: library.facts(path)))
        except UnreadableError, NeedsReaderError, PictureGoneError:
            return None
    try:
        if kind == "heif":
            found = _heif_layout(path)[1]
        else:
            with Image.open(path) as image:
                found = _exif_of(image)
                for inner in (_EXIF_IFD, _GPS_IFD):
                    found.get_ifd(inner)  # read in now, while the file is open
        if not len(found):
            return None
        whole = Image.Exif()
        whole.load(found.tobytes())
    except Exception:  # damaged EXIF: the picture made carries none
        return None
    return whole


def _raw[T](path: Path, reader: Reader | None, read: Callable[[LibRaw], T]) -> T:
    """What LibRaw reads of a RAW, its errors in Mado's words, noted while it reads (an engine
    LibRaw stops is found as the next starts). A RAW another app holds is in use, not damaged;
    one too big for the memory free now is short of memory; one LibRaw faults on (ctypes turns
    Windows' fault into OSError) won't open."""
    if reader is None:
        raise NeedsReaderError
    library = reader.library()
    try:
        opens_to_read(path)  # another app holding it shows here, before LibRaw takes it for damage
    except OSError as error:
        _raise_in_use(path, error)
        raise UnreadableError(f"{_DAMAGED}: {error.strerror or error}.") from None
    try:
        with reader.reading(path):
            return read(library)
    except RawError as error:
        if error.problem.kind == "memory":
            raise ShortOfMemoryError(error.problem.sentence) from None
        raise UnreadableError(error.problem.sentence) from None
    except OSError as error:
        raise UnreadableError(
            f"Mado's RAW reader stopped on it ({error}). Mado left it exactly as it is."
        ) from None


def _developed(library: LibRaw, path: Path, longest: int | None) -> Image.Image:
    """A RAW at a size: its camera's preview, upright, for a small copy when that will do; else
    developed, at half size when that's big enough. A preview LibRaw won't hand over, or one
    that won't decode, is no fault of the RAW's: it's developed instead."""
    found = library.facts(path)
    shown = (found.width, found.height)
    preview: Preview | None = None
    turn: int | None = None
    if longest is not None and longest <= raw.PREVIEW_UP_TO:
        try:
            preview = library.preview(path)
        except RawError:
            preview = None
        turn = raw.preview_turn(preview.size, shown, found.flip) if preview else None
    upright = None
    if preview is not None and turn is not None:
        upright = (preview.size[1], preview.size[0]) if turn & 4 else preview.size
    way = raw.wanted(upright, shown, longest)
    if way == "preview" and preview is not None and turn is not None:
        try:
            return _from_preview(preview, turn, longest)
        except UnreadableError:
            way = raw.wanted(None, shown, longest)
    return library.develop(path, half=way == "half")


def _from_preview(preview: Preview, turn: int, longest: int | None) -> Image.Image:
    """A camera's preview, decoded (a JPEG at a smaller scale first) and laid out upright."""
    try:
        if preview.kind == "jpeg":
            with Image.open(io.BytesIO(preview.data)) as stored:
                if longest is not None:
                    stored.draft("RGB", (longest, longest))
                stored.load()
                profile = stored.info.get("icc_profile")
                image = _showable(stored.convert("RGB"), profile)
        else:
            mode = "L" if preview.colors == 1 else "RGB"
            image = Image.frombytes(mode, preview.size, preview.data)
    except (OSError, SyntaxError, ValueError) as error:
        raise UnreadableError(f"{_DAMAGED}: its camera's preview won't open ({error}).") from None
    step = _TURNS.get(raw.orientation(turn))
    turned = image.transpose(step) if step is not None else image
    if "icc_profile" in image.info:
        turned.info["icc_profile"] = image.info["icc_profile"]
    return turned


def _raw_exif(found: RawFacts) -> Image.Exif | None:
    """The EXIF a picture made from a RAW carries: the camera, when it was taken, how, and where
    (encode.py leaves the place out unless the owner keeps it)."""
    made = Image.Exif()
    if found.make:
        made[_MAKE] = found.make
    if found.model:
        made[_MODEL] = found.model
    inner = made.get_ifd(_EXIF_IFD)
    if found.taken is not None:
        inner[_TAKEN] = found.taken.strftime("%Y:%m:%d %H:%M:%S")
    if found.iso > 0:
        inner[_ISO] = round(found.iso)
    if found.shutter > 0:
        inner[_EXPOSURE] = found.shutter
    if found.aperture > 0:
        inner[_F_NUMBER] = found.aperture
    if found.focal > 0:
        inner[_FOCAL] = found.focal
    if found.lens:
        inner[_LENS] = found.lens
    if found.latitude is not None and found.longitude is not None:
        gps = made.get_ifd(_GPS_IFD)
        gps.update(
            {
                1: "N" if found.latitude >= 0 else "S",
                2: _dms(found.latitude),
                3: "E" if found.longitude >= 0 else "W",
                4: _dms(found.longitude),
            }
        )
    if not len(made) and not len(inner):
        return None
    whole = Image.Exif()
    whole.load(made.tobytes())
    return whole


def _dms(degrees: float) -> tuple[float, float, float]:
    whole = abs(degrees)
    minutes = (whole - int(whole)) * 60
    return float(int(whole)), float(int(minutes)), round((minutes - int(minutes)) * 60, 4)


def meta_box(file: BinaryIO) -> bytes:
    """The payload of a HEIF's top-level meta box, found by walking the boxes before it."""
    file.seek(0, io.SEEK_END)
    end = file.tell()
    at = 0
    while at + 8 <= end:
        file.seek(at)
        kind, header, size = heif.box_header(file.read(16))
        size = end - at if size is None else size
        if size < header or at + size > end:
            raise heif.HeifError("a box runs past the end of the file")
        if kind == b"meta":
            if size > _LAYOUT_LIMIT:
                raise heif.HeifError("its layout is far bigger than any picture's")
            file.seek(at + header)
            return file.read(size - header)
        at += size
    raise heif.HeifError("it has no layout saying what it holds")


def _read_extents(file: BinaryIO, extents: tuple[heif.Extent, ...]) -> bytes | None:
    if not extents or sum(extent.length for extent in extents) > _EXIF_LIMIT:
        return None
    parts: list[bytes] = []
    for extent in extents:
        file.seek(extent.offset)
        parts.append(file.read(extent.length))
    return b"".join(parts)


def _decode_heif(path: Path, longest: int | None, ffmpeg: Command | None) -> Image.Image:
    found = _heif_facts(path)  # its size and turn, and whether it's a HEIF at all
    profile = _heif_layout(path)[0].profile
    if ffmpeg is None:
        raise NeedsFfmpegError
    command = [str(ffmpeg)] if isinstance(ffmpeg, Path) else list(ffmpeg)
    scale: list[str] = []
    if longest is not None:
        fit = f"'min(iw,{longest})':'min(ih,{longest})':force_original_aspect_ratio=decrease"
        scale = ["-vf", f"scale={fit}"]
    try:
        done = subprocess.run(  # noqa: S603 - Mado's own ffmpeg, and a path, never a shell
            [
                *command,
                *("-v", "error", "-nostdin", "-noautorotate", "-i", str(path)),
                *("-frames:v", "1", *scale),
                *("-f", "image2pipe", "-c:v", "png", "-pix_fmt", "rgb24", "-"),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_DECODE_TIMEOUT,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise UnreadableError(
            f"ffmpeg spent more than {_DECODE_TIMEOUT} seconds on it without a picture, so Mado "
            "stopped it. The file may be damaged."
        ) from None
    except OSError as error:
        raise UnreadableError(f"ffmpeg couldn't start: {error.strerror or error}.") from None
    if done.returncode != 0 or not done.stdout:
        lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
        said = (
            lines[-1].removeprefix(f"{path}: ") if lines else f"it stopped with {done.returncode}"
        )
        raise UnreadableError(f"{_DAMAGED}: ffmpeg says “{said.rstrip('.')}”.")
    try:
        with Image.open(io.BytesIO(done.stdout)) as decoded:
            decoded.load()
            image = decoded.convert("RGB")
    except (OSError, SyntaxError, ValueError) as error:
        raise UnreadableError(f"ffmpeg gave Mado something it couldn't read: {error}.") from None
    # ffmpeg decodes it as stored (-noautorotate); Mado turns it as its layout says.
    stored = facts.shown_size(found.width, found.height, found.orientation)
    if abs(image.width / image.height - stored[0] / stored[1]) > 0.02:
        raise UnreadableError(
            f"ffmpeg gave only part of it ({image.width} × {image.height} of "
            f"{stored[0]} × {stored[1]}), so Mado didn't show that as the whole."
        )
    turn = _TURNS.get(found.orientation or 1)
    shown = image.transpose(turn) if turn is not None else image
    if profile is not None and _rgb_profile(profile):
        shown.info["icc_profile"] = profile  # a phone's wide colours stay wide
    return shown


def _showable(image: Image.Image, profile: object) -> Image.Image:
    """The picture in pixels the window shows (RGB, RGBA or grey), keeping a colour profile it
    can use (the browser shows wide colours from it) and turning print colours (CMYK) into
    screen ones."""
    mode = image.mode
    see_through = "transparency" in image.info
    if mode == "RGBA" or (mode in ("RGB", "L") and not see_through):
        shown = image
    elif mode.startswith("I;16") or mode == "I":
        shown = _eight_bit(image)
    elif mode == "CMYK":
        shown = _screen_colours(image, profile)
        profile = None
    elif mode in ("LA", "La", "PA", "RGBa") or see_through:
        shown = image.convert("RGBA")
    elif mode in ("1", "F"):
        shown = image.convert("L")
    else:  # P, YCbCr, RGBX and the rest
        shown = image.convert("RGB")
    if isinstance(profile, bytes) and shown.mode in ("RGB", "RGBA") and _rgb_profile(profile):
        shown.info["icc_profile"] = profile
    else:
        shown.info.pop("icc_profile", None)
    return shown


def _eight_bit(image: Image.Image) -> Image.Image:
    """A 16-bit grey picture (a scanner's) in 8-bit grey, keeping its light and dark: each
    pixel's high byte."""
    sixteen = image if image.mode == "I;16" else image.convert("I").convert("I;16")
    return Image.frombytes("L", sixteen.size, sixteen.tobytes("raw", "I;16")[1::2])


def _screen_colours(image: Image.Image, profile: object) -> Image.Image:
    """A CMYK picture in screen colours, through its own profile when it has one."""
    if isinstance(profile, bytes):
        try:
            srgb = _CMS.createProfile("sRGB")
            converted = _CMS.profileToProfile(image, io.BytesIO(profile), srgb, outputMode="RGB")
        except ImageCms.PyCMSError:
            converted = None
        if isinstance(converted, Image.Image):
            return converted
    return image.convert("RGB")


def _rgb_profile(profile: bytes) -> bool:
    """Whether a colour profile is a screen's (RGB), which the window can show pictures in."""
    try:
        space: object = _CMS.ImageCmsProfile(io.BytesIO(profile)).profile.xcolor_space
    except ImageCms.PyCMSError, OSError, TypeError:
        return False
    return space == "RGB "


def _too_big(path: Path) -> str:
    return f"{path.name} is bigger than a gigapixel, which Mado doesn't open."
