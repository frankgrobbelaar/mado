"""SigLIP base, which reads a picture, or a search, into 768 numbers: the closer two are, the more
the picture looks like what the search describes (docs/stack/search.md). Google's model
(Apache-2.0), as Xenova's int8 ONNX conversion, a download from Mado's `models-3`.

Its vision model reads a picture squeezed to 224 × 224; its text model reads a search as 64
tokens, from SigLIP's own tokenizer.json (read with Hugging Face's tokenizers package). Both run
on the processor: int8 runs no faster on a GTX 16 card than on six cores, and a session on the
card would keep over a gigabyte of its memory for good (mado/directml.py), memory the queue's
pictures need (measured: docs/stack/search.md).
"""

import threading
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado.core.search import DIMENSIONS, TOKENS, canonical, padded, picture_input, unit
from mado.directml import ModelError, Sessions
from mado.tools import Tools

if TYPE_CHECKING:
    from tokenizers import Tokenizer

SIGLIP = "siglip-base-patch16-224"  # the download (downloads.json)
VISION = "vision-int8.onnx"
TEXT = "text-int8.onnx"
TOKENIZER = "tokenizer.json"
READING_THREADS = 2  # of the processor's, for reading the library in the background
_VISION_SIZES = {"batch_size": 1, "num_channels": 3, "height": 224, "width": 224}
_TEXT_SIZES = {"batch_size": 1, "sequence_length": TOKENS}

type Vector = npt.NDArray[np.float32]  # 768 numbers, made one long


class Siglip:
    """SigLIP base, once it's downloaded: a picture's vector, and a search's."""

    def __init__(self, sessions: Sessions, tools: Tools) -> None:
        self._sessions = sessions
        self._tools = tools
        self._tokenizer: Tokenizer | None = None
        self._lock = threading.Lock()

    def folder(self) -> Path | None:
        """Where its files are, once they're downloaded."""
        try:
            return self._tools.folder(SIGLIP)
        except KeyError:  # a list without it
            return None

    def ready(self) -> bool:
        return self.folder() is not None

    def fetch(self) -> None:
        """Starts fetching it, as what needs it asks by itself: not again after a download that
        didn't match the list."""
        with suppress(KeyError):
            self._tools.start(SIGLIP, by_itself=True)

    def picture(self, image: Image.Image, *, threads: int | None = READING_THREADS) -> Vector:
        """A picture's 768 numbers, made one long, read on `threads` of the processor's. Raises
        ModelError while SigLIP isn't downloaded, or when it can't run."""
        folder = self._needed()
        session = self._sessions.get(
            folder / VISION, None, "processor", fixed=_VISION_SIZES, threads=threads
        )
        found = session.run({"pixel_values": picture_input(image)})[1]  # pooler_output
        return _one(found)

    def search(self, words: str) -> Vector:
        """A search's 768 numbers, made one long, read on the processor at once (in moments).
        Raises ModelError while SigLIP isn't downloaded, or when it can't run."""
        folder = self._needed()
        ids = np.array([padded(self._tokens(folder, canonical(words)))], np.int64)
        session = self._sessions.get(folder / TEXT, None, "processor", fixed=_TEXT_SIZES)
        return _one(session.run({"input_ids": ids})[1])  # pooler_output

    def _needed(self) -> Path:
        folder = self.folder()
        if folder is None:
            raise ModelError("SigLIP, which reads what's in a picture, isn't downloaded yet.")
        return folder

    def _tokens(self, folder: Path, words: str) -> list[int]:
        with self._lock:
            if self._tokenizer is None:
                from tokenizers import Tokenizer  # loaded when first needed

                try:
                    self._tokenizer = Tokenizer.from_file(str(folder / TOKENIZER))
                except Exception as error:  # the package raises its own kinds
                    raise ModelError(f"Mado couldn't read SigLIP's tokens ({error}).") from error
            tokenizer = self._tokenizer
        return list(tokenizer.encode(words).ids)


def _one(found: npt.NDArray[np.float32]) -> Vector:
    vector = unit(np.asarray(found, np.float32).reshape(-1)[:DIMENSIONS])[0]
    if vector.shape != (DIMENSIONS,):
        raise ModelError("SigLIP answered with numbers Mado doesn't know how to use.")
    return vector
