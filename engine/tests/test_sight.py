"""What Mado sees in a picture, kept for the previews that follow: asked for twice at once (the
Looks tab's picture with its look and without, together), the work is done once."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from mado import making
from mado.core.framing import Box
from mado.directml import Tensor
from mado.extend import Filler
from mado.making import Picture, Sight
from tests.drawn import draw


def _picture(tmp_path: Path) -> Picture:
    return Picture(draw(tmp_path / "Tide.jpg", size=(160, 120)), "picture", "JPEG", None)


def test_the_picture_decoded_once_however_many_ask_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    picture = _picture(tmp_path)
    decoded: list[Path] = []
    real = making.decode

    def slow(path: Path, kind: Any, **options: Any) -> Image.Image:
        decoded.append(path)
        time.sleep(0.2)
        return real(path, kind, **options)

    monkeypatch.setattr(making, "decode", slow)
    sight = Sight(lambda: None)

    with ThreadPoolExecutor(2) as pool:
        asks = [pool.submit(sight.picture, picture, "v1") for _ in range(2)]
        images = [ask.result() for ask in asks]

    assert images[0] is images[1]
    assert decoded == [picture.path]


def test_a_picture_made_small_for_a_preview_is_made_once_and_kept(tmp_path: Path):
    sight = Sight(lambda: None)
    made: list[int] = []

    def make() -> Image.Image:
        made.append(1)
        time.sleep(0.2)
        return Image.new("RGB", (40, 30))

    with ThreadPoolExecutor(2) as pool:
        asks = [pool.submit(sight.fitted, ("Tide", "v1", 40), make) for _ in range(2)]
        images = [ask.result() for ask in asks]

    assert images[0] is images[1]
    assert made == [1]
    assert sight.fitted(("Tide", "v1", 40), make) is images[0]  # kept for the next look


def test_the_new_edges_are_drawn_once_however_many_ask_at_once(tmp_path: Path):
    picture = _picture(tmp_path)
    sight = Sight(lambda: None)
    drawn: list[int] = []

    def filler() -> Filler:
        drawn.append(1)
        time.sleep(0.2)
        return _nothing_new

    canvas = Box(-20.0, 0.0, 200.0, 120.0)
    with ThreadPoolExecutor(2) as pool:
        asks = [pool.submit(sight.extended, picture, "v1", canvas, filler) for _ in range(2)]
        results = [ask.result() for ask in asks]

    assert results[0] is results[1]
    assert drawn == [1]
    assert isinstance(results[0][0], np.ndarray)


def _nothing_new(pixels: Tensor, _mask: Tensor) -> Tensor:
    """A stand-in for LaMa that draws nothing new: what's there stays."""
    return pixels
