"""The depth model as the tests have it: Depth Anything V2 Small is a download that CI never has,
so this stands in for it through the same sessions Mado makes (mado/directml.py). It reads the
picture it's given as a made-up scene's depth would be: nearer further down (a ground seen from a
little above it) and red things nearest (the scenes' ball), with nothing far in a picture of no
colour at all (a scan of a page, a grey picture: flat)."""

from collections import Counter
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from mado.ai import DEPTH, DEPTH_FILE, Ai
from mado.directml import Array, Place, Session, Sessions

type Floats = npt.NDArray[np.float32]

_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


class FakeDepth:
    """A stand-in session: the scene's nearness, as the model's own numbers (bigger, nearer)."""

    def __init__(self, runs: Counter[str]) -> None:
        self._runs = runs

    def run(self, feed: Mapping[str, Array], /) -> list[Array]:
        self._runs["depth"] += 1
        pixels = np.asarray(feed["pixel_values"], np.float32)
        assert pixels.shape == (1, 3, 518, 518), "a size the real model's session wasn't made for"
        rgb = np.clip(pixels[0].transpose(1, 2, 0) * _STD + _MEAN, 0, 1)
        colourful = float(np.clip((rgb.max(axis=-1) - rgb.min(axis=-1)).mean() * 6, 0, 1))
        rows = np.linspace(0, 1, 518, dtype=np.float32)[:, None] * np.ones((1, 518), np.float32)
        red = (rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2]) > 0.25).astype(np.float32)
        raw = 3.0 + colourful * (4.0 * rows - 3.0 + 2.0 * red)
        return [raw[None].astype(np.float32)]

    def meta(self) -> Mapping[str, str]:
        return {}


class DepthModel:
    """The stand-in, as if downloaded, and how often it ran."""

    def __init__(self) -> None:
        self.runs: Counter[str] = Counter()


def with_depth_model(monkeypatch: pytest.MonkeyPatch, ai: Ai, folder: Path) -> DepthModel:
    """`ai` with the stand-in depth model, as if downloaded (its file in `folder`), run through
    Mado's own sessions."""
    fake = DepthModel()
    real_file = ai.edit_file
    real_get = Sessions.get

    def edit_file(download: str, name: str) -> Path | None:
        if download == DEPTH:
            made = folder / DEPTH / DEPTH_FILE
            made.parent.mkdir(parents=True, exist_ok=True)
            made.touch()
            return made
        return real_file(download, name)

    def get(
        self: Sessions,
        model: Path,
        size: int | None,
        place: Place,
        *,
        fixed: Mapping[str, int] | None = None,
        settings: Mapping[str, str] | None = None,
        threads: int | None = None,
    ) -> Session:
        if model.name == DEPTH_FILE:
            return FakeDepth(fake.runs)
        return real_get(self, model, size, place, fixed=fixed, settings=settings, threads=threads)

    monkeypatch.setattr(ai, "edit_file", edit_file)
    monkeypatch.setattr(Sessions, "get", get)
    return fake
