"""Restoring's models as the tests have them: the scratch detector and DDColor are downloads CI
never has, so these stand in for them through the same sessions Mado makes (mado/directml.py). The
stand-in detector is sure of a pixel much brighter or darker than what's round it (a thin line, a
speck), never of a smooth sky; the stand-in DDColor says the top of a picture is sky blue and the
rest grass green, whatever it shows. LaMa's stand-in paints a hole the mean colour of the square
round it (tests/edit_models.py)."""

from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np
import pytest

from mado.ai import COLOURER, COLOURER_FILE, DETECTOR, DETECTOR_FILE, Ai, Fill, Timer
from mado.core.masks import box
from mado.directml import Array, Place, Session, Sessions
from tests.edit_models import fill_with_mean

SKY_AB = (-2.0, -32.0)  # what the stand-in DDColor says the top half is: Lab's a and b
GRASS_AB = (-30.0, 30.0)  # and the rest


class FakeDetector:
    def __init__(self, runs: Counter[str], shapes: list[tuple[int, ...]]) -> None:
        self._runs = runs
        self._shapes = shapes

    def run(self, feed: Mapping[str, Array], /) -> list[Array]:
        self._runs[DETECTOR] += 1
        canvas = np.asarray(feed["input"], np.float32)
        self._shapes.append(canvas.shape)
        grey = canvas[0, 0]
        apart = np.abs(grey - box(grey, 2))
        sure = np.clip((apart - 0.15) * 4, 0, 1)
        return [sure[None, None].astype(np.float32)]

    def meta(self) -> Mapping[str, str]:
        return {}


class FakeColourer:
    def __init__(self, runs: Counter[str]) -> None:
        self._runs = runs

    def run(self, feed: Mapping[str, Array], /) -> list[Array]:
        self._runs[COLOURER] += 1
        grey = np.asarray(feed["input"], np.float32)
        assert grey.shape == (1, 3, 512, 512), "the real one takes only its square"
        ab = np.empty((1, 2, 512, 512), np.float32)
        ab[0, 0, :256], ab[0, 1, :256] = SKY_AB
        ab[0, 0, 256:], ab[0, 1, 256:] = GRASS_AB
        return [ab]

    def meta(self) -> Mapping[str, str]:
        return {}


class RestoreModels:
    """The stand-ins, as if downloaded: how often each ran, and the canvases the detector saw."""

    def __init__(self) -> None:
        self.runs: Counter[str] = Counter()
        self.canvases: list[tuple[int, ...]] = []
        self.fills = 0


def with_restore_models(monkeypatch: pytest.MonkeyPatch, ai: Ai, folder: Path) -> RestoreModels:
    """`ai` with the stand-ins for restoring's models, as if downloaded (their files in
    `folder`), the detector and DDColor run through Mado's own sessions."""
    fake = RestoreModels()
    files = {DETECTOR: DETECTOR_FILE, COLOURER: COLOURER_FILE}

    def restore_file(download: str, name: str) -> Path | None:
        made = folder / download / name
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
        threads: int | None = None,
        data: Callable[[], bytes] | None = None,
        processor_settings: Mapping[str, str] | None = None,
        half: bool = False,
    ) -> Session:
        if model.name == files[DETECTOR]:
            return FakeDetector(fake.runs, fake.canvases)
        if model.name == files[COLOURER]:
            return FakeColourer(fake.runs)
        return real(
            self,
            model,
            size,
            place,
            fixed=fixed,
            settings=settings,
            threads=threads,
            data=data,
            processor_settings=processor_settings,
            half=half,
        )

    def eraser(_quality: str, timer: Timer | None = None) -> tuple[Fill, str]:
        def fill(picture: np.ndarray, hole: np.ndarray) -> np.ndarray:
            fake.fills += 1
            return fill_with_mean(picture, hole)

        return fill, "processor"

    lama = folder / "lama" / "lama_fp32_dml.onnx"
    lama.parent.mkdir(parents=True, exist_ok=True)
    lama.touch()
    monkeypatch.setattr(ai, "restore_file", restore_file)
    monkeypatch.setattr(ai, "eraser", eraser)
    monkeypatch.setattr(ai, "lama_file", lambda: lama)
    monkeypatch.setattr(Sessions, "get", get)
    return fake
