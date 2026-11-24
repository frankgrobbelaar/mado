"""Mado's AI models, ready to run: where each one's file is (shipped in Mado's assets, or a
download once it's fetched), where it runs on this PC (the graphics card, or the processor where
the card can't run them) and at which tile size, each through its kept session
(mado/directml.py). Every run is timed, so each picture made teaches Mado this PC's speeds.
"""

import time
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado import hardware
from mado.core.fixes import FBCNN, NAFNET, SCUNET, FixModel, guarded
from mado.core.hardware import Place, overlap_for, tile_for
from mado.core.models import BEST_PHOTO, Model, Quality
from mado.directml import LOCK, Array, ModelError, Session, Sessions, Tensor
from mado.extend import SIZE as LAMA_SIZE
from mado.extend import Filler
from mado.hardware import Here
from mado.painting import Painter
from mado.tools import Tools
from mado.upscale import Tiling

ASSETS = Path(__file__).parent / "assets"
LAMA = "lama"  # the download that extends edges, and erases at its best (downloads.json)
LAMA_FILE = "lama_fp32_dml.onnx"
# The editing models (docs/stack/editing.md): picking a part with a click, erasing it at Fast,
# and cutting out the subject at Best, each a download; cutting out at Fast is shipped.
SAM = "sam2.1-hiera-tiny"
SAM_READER = "vision_encoder.onnx"
SAM_PICKER = "prompt_encoder_mask_decoder.onnx"
MIGAN = "mi-gan"
MIGAN_FILE = "migan-pipeline-v2.onnx"
BIREFNET = "birefnet-lite"
BIREFNET_FILE = "birefnet-lite.onnx"
U2NETP_FILE = "u2netp.onnx"
_MIB = 1024 * 1024
# What each keeps of the graphics card's own memory once it has run, as measured on the owner's
# card: a session is never let go (mado/directml.py), so one is made there only when the card has
# room for it, and on the processor otherwise. BiRefNet, which DirectML runs only with its graph
# fusion off, takes far more than the card has unless the card is big. The fixes' models at
# their tile (docs/stack/fixes.md) likewise.
HELD: dict[str, int] = {
    SAM: 1300 * _MIB,
    MIGAN: 600 * _MIB,
    BIREFNET: 10240 * _MIB,
    # Search's reader of words at Best keeps about 910 MB (its detector's two canvases and the
    # recogniser's three widths); as reading is background work, it goes on the card only with
    # room besides for the queue's heaviest model at its tile (docs/stack/search.md).
    "pp-ocrv6-small": 2560 * _MIB,
    SCUNET.id: 1300 * _MIB,
    FBCNN.id: 1340 * _MIB,
    NAFNET.id: 380 * _MIB,
}
_SPARE = 512 * _MIB  # room left on the card besides
_UNKNOWN_ROOM = 4096 * _MIB  # where DirectX can't say how much room there is: a small card's
_BIREFNET_SETTINGS = {"ep.dml.disable_graph_fusion": "1"}
# The fixes' models (docs/stack/fixes.md) take squares this big, overlapping by this much, on the
# card or the processor alike: big enough for NAFNet, which needs 384 at least to see a shake.
FIX_TILE = 384
FIX_OVERLAP = 32
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)  # ImageNet's, as SAM, U²-Net and BiRefNet take
_STD = np.array([0.229, 0.224, 0.225], np.float32)

type Pixels = npt.NDArray[np.uint8]


@dataclass
class Timer:
    """How long a model spent, and on how many megapixels of tiles; and how long it waited for
    the graphics card, while another picture had it."""

    seconds: float = 0.0
    megapixels: float = 0.0
    waited: float = 0.0
    place: Place | None = None  # where its model ran, once it has

    def add(self, seconds: float, megapixels: float) -> None:
        self.seconds += seconds
        self.megapixels += megapixels

    @property
    def per_megapixel(self) -> float | None:
        return self.seconds / self.megapixels if self.megapixels > 0 else None


@dataclass(frozen=True)
class Selector:
    """SAM 2.1: `read` takes the picture once at 1024 × 1024 (on the card when it has room), and
    `pick` gives each part's three answers from its clicks, on the processor, in moments."""

    read: Callable[[Tensor], tuple[Array, Array, Array]]
    pick: Callable[
        [tuple[Array, Array, Array], Tensor, npt.NDArray[np.int64]], tuple[Tensor, Tensor]
    ]
    place: Place  # where `read` runs


@dataclass(frozen=True)
class EditingPlaces:
    """Where each editing model runs now (picking a part's clicks is on the processor always)."""

    select: Place  # SAM reading a picture
    erase_fast: Place
    erase_best: Place
    cut_fast: Place
    cut_best: Place


type Fill = Callable[[Pixels, npt.NDArray[np.bool_]], Pixels]  # a 512 square, its hole filled
type Matte = Callable[[Image.Image], Tensor]  # a picture's subject, 0 to 1, at its own size


class Ai:
    def __init__(
        self,
        sessions: Sessions,
        tools: Tools,
        where: Callable[[], Here],
        room: Callable[[], int | None] = hardware.room,
    ) -> None:
        """`room` says how much of the card's memory this process may still use (tests pass
        their own)."""
        self._sessions = sessions
        self._tools = tools
        self._where = where
        self._room = room
        self.painter = Painter(sessions, tools, where, room)  # the painting styles' networks

    def where(self) -> Here:
        return self._where()

    def starts_on(self, here: Here | None = None) -> dict[Literal["photo", "drawing"], Quality]:
        """Which of Fast and Best each kind of picture starts on here: as this PC suits, but a
        photo on Fast while Best's model isn't downloaded, as it's fetched only when asked for."""
        found = (here or self._where()).starts_on()
        if found["photo"] == "best" and self.file(BEST_PHOTO) is None:
            found["photo"] = "fast"
        return found

    def fix_starts_on(self) -> Quality:
        """Which of Fast and Best JPEG blocks start on: Best once FBCNN is downloaded, else Fast,
        whose model (SCUNet) also takes noise out, so a fix needs one download, not two."""
        return "best" if self.fix_file(FBCNN) is not None else "fast"

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
            return (out / 255.0).astype(np.float32)  # LaMa gives 0 to 255

        return fill

    # The quick fixes.

    def fix_file(self, model: FixModel) -> Path | None:
        """A fix's model file, once it's downloaded."""
        folder = self._tools.folder(model.id)
        return folder / model.file if folder is not None else None

    def fix_place(self, models: Sequence[FixModel]) -> Place:
        """Where the fixes these models make run now: on the card when it has room for each
        (or made it there already), as the editing models; on the processor when one hasn't."""
        places = {self.edit_place(model.id, self.fix_file(model)) for model in models}
        return "processor" if "processor" in places else self._where().place

    def fixer(
        self,
        model: FixModel,
        timer: Timer | None = None,
        *,
        strength: float = 1.0,
        qf: float | None = None,
        guard: bool = False,
    ) -> Tiling:
        """A fix's model a tile at a time, through its kept session, its answer the tile's own
        size: FBCNN told how hard (`qf`: 0.7 takes it for a JPEG saved at 30), NAFNet's answer
        held by the guard, and either kept as strongly as asked (`strength` of the change). On
        the card where this PC runs the models and the card has room for it (on the processor
        each is 12 to 21 times slower). Raises ModelError when it isn't downloaded, or as it runs
        when it can't."""
        found = self.fix_file(model)
        if found is None:
            raise ModelError(f"{model.name} isn't downloaded yet.")
        place = self.edit_place(model.id, found)
        clock = timer or Timer()
        clock.place = place
        extra: dict[str, Array] = {}
        if model is FBCNN:
            told = 0.5 if qf is None else min(max(qf, 0.05), 0.95)
            extra["qf_override"] = np.array([[told]], np.float32)

        def run(batch: Tensor) -> Tensor:
            with _turn(place, clock):  # timed once it has the card, not while it waits its turn
                session = self._sessions.get(found, FIX_TILE, place)
                began = time.perf_counter()
                out = session.run({"input": batch, **extra})[0]
                clock.add(time.perf_counter() - began, FIX_TILE * FIX_TILE / 1e6)
            answer: Tensor = np.asarray(out, np.float32)
            if guard:
                answer = guarded(batch, answer)
            if strength < 1.0:
                answer = (batch + np.float32(strength) * (answer - batch)).astype(np.float32)
            return answer

        return Tiling(run, FIX_TILE, FIX_OVERLAP, scale=1)

    # Editing by clicking.

    def edit_file(self, download: str, name: str) -> Path | None:
        """An editing model's file once it's downloaded (u2netp's is shipped)."""
        if download == "u2netp":
            return ASSETS / U2NETP_FILE
        folder = self._tools.folder(download)
        return folder / name if folder is not None else None

    def edit_place(self, download: str, file: Path | None = None) -> Place:
        """Where an editing model runs now: on the card when it was made there already, or when
        the card has room for what it keeps there (where DirectX can't say, as much as a small
        card has); otherwise on the processor, and Mado says so. On a PC whose card can't run the
        models, the processor."""
        if self._where().place == "processor":
            return "processor"
        if file is not None and self._sessions.has(file, "card"):
            return "card"
        free = self._room()
        if free is None:
            free = _UNKNOWN_ROOM
        return "card" if free >= HELD.get(download, 0) + _SPARE else "processor"

    def editing_places(self) -> EditingPlaces:
        """Where each editing model would run now, as the Edit tab says."""
        return EditingPlaces(
            select=self.edit_place(SAM, self.edit_file(SAM, SAM_READER)),
            erase_fast=self.edit_place(MIGAN, self.edit_file(MIGAN, MIGAN_FILE)),
            erase_best=self._where().place,
            cut_fast="processor",
            cut_best=self.edit_place(BIREFNET, self.edit_file(BIREFNET, BIREFNET_FILE)),
        )

    def selector(self, timer: Timer | None = None) -> Selector:
        """SAM 2.1, to pick parts: each session made the first time it runs, so a click, which
        only picks (on the processor), never waits for the card. Raises ModelError when it isn't
        downloaded, or as it runs when it can't."""
        reading = self.edit_file(SAM, SAM_READER)
        picking = self.edit_file(SAM, SAM_PICKER)
        if reading is None or picking is None:
            raise ModelError("SAM 2.1, which picks parts, isn't downloaded yet.")
        place = self.edit_place(SAM, reading)
        clock = timer or Timer()

        def read(pixels: Tensor) -> tuple[Array, Array, Array]:
            with _turn(place, clock):
                reader = self._sessions.get(reading, None, place, fixed={"batch_size": 1})
                began = time.perf_counter()
                found = reader.run({"pixel_values": pixels})
                clock.add(time.perf_counter() - began, 1024 * 1024 / 1e6)
            return found[0], found[1], found[2]

        def pick(
            read: tuple[Array, Array, Array], points: Tensor, labels: npt.NDArray[np.int64]
        ) -> tuple[Tensor, Tensor]:
            picker = self._sessions.get(picking, None, "processor")
            scores, masks = picker.run(
                {
                    "image_embeddings.0": read[0],
                    "image_embeddings.1": read[1],
                    "image_embeddings.2": read[2],
                    "input_points": points,
                    "input_labels": labels,
                    "input_boxes": np.zeros((1, 0, 4), np.float32),
                }
            )[:2]
            return scores[0, 0].astype(np.float32), masks[0, 0].astype(np.float32)

        return Selector(read, pick, place)

    def eraser(self, quality: Quality, timer: Timer | None = None) -> tuple[Fill, Place]:
        """Erasing a 512 square's hole: MI-GAN at Fast, LaMa at Best; and where it runs. Raises
        ModelError when it isn't downloaded, or as it runs when it can't."""
        clock = timer or Timer()
        if quality == "best":
            lama = self.lama_file()
            if lama is None:
                raise ModelError("LaMa, which erases at its best, isn't downloaded yet.")
            place = self._where().place
            return _lama(lambda: self._sessions.get(lama, None, place), place, clock), place
        found = self.edit_file(MIGAN, MIGAN_FILE)
        if found is None:
            raise ModelError("MI-GAN, which erases, isn't downloaded yet.")
        place = self.edit_place(MIGAN, found)
        fixed = {"batch_size": 1, "height": ERASE_SIZE, "width": ERASE_SIZE}

        def fill(picture: Pixels, hole: npt.NDArray[np.bool_]) -> Pixels:
            image = np.ascontiguousarray(picture.transpose(2, 0, 1)[None])
            keep = np.ascontiguousarray(np.where(hole, 0, 255).astype(np.uint8)[None, None])
            with _turn(place, clock):
                session = self._sessions.get(found, None, place, fixed=fixed)
                began = time.perf_counter()
                out = session.run({"image": image, "mask": keep})[0]
                clock.add(time.perf_counter() - began, ERASE_SIZE * ERASE_SIZE / 1e6)
            return np.ascontiguousarray(out[0].transpose(1, 2, 0).astype(np.uint8))

        return fill, place

    def matte(self, quality: Quality, timer: Timer | None = None) -> tuple[Matte, Place]:
        """Finding a picture's subject: u2netp at Fast (shipped, on the processor, where it takes
        a fifth of a second), BiRefNet lite at Best (on the card only when it has a great deal of
        room). Raises ModelError when it isn't downloaded or can't run."""
        clock = timer or Timer()
        if quality == "fast":
            small = self.edit_file("u2netp", U2NETP_FILE)
            assert small is not None  # noqa: S101 - shipped

            def shipped() -> Session:
                return self._sessions.get(small, None, "processor")

            return _matte(shipped, "input.1", 320, "processor", clock, logits=False), "processor"
        found = self.edit_file(BIREFNET, BIREFNET_FILE)
        if found is None:
            raise ModelError("BiRefNet lite, which cuts out at its best, isn't downloaded yet.")
        place = self.edit_place(BIREFNET, found)
        settings = _BIREFNET_SETTINGS if place == "card" else None

        def fetched() -> Session:
            return self._sessions.get(found, None, place, settings=settings)

        return _matte(fetched, "input_image", 1024, place, clock, logits=True), place


ERASE_SIZE = 512  # the square the erasing models take


def imagenet(picture: Image.Image, size: int) -> Tensor:
    """A picture (RGB) as SAM, U²-Net and BiRefNet take it, `size` square: its colours 0 to 1,
    less ImageNet's mean, over its spread, as 1 × 3 × size × size. A big picture is first made
    smaller by whole steps, so a hundred megapixels take a moment."""
    resized = picture.resize((size, size), Image.Resampling.BILINEAR, reducing_gap=3.0)
    values = (np.asarray(resized, np.float32) / 255.0 - _MEAN) / _STD
    return np.ascontiguousarray(values.transpose(2, 0, 1)[None], dtype=np.float32)


def _turn(place: Place, clock: Timer) -> AbstractContextManager[object]:
    """The card's lock, for a model on the card, with how long it waited for it; nothing on the
    processor."""
    if place == "processor":
        return nullcontext()
    return _Waited(clock)


class _Waited:
    def __init__(self, clock: Timer) -> None:
        self._clock = clock

    def __enter__(self) -> object:
        began = time.perf_counter()
        LOCK.acquire()
        self._clock.waited += time.perf_counter() - began
        return self

    def __exit__(self, *_exc: object) -> None:
        LOCK.release()


def _lama(session: Callable[[], Session], place: Place, clock: Timer) -> Fill:
    """LaMa erasing, its session made the first time it runs."""

    def fill(picture: Pixels, hole: npt.NDArray[np.bool_]) -> Pixels:
        image = np.ascontiguousarray(picture.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        mask = np.ascontiguousarray(hole[None, None], dtype=np.float32)
        with _turn(place, clock):
            kept = session()
            began = time.perf_counter()
            out = kept.run({"image": image, "mask": mask})[0]
            clock.add(time.perf_counter() - began, ERASE_SIZE * ERASE_SIZE / 1e6)
        made = np.clip(out[0].transpose(1, 2, 0), 0, 255)  # LaMa gives 0 to 255
        return np.ascontiguousarray((made + 0.5).astype(np.uint8))

    return fill


def _matte(
    session: Callable[[], Session],
    name: str,
    size: int,
    place: Place,
    clock: Timer,
    *,
    logits: bool,
) -> Matte:
    """A subject found by U²-Net or BiRefNet, its session made the first time it runs."""

    def found(picture: Image.Image) -> Tensor:
        values = imagenet(picture, size)
        with _turn(place, clock):
            kept = session()
            began = time.perf_counter()
            out = kept.run({name: values})[0]
            clock.add(time.perf_counter() - began, size * size / 1e6)
        soft = out[0, 0].astype(np.float32)
        if logits:
            soft = 1.0 / (1.0 + np.exp(-np.clip(soft, -30, 30)))
        low, high = float(soft.min()), float(soft.max())
        if high - low > 1e-6:  # stretched to 0 to 1, as rembg does
            soft = (soft - low) / (high - low)
        return soft.astype(np.float32)

    return found
