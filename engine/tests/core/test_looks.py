"""Mado's own looks: the list, what each does to colours, a look at a strength with fade in the
same table, and the words for it."""

import re

import numpy as np
import pytest

from mado.core.grids import SIDE, identity, sample
from mado.core.looks import ORIGINAL, Look, built_in, changes, label, mado_look, phrase, table
from mado.core.touches import NONE, Touches

# Film brands, camera makers and apps' own filter names: never a look's name.
_NOT_OURS = (
    "kodak", "portra", "ektar", "ektachrome", "kodachrome", "fuji", "velvia", "provia", "astia",
    "acros", "eterna", "ilford", "agfa", "polaroid", "lomo", "cinestill", "leica", "canon",
    "nikon", "sony", "olympus", "hasselblad", "instagram", "vsco", "clarendon", "gingham",
    "juno", "lark", "valencia", "nashville", "inkwell", "vivid", "dramatic", "silvertone",
    "noir", "mono", "matte", "chrome", "kelvin", "toaster", "hudson", "amaro", "reyes",
)  # fmt: skip
_GREYS = np.repeat(np.linspace(0, 1, 64, dtype=np.float32)[:, None], 3, axis=1)


def _look(look_id: str) -> Look:
    found = mado_look(look_id)
    assert found is not None
    return found


def test_the_list_starts_with_the_original_then_the_boards_looks_then_mados_own():
    names = [look.name for look in built_in()]

    assert names[:9] == [
        "Original",
        "Warm film",
        "Cool film",
        "Faded",
        "Teal and orange",
        "Silver",
        "Golden hour",
        "Night neon",
        "Duotone",
    ]
    assert len(names) == len(set(names)) == 14
    assert len({look.id for look in built_in()}) == 14


def test_no_look_is_named_after_a_film_a_camera_or_an_apps_filter():
    for look in built_in():
        words = set(re.findall(r"[a-z]+", look.name.casefold()))
        assert not words & set(_NOT_OURS), look.name


def test_every_look_but_the_original_changes_colours_and_stays_within_them():
    assert _look(ORIGINAL).grid is None
    for look in built_in()[1:]:
        assert look.grid is not None
        assert look.grid.shape == (SIDE, SIDE, SIDE, 3)
        assert look.grid.min() >= 0.0
        assert look.grid.max() <= 1.0
        assert np.abs(look.grid - identity(SIDE)).max() > 0.05, look.name


def test_no_look_turns_a_light_grey_darker_than_a_darker_one():
    for look in built_in()[1:]:
        assert look.grid is not None
        light = sample(look.grid, _GREYS).mean(axis=1)
        assert (np.diff(light) >= -1e-4).all(), look.name


def test_silver_is_black_and_white_and_the_toned_looks_are_one_colour_through_its_greys():
    silver = _look("silver").grid
    assert silver is not None
    assert np.array_equal(silver[..., 0], silver[..., 1])
    assert np.array_equal(silver[..., 1], silver[..., 2])
    sepia = _look("sepia-print").grid
    assert sepia is not None
    mid = sample(sepia, np.array([[0.5, 0.5, 0.5]], np.float32))[0]
    assert mid[0] > mid[1] > mid[2]  # brown


def test_a_look_at_a_strength_is_mixed_with_the_colours_as_they_were():
    warm = _look("warm-film")
    assert warm.grid is not None

    half = table(warm, 0.5, NONE)

    assert half is not None
    assert np.allclose(half, (identity(SIDE) + warm.grid) / 2, atol=1e-6)
    assert table(warm, 1.0, NONE) is not None
    assert table(warm, 0.0, NONE) is None
    assert table(_look(ORIGINAL), 1.0, NONE) is None


def test_fade_goes_into_the_same_table_even_on_the_original():
    faded = table(_look(ORIGINAL), 1.0, Touches(fade=100))

    assert faded is not None
    black, white = faded[0, 0, 0], faded[-1, -1, -1]
    assert black.min() > 0.1
    assert white.max() < 0.97


def test_whether_a_look_changes_the_picture_at_all():
    assert changes(_look("faded"), 0.6, NONE)
    assert not changes(_look("faded"), 0.0, NONE)
    assert not changes(_look(ORIGINAL), 1.0, NONE)
    assert changes(_look(ORIGINAL), 1.0, Touches(dust=5))


@pytest.mark.parametrize(
    ("look_id", "strength", "touches", "named", "said"),
    [
        ("warm-film", 1.0, NONE, "Warm film", "Warm film"),
        ("warm-film", 0.6, Touches(grain=20), "Warm film", "Warm film at 60%"),
        (ORIGINAL, 1.0, Touches(grain=20), "Grain", "grain"),
        (ORIGINAL, 1.0, Touches(leak=40), "Light leak", "light leak"),
        (ORIGINAL, 1.0, Touches(grain=20, dust=10), "Finishing touches", "finishing touches"),
        ("silver", 0.0, Touches(vignette=30), "Vignette", "vignette"),
    ],
)
def test_the_words_for_a_look(
    look_id: str, strength: float, touches: Touches, named: str, said: str
):
    look = _look(look_id)

    assert label(look, strength, touches) == named
    assert phrase(look, strength, touches) == said


def test_a_look_mado_doesnt_have_is_none():
    assert mado_look("kodachrome") is None
