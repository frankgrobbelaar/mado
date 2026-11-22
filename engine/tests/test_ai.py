"""The AI models ready to run: where each one's file is, and which way each kind starts on."""

import threading
import time
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from mado.ai import ASSETS, Ai, Timer
from mado.config import DataPaths
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST
from mado.core.recipe import Recipe
from mado.core.sizes import resolve
from mado.directml import LOCK, ModelError, Sessions, Tensor
from mado.extend import Filler
from mado.hardware import Here
from mado.making import Picture, make, planned, see
from mado.tools import Tools
from mado.upscale import Tiling
from tests.drawn import photo_like
from tests.test_upscale import repeated

ON_CARD = Here("card", None, {})


def _ai(paths: DataPaths, here: Here = ON_CARD) -> Ai:
    return Ai(Sessions(), Tools(paths), lambda: here)


def test_the_shipped_models_are_in_mados_assets_and_best_for_photos_is_a_download(
    paths: DataPaths,
):
    ai = _ai(paths)

    assert ai.file(FAST) == ASSETS / FAST.file
    assert ai.file(BEST_DRAWING) == ASSETS / BEST_DRAWING.file
    assert (ASSETS / FAST.file).is_file()
    assert ai.file(BEST_PHOTO) is None  # not downloaded yet
    with pytest.raises(ModelError, match="isn't downloaded yet"):
        ai.tiling(BEST_PHOTO)


def test_a_photo_starts_on_fast_till_best_is_downloaded_as_its_fetched_only_when_asked_for(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ai = _ai(paths)

    assert ai.starts_on() == {"photo": "fast", "drawing": "best"}

    fetched = tmp_path / "x4plus"
    fetched.mkdir()
    (fetched / BEST_PHOTO.file).write_bytes(b"model")
    monkeypatch.setenv("MADO_REALESRGAN_X4PLUS_DIR", str(fetched))
    assert ai.starts_on() == {"photo": "best", "drawing": "best"}


def test_on_the_processor_every_kind_starts_on_fast(paths: DataPaths):
    assert _ai(paths, Here("processor", None, {})).starts_on() == {
        "photo": "fast",
        "drawing": "fast",
    }


def test_a_model_is_timed_once_it_has_the_card_not_while_it_waits_its_turn(
    paths: DataPaths, monkeypatch: pytest.MonkeyPatch
):
    class Instant:
        def run(self, _feed: object, /) -> list[Tensor]:
            with LOCK:
                return [np.zeros((1, 3, 16, 16), np.float32)]

    def instant(*_args: object) -> Instant:
        return Instant()

    monkeypatch.setattr(Sessions, "get", instant)
    timer = Timer()
    tiling = _ai(paths).tiling(FAST, timer)
    holding = threading.Event()

    def preview_on_the_card() -> None:
        with LOCK:
            holding.set()
            time.sleep(0.3)

    other = threading.Thread(target=preview_on_the_card)
    other.start()
    holding.wait()
    tiling.run(np.zeros((1, 3, 4, 4), np.float32))
    other.join()

    assert timer.seconds < 0.1


def test_the_time_lama_takes_isnt_learned_as_the_upscalers():
    class Recording:
        def __init__(self) -> None:
            self.timers: dict[str, Timer | None] = {}

        def filler(self, timer: Timer | None = None) -> Filler:
            self.timers["lama"] = timer
            return lambda image, mask: np.where(mask > 0, np.float32(0.5), image).astype(np.float32)

        def tiling(self, _model: object, timer: Timer | None = None) -> Tiling:
            self.timers["upscaler"] = timer
            return Tiling(repeated, 64, 16)

    image = photo_like((96, 72))
    seen = see(image, Picture(Path("Tide.jpg"), "picture", "JPEG", None))
    made = planned(
        Recipe(size=resolve("other-256x144", []), shape="extend"),
        seen,
        {"photo": "fast", "drawing": "fast"},
    )
    recording, timer = Recording(), Timer()

    make(
        image,
        made,
        cast("Ai", recording),
        report=lambda _stage, _within: None,
        stop=lambda: False,
        timer=timer,
    )

    assert recording.timers == {"lama": None, "upscaler": timer}
