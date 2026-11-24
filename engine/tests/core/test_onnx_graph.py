"""An ONNX model's weights read out, and made inputs of its graph, so one session runs it with any
set of them (mado/core/onnx_graph.py): checked on the upscaler Mado ships and on made-up styles,
through ONNX Runtime on the processor."""

from pathlib import Path

import numpy as np
import onnxruntime as ort
import pytest

import mado
from mado.core.onnx_graph import GraphError, initializers, weights_as_inputs
from tests.style_files import style_file

SHIPPED = Path(mado.__file__).parent / "assets" / "realesr-general-x4v3.onnx"
_PICTURE = np.random.default_rng(1).random((1, 3, 16, 16), dtype=np.float32)


def _session(model: bytes) -> ort.InferenceSession:
    return ort.InferenceSession(model, providers=["CPUExecutionProvider"])


def _is_weight(name: str) -> bool:
    return name.startswith("net.")


def test_a_model_with_its_weights_as_inputs_gives_what_it_gave_with_them_inside():
    model = SHIPPED.read_bytes()

    graph, weights = weights_as_inputs(model, lambda _name: True)

    want = _session(model).run(None, {"input": _PICTURE})[0]
    got = _session(graph).run(None, {"input": _PICTURE, **weights})[0]
    assert len(weights) > 10
    assert float(np.abs(got - want).max()) < 1e-5
    # Nothing to fall back on: every weight taken out must be given.
    assert {each.name for each in _session(graph).get_inputs()} == {"input", *weights}


def test_only_the_weights_asked_for_leave_the_graph():
    model = SHIPPED.read_bytes()
    every = initializers(model, lambda _name: True)
    first = next(iter(every))

    graph, weights = weights_as_inputs(model, lambda name: name == first)

    assert list(weights) == [first]
    assert np.array_equal(weights[first], every[first])
    assert {each.name for each in _session(graph).get_inputs()} == {"input", first}


def test_one_graph_runs_any_style_with_that_styles_weights(tmp_path: Path):
    one = style_file(tmp_path / "one.onnx", seed=1).read_bytes()
    other = style_file(tmp_path / "other.onnx", seed=2).read_bytes()
    graph, own = weights_as_inputs(one, _is_weight)
    shared = _session(graph)
    theirs = initializers(other, _is_weight)

    for model, weights in ((one, own), (other, theirs)):
        want = _session(model).run(None, {"input": _PICTURE})[0]
        got = shared.run(None, {"input": _PICTURE, **weights})[0]
        assert float(np.abs(got - want).max()) < 1e-6
    # The constant beside the weights (a real style's dither) stays inside.
    assert "da" not in own
    assert set(own) == set(theirs) == {"net.conv.weight", "net.conv.bias"}


def test_weights_come_out_in_their_own_shapes_as_32_bit_floats(tmp_path: Path):
    model = style_file(tmp_path / "style.onnx", seed=3).read_bytes()

    found = initializers(model, lambda name: name.startswith("net."))

    assert found["net.conv.weight"].shape == (3, 3, 1, 1)
    assert found["net.conv.bias"].shape == (3,)
    assert all(each.dtype == np.float32 and each.flags.c_contiguous for each in found.values())


@pytest.mark.parametrize(
    "broken",
    [b"", b"\x0a", b"\x3a\xff\xff\xff\xff\x0f", b"not a model at all, just words"],
)
def test_a_file_that_isnt_a_model_is_refused_with_a_sentence(broken: bytes):
    with pytest.raises(GraphError, match="isn't a model"):
        weights_as_inputs(broken, lambda _name: True)


def test_a_cut_short_model_is_refused(tmp_path: Path):
    model = style_file(tmp_path / "style.onnx", seed=4).read_bytes()

    with pytest.raises(GraphError):
        initializers(model[: len(model) - 7], lambda _name: True)
