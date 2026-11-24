"""An ONNX model's weights, read out of its file and made inputs of its graph, so that one session
runs the same network with any set of them. Pure.

Mado's painting styles are one network trained six times: the same graph, each with its own
weights. A DirectML session holds about 2.2 GB of the card's memory for good (mado/directml.py
never lets one go), so a session each wouldn't fit a 6 GB card; one session whose weights come
in with the picture serves them all at the same speed. The weights must be plain inputs, with
no values left in the graph: given defaults (an initializer that's also an input), DirectML's
fused graph keeps the defaults and ignores what's given (measured, docs/stack/styles.md).

An ONNX file is a protocol buffer. Only the few fields this needs are read: the model's graph
(field 7), the graph's initializers (5) and inputs (11), and a tensor's dims (1), type (2), name
(8) and data (9, or 4 for floats written one by one); every other field is kept byte for byte.
"""

import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

type Floats = npt.NDArray[np.float32]

_FLOAT = 1  # TensorProto.DataType.FLOAT
_VARINT, _I64, _LEN, _I32 = 0, 1, 2, 5  # the wire types an ONNX file uses
_GRAPH, _INITIALIZER, _INPUT = 7, 5, 11  # ModelProto.graph, GraphProto.initializer and input
_NOT_A_MODEL = "It isn't a model Mado can read: the file is damaged or of another kind."


class GraphError(ValueError):
    """A model this can't read or change, with a sentence saying why."""


@dataclass(frozen=True)
class _Field:
    number: int
    wire: int
    value: int | memoryview  # a number, or a length-delimited field's bytes
    raw: memoryview  # the whole field as written: its key, length and value


def weights_as_inputs(
    model: bytes, moved: Callable[[str], bool]
) -> tuple[bytes, dict[str, Floats]]:
    """The model with the 32-bit float weights `moved` names taken out of its graph and made
    inputs of it, each its own shape; and the weights taken out, by name. Raises GraphError."""
    found_graph: _Field | None = None
    kept: list[bytes] = []
    for field in _fields(memoryview(model)):
        if field.number == _GRAPH and field.wire == _LEN and found_graph is None:
            found_graph = field
        else:
            kept.append(bytes(field.raw))
    if found_graph is None or not isinstance(found_graph.value, memoryview):
        raise GraphError(_NOT_A_MODEL)
    graph: list[bytes] = []
    taken: dict[str, Floats] = {}
    listed: set[str] = set()
    for field in _fields(found_graph.value):
        if field.number == _INITIALIZER and isinstance(field.value, memoryview):
            name, values = _tensor(field.value, moved)
            if values is not None:
                taken[name] = values
                continue
        elif field.number == _INPUT and isinstance(field.value, memoryview):
            listed.add(_name_of(field.value))
        graph.append(bytes(field.raw))
    for name, values in taken.items():
        if name not in listed:  # an old model may list its weights as inputs already
            graph.append(_len(_INPUT, _value_info(name, values.shape)))
    return b"".join([*kept, _len(_GRAPH, b"".join(graph))]), taken


def initializers(model: bytes, wanted: Callable[[str], bool]) -> dict[str, Floats]:
    """The 32-bit float weights `wanted` names, read out of a model, by name. Raises GraphError."""
    return weights_as_inputs(model, wanted)[1]


def _tensor(data: memoryview, moved: Callable[[str], bool]) -> tuple[str, Floats | None]:
    """A weight's name, and its values when `moved` wants them (None when it stays)."""
    name, dims, kind = "", list[int](), _FLOAT
    raw: memoryview | None = None
    floats: list[float] = []
    external = False
    for field in _fields(data):
        match field.number, field.value:
            case 1, int(size):
                dims.append(size)
            case 1, memoryview() as packed:
                dims.extend(_varints(packed))
            case 2, int(found):
                kind = found
            case 8, memoryview() as text:
                name = bytes(text).decode("utf-8", errors="replace")
            case 9, memoryview() as values:
                raw = values
            case 4, memoryview() as packed:
                floats.extend(struct.unpack(f"<{len(packed) // 4}f", packed))
            case 4, int(bits):
                floats.append(struct.unpack("<f", struct.pack("<I", bits))[0])
            case 13 | 14, _:
                external = True  # its data in another file, or its location said
            case _:
                pass
    if not name or not moved(name):
        return name, None
    if kind != _FLOAT or external:
        raise GraphError(f"Its weight {name} isn't 32-bit numbers kept in the file.")
    count = int(np.prod(dims)) if dims else 1
    if raw is not None:
        if len(raw) != count * 4:
            raise GraphError(f"Its weight {name} is cut short: the file is damaged.")
        values = np.frombuffer(raw, dtype="<f4").astype(np.float32)
    elif len(floats) == count:
        values = np.array(floats, np.float32)
    else:
        raise GraphError(f"Its weight {name} is cut short: the file is damaged.")
    return name, np.ascontiguousarray(values.reshape(dims))


def _name_of(data: memoryview) -> str:
    """A ValueInfoProto's name (its field 1)."""
    for field in _fields(data):
        if field.number == 1 and isinstance(field.value, memoryview):
            return bytes(field.value).decode("utf-8", errors="replace")
    return ""


def _value_info(name: str, dims: tuple[int, ...]) -> bytes:
    """An input of 32-bit floats, `dims` big: ValueInfoProto { name, TypeProto { tensor_type {
    elem_type, TensorShapeProto { dim: Dimension { dim_value } } } } }."""
    shape = b"".join(_len(1, _number(1, size)) for size in dims)
    tensor = _number(1, _FLOAT) + _len(2, shape)
    return _len(1, name.encode()) + _len(2, _len(1, tensor))


def _fields(data: memoryview) -> Iterator[_Field]:
    """The fields of a protocol buffer message, in the order written. Raises GraphError for one
    that's cut short or of a kind ONNX doesn't write."""
    at, end = 0, len(data)
    while at < end:
        start = at
        key, at = _varint(data, at)
        number, wire = key >> 3, key & 7
        value: int | memoryview
        if number == 0:
            raise GraphError(_NOT_A_MODEL)
        if wire == _VARINT:
            value, at = _varint(data, at)
        elif wire == _LEN:
            size, at = _varint(data, at)
            if at + size > end:
                raise GraphError(_NOT_A_MODEL)
            value, at = data[at : at + size], at + size
        elif wire in (_I64, _I32):
            width = 8 if wire == _I64 else 4
            if at + width > end:
                raise GraphError(_NOT_A_MODEL)
            value = int.from_bytes(data[at : at + width], "little")
            at += width
        else:
            raise GraphError(_NOT_A_MODEL)
        yield _Field(number, wire, value, data[start:at])


def _varint(data: memoryview, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if at >= len(data) or shift > 63:
            raise GraphError(_NOT_A_MODEL)
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, at
        shift += 7


def _varints(data: memoryview) -> list[int]:
    found: list[int] = []
    at = 0
    while at < len(data):
        value, at = _varint(data, at)
        found.append(value)
    return found


def _varint_bytes(value: int) -> bytes:
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _number(field: int, value: int) -> bytes:
    return _varint_bytes(field << 3 | _VARINT) + _varint_bytes(value)


def _len(field: int, payload: bytes) -> bytes:
    return _varint_bytes(field << 3 | _LEN) + _varint_bytes(len(payload)) + payload
