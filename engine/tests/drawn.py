"""Made-up pictures for the tests, drawn by Pillow: a sky over a hill, never a real photo. EXIF
is written the way a camera writes it, when a test asks for it."""

import os
from datetime import datetime
from pathlib import Path

import numpy as np
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


def photo_like(size: tuple[int, int] = (320, 240), seed: int = 1) -> Image.Image:
    """A made-up scene with a camera's grain: a sky fading down to a field, never two
    neighbouring pixels quite the same."""
    width, height = size
    rows = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    sky = np.array([110, 160, 225], np.float32)
    field = np.array([60, 110, 50], np.float32)
    scene = sky * (1 - rows) + field * rows + np.zeros((height, width, 3), np.float32)
    noise = np.random.default_rng(seed).normal(0, 6, (height, width, 3))
    return Image.fromarray(np.clip(scene + noise, 0, 255).astype(np.uint8))


def cartoon(size: tuple[int, int] = (320, 240)) -> Image.Image:
    """A made-up drawing in flat colours: a sun, a hill and a house."""
    width, height = size
    image = Image.new("RGB", size, (140, 200, 240))
    draw = ImageDraw.Draw(image)
    draw.ellipse([width // 12, height // 12, width // 4, height // 4], fill=(255, 210, 60))
    hill = [(0, height), (0, height * 3 // 5), (width, height // 2), (width, height)]
    draw.polygon(hill, fill=(90, 170, 80))
    draw.rectangle([width // 2, height // 3, width * 2 // 3, height // 2], fill=(200, 80, 60))
    return image


def sprite(block: int = 8, cells: int = 16) -> Image.Image:
    """Made-up pixel art: a little figure of four colours, `cells` pixels square, made `block`
    times bigger by repeating each pixel."""
    rng = np.random.default_rng(3)
    palette = np.array([[20, 20, 30], [240, 200, 160], [60, 120, 220], [250, 250, 250]], np.uint8)
    grid = palette[rng.integers(0, 4, (cells, cells))]
    return Image.fromarray(np.repeat(np.repeat(grid, block, axis=0), block, axis=1))


def screen_like(size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """A made-up screen: flat panels, a bar along the top and rows of little dark marks where
    words would be."""
    width, height = size
    image = Image.new("RGB", size, (243, 243, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, height // 18], fill=(40, 44, 52))
    draw.rectangle([0, height // 18, width // 6, height], fill=(225, 226, 230))
    for row in range(height // 8, height - 40, 36):
        for word in range(width // 5, width - 200, 90):
            draw.rectangle([word, row, word + 60, row + 12], fill=(30, 30, 30))
    return image


def spot(size: tuple[int, int] = (240, 160), at: tuple[float, float] = (0.8, 0.3)) -> Image.Image:
    """A flat grey ground with one busy patch at `at` (fractions across and down): a subject to
    find."""
    width, height = size
    pixels = np.full((height, width, 3), 128, np.uint8)
    cx, cy = int(at[0] * width), int(at[1] * height)
    half = min(width, height) // 10
    rng = np.random.default_rng(5)
    patch = rng.integers(0, 256, (2 * half, 2 * half, 3), dtype=np.uint8)
    pixels[cy - half : cy + half, cx - half : cx + half] = patch
    return Image.fromarray(pixels)


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
