"""Made-up camera RAW files for the tests: DNGs written tag by tag from scenes drawn by code, never
a real photo. Each has a Bayer mosaic (RGGB, 14 bits; or, as some phones and monochrome cameras
write, linear pixels with every colour in each) under the tags a camera writes (its maker and
model, made up too; when it was taken; which way up; its white balance as shot; its colours; a
crop), and, when a test asks, the previews a camera embeds: a JPEG and a small thumbnail.

A DNG is a TIFF: IFD0 is the small thumbnail with the camera's tags, and the raw picture and the
JPEG preview are IFDs below it (SubIFDs). Without previews, IFD0 is the raw picture itself, as
many phones write it.
"""

import struct
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

# The made-up sensor sees red at half and blue at 0.7 of green's strength, so a grey only comes
# out grey with the camera's white balance (AsShotNeutral) applied.
NEUTRAL = (0.5, 1.0, 0.7)
BLACK, WHITE = 256, 16383
HEADROOM = 0.8  # the scene's white sits this far up the sensor's range, as a camera exposes it
# XYZ to linear sRGB (D65): the made-up sensor's own colours are sRGB's, scaled as NEUTRAL says.
XYZ_TO_SRGB = (
    (3.2404542, -1.5371385, -0.4985314),
    (-0.9692660, 1.8760108, 0.0415560),
    (0.0556434, -0.2040259, 1.0572252),
)
_TURNED = {  # what a picture is stored as, for an orientation to show it upright
    3: Image.Transpose.ROTATE_180,
    6: Image.Transpose.ROTATE_90,
    8: Image.Transpose.ROTATE_270,
}
_BYTE, _ASCII, _SHORT, _LONG, _RATIONAL, _SRATIONAL = 1, 2, 3, 4, 5, 10


def dng(
    path: Path,
    image: Image.Image,
    *,
    make: str = "Lumen",
    model: str = "Lumen X100",
    taken: str | None = "2026:11:12 18:42:07",
    orientation: int = 1,
    preview: Image.Image | int | None = 0,
    thumbnail: bool = True,
    crop: tuple[int, int, int, int] | None = None,
    linear: bool = False,
    compression: int = 1,
    preview_cut: float | None = None,
) -> Path:
    """Writes `image` (upright, in sRGB) as a camera would have caught it: its pixels the sensor's,
    stored turned as `orientation` says, cropped by `crop` (left, top, width, height: the DNG's
    default crop) when shown. `preview` is the JPEG preview: 0 for one as big as the picture, a
    number for its longer side, a picture of its own, or None for none; `preview_cut` keeps only
    that share of it, as a damaged one. `linear` stores every colour in each pixel rather than a
    mosaic; `compression` is what the raw picture says it's packed as (its pixels are always
    written plainly: 8 says deflate, which only a reader with zlib unpacks)."""
    stored = image.convert("RGB")
    if orientation in _TURNED:
        stored = stored.transpose(_TURNED[orientation])
    width, height = stored.size
    width, height = width - width % 2, height - height % 2  # whole 2 x 2 cells of the mosaic
    stored = stored.crop((0, 0, width, height))
    raw = (linear_pixels(stored) if linear else mosaic(stored)).astype("<u2").tobytes()
    jpeg = _jpeg(stored, preview)
    if jpeg is not None and preview_cut is not None:
        jpeg = (jpeg[0][: int(len(jpeg[0]) * preview_cut)], jpeg[1])
    small: Image.Image | None = None
    if thumbnail or jpeg is not None:
        small = stored.copy()
        small.thumbnail((256, 256))
    pictures = {  # after the tags, as a camera writes them: a copy cut short loses pixels first
        "small": small.tobytes() if small is not None else b"",
        "preview": jpeg[0] if jpeg is not None else b"",
        "raw": raw,
    }

    def tags(at: dict[str, int]) -> dict[str, dict[int, tuple[int, int, bytes]]]:
        """Every IFD's tags, the pictures and the IFDs below placed `at`."""
        raw_tags: dict[int, tuple[int, int, bytes]] = {
            254: _longs(0),
            256: _longs(width),
            257: _longs(height),
            258: _shorts(16, 16, 16) if linear else _shorts(16),
            259: _shorts(compression),
            262: _shorts(34892 if linear else 32803),  # linear pixels, or a colour filter array
            273: _longs(at["raw"]),
            277: _shorts(3 if linear else 1),
            278: _longs(height),
            279: _longs(len(raw)),
            284: _shorts(1),
            50714: _longs(BLACK),
            50717: _longs(WHITE),
        }
        if not linear:
            raw_tags[33421] = _shorts(2, 2)
            raw_tags[33422] = _bytes(0, 1, 1, 2)  # red, green / green, blue
            raw_tags[50710] = _bytes(0, 1, 2)
            raw_tags[50711] = _shorts(1)
        if crop is not None:
            raw_tags[50719] = _longs(crop[0], crop[1])
            raw_tags[50720] = _longs(crop[2], crop[3])
        camera: dict[int, tuple[int, int, bytes]] = {
            271: _ascii(make),
            272: _ascii(model),
            274: _shorts(orientation),
            305: _ascii("Made-up firmware 1.0"),
            50706: _bytes(1, 4, 0, 0),
            50707: _bytes(1, 1, 0, 0),
            50708: _ascii(f"{make} {model}"),
            50721: _srationals(*(value for row in XYZ_TO_SRGB for value in row)),
            50728: _rationals(*NEUTRAL),
            50778: _shorts(21),  # D65
        }
        found: dict[str, dict[int, tuple[int, int, bytes]]] = {}
        if taken:
            found["exif"] = {36867: _ascii(taken)}
            camera[34665] = _longs(at["exif"])
        if small is None:  # IFD0 is the raw picture itself, as many phones write it
            found["top"] = {**raw_tags, **camera}
            return found
        below = [at["raw tags"]]
        if jpeg is not None:
            found["preview tags"] = {
                254: _longs(1),
                256: _longs(jpeg[1][0]),
                257: _longs(jpeg[1][1]),
                258: _shorts(8, 8, 8),
                259: _shorts(7),  # JPEG
                262: _shorts(6),  # YCbCr
                273: _longs(at["preview"]),
                277: _shorts(3),
                278: _longs(jpeg[1][1]),
                279: _longs(len(pictures["preview"])),
                284: _shorts(1),
            }
            below.append(at["preview tags"])
        found["raw tags"] = raw_tags
        found["top"] = {
            254: _longs(1),
            256: _longs(small.width),
            257: _longs(small.height),
            258: _shorts(8, 8, 8),
            259: _shorts(1),
            262: _shorts(2),
            273: _longs(at["small"]),
            277: _shorts(3),
            278: _longs(small.height),
            279: _longs(len(pictures["small"])),
            284: _shorts(1),
            330: _longs(*below),
            **camera,
        }
        return found

    names = ("top", "raw tags", "preview tags", "exif", "small", "preview", "raw")
    # Tags take the same room wherever they're placed: measured once, then placed for real.
    measured = {name: len(_ifd(each, 0)) for name, each in tags(dict.fromkeys(names, 0)).items()}
    sizes = {**measured, **{name: len(data) for name, data in pictures.items()}}
    at: dict[str, int] = {}
    end = 8
    for name in names:
        if name in sizes and (name in measured or sizes[name]):
            at[name] = end
            end += sizes[name] + sizes[name] % 2
    written = bytearray(b"II*\x00" + struct.pack("<I", at["top"]))
    placed = tags({**dict.fromkeys(names, 0), **at})
    for name in names:
        if name not in at:
            continue
        data = _ifd(placed[name], at[name]) if name in placed else pictures[name]
        written.extend(data + b"\x00" * (len(data) % 2))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(written))
    return path


GREY, RED, GREEN, BLUE = (128, 128, 128), (200, 40, 40), (40, 160, 60), (40, 70, 200)


def card(size: tuple[int, int] = (600, 400)) -> Image.Image:
    """A made-up test card: a mid-grey ground, a white square at its top left (which way up it
    is), and red, green and blue squares along its foot."""
    width, height = size
    pixels = np.empty((height, width, 3), np.uint8)
    pixels[:] = GREY
    side = min(width, height) // 4
    pixels[side // 2 : side // 2 + side, side // 2 : side // 2 + side] = (235, 235, 235)
    for at, colour in enumerate((RED, GREEN, BLUE)):
        left = width // 8 + at * width // 4
        pixels[height - side - side // 2 : height - side // 2, left : left + side] = colour
    return Image.fromarray(pixels)


def linear_pixels(image: Image.Image) -> np.ndarray:
    """The sensor's view of an sRGB picture with every colour in each pixel: linear light, each
    colour at its strength (NEUTRAL), up to HEADROOM of the range above black."""
    srgb = np.asarray(image)
    levels = np.arange(256) / 255
    linear = np.where(levels <= 0.04045, levels / 12.92, ((levels + 0.055) / 1.055) ** 2.4)
    raw = np.empty(srgb.shape, np.uint16)
    for colour in range(3):
        table = linear * NEUTRAL[colour] * HEADROOM * (WHITE - BLACK) + BLACK
        lookup = np.clip(np.round(table), 0, WHITE).astype(np.uint16)
        raw[:, :, colour] = lookup[srgb[:, :, colour]]
    return raw


def mosaic(image: Image.Image) -> np.ndarray:
    """The sensor's view of an sRGB picture: linear light, each colour at its strength (NEUTRAL),
    up to HEADROOM of the range above black, then one colour a pixel, red, green / green, blue."""
    srgb = np.asarray(image)
    levels = np.arange(256) / 255
    linear = np.where(levels <= 0.04045, levels / 12.92, ((levels + 0.055) / 1.055) ** 2.4)
    raw = np.empty(srgb.shape[:2], np.uint16)
    for row, column, colour in ((0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 2)):
        table = linear * NEUTRAL[colour] * HEADROOM * (WHITE - BLACK) + BLACK
        lookup = np.clip(np.round(table), 0, WHITE).astype(np.uint16)
        raw[row::2, column::2] = lookup[srgb[row::2, column::2, colour]]
    return raw


def alike(a: Image.Image, b: Image.Image) -> float:
    """How alike two pictures' shapes are, whatever their brightness and colours: 1 the same."""
    small = [np.asarray(each.convert("L").resize((60, 40)), np.float64).ravel() for each in (a, b)]
    return float(np.corrcoef(small[0], small[1])[0, 1])


def truncated(path: Path, keep: float = 0.4) -> Path:
    """A DNG only partly copied: its tags all there, its pixels cut short."""
    data = path.read_bytes()
    path.write_bytes(data[: int(len(data) * keep)])
    return path


def _jpeg(
    stored: Image.Image, preview: Image.Image | int | None
) -> tuple[bytes, tuple[int, int]] | None:
    if preview is None:
        return None
    if isinstance(preview, Image.Image):
        shown = preview.convert("RGB")
    else:
        shown = stored.copy()
        if preview:
            shown.thumbnail((preview, preview))
    out = BytesIO()
    shown.save(out, "JPEG", quality=90)
    return out.getvalue(), shown.size


def _ifd(tags: dict[int, tuple[int, int, bytes]], at: int) -> bytes:
    """An IFD to be written at `at`: its entries by tag, then the values too big to sit in one."""
    size = 2 + 12 * len(tags) + 4
    table = bytearray(struct.pack("<H", len(tags)))
    spill = bytearray()
    for number in sorted(tags):
        kind, count, data = tags[number]
        if len(data) <= 4:
            value = data.ljust(4, b"\x00")
        else:
            value = struct.pack("<I", at + size + len(spill))
            spill.extend(data)
            if len(spill) % 2:
                spill.append(0)
        table.extend(struct.pack("<HHI", number, kind, count) + value)
    table.extend(struct.pack("<I", 0))
    return bytes(table + spill)


def _shorts(*values: int) -> tuple[int, int, bytes]:
    return _SHORT, len(values), struct.pack(f"<{len(values)}H", *values)


def _longs(*values: int) -> tuple[int, int, bytes]:
    return _LONG, len(values), struct.pack(f"<{len(values)}I", *values)


def _bytes(*values: int) -> tuple[int, int, bytes]:
    return _BYTE, len(values), bytes(values)


def _ascii(text: str) -> tuple[int, int, bytes]:
    data = text.encode("ascii") + b"\x00"
    return _ASCII, len(data), data


def _rationals(*values: float) -> tuple[int, int, bytes]:
    pairs = [(round(value * 1_000_000), 1_000_000) for value in values]
    return _RATIONAL, len(values), b"".join(struct.pack("<II", *pair) for pair in pairs)


def _srationals(*values: float) -> tuple[int, int, bytes]:
    pairs = [(round(value * 1_000_000), 1_000_000) for value in values]
    return _SRATIONAL, len(values), b"".join(struct.pack("<ii", *pair) for pair in pairs)
