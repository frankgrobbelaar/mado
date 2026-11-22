"""Made-up pictures for the tests, drawn by Pillow: a sky over a hill, never a real photo. EXIF
is written the way a camera writes it, when a test asks for it."""

import os
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

MAKE, MODEL, ORIENTATION, EXIF_IFD, GPS_IFD = 0x010F, 0x0110, 0x0112, 0x8769, 0x8825
TAKEN = 0x9003  # DateTimeOriginal


def picture(size: tuple[int, int] = (64, 48), mode: str = "RGB") -> Image.Image:
    """A sky, a hill and a sun: enough to tell which way up it is (the sun is top left)."""
    width, height = size
    image = Image.new("RGB", size, (120, 170, 230))
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(0, height), (0, height * 2 // 3), (width, height // 2), (width, height)],
        fill=(40, 90, 50),
    )
    draw.ellipse([2, 2, 2 + width // 6, 2 + width // 6], fill=(250, 220, 120))
    return image.convert(mode) if mode != "RGB" else image


def exif(
    *,
    taken: str | None = None,
    make: str | None = None,
    model: str | None = None,
    orientation: int | None = None,
    where: bool = False,
) -> Image.Exif:
    found = Image.Exif()
    if make is not None:
        found[MAKE] = make
    if model is not None:
        found[MODEL] = model
    if orientation is not None:
        found[ORIENTATION] = orientation
    if taken is not None:
        found.get_ifd(EXIF_IFD)[TAKEN] = taken
    if where:
        gps = found.get_ifd(GPS_IFD)
        gps.update({1: "S", 2: (33.0, 55.0, 0.0), 3: "E", 4: (18.0, 25.0, 0.0)})
    return found


def draw(
    path: Path,
    *,
    size: tuple[int, int] = (64, 48),
    mode: str = "RGB",
    format: str | None = None,  # noqa: A002 - Pillow's own word for it
    described: Image.Exif | None = None,
    modified: datetime | None = None,
) -> Path:
    """Saves a made-up picture at `path`, in the format its extension says (or `format`), with
    `described` as its EXIF and `modified` as the file's time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = picture(size, mode)
    options: dict[str, object] = {}
    if described is not None:
        options["exif"] = described
    image.save(path, format=format, **options)
    if modified is not None:
        stamp = modified.timestamp()
        os.utime(path, (stamp, stamp))
    return path
