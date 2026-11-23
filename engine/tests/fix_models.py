"""The fixes' models as the tests have them: SCUNet, FBCNN and NAFNet are downloads that CI never
has, so these stand in for them through the same sessions Mado makes (mado/directml.py): SCUNet
smooths each pixel with its neighbours, FBCNN smooths more the smaller it's told the JPEG was
saved, and NAFNet sharpens, inventing a bright speck in the middle of every tile as the real one
invents colour in a flat place, which the guard must hold back."""

from collections import Counter
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

from mado.ai import Ai
from mado.core.fixes import FBCNN, FIX_MODELS, NAFNET, SCUNET, FixModel
from mado.directml import Array, Place, Session, Sessions

type Floats = np.ndarray


def _smoothed(values: Floats, reach: int) -> Floats:
    """Each pixel the mean of its square `reach` out each way (the edges repeated)."""
    padded = np.pad(values, ((0, 0), (0, 0), (reach, reach), (reach, reach)), mode="edge")
    total = np.zeros_like(values)
    height, width = values.shape[2:]
    for dy in range(2 * reach + 1):
        for dx in range(2 * reach + 1):
            total += padded[:, :, dy : dy + height, dx : dx + width]
    return (total / (2 * reach + 1) ** 2).astype(np.float32)


class FakeFix:
    """A stand-in model's session: what it does to a tile, and how often it ran."""

    def __init__(self, model: FixModel, runs: Counter[str]) -> None:
        self._model = model
        self._runs = runs

    def run(self, feed: Mapping[str, Array], /) -> list[Array]:
        self._runs[self._model.id] += 1
        tile = np.asarray(feed["input"], np.float32)
        assert tile.shape[2] % self._model.multiple == 0, "a tile the real model refuses"
        if self._model is SCUNET:
            return [_smoothed(tile, 1)]
        if self._model is FBCNN:
            told = float(np.asarray(feed["qf_override"]).ravel()[0])
            return [_smoothed(tile, 2 if told >= 0.5 else 1)]
        sharpened = tile + 0.5 * (tile - _smoothed(tile, 1))
        middle = tile.shape[2] // 2
        sharpened[:, :, middle, middle] += 0.5  # what the real one invents in a flat place
        return [np.clip(sharpened, 0, 1).astype(np.float32)]

    def meta(self) -> Mapping[str, str]:
        return {}


class FixModels:
    """The stand-ins, as if downloaded, and how often each ran."""

    def __init__(self) -> None:
        self.runs: Counter[str] = Counter()


def with_fix_models(monkeypatch: pytest.MonkeyPatch, ai: Ai, folder: Path) -> FixModels:
    """`ai` with the stand-ins for the fixes' models, as if downloaded (their files in
    `folder`), run through Mado's own sessions and tiles."""
    fake = FixModels()
    by_file = {model.file: model for model in FIX_MODELS.values()}

    def fix_file(model: FixModel) -> Path | None:
        made = folder / model.id / model.file
        made.parent.mkdir(parents=True, exist_ok=True)
        made.touch()
        return made

    real = Sessions.get

    def get(
        self: Sessions,
        model: Path,
        size: int | None,
        place: Place,
        *,
        fixed: Mapping[str, int] | None = None,
        settings: Mapping[str, str] | None = None,
    ) -> Session:
        found = by_file.get(model.name)
        if found is not None:
            return FakeFix(found, fake.runs)
        return real(self, model, size, place, fixed=fixed, settings=settings)

    monkeypatch.setattr(ai, "fix_file", fix_file)
    monkeypatch.setattr(Sessions, "get", get)
    return fake


__all__ = ["FBCNN", "NAFNET", "SCUNET", "FixModels", "with_fix_models"]
