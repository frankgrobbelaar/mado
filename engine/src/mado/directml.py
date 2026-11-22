"""ONNX Runtime sessions, on the graphics card through DirectML or on the processor: made once
for each model and size, and kept for the engine's life.

DirectML has three rules on Windows (docs/stack/upscaling.md, tested on the owner's PC,
2026-11-22), and every session here keeps them:

- One call at a time. Two threads making or running sessions at once can crash the graphics
  driver, so every DirectML call is made under LOCK, a tile at a time, taking turns with any
  other use of it in the engine.
- Never let a session go. Releasing one session crashed another that was still in use (five
  times out of five), so a session, once made, stays until the engine ends.
- Fixed sizes. A session made for one size runs much faster than one left free, and its first
  run compiles the graph for that size (one to eight seconds), so sessions are made per model
  and tile size, every free dimension pinned, and kept.

The card is the PC's high-performance one (a laptop's own, not the processor's graphics that
drive its screen). Where the card should run a model and can't, that's an error that says so:
ONNX Runtime never quietly falls back to the processor here. A PC whose card can't run the
models at all (the PC check finds that) gets sessions on the processor, and Mado says so.
"""

import threading
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

type Place = Literal["card", "processor"]
type Tensor = npt.NDArray[np.float32]

# The PC's high-performance card: on a laptop with two, its own rather than the processor's.
PROVIDER = ("DmlExecutionProvider", {"performance_preference": "high_performance"})
LOCK = threading.RLock()


class ModelError(Exception):
    """A model that can't run where it should, with a sentence saying why."""


class Session(Protocol):
    def run(self, feed: Mapping[str, Tensor], /) -> list[Tensor]: ...


class _Kept:
    """An ONNX Runtime session, run under the lock."""

    def __init__(self, session: InferenceSession) -> None:
        self._session = session

    def run(self, feed: Mapping[str, Tensor], /) -> list[Tensor]:
        with LOCK:
            return self._session.run(None, feed)


class Sessions:
    """Every session the engine has made, by model file, size and place, each kept for good."""

    def __init__(self) -> None:
        self._kept: dict[tuple[str, int | None, Place], Session] = {}

    def get(self, model: Path, size: int | None, place: Place) -> Session:
        """The session for a model at a fixed square `size` (its free height and width pinned;
        None for a model whose size is fixed already), on the card or the processor. Made the
        first time it's asked for, then kept. Raises ModelError when it can't be made where it
        should run."""
        key = (str(model).casefold(), size, place)
        with LOCK:
            found = self._kept.get(key)
            if found is None:
                found = _make(model, size, place)
                self._kept[key] = found
            return found


def _make(model: Path, size: int | None, place: Place) -> Session:
    try:
        import onnxruntime as ort  # loaded when first needed: the engine starts sooner
    except ImportError as error:
        raise ModelError(f"Mado couldn't load ONNX Runtime ({error}).") from error
    ort.disable_telemetry_events()  # its Windows builds report use to Microsoft unless told not to
    if not model.is_file():
        raise ModelError(f"The AI model {model.name} isn't there: Mado may need it again.")
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.enable_mem_pattern = False  # DirectML asks for both of these
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    if size is not None:
        options.add_free_dimension_override_by_name("batch", 1)
        options.add_free_dimension_override_by_name("height", size)
        options.add_free_dimension_override_by_name("width", size)
    providers: list[str | tuple[str, Mapping[str, object]]] = (
        [PROVIDER] if place == "card" else ["CPUExecutionProvider"]
    )
    try:
        session = ort.InferenceSession(str(model), options, providers=providers)
    except Exception as error:  # ONNX Runtime raises its own kinds, all plain Exceptions
        where = "The graphics card" if place == "card" else "The processor"
        raise ModelError(f"{where} couldn't run the AI model ({error}).") from error
    if place == "card" and "DmlExecutionProvider" not in session.get_providers():
        raise ModelError("The graphics card couldn't run the AI model: it needs DirectX 12.")
    return _Kept(session)


def tensor(values: npt.ArrayLike) -> Tensor:
    """Values as the models take them: 32-bit floats, in one block of memory."""
    return np.ascontiguousarray(values, dtype=np.float32)
