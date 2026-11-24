"""Running the painting styles' networks (mado/painting.py): where each paints, and at which
canvas. Sessions are recorded rather than made, so nothing runs on the graphics card."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from PIL import Image

from mado.config import DataPaths
from mado.core.painting import CANVAS, PAINTERS, SMALL_CANVAS, picture_style
from mado.directml import Sessions
from mado.hardware import Here
from mado.painting import Painter
from mado.tools import Tools
from tests.style_files import with_styles

type Array = np.ndarray


class _Session:
    """Paints nothing: gives the canvas back, as a network's answer is shaped."""

    def run(self, feeds: Mapping[str, Array]) -> list[Array]:
        canvas = feeds.get("input", feeds.get("content"))
        assert canvas is not None
        return [canvas]


class _Sessions:
    """Records each session asked for: the place and the sizes pinned."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, dict[str, int]]] = []

    def get(
        self,
        model: Path,
        size: int | None,
        place: str,
        *,
        fixed: Mapping[str, int] | None = None,
        settings: Mapping[str, str] | None = None,
        threads: int | None = None,
        data: Callable[[], bytes] | None = None,
        processor_settings: Mapping[str, str] | None = None,
    ) -> _Session:
        if data is not None:
            data()  # the painters' shared graph is made as it would be
        self.asked.append((place, dict(fixed or {})))
        return _Session()

    def has(self, model: Path, place: str) -> bool:
        return False


def _painter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sessions: _Sessions) -> Painter:
    with_styles(monkeypatch, tmp_path / "models")
    here = Here("card", None, {})
    tools = Tools(DataPaths(tmp_path / "data"))
    recorded = cast("Sessions", sessions)  # stands in for the engine's own
    return Painter(recorded, tools, lambda: here, room=lambda: 8 * 1024**3)


def _square(side: int) -> dict[str, int]:
    return {"batch": 1, "height": side, "width": side}


def test_a_small_copy_is_painted_on_the_processor_at_the_small_canvas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    sessions = _Sessions()
    painter = _painter(monkeypatch, tmp_path, sessions)
    picture = Image.new("RGB", (256, 192), (90, 120, 160))

    small = painter.paint(picture, PAINTERS[0], small=True)
    big = painter.paint(picture, PAINTERS[0])

    # Going through the styles never takes the card; a style chosen paints there when it has room.
    assert sessions.asked == [("processor", _square(SMALL_CANVAS)), ("card", _square(CANVAS))]
    assert small.size == (SMALL_CANVAS, SMALL_CANVAS * 192 // 256)
    assert big.size == (CANVAS, CANVAS * 192 // 256)


def test_a_small_copy_in_a_pictures_style_is_painted_on_the_processor_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    sessions = _Sessions()
    painter = _painter(monkeypatch, tmp_path, sessions)
    style = picture_style("Night market", np.zeros(512, np.float32))

    painter.paint(Image.new("RGB", (192, 256), (200, 90, 60)), style, small=True)

    assert sessions.asked == [("processor", _square(SMALL_CANVAS))]
