"""The shape a picture takes for a size, the words for it, and where its subject is."""

import numpy as np
import pytest

from mado.core.framing import Box, frame, note, subject
from tests.drawn import spot


def test_a_crop_keeps_the_whole_width_and_loses_some_top_and_bottom_for_a_wider_size():
    made = frame(4032, 3024, 7680, 4320, "crop")

    assert made.kept == Box(0.0, 378.0, 4032.0, 2268.0)
    assert made.canvas == made.kept
    assert made.sides == "top and bottom"
    assert made.kept.width / made.kept.height == pytest.approx(16 / 9)


def test_a_crop_follows_the_focus_point_as_far_as_the_edges_let_it():
    low = frame(4032, 3024, 7680, 4320, "crop", focus=(0.5, 0.9))
    high = frame(4032, 3024, 7680, 4320, "crop", focus=(0.5, 0.0))

    assert low.kept.y == pytest.approx(3024 - 2268)  # as low as it goes
    assert high.kept.y == 0.0


def test_a_crop_for_a_taller_size_loses_some_of_the_sides():
    made = frame(4032, 3024, 1290, 2796, "crop", focus=(0.25, 0.5))

    assert made.sides == "sides"
    assert made.kept.height == 3024.0
    assert made.kept.width == pytest.approx(3024 * 1290 / 2796)
    assert made.kept.x == pytest.approx(0.25 * 4032 - made.kept.width / 2)
    assert made.share == pytest.approx(1 - made.kept.width / 4032)


def test_extending_keeps_all_of_the_picture_and_draws_more_at_two_sides():
    made = frame(4032, 3024, 7680, 4320, "extend")

    assert made.kept == Box(0.0, 0.0, 4032.0, 3024.0)
    assert made.canvas.width == pytest.approx(5376.0)
    assert made.canvas.x == pytest.approx(-672.0)
    assert made.sides == "sides"
    assert made.share == pytest.approx(1 - 4032 / 5376)


def test_a_picture_already_the_right_shape_keeps_its_all():
    made = frame(3840, 2160, 7680, 4320, "crop")

    assert made.sides == "none"
    assert made.kept == Box(0.0, 0.0, 3840.0, 2160.0)


def test_the_words_say_what_the_shape_does():
    crop = frame(4032, 3024, 7680, 4320, "crop")
    extend = frame(4032, 3024, 7680, 4320, "extend")
    same = frame(3840, 2160, 7680, 4320, "crop")
    a4 = frame(4032, 3024, 3508, 2480, "crop")

    assert note(crop, "A TV", 4032, 3024, (7680, 4320)) == (
        "A TV is 16:9 and this picture is 4:3, so a little of the top and bottom goes."
    )
    assert note(extend, "A TV", 4032, 3024, (7680, 4320)) == (
        "A TV is 16:9 and this picture is 4:3, so Mado draws more at the sides."
    )
    assert note(same, "A TV", 3840, 2160, (7680, 4320)) == (
        "This picture is already 16:9, the shape a TV is."
    )
    assert note(a4, "An A4 print", 4032, 3024, (3508, 2480)) == (
        "An A4 print is wider than this picture, so a little of the top and bottom goes."
    )


def test_the_subject_is_the_busiest_part_of_the_picture():
    grey = np.asarray(spot((240, 160), at=(0.8, 0.3)).convert("L"), np.float32)
    grey /= 255.0

    x, y = subject(grey)

    assert x == pytest.approx(0.8, abs=0.08)
    assert y == pytest.approx(0.3, abs=0.08)


def test_a_picture_with_nothing_standing_out_has_its_subject_in_the_middle():
    assert subject(np.full((60, 80), 0.5, np.float32)) == (0.5, 0.5)
