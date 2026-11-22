"""Mado's AI models, ready to run: where each one's file is (shipped in Mado's assets, or a
download once it's fetched), where it runs on this PC (the graphics card, or the processor where
the card can't run them) and at which tile size, each through its kept session
(mado/directml.py). Every run is timed, so each picture made teaches Mado this PC's speeds.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mado.core.hardware import overlap_for, tile_for
from mado.core.models import BEST_PHOTO, Model, Quality
from mado.directml import LOCK, ModelError, Sessions, Tensor
from mado.extend import SIZE as LAMA_SIZE
from mado.extend import Filler
from mado.hardware import Here
from mado.tools import Tools
from mado.upscale import Tiling

ASSETS = Path(__file__).parent / "assets"
LAMA = "lama"  # the download that extends edges (downloads.json)
LAMA_FILE = "lama_fp32_dml.onnx"


@dataclass
class Timer:
    """How long a model spent, and on how many megapixels of tiles."""

    seconds: float = 0.0
    megapixels: float = 0.0

    def add(self, seconds: float, megapixels: float) -> None:
        self.seconds += seconds
        self.megapixels += megapixels

    @property
    def per_megapixel(self) -> float | None:
        return self.seconds / self.megapixels if self.megapixels > 0 else None


class Ai:
    def __init__(self, sessions: Sessions, tools: Tools, where: Callable[[], Here]) -> None:
        self._sessions = sessions
        self._tools = tools
        self._where = where

    def where(self) -> Here:
        return self._where()

    def starts_on(self, here: Here | None = None) -> dict[Literal["photo", "drawing"], Quality]:
        """Which of Fast and Best each kind of picture starts on here: as this PC suits, but a
        photo on Fast while Best's model isn't downloaded, as it's fetched only when asked for."""
        found = (here or self._where()).starts_on()
        if found["photo"] == "best" and self.file(BEST_PHOTO) is None:
            found["photo"] = "fast"
        return found

    def file(self, model: Model) -> Path | None:
        """Where a model's file is: in Mado's assets, or its download's folder once fetched."""
        if model.download is None:
            return ASSETS / model.file
        folder = self._tools.folder(model.download)
        return folder / model.file if folder is not None else None

    def lama_file(self) -> Path | None:
        folder = self._tools.folder(LAMA)
        return folder / LAMA_FILE if folder is not None else None

    def tiling(self, model: Model, timer: Timer | None = None) -> Tiling:
        """The model at the tile size it takes here, through its kept session. Raises ModelError
        when its file isn't there or it can't run where it should."""
        found = self.file(model)
        if found is None:
            raise ModelError(f"{model.name} isn't downloaded yet.")
        where = self._where()
        size = tile_for(model, where.place, where.card)
        session = self._sessions.get(found, size, where.place)
        clock = timer or Timer()

        def run(batch: Tensor) -> Tensor:
            with LOCK:  # timed once it has the card, not while it waits its turn
                began = time.perf_counter()
                out = session.run({"input": batch})[0]
                clock.add(time.perf_counter() - began, size * size / 1e6)
            return out

        return Tiling(run, size, overlap_for(size))

    def filler(self, timer: Timer | None = None) -> Filler:
        """LaMa, drawing a 512 square's missing part. Raises ModelError when it isn't
        downloaded or can't run."""
        found = self.lama_file()
        if found is None:
            raise ModelError("LaMa, which extends edges, isn't downloaded yet.")
        session = self._sessions.get(found, None, self._where().place)
        clock = timer or Timer()

        def fill(picture: Tensor, mask: Tensor) -> Tensor:
            with LOCK:
                began = time.perf_counter()
                out = session.run({"image": picture, "mask": mask})[0]
                clock.add(time.perf_counter() - began, LAMA_SIZE * LAMA_SIZE / 1e6)
            return out / 255.0  # LaMa gives 0 to 255

        return fill
