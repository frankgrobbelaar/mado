"""Finishing touches: their amounts, and the shapes and numbers each is made of, the same for the
same picture however much of it is asked for."""

import numpy as np

from mado.core.touches import (
    GRAIN_CELLS,
    NONE,
    Touches,
    fade,
    grain_cell,
    grain_weights,
    leak,
    leak_light,
    named,
    noise,
    specks,
    vignette,
    words,
)


def test_touches_come_from_their_amounts_by_name_held_to_0_to_100():
    touches = named({"grain": 20, "vignette": 135, "dust": -4, "sparkle": 50})

    assert touches == Touches(grain=20, vignette=100)
    assert touches.on() == ["grain", "vignette"]
    assert words(touches) == "grain 20, vignette 100"
    assert NONE.on() == []
    assert not Touches(fade=30).spatial()
    assert Touches(dust=1).spatial()


def test_fade_lifts_black_and_brings_white_down_keeping_their_order():
    values = np.linspace(0, 1, 11, dtype=np.float32)

    faded = fade(values, 100)

    assert faded[0] > 0.1
    assert faded[-1] < 0.97
    assert (np.diff(faded) > 0).all()
    assert np.allclose(fade(values, 0), values)


def test_grain_is_the_same_for_the_same_picture_however_much_of_it_is_asked_for():
    whole = noise(41, range(0, 40), range(0, 60))
    part = noise(41, range(10, 25), range(30, 50))

    assert np.array_equal(part, whole[10:25, 30:50])
    assert not np.array_equal(noise(42, range(0, 40), range(0, 60)), whole)
    assert abs(float(whole.mean())) < 0.1
    assert 0.8 < float(whole.std()) < 1.2
    assert np.array_equal(noise(7, range(-5, 0), range(0, 3)), noise(7, range(-5, 0), range(0, 3)))


def test_grain_specks_are_sized_by_the_short_side():
    assert grain_cell(GRAIN_CELLS * 2) == 2.0
    assert grain_cell(700) == 0.5


def test_grain_is_strongest_in_the_mid_tones_and_grows_with_its_amount():
    weights = grain_weights(100)

    assert weights.shape == (256,)
    assert weights[128] > weights[0]
    assert weights[128] > weights[255]
    assert 25 < weights[128] < 30  # at 100, a speck moves mid-grey about 28 levels
    assert np.allclose(grain_weights(50), weights / 2)
    assert not grain_weights(0).any()


def test_a_vignette_darkens_the_corners_softly_and_leaves_the_middle():
    across = np.array([0.0, 0.5, 1.0], np.float32)
    down = np.array([0.0, 0.5, 1.0], np.float32)

    kept = vignette(across, down, 100)

    assert kept[0] == 1.0
    assert kept[0] > kept[1] > kept[2]
    assert np.allclose(vignette(across, down, 0), 1.0)


def test_a_light_leak_comes_in_at_an_edge_the_same_for_the_same_picture():
    at = leak(9)

    assert at == leak(9)
    assert at.x < 0 or at.x > 1  # just past the left or right edge
    near_x = 0.02 if at.x < 0 else 0.98
    near = leak_light(np.array([near_x], np.float32), np.array([at.y], np.float32), 1.5, at, 100)
    far_x = 0.98 if at.x < 0 else 0.02
    far = leak_light(np.array([far_x], np.float32), np.array([at.y], np.float32), 1.5, at, 100)
    assert near[0] > 0.3
    assert far[0] < near[0] / 4


def test_dust_is_the_same_specks_for_the_same_picture_more_as_its_amount_grows():
    some = specks(5, 20, 1.5)
    more = specks(5, 80, 1.5)

    assert some == specks(5, 20, 1.5)
    assert len(more) > len(some) > 0
    assert more[: len([each for each in some if not each.hair])] == [
        each for each in some if not each.hair
    ]
    assert specks(5, 0, 1.5) == []
    assert len(specks(5, 100, 3.0)) > len(specks(5, 100, 1.0))
    assert any(each.hair for each in specks(5, 100, 1.5))
