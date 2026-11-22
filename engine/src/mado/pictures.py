"""Reading pictures: what each one is (its facts), and decoding it the way it's shown, for the
smaller copies the window shows (mado/previews.py).

Pillow reads most formats by itself. A HEIF (a phone's HEIC) has its facts read from its layout
and Exif (mado/core/heif.py), and its picture decoded by ffmpeg. Camera RAW is listed, not read,
until Mado has a RAW reader. Nothing here changes a picture: files are only opened to read.
"""

import io
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from mado.core import facts, heif
from mado.core.files import Kind

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


def read_facts(path: Path, kind: Kind) -> Facts:
    """What a picture is, read from its header and EXIF, without decoding it."""
    if not path.is_file():
        raise PictureGoneError(path)
    if kind == "heif":
        return _heif_facts(path)
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
        raise UnreadableError(f"{_DAMAGED}: {error.strerror or error}.") from None
    except (SyntaxError, ValueError) as error:  # a part of it Pillow won't take, as decode says
        raise UnreadableError(f"{_DAMAGED}: {error}.") from None
    return _facts(name, width, height, found)


def decode(
    path: Path, kind: Kind, *, longest: int | None, ffmpeg: Command | None = None
) -> Image.Image:
    """The picture, decoded and turned the way it's shown, no longer on its longer side than
    `longest` (None: as big as it is; never made bigger), in pixels the window can show: RGB,
    RGBA or grey."""
    if kind == "raw":
        raise UnreadableError("Mado can't read camera RAW yet: it lists them as they are.")
    if not path.is_file():
        raise PictureGoneError(path)
    if kind == "heif":
        return _decode_heif(path, longest, ffmpeg)
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
    except (OSError, SyntaxError, ValueError) as error:
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
    try:
        with path.open("rb") as file:
            layout = heif.meta_layout(_meta_box(file))
            item = layout.exif_inline or _read_extents(file, layout.exif)
    except heif.HeifError as error:
        raise UnreadableError(f"{_DAMAGED}: {error}.") from None
    except OSError as error:
        raise UnreadableError(f"{_DAMAGED}: {error.strerror or error}.") from None
    if not layout.width or not layout.height:
        raise UnreadableError(f"{_DAMAGED}: it doesn't say how big its picture is.")
    found = Image.Exif()
    tiff = heif.exif_tiff(item) if item else None
    if tiff is not None:
        try:
            found.load(tiff)
        except OSError, SyntaxError, ValueError:
            found = Image.Exif()  # damaged Exif: the picture is still the picture
    name = "HEIC" if path.suffix.casefold() == ".heic" else "HEIF"
    return _facts_turned(name, layout.width, layout.height, found, layout.orientation)


def _meta_box(file: BinaryIO) -> bytes:
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
    return image.transpose(turn) if turn is not None else image


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
