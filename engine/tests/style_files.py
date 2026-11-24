"""Made-up painting styles for the tests, as ONNX files written field by field: Mado's six are
downloads CI never has, so these stand in for them, built as the real ones are (a picture in, a
picture out, sides free; the network's weights named `net.`, a fixed constant beside them, as
the real ones keep their dither). Each is one convolution, every colour made from all three,
and a sigmoid: two seeds make two styles that tell apart."""

import struct
from pathlib import Path

import numpy as np
import pytest

_FLOAT = 1  # ONNX's number for 32-bit floats


def style_file(path: Path, seed: int) -> Path:
    """A made-up style at `path`: the picture plus a constant, through a 1 × 1 convolution and a
    sigmoid. Different seeds, different weights."""
    rng = np.random.default_rng(seed)
    weight = rng.normal(0, 1.5, (3, 3, 1, 1)).astype(np.float32)
    bias = rng.normal(0, 0.5, 3).astype(np.float32)
    graph = b"".join(
        [
            _message(1, _node("Add", ["input", "da"], ["dithered"])),
            _message(1, _node("Conv", ["dithered", "net.conv.weight", "net.conv.bias"], ["c"])),
            _message(1, _node("Sigmoid", ["c"], ["output"])),
            _message(2, b"made-up style"),
            _message(5, _tensor("da", np.full((1, 1, 1, 1), 0.01, np.float32))),
            _message(5, _tensor("net.conv.weight", weight)),
            _message(5, _tensor("net.conv.bias", bias)),
            _message(11, _picture_info("input")),
            _message(12, _picture_info("output")),
        ]
    )
    opset = _message(1, b"") + _number(2, 17)
    model = _number(1, 8) + _message(2, b"mado tests") + _message(8, opset) + _message(7, graph)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(model)
    return path


PAINTER_DOWNLOADS = (
    "style-van-gogh-starry-night",
    "style-hokusai-great-wave",
    "style-monet-water-lilies-1915",
    "style-seurat-gravelines",
)


def with_styles(monkeypatch: pytest.MonkeyPatch, folder: Path, *, microast: bool = True) -> Path:
    """Made-up painters (and MicroAST) where Mado finds its downloads, as if they were downloaded:
    each in a folder of its own, named by the development copy each download may stand in with
    (MADO_<DOWNLOAD>_DIR), which an engine run from its source uses."""
    for at, download in enumerate(PAINTER_DOWNLOADS):
        style_file(folder / download / f"{download}.onnx", seed=at + 1)
        monkeypatch.setenv(f"MADO_{download.upper().replace('-', '_')}_DIR", str(folder / download))
    if microast:
        microast_files(folder / "microast")
        monkeypatch.setenv("MADO_MICROAST_DIR", str(folder / "microast"))
    return folder


def microast_files(folder: Path, seed: int = 9) -> Path:
    """A made-up MicroAST in `folder`, as its two halves are: one reads a style picture into 512
    numbers (its mean colour through a 1 × 1 convolution), the other paints a picture with them
    (the picture times the sigmoid of their mean, so another style paints it otherwise)."""
    rng = np.random.default_rng(seed)
    reader = b"".join(
        [
            _message(1, _node("GlobalAveragePool", ["style"], ["pooled"])),
            _message(1, _node("Conv", ["pooled", "net.w", "net.b"], ["style_code"])),
            _message(2, b"made-up style reader"),
            _message(5, _tensor("net.w", rng.normal(0, 1, (512, 3, 1, 1)).astype(np.float32))),
            _message(5, _tensor("net.b", rng.normal(0, 0.2, 512).astype(np.float32))),
            _message(11, _picture_info("style")),
            _message(12, _code_info("style_code")),
        ]
    )
    axes = _message(1, b"axes") + _number(20, 7) + _number(8, 1)  # an INTS attribute: [1]
    painter = b"".join(
        [
            _message(1, _node("ReduceMean", ["style_code"], ["mean"], _message(5, axes))),
            _message(1, _node("Sigmoid", ["mean"], ["tint"])),
            _message(1, _node("Mul", ["content", "tint"], ["output"])),
            _message(2, b"made-up style painter"),
            _message(11, _picture_info("content")),
            _message(11, _code_info("style_code")),
            _message(11, _strength_info("strength")),
            _message(12, _picture_info("output")),
        ]
    )
    folder.mkdir(parents=True, exist_ok=True)
    for name, graph in (("microast-style.onnx", reader), ("microast-stylize.onnx", painter)):
        opset = _message(1, b"") + _number(2, 17)
        model = _number(1, 8) + _message(2, b"mado tests") + _message(8, opset) + _message(7, graph)
        (folder / name).write_bytes(model)
    return folder


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _number(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _message(field: int, payload: bytes) -> bytes:
    return _varint(field << 3 | 2) + _varint(len(payload)) + payload


def _node(op: str, inputs: list[str], outputs: list[str], attributes: bytes = b"") -> bytes:
    named = b"".join(_message(1, name.encode()) for name in inputs)
    made = b"".join(_message(2, name.encode()) for name in outputs)
    return named + made + _message(4, op.encode()) + attributes


def _tensor(name: str, values: np.ndarray) -> bytes:
    dims = b"".join(_number(1, size) for size in values.shape)
    data = struct.pack(f"<{values.size}f", *values.ravel().tolist())
    return dims + _number(2, _FLOAT) + _message(8, name.encode()) + _message(9, data)


def _picture_info(name: str) -> bytes:
    """A picture's place in the graph: batch, three colours, height and width, the sides free."""
    dims = (
        _message(1, _message(2, b"batch"))
        + _message(1, _number(1, 3))
        + _message(1, _message(2, b"height"))
        + _message(1, _message(2, b"width"))
    )
    tensor = _number(1, _FLOAT) + _message(2, dims)
    return _message(1, name.encode()) + _message(2, _message(1, tensor))


def _code_info(name: str) -> bytes:
    """A style's numbers in the graph: batch × 512 × 1 × 1."""
    dims = (
        _message(1, _message(2, b"batch"))
        + _message(1, _number(1, 512))
        + _message(1, _number(1, 1))
        + _message(1, _number(1, 1))
    )
    tensor = _number(1, _FLOAT) + _message(2, dims)
    return _message(1, name.encode()) + _message(2, _message(1, tensor))


def _strength_info(name: str) -> bytes:
    tensor = _number(1, _FLOAT) + _message(2, _message(1, _number(1, 1)))
    return _message(1, name.encode()) + _message(2, _message(1, tensor))
