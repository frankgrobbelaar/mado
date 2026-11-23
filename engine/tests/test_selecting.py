"""Picking parts: an answer made the picture's size only over the part it reaches, the answers
kept smallest first, which part a point is in, and the outline round them."""

import numpy as np
import pytest
from PIL import Image

from mado.ai import Selector
from mado.core.edits import Click, Part
from mado.selecting import answers, drawn, grid_size, holding, mask_at, on_grid


def _logits(at: tuple[int, int], radius: int) -> np.ndarray:
    ys, xs = np.mgrid[0:256, 0:256]
    distance = np.hypot(xs - at[0], ys - at[1])
    return ((radius - distance) * 2).astype(np.float32)


def test_an_answer_is_made_the_pictures_size_only_where_it_reaches_and_the_same_as_whole():
    logits = _logits((200, 60), 12)
    size = (1203, 901)

    found = mask_at(logits, size)

    whole = np.asarray(
        Image.fromarray(logits, "F").resize(size, Image.Resampling.BILINEAR), np.float32
    )
    expected = (1.0 / (1.0 + np.exp(-np.clip(whole, -30, 30))) * 255 + 0.5).astype(np.uint8)
    assert np.abs(found.astype(int) - expected.astype(int)).max() <= 1
    assert found.shape == (901, 1203)
    assert found[:, :500].max() == 0  # far from the part, never worked out
    assert mask_at(np.full((256, 256), -20, np.float32), size).max() == 0


def test_a_parts_answers_are_kept_smallest_first():
    small, middle, big = _logits((128, 128), 5), _logits((128, 128), 20), _logits((128, 128), 60)

    def pick(*_args: object) -> tuple[np.ndarray, np.ndarray]:
        return np.array([0.5, 0.9, 0.7], np.float32), np.stack([big, small, middle])

    selector = Selector(lambda _pixels: (np.zeros(1), np.zeros(1), np.zeros(1)), pick, "card")

    found = answers(selector, (np.zeros(1), np.zeros(1), np.zeros(1)), Part((Click(0.5, 0.5),)))

    assert found.areas[0] < found.areas[1] < found.areas[2]
    assert found.scores == pytest.approx((0.9, 0.7, 0.5))  # each answer's score went with it
    assert found.choice(None) == 0  # the surest
    assert found.choice(2) == 2
    assert found.choice(9) == 2


def test_the_last_part_a_point_is_in_and_the_outline_round_them():
    size = (800, 600)
    sun = on_grid(_logits((40, 40), 20), size)
    sea = on_grid(_logits((128, 200), 60), size)

    assert grid_size(size) == (800, 600)
    assert grid_size((4032, 3024)) == (1024, 768)
    assert holding([sun, sea], 40 / 256, 40 / 256) == 0
    assert holding([sun, sea], 0.5, 200 / 256) == 1
    assert holding([sun, sea], 0.95, 0.05) is None
    assert drawn([sun, sea], size).count("M") == 2
    assert drawn([], size) == ""
