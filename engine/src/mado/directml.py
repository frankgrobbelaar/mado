"""ONNX Runtime sessions, on the graphics card through DirectML or on the processor: made once
for each model and size, and kept for the engine's life.

DirectML has three rules on Windows (docs/stack/upscaling.md, tested on the owner's PC,
2026-11-22), and every session here keeps them:

- One call at a time. Two threads making or running sessions at once can crash the graphics
  driver, so every DirectML call is made under LOCK, a tile at a time, taking turns with any
  other use of it in the engine. A session on the processor is made and run without it, and a
  session made already is handed out without it: neither touches the card, so a click picked
  on the processor never waits for the queue's picture.
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
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

type Place = Literal["card", "processor"]
type Tensor = npt.NDArray[np.float32]
type Array = npt.NDArray[Any]  # what a model takes and gives: floats, or bytes, or labels

# The PC's high-performance card: on a laptop with two, its own rather than the processor's.
PROVIDER = ("DmlExecutionProvider", {"performance_preference": "high_performance"})
LOCK = threading.RLock()


class ModelError(Exception):
    """A model that can't run where it should, with a sentence saying why."""


class Session(Protocol):
    def run(self, feed: Mapping[str, Array], /) -> list[Array]: ...

    def meta(self) -> Mapping[str, str]: ...


class _Kept:
    """An ONNX Runtime session: on the card, run under the lock; on the processor, run as it's
    asked, as it doesn't touch the card (a click's few milliseconds there never wait for the
    queue's picture)."""

    def __init__(self, session: InferenceSession, place: Place) -> None:
        self._session = session
        self._place = place

    def run(self, feed: Mapping[str, Array], /) -> list[Array]:
        if self._place == "processor":
            return self._session.run(None, feed)
        with LOCK:
            return self._session.run(None, feed)

    def meta(self) -> Mapping[str, str]:
        """What the model's file says of itself (a recogniser's characters, say)."""
        return dict(self._session.get_modelmeta().custom_metadata_map)


class Sessions:
    """Every session the engine has made, by model file, size and place, each kept for good."""

    def __init__(self) -> None:
        self._kept: dict[tuple[object, ...], Session] = {}
        self._guard = threading.Lock()  # the list itself, held a moment at a time
        self._making = threading.Lock()  # one made on the processor at a time

    def get(
        self,
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
        """The session for a model at a fixed square `size` (its free height and width pinned;
        None for a model whose size is fixed already, or whose sizes are pinned by name in
        `fixed`), on the card or the processor, with ONNX Runtime's `settings` for the card,
        `processor_settings` and at most `threads` of the processor's (None: as many as it has
        cores) for one there. `data` gives the model itself, made in memory, when there's no
        file (`model` then only names it). `half`: a model stored in half precision, which ONNX
        Runtime's highest optimisation can break on the processor (its fused layer norms), so
        there it's made one level lower. Made the first time it's asked for, then kept. Raises
        ModelError when it can't be made where it should run."""
        pinned = tuple(sorted((fixed or {}).items()))
        chosen = settings if place == "card" else processor_settings
        configured = tuple(sorted((chosen or {}).items()))
        lower = half and place == "processor"
        key = (str(model).casefold(), size, place, pinned, configured, threads, lower)
        with self._guard:
            found = self._kept.get(key)
        if found is not None:
            return found
        # Made on the card under the card's lock, as any DirectML call; on the processor without
        # it, never waiting for the queue's picture. Either way made once.
        with LOCK if place == "card" else self._making:
            with self._guard:
                found = self._kept.get(key)
            if found is None:
                made = data() if data is not None else None
                found = _make(
                    model, size, place, dict(pinned), dict(configured), threads, made, lower
                )
                with self._guard:
                    self._kept[key] = found
            return found

    def has(self, model: Path, place: Place) -> bool:
        """Whether a session for a model was made on the card or the processor already."""
        named = str(model).casefold()
        with self._guard:
            return any(key[0] == named and key[2] == place for key in self._kept)


def _make(
    model: Path,
    size: int | None,
    place: Place,
    fixed: Mapping[str, int] | None = None,
    settings: Mapping[str, str] | None = None,
    threads: int | None = None,
    data: bytes | None = None,
    lower: bool = False,
) -> Session:
    try:
        import onnxruntime as ort  # loaded when first needed: the engine starts sooner
    except ImportError as error:
        raise ModelError(f"Mado couldn't load ONNX Runtime ({error}).") from error
    ort.disable_telemetry_events()  # its Windows builds report use to Microsoft unless told not to
    if data is None and not model.is_file():
        raise ModelError(f"The AI model {model.name} isn't there: Mado may need it again.")
    options = ort.SessionOptions()
    options.graph_optimization_level = (
        ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
        if lower
        else ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    )
    options.enable_mem_pattern = False  # DirectML asks for both of these
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    if size is not None:
        options.add_free_dimension_override_by_name("batch", 1)
        options.add_free_dimension_override_by_name("height", size)
        options.add_free_dimension_override_by_name("width", size)
    for name, value in (fixed or {}).items():
        options.add_free_dimension_override_by_name(name, value)
    for name, setting in (settings or {}).items():
        options.add_session_config_entry(name, setting)
    if place == "processor" and threads is not None:
        options.intra_op_num_threads = threads
    providers: list[str | tuple[str, Mapping[str, object]]] = (
        [PROVIDER] if place == "card" else ["CPUExecutionProvider"]
    )
    try:
        session = ort.InferenceSession(
            data if data is not None else str(model), options, providers=providers
        )
    except Exception as error:  # ONNX Runtime raises its own kinds, all plain Exceptions
        where = "The graphics card" if place == "card" else "The processor"
        raise ModelError(f"{where} couldn't run the AI model ({error}).") from error
    if place == "card" and "DmlExecutionProvider" not in session.get_providers():
        raise ModelError("The graphics card couldn't run the AI model: it needs DirectX 12.")
    return _Kept(session, place)


def tensor(values: npt.ArrayLike) -> Tensor:
    """Values as the models take them: 32-bit floats, in one block of memory."""
    return np.ascontiguousarray(values, dtype=np.float32)
