"""What a picture is: a photo, a drawing, pixel art or a screenshot, guessed from made-up ones."""

import numpy as np
from PIL import Image

from mado.core.kind import Kind, colour_count, flatness, guess, repeats
from tests.drawn import cartoon, photo_like, screen_like, sprite


def _guess(
    image: Image.Image, name: str, *, camera: str | None = None, format_: str = "PNG"
) -> Kind:
    pixels = np.asarray(image.convert("RGB"))
    return guess(
        pixels, name=name, camera=camera, format_=format_, width=image.width, height=image.height
    )


def test_a_photo_with_a_camera_is_a_photo_whatever_it_looks_like():
    assert _guess(cartoon(), "IMG_2041.JPG", camera="Pixelworks PW-7 Pro") == "photo"


def test_a_grainy_picture_without_a_camera_is_still_taken_for_a_photo():
    assert _guess(photo_like(), "Harbour at dusk.jpg", format_="JPEG") == "photo"


def test_flat_colour_art_is_a_drawing():
    assert _guess(cartoon(), "Sunny hill.png") == "drawing"


def test_a_little_picture_of_few_colours_made_of_repeated_pixels_is_pixel_art():
    art = sprite(block=8, cells=16)

    assert repeats(np.asarray(art)) == 8
    assert _guess(art, "Hero.png") == "pixels"
    assert _guess(sprite(block=1, cells=48), "Tiny hero.png") == "pixels"


def test_a_screen_sized_flat_png_is_a_screenshot_and_so_is_one_named_so():
    assert _guess(screen_like((1920, 1080)), "Panel.png") == "screenshot"
    assert _guess(photo_like(), "Screenshot 2026-11-14 101500.png") == "screenshot"


def test_the_clues_are_measured_on_the_pixels():
    flat = np.zeros((10, 10, 3), np.uint8)
    grain = np.asarray(photo_like((40, 30)))

    assert flatness(flat) == 1.0
    assert flatness(grain) < 0.05
    assert colour_count(flat) == 1
    assert repeats(grain) == 1
