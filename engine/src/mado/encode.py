"""Saving a picture Mado made: in JPEG, PNG, WebP or AVIF, with what the owner keeps of its
original (the date taken and the camera's details, its colour profile, and where it was taken
only when asked), then checked before it takes its place.

The date and camera come over in its EXIF, turned upright (it was turned as it was read), its
pixel size the new one, and without the original's little thumbnail; a print's says 300 dpi.
Its colours keep the original's profile, so a phone's wide colours stay wide; not kept, they're
turned into sRGB first, never just stripped, so they look the same.
"""

import io
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, ImageCms

from mado.core.quality import Format

_ORIENTATION, _EXIF_IFD, _GPS_IFD = 0x0112, 0x8769, 0x8825
_X_RESOLUTION, _Y_RESOLUTION, _RESOLUTION_UNIT = 0x011A, 0x011B, 0x0128
_PIXEL_X, _PIXEL_Y = 0xA002, 0xA003
_PILLOW = {"JPEG": "JPEG", "PNG": "PNG", "WebP": "WEBP", "AVIF": "AVIF"}
# Pillow's colour management, whose types are partly unknown to Pyright: called through Any.
_CMS: Any = ImageCms


class SaveError(Exception):
    """A picture that couldn't be saved, or didn't come out right, with a sentence saying why."""


def prepared_exif(
    original: Image.Exif | None,
    *,
    keep_camera: bool,
    keep_location: bool,
    size: tuple[int, int],
    dpi: int | None,
) -> Image.Exif | None:
    """The EXIF a made picture carries: its original's (the date taken, the camera's details)
    when kept, upright, its new size, its location only when kept; nothing when not."""
    if original is None or not keep_camera:
        return None
    made = Image.Exif()
    made.load(original.tobytes())
    made[_ORIENTATION] = 1  # it was turned upright as it was read
    if not keep_location:
        made.get_ifd(_GPS_IFD).clear()
        made.pop(_GPS_IFD, None)
    inner = made.get_ifd(_EXIF_IFD)
    if _PIXEL_X in inner or _PIXEL_Y in inner:
        inner[_PIXEL_X], inner[_PIXEL_Y] = size
    made.get_ifd(ExifTags.IFD.IFD1).clear()  # the original's little thumbnail: not this picture
    if dpi is not None:
        made[_X_RESOLUTION] = made[_Y_RESOLUTION] = float(dpi)
        made[_RESOLUTION_UNIT] = 2  # inches
    return made


def in_srgb(image: Image.Image, profile: bytes | None) -> Image.Image:
    """The picture's colours in sRGB: turned from its own profile, when it has one."""
    if profile is None:
        return image
    try:
        source = _CMS.ImageCmsProfile(io.BytesIO(profile))
        turned = _CMS.profileToProfile(image, source, _CMS.createProfile("sRGB"))
    except ImageCms.PyCMSError, OSError, TypeError:
        return image
    return turned if isinstance(turned, Image.Image) else image


def profile_name(profile: bytes | None) -> str | None:
    """A colour profile's name, as it calls itself: "Display P3", "sRGB IEC61966-2.1"."""
    if profile is None:
        return None
    try:
        name: object = _CMS.getProfileDescription(_CMS.ImageCmsProfile(io.BytesIO(profile)))
    except ImageCms.PyCMSError, OSError, TypeError:
        return None
    return str(name).strip() or None if isinstance(name, str) else None


def save(
    image: Image.Image,
    path: Path,
    format_: Format,
    quality: int | None,
    *,
    exif: Image.Exif | None,
    profile: bytes | None,
    dpi: int | None,
) -> None:
    """Writes the picture to `path` in `format_`, at `quality` (JPEG, WebP and AVIF), with its
    EXIF and colour profile."""
    options: dict[str, object] = {}
    if exif is not None:
        options["exif"] = exif
    if profile is not None:
        options["icc_profile"] = profile
    if dpi is not None and format_ in ("JPEG", "PNG"):
        options["dpi"] = (dpi, dpi)
    picture = image
    match format_:
        case "JPEG":
            picture = _flattened(image) if image.mode not in ("RGB", "L") else image
            level = quality or 92
            options.update(quality=level, optimize=True, subsampling=0 if level >= 90 else 2)
        case "PNG":
            options.update(compress_level=6)
        case "WebP":
            options.update(quality=quality or 90, method=4)
        case "AVIF":
            options.update(quality=quality or 80, speed=6)
    try:
        picture.save(path, format=_PILLOW[format_], **options)
    except OSError as error:
        raise SaveError(f"Mado couldn't write {path.name}: {error.strerror or error}.") from error
    except (ValueError, KeyError) as error:
        raise SaveError(f"Mado couldn't save it as {format_}: {error}.") from error


def _flattened(image: Image.Image) -> Image.Image:
    """A picture for JPEG, which has no see-through parts: those go white, as a page is, rather
    than whatever colour was hidden in them."""
    if "A" not in image.getbands() and "transparency" not in image.info:
        return image.convert("RGB")
    seen = image.convert("RGBA")
    white = Image.new("RGBA", seen.size, (255, 255, 255, 255))
    return Image.alpha_composite(white, seen).convert("RGB")


def check(path: Path, size: tuple[int, int]) -> None:
    """The picture as written opens whole and is the size it should be: checked before it's
    kept. Raises SaveError."""
    try:
        with Image.open(path) as written:
            written.load()
            found = written.size
    except (OSError, SyntaxError, ValueError) as error:
        raise SaveError(
            f"The picture didn't come out whole ({error}), so Mado didn't keep it."
        ) from error
    if found != size:
        raise SaveError(
            f"The picture came out {found[0]} × {found[1]}, not {size[0]} × {size[1]}, so Mado "
            "didn't keep it."
        )
