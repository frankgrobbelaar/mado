"""Painting styles, run: Mado's painters through one session they share, a picture's own style
through MicroAST, each at the working size (mado/core/painting.py), on the graphics card when it
has room for them, else the processor; and the last few paintings kept for the previews.

Mado's four painters are one network trained four times. Each session on the card keeps about
2.2 GB of its memory for good (mado/directml.py never lets one go), so a session each wouldn't
fit a 6 GB card: one session, made from the first painter's file with its weights taken out as
inputs (mado/core/onnx_graph.py), runs every painter with its own weights, at the same speed.
MicroAST comes in two halves: one reads a style picture into 512 numbers, on the processor in
moments; the other paints with them. docs/stack/styles.md has what was measured.
"""

import threading
from collections import OrderedDict
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

import numpy as np
from PIL import Image

from mado import hardware
from mado.core.onnx_graph import Floats, GraphError, initializers, weights_as_inputs
from mado.core.painting import (
    CANVAS,
    CODE,
    SMALL_CANVAS,
    Style,
    off_canvas,
    on_canvas,
    working_size,
)
from mado.directml import LOCK, ModelError, Place, Sessions
from mado.hardware import Here
from mado.tools import Tools

MICROAST = "microast"  # the download that paints in a picture's style (downloads.json)
MICROAST_READER = "microast-style.onnx"
MICROAST_PAINTER = "microast-stylize.onnx"
_MIB = 1024 * 1024
# What each keeps of the card's own memory once it has run at the working size, measured on the
# owner's card (docs/stack/styles.md): made there only when the card has room for it.
PAINTERS_HELD = 2300 * _MIB
MICROAST_HELD = 1250 * _MIB
_SPARE = 512 * _MIB  # room left on the card besides
_UNKNOWN_ROOM = 4096 * _MIB  # where DirectX can't say: a small card's
_SHARED = Path("mado-painters.onnx")  # names the painters' shared session: it has no file
_IS_WEIGHT = "net."  # a painter's own weights; the rest (its fixed dither) stays in the graph
# On the processor, numbers too small to matter are taken as nought: the same painting, up to a
# fifth quicker (measured by the models agent, 2026-11-23).
_PROCESSOR = {"session.set_denormal_as_zero": "1"}
_READ_SIDE = 512  # a style picture is read this big on its long side
_READ_LEAST = 64  # and at least this big on its short side
_KEPT = 6  # paintings at the working size kept for the previews


class Painter:
    """The painting styles' networks, ready to run."""

    def __init__(
        self,
        sessions: Sessions,
        tools: Tools,
        where: Callable[[], Here],
        room: Callable[[], int | None] = hardware.room,
    ) -> None:
        self._sessions = sessions
        self._tools = tools
        self._where = where
        self._room = room
        self._lock = threading.Lock()
        self._weights: dict[str, dict[str, Floats]] = {}  # each painter's, by its download
        self._shapes: dict[str, tuple[int, ...]] | None = None  # the shared graph's weights
        self._graph: bytes | None = None
        self._kept: OrderedDict[tuple[object, ...], Image.Image] = OrderedDict()
        self._keeping = threading.Lock()

    def file(self, style: Style) -> Path | None:
        """A painter's network once it's downloaded (MicroAST's painting half, for a picture's
        style); None for a classic one, or one not downloaded yet."""
        if style.kind == "painter" and style.download is not None:
            folder = self._tools.folder(style.download)
            return folder / f"{style.download}.onnx" if folder is not None else None
        if style.kind == "picture":
            folder = self._tools.folder(MICROAST)
            return folder / MICROAST_PAINTER if folder is not None else None
        return None

    def needs(self, style: Style) -> str | None:
        """The download a style waits for, or None: a classic one needs none."""
        if style.kind == "classic" or self.file(style) is not None:
            return None
        return style.download if style.kind == "painter" else MICROAST

    def place(self, style: Style) -> Place:
        """Where a style paints now: the card once its session is there, or when the card has
        room for what it keeps (where DirectX can't say, as much as a small card has); else the
        processor, as a classic one always does. On a PC whose card can't run the models, the
        processor."""
        if style.kind == "classic" or self._where().place == "processor":
            return "processor"
        named = _SHARED if style.kind == "painter" else self.file(style)
        if named is not None and self._sessions.has(named, "card"):
            return "card"
        held = PAINTERS_HELD if style.kind == "painter" else MICROAST_HELD
        free = self._room()
        return (
            "card"
            if (free if free is not None else _UNKNOWN_ROOM) >= held + _SPARE
            else ("processor")
        )

    def read(self, picture: Image.Image) -> Floats:
        """A picture's style, as MicroAST reads it: 512 numbers, from a copy 512 pixels on its
        long side (64 at least on its short side, for a long panorama), on the processor (a few
        tens of milliseconds). Raises ModelError."""
        folder = self._tools.folder(MICROAST)
        if folder is None:
            raise ModelError("MicroAST, which reads a picture's style, isn't downloaded yet.")
        rgb = picture.convert("RGB")
        k = min(1.0, max(_READ_SIDE / max(rgb.size), _READ_LEAST / min(rgb.size)))
        size = (max(4, round(rgb.width * k / 4) * 4), max(4, round(rgb.height * k / 4) * 4))
        shown = np.asarray(rgb.resize(size, Image.Resampling.LANCZOS), np.float32) / 255
        session = self._sessions.get(folder / MICROAST_READER, None, "processor")
        code = session.run({"style": np.ascontiguousarray(shown.transpose(2, 0, 1)[None])})[0]
        return np.ascontiguousarray(code.reshape(CODE), dtype=np.float32)

    def paint(self, image: Image.Image, style: Style, *, small: bool = False) -> Image.Image:
        """A picture (RGB) painted in a painter's or a picture's style at its working size, as
        RGB; for a small copy (`small`), on the processor at `SMALL_CANVAS`, so going through
        the styles never takes the card's memory for one not chosen. Raises ModelError when the
        style's network isn't there or can't run."""
        side = SMALL_CANVAS if small else CANVAS
        size = working_size(*image.size, side=side)
        shown = image.convert("RGB").resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
        canvas, at = on_canvas(np.asarray(shown), side=side)
        place: Place = "processor" if small else self.place(style)
        if style.kind == "painter":
            run = self._painter(style, place, side)
        elif style.kind == "picture" and style.code is not None:
            run = self._picture(style, place, side)
        else:
            raise ModelError(f"{style.name} isn't painted by a network.")
        with LOCK if place == "card" else nullcontext():
            painted = run(canvas)
        return Image.fromarray(off_canvas(painted, at, size), "RGB")

    def kept(self, key: tuple[object, ...], make: Callable[[], Image.Image]) -> Image.Image:
        """A painting at the working size for a preview (`key` says which picture, as its edits
        and size step leave it, in which style), the last few kept: going back to a style, or
        moving its strength, takes moments."""
        with self._keeping:
            found = self._kept.get(key)
            if found is not None:
                self._kept.move_to_end(key)
                return found
        made = make()
        with self._keeping:
            self._kept[key] = made
            while len(self._kept) > _KEPT:
                self._kept.popitem(last=False)
        return made

    def _painter(self, style: Style, place: Place, side: int) -> Callable[[Floats], Floats]:
        found = self.file(style)
        if found is None or style.download is None:
            raise ModelError(f"{style.name}'s network isn't downloaded yet.")
        weights = self._weights_of(style.download, found)
        session = self._sessions.get(
            _SHARED,
            None,
            place,
            fixed=_pinned(side),
            data=lambda: self._shared(found),
            processor_settings=_PROCESSOR,
        )
        return lambda canvas: session.run({"input": canvas, **weights})[0]

    def _picture(self, style: Style, place: Place, side: int) -> Callable[[Floats], Floats]:
        found = self.file(style)
        if found is None or style.code is None:
            raise ModelError("MicroAST, which paints in a picture's style, isn't downloaded yet.")
        session = self._sessions.get(
            found, None, place, fixed=_pinned(side), processor_settings=_PROCESSOR
        )
        code = np.ascontiguousarray(style.code.reshape(1, CODE, 1, 1), dtype=np.float32)
        whole = np.array([1.0], np.float32)  # its own strength in full: Mado mixes afterwards
        return lambda canvas: session.run(
            {"content": canvas, "style_code": code, "strength": whole}
        )[0]

    def _shared(self, file: Path) -> bytes:
        """The painters' one graph, made from the first painter's file with its weights taken out
        as inputs."""
        with self._lock:
            if self._graph is None:
                try:
                    graph, weights = weights_as_inputs(file.read_bytes(), _starts_weight)
                except (OSError, GraphError) as error:
                    raise ModelError(f"Mado couldn't read the style's network ({error}).") from None
                self._graph = graph
                self._shapes = {name: values.shape for name, values in weights.items()}
            return self._graph

    def _weights_of(self, download: str, file: Path) -> dict[str, Floats]:
        """A painter's own weights, read once, checked against the graph they share."""
        with self._lock:
            found = self._weights.get(download)
        if found is None:
            try:
                found = initializers(file.read_bytes(), _starts_weight)
            except (OSError, GraphError) as error:
                raise ModelError(f"Mado couldn't read the style's network ({error}).") from None
            with self._lock:
                self._weights[download] = found
        self._shared(file)  # the graph first, so there are shapes to check against
        with self._lock:
            shapes = self._shapes or {}
        if {name: values.shape for name, values in found.items()} != shapes:
            raise ModelError(
                "That style's network doesn't fit the others: Mado can't paint with it."
            )
        return found


def _starts_weight(name: str) -> bool:
    return name.startswith(_IS_WEIGHT)


def _pinned(side: int) -> dict[str, int]:
    """The networks' free sizes pinned to a square canvas `side` pixels across."""
    return {"batch": 1, "height": side, "width": side}
