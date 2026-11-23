"""The editing models as the tests have them: SAM 2.1, MI-GAN and LaMa are downloads that CI never
has, so these stand in for them. The stand-in SAM answers a click with the patch of like colour
round it (smallest: that patch less its edge; biggest: it grown), as SAM's numbers at 256 square;
the stand-in fill paints a hole with the mean of the square round it. U²-Net is shipped, so the
tests run the real one on the processor."""

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from mado.ai import Ai, Fill, Selector, Timer
from mado.directml import Array

type Floats = npt.NDArray[np.float32]
type Pixels = npt.NDArray[np.uint8]

_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)
_LIKE = 0.12  # colours this near the clicked one's, 0 to 1 each, are the same patch


class FakeSam:
    def __init__(self) -> None:
        self.reads = 0
        self.picks = 0

    def selector(self, timer: Timer | None = None) -> Selector:
        def read(pixels: Floats) -> tuple[Array, Array, Array]:
            self.reads += 1
            rgb = pixels[0].transpose(1, 2, 0) * _STD + _MEAN
            small = np.ascontiguousarray(rgb[::4, ::4], np.float32)  # 256 square
            return small, np.zeros(1, np.float32), np.zeros(1, np.float32)

        def pick(
            read: tuple[Array, Array, Array], points: Floats, labels: npt.NDArray[np.int64]
        ) -> tuple[Floats, Floats]:
            self.picks += 1
            colours: Floats = read[0]
            found = np.zeros((256, 256), bool)
            for (x, y), keep in zip(points[0, 0], labels[0, 0], strict=True):
                patch = _patch(colours, int(x / 4), int(y / 4))
                found = found | patch if keep else found & ~patch
            answers = np.stack([_shrunk(found), found, _grown(found)])
            logits = np.where(answers, 8.0, -8.0).astype(np.float32)
            return np.array([0.6, 0.95, 0.5], np.float32), logits

        return Selector(read, pick, "processor")


def _patch(colours: Floats, x: int, y: int) -> npt.NDArray[np.bool_]:
    x, y = min(max(x, 0), 255), min(max(y, 0), 255)
    like = np.abs(colours - colours[y, x]).max(axis=-1) <= _LIKE
    found = np.zeros_like(like)
    found[y, x] = True
    for _ in range(512):
        grown = _grown(found, 1) & like
        if (grown == found).all():
            break
        found = grown
    return found


def _grown(mask: npt.NDArray[np.bool_], by: int = 6) -> npt.NDArray[np.bool_]:
    found = mask.copy()
    for _ in range(by):
        step = found.copy()
        step[1:] |= found[:-1]
        step[:-1] |= found[1:]
        step[:, 1:] |= found[:, :-1]
        step[:, :-1] |= found[:, 1:]
        found = step
    return found


def _shrunk(mask: npt.NDArray[np.bool_], by: int = 3) -> npt.NDArray[np.bool_]:
    return ~_grown(~mask, by)


def fill_with_mean(picture: Pixels, hole: npt.NDArray[np.bool_]) -> Pixels:
    """The stand-in erase: the hole painted the mean colour of the square round it."""
    made = picture.copy()
    if (~hole).any():
        made[hole] = picture[~hole].mean(axis=0).astype(np.uint8)
    return made


def with_editing_models(monkeypatch: pytest.MonkeyPatch, ai: Ai, folder: Path) -> FakeSam:
    """`ai` with the stand-ins for the editing models it would download, as if downloaded
    (their files in `folder`)."""
    sam = FakeSam()
    monkeypatch.setattr(ai, "selector", sam.selector)

    def eraser(_quality: str, timer: Timer | None = None) -> tuple[Fill, str]:
        return fill_with_mean, "processor"

    real = ai.edit_file

    def edit_file(download: str, name: str) -> Path | None:
        if download == "u2netp":
            return real(download, name)
        made = folder / download / name
        made.parent.mkdir(parents=True, exist_ok=True)
        made.touch()
        return made

    lama = folder / "lama" / "lama_fp32_dml.onnx"
    lama.parent.mkdir(parents=True, exist_ok=True)
    lama.touch()
    monkeypatch.setattr(ai, "eraser", eraser)
    monkeypatch.setattr(ai, "edit_file", edit_file)
    monkeypatch.setattr(ai, "lama_file", lambda: lama)
    return sam


def part_at(x: float, y: float, choice: int | None = None) -> dict[str, Any]:
    """A part picked with one click, as the window sends it."""
    return {"clicks": [{"x": x, "y": y, "keep": True}], "choice": choice}
