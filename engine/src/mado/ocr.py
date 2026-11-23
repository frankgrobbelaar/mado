"""Reading the words in a picture, for search (docs/stack/search.md).

- Best is PP-OCRv6 small, a detector and a recogniser (Apache-2.0, RapidOCR's ONNX conversion of
  PaddleOCR's models, a 31 MB download from Mado's `models-3`), run through ONNX Runtime with
  Mado's own NumPy port of their pre- and post-processing (mado/core/ocr.py): no OpenCV. It
  reads Latin letters with their accents, Greek, Chinese and Japanese, whatever languages
  Windows has. The detector looks first, on the thumbnail the scan made: only a picture where it
  finds text is read in full, as most photos show none.
- Fast is Windows' own reader (Windows.Media.Ocr, through pywinrt): nothing to download, but it
  reads only the languages Windows has its OCR for, and needs the picture at twice its size to
  read small print.
"""

import asyncio
import logging
import threading
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from mado.core import ocr
from mado.core.hardware import Place
from mado.directml import ModelError, Session, Sessions
from mado.tools import Tools

if TYPE_CHECKING:
    from winrt.windows.graphics.imaging import SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine, OcrResult

log = logging.getLogger(__name__)

PPOCR = "pp-ocrv6-small"  # the download (downloads.json)
DETECTOR = "det.onnx"
RECOGNISER = "rec.onnx"
# The canvas the detector reads a picture on, one session (kept for good on the card): a square,
# as one session for every shape holds a sixth of the card's memory less than one a shape.
CANVASES: tuple[tuple[int, int], ...] = ((1280, 1280),)
# The thumbnail's, for the first look: does the picture show any text at all?
GLANCES: tuple[tuple[int, int], ...] = ((512, 512),)
# The widths the recogniser reads a line at on the card, a line at a time (a session each); on
# the processor, any width, BATCH lines at a time.
WIDTHS = (320, 960, 2560)
LINES_ON_CARD = True  # the recogniser on the card too, when the detector is
SIDE = 2048  # a picture is read for its words at most this big on its longer side
BATCH = 6  # lines read at once on the processor
WINDOWS_SCALE = 2.0  # Windows' reader reads a picture at twice its size, or misses small print


@dataclass(frozen=True)
class Read:
    """What a reader read in a picture: its words, a line of text to a line, and with which
    Windows language (Fast)."""

    text: str
    lines: int
    language: str | None = None


class Best:
    """PP-OCRv6 small, once it's downloaded: on the card when it has room, else the processor."""

    def __init__(self, sessions: Sessions, tools: Tools, place: Callable[[], Place]) -> None:
        self._sessions = sessions
        self._tools = tools
        self._place = place
        self._characters: list[str] | None = None
        self._lock = threading.Lock()

    def folder(self) -> Path | None:
        try:
            return self._tools.folder(PPOCR)
        except KeyError:  # a list without it
            return None

    def ready(self) -> bool:
        return self.folder() is not None

    def fetch(self) -> None:
        """Starts fetching it, as what needs it asks by itself: not again after a download that
        didn't match the list."""
        with suppress(KeyError):
            self._tools.start(PPOCR, by_itself=True)

    def detector(self) -> Path | None:
        """The detector's file, once it's downloaded: where it runs goes by whether its session
        was made on the card already."""
        folder = self.folder()
        return folder / DETECTOR if folder is not None else None

    def place(self) -> Place:
        return self._place()

    def glance(self, thumbnail: Image.Image) -> bool:
        """Whether the detector finds any text in a picture's thumbnail: only then is it read in
        full."""
        return bool(self._lines(ocr.on_white(thumbnail), GLANCES, tallest=ocr.TALLEST))

    def read(self, picture: Image.Image) -> Read:
        """The words in a picture (no bigger than SIDE on its longer side), line by line, in
        reading order. Raises ModelError while it isn't downloaded, or when it can't run."""
        rgb = ocr.on_white(picture)
        found = self._lines(rgb, CANVASES)
        cuts = [cut for cut in (ocr.cut_out(rgb, line) for line in found) if cut is not None]
        if not cuts:
            return Read("", 0)
        words = self._recognised(cuts)
        text = ocr.text_of(words)
        return Read(text, len(text.splitlines()) if text else 0)

    def _lines(
        self,
        picture: Image.Image,
        canvases: Sequence[tuple[int, int]],
        *,
        tallest: float | None = None,
    ) -> list[ocr.Line]:
        folder = self._needed()
        canvas = ocr.placed(picture.width, picture.height, canvases)
        scaled = picture.resize(
            (
                max(1, min(canvas.width, round(picture.width * canvas.scale))),
                max(1, min(canvas.height, round(picture.height * canvas.scale))),
            ),
            Image.Resampling.BILINEAR,
        )
        sizes = {"DynamicDimension.0": 1, "DynamicDimension.1": canvas.height}
        sizes["DynamicDimension.2"] = canvas.width
        session = self._sessions.get(folder / DETECTOR, None, self._place(), fixed=sizes)
        found = session.run({"x": ocr.detector_input(np.asarray(scaled), canvas)})[0]
        return ocr.lines(found[0, 0], canvas, picture.width, picture.height, tallest=tallest)

    def _recognised(self, cuts: list[Image.Image]) -> list[ocr.Words]:
        """Each line's words. On the card a line at a time, at the width of WIDTHS that holds it
        (a session a width); on the processor BATCH at a time, as wide as the widest."""
        folder = self._needed()
        place = self._place() if LINES_ON_CARD else "processor"
        if place == "card":
            found: list[ocr.Words] = []
            for cut in cuts:
                width = ocr.line_width(cut, WIDTHS)
                sizes = {"DynamicDimension.0": 1, "DynamicDimension.1": width}
                session = self._sessions.get(folder / RECOGNISER, None, "card", fixed=sizes)
                answer = session.run({"x": ocr.recogniser_input([cut], width)})[0]
                found.extend(ocr.decoded(answer, self._alphabet(session)))
            return found
        session = self._sessions.get(folder / RECOGNISER, None, "processor")
        order = sorted(range(len(cuts)), key=lambda at: cuts[at].width / cuts[at].height)
        read: list[ocr.Words | None] = [None] * len(cuts)
        for start in range(0, len(order), BATCH):
            chosen = order[start : start + BATCH]
            batch = [cuts[at] for at in chosen]
            width = max(ocr.line_width(cut) for cut in batch)
            answer = session.run({"x": ocr.recogniser_input(batch, width)})[0]
            for at, words in zip(chosen, ocr.decoded(answer, self._alphabet(session)), strict=True):
                read[at] = words
        return [each for each in read if each is not None]

    def _alphabet(self, session: Session) -> list[str]:
        """The recogniser's characters, as its file lists them, a line each."""
        with self._lock:
            if self._characters is None:
                listed = session.meta().get("character")
                if not listed:
                    raise ModelError("The words reader's characters aren't in its file.")
                self._characters = listed.splitlines()
            return self._characters

    def _needed(self) -> Path:
        folder = self.folder()
        if folder is None:
            raise ModelError("PP-OCRv6, which reads words at Best, isn't downloaded yet.")
        return folder


class Fast:
    """Windows' own reader: the languages Windows has its OCR for, nothing downloaded."""

    def languages(self) -> list[str]:
        """The languages Windows can read words in here ("en-GB"); none off Windows."""
        try:
            from winrt.windows.media.ocr import OcrEngine
        except ImportError:
            return []
        try:
            return [each.language_tag for each in OcrEngine.available_recognizer_languages]
        except OSError:
            return []

    def ready(self) -> bool:
        return bool(self.languages())

    def read(self, picture: Image.Image) -> Read:
        """The words in a picture, read at twice its size (Windows' largest side at most), line by
        line. Raises ModelError where Windows has no OCR for the owner's languages."""
        from winrt.windows.graphics.imaging import (
            BitmapAlphaMode,
            BitmapPixelFormat,
            SoftwareBitmap,
        )
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import Buffer

        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:  # none for the owner's own languages: one Windows has
            for language in OcrEngine.available_recognizer_languages:
                engine = OcrEngine.try_create_from_language(language)
                if engine is not None:
                    break
        if engine is None:
            raise ModelError("Windows can't read words here: it has no OCR language.")
        largest = OcrEngine.max_image_dimension
        scale = min(WINDOWS_SCALE, largest / max(picture.width, picture.height))
        size = (max(1, int(picture.width * scale)), max(1, int(picture.height * scale)))
        opaque = ocr.on_white(picture).convert("RGBA")  # opaque: premultiplied, as it's told
        bgra = opaque.resize(size, Image.Resampling.LANCZOS).tobytes("raw", "BGRA")
        buffer = Buffer(len(bgra))
        buffer.length = len(bgra)
        memoryview(buffer)[:] = bgra
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            buffer, BitmapPixelFormat.BGRA8, size[0], size[1], BitmapAlphaMode.PREMULTIPLIED
        )
        result = asyncio.run(_recognised(engine, bitmap))
        texts = [" ".join(line.text.split()) for line in result.lines]
        kept = [each for each in texts if ocr.worth_keeping(each)]
        return Read("\n".join(kept), len(kept), engine.recognizer_language.language_tag)


async def _recognised(engine: OcrEngine, bitmap: SoftwareBitmap) -> OcrResult:
    return await engine.recognize_async(bitmap)
