"""Search's readers as the tests have them: SigLIP and PP-OCRv6 are downloads CI never has, and
Windows' own reader reads only the languages the PC has, so these stand in for them.

The stand-in SigLIP reads a picture as its colour: a picture's vector points the way of its mean
colour, and a search for a colour's name ("red") points where pictures of that colour do, so it
finds them; any other search points nowhere a picture does, so it finds nothing. The stand-in
readers of words read what `words` says each colour of picture shows (a picture's colour, as the
tests draw flat ones), and look first by the same.
"""

from collections.abc import Mapping

import numpy as np
from PIL import Image

from mado.core.hardware import Place
from mado.core.search import DIMENSIONS, unit
from mado.ocr import Read
from mado.search import Vector

COLOURS: dict[str, tuple[int, int, int]] = {
    "red": (220, 30, 30),
    "green": (30, 160, 60),
    "blue": (30, 60, 220),
    "yellow": (230, 210, 40),
    "grey": (128, 128, 128),
}


def colour_of(picture: Image.Image) -> tuple[int, int, int]:
    """A picture's mean colour, as whole numbers."""
    mean = np.asarray(picture.convert("RGB"), np.float32).reshape(-1, 3).mean(axis=0)
    red, green, blue = (round(float(each)) for each in mean)
    return red, green, blue


def vector_of(rgb: tuple[int, int, int]) -> Vector:
    """Where a colour points: its red, green and blue about their middle, and a little in common."""
    values = np.zeros(DIMENSIONS, np.float32)
    values[:3] = np.asarray(rgb, np.float32) / 255.0 - 0.5
    values[3] = 0.05
    return unit(values)[0]


def nearest_name(rgb: tuple[int, int, int]) -> str:
    return min(
        COLOURS,
        key=lambda name: sum((a - b) ** 2 for a, b in zip(COLOURS[name], rgb, strict=True)),
    )


class FakeSiglip:
    def __init__(self, ready: bool = True) -> None:
        self.is_ready = ready
        self.pictures = 0  # pictures read
        self.searches: list[str] = []
        self.fetched = 0  # times its download was asked for

    def ready(self) -> bool:
        return self.is_ready

    def fetch(self) -> None:
        self.fetched += 1

    def picture(self, image: Image.Image, *, threads: int | None = 2) -> Vector:
        self.pictures += 1
        return vector_of(colour_of(image))

    def search(self, words: str) -> Vector:
        self.searches.append(words)
        named = words.strip().lower()
        if named in COLOURS:
            return vector_of(COLOURS[named])
        elsewhere = np.zeros(DIMENSIONS, np.float32)
        elsewhere[400] = 1.0  # nothing any picture is
        return elsewhere


class FakeWords:
    """A reader of words: Best's or Fast's (languages, Windows' own)."""

    def __init__(
        self,
        words: Mapping[str, str],
        *,
        languages: tuple[str, ...] = ("en-GB",),
        place: Place = "processor",
        ready: bool = True,
    ) -> None:
        self.words = dict(words)  # colour's name → what such a picture shows
        self._languages = list(languages)
        self._place: Place = place
        self.is_ready = ready
        self.read_pictures = 0
        self.glanced = 0
        self.fetched = 0

    def ready(self) -> bool:
        return self.is_ready

    def fetch(self) -> None:
        self.fetched += 1

    def languages(self) -> list[str]:
        return self._languages

    def place(self) -> Place:
        return self._place

    def glance(self, thumbnail: Image.Image) -> bool:
        self.glanced += 1
        return nearest_name(colour_of(thumbnail)) in self.words

    def read(self, picture: Image.Image) -> Read:
        self.read_pictures += 1
        text = self.words.get(nearest_name(colour_of(picture)), "")
        return Read(text, len(text.splitlines()) if text else 0, "en-GB")


def flat(colour: str, size: tuple[int, int] = (96, 72)) -> Image.Image:
    """A made-up picture of one colour."""
    return Image.new("RGB", size, COLOURS[colour])
