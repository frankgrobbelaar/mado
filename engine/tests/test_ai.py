"""The AI models ready to run: where each one's file is, which way each kind starts on, where the
editing models run, and sessions handed out without waiting for the card, so a click never does."""

import threading
import time
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from mado.ai import ASSETS, BIREFNET, MIGAN, SAM, Ai, Timer
from mado.config import DataPaths
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST
from mado.core.recipe import Recipe, Sizing
from mado.core.sizes import resolve
from mado.directml import LOCK, Array, ModelError, Sessions, Tensor
from mado.extend import Filler
from mado.hardware import Here
from mado.making import Picture, make, planned, see
from mado.tools import Tools
from mado.upscale import Tiling
from tests.conftest import ON_PROCESSOR
from tests.drawn import photo_like
from tests.test_upscale import repeated

ON_CARD = Here("card", None, {})
GIB = 1024**3


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
        Recipe(Sizing(size=resolve("other-256x144", []), shape="extend")),
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


class _Answering:
    """A session that answers at once, as SAM's parts would (its scores, masks and a third)."""

    def run(self, _feed: object, /) -> list[Array]:
        return [
            np.zeros((1, 1, 3), np.float32),
            np.zeros((1, 1, 3, 256, 256), np.float32),
            np.zeros(1, np.float32),
        ]


def test_sessions_on_the_processor_are_made_and_handed_out_while_the_card_is_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    made: list[str] = []

    def making(_model: Path, _size: object, place: str, *_rest: object) -> _Answering:
        made.append(place)
        return _Answering()

    monkeypatch.setattr("mado.directml._make", making)
    sessions = Sessions()
    picker = tmp_path / "picker.onnx"
    sessions.get(picker, None, "processor")
    took: list[float] = []

    def click() -> None:
        began = time.perf_counter()
        sessions.get(picker, None, "processor")  # kept
        sessions.has(picker, "processor")
        sessions.get(tmp_path / "u2netp.onnx", None, "processor")  # made now
        took.append(time.perf_counter() - began)

    clicking = threading.Thread(target=click)
    card = threading.Thread(target=sessions.get, args=(tmp_path / "reader.onnx", None, "card"))
    with LOCK:  # the queue's picture has the card
        clicking.start()
        card.start()
        clicking.join(timeout=5)
        time.sleep(0.1)
        while_busy = list(made)
    card.join(timeout=5)

    assert len(took) == 1
    assert took[0] < 1  # never waited for the card
    assert while_busy == ["processor", "processor"]  # one on the card waits its turn to be made
    assert made == ["processor", "processor", "card"]


def test_a_click_never_waits_for_the_card_while_the_queue_has_it(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def making(*_args: object) -> _Answering:
        return _Answering()

    def downloaded(_download: str, name: str) -> Path:
        return tmp_path / name

    monkeypatch.setattr("mado.directml._make", making)
    ai = Ai(Sessions(), Tools(paths), lambda: ON_CARD, room=lambda: 8 * GIB)
    monkeypatch.setattr(ai, "edit_file", downloaded)
    points = np.zeros((1, 1, 1, 2), np.float32)
    labels = np.ones((1, 1, 1), np.int64)
    read = ai.selector().read(np.zeros((1, 3, 1024, 1024), np.float32))  # its sessions made
    ai.selector().pick(read, points, labels)
    took: list[float] = []

    def click() -> None:
        began = time.perf_counter()
        ai.selector().pick(read, points, labels)
        took.append(time.perf_counter() - began)

    clicking = threading.Thread(target=click)
    with LOCK:  # the queue's picture has the card
        clicking.start()
        clicking.join(timeout=5)

    assert len(took) == 1
    assert took[0] < 1


def test_an_editing_model_goes_on_the_card_only_when_it_has_room_for_what_it_keeps(
    paths: DataPaths,
):
    def ai(room: int | None, here: Here = ON_CARD) -> Ai:
        return Ai(Sessions(), Tools(paths), lambda: here, room=lambda: room)

    assert ai(8 * GIB).edit_place(SAM) == "card"
    assert ai(1 * GIB).edit_place(SAM) == "processor"  # it keeps 1.2 GB there
    assert ai(8 * GIB).edit_place(BIREFNET) == "processor"  # it commits about 10 GB
    assert ai(16 * GIB).edit_place(BIREFNET) == "card"
    assert ai(16 * GIB, ON_PROCESSOR).edit_place(SAM) == "processor"
    # Where DirectX can't say: the card for what a small one holds, never for BiRefNet.
    assert ai(None).edit_place(SAM) == "card"
    assert ai(None).edit_place(MIGAN) == "card"
    assert ai(None).edit_place(BIREFNET) == "processor"
