"""How a picture is made to a recipe: the shape, the way of making it bigger and the model."""

import pytest

from mado.core.kind import Kind
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST, FAST_GRAIN, model_for
from mado.core.recipe import Plan, Recipe, plan
from mado.core.sizes import resolve


def _plan(recipe: Recipe, width: int = 4032, height: int = 3024, kind: Kind = "photo") -> Plan:
    return plan(
        recipe,
        width,
        height,
        guessed_kind=kind,
        found_focus=(0.4, 0.6),
        starts_on={"photo": "best", "drawing": "best"},
    )


def test_a_photo_made_for_a_tv_is_cropped_around_its_subject_and_made_with_the_photo_model():
    made = _plan(Recipe(resolve("tv-8k")))

    assert (made.width, made.height) == (7680, 4320)
    assert made.method == "ai"
    assert made.model == BEST_PHOTO
    assert made.focus == (0.4, 0.6)
    assert made.focus_found
    assert made.scale == pytest.approx(7680 / 4032)
    assert made.how == "Made with the photo model, guessed from the picture."
    assert made.warning is None


def test_the_owners_choices_win_over_mados_guesses():
    made = _plan(Recipe(resolve("tv-8k"), focus=(0.5, 0.1), kind="drawing", quality="fast"))

    assert made.focus == (0.5, 0.1)
    assert not made.focus_found
    assert made.kind == "drawing"
    assert not made.kind_guessed
    assert made.model == FAST
    assert made.how == "Made with the drawing model."


def test_pixel_art_and_screenshots_are_made_bigger_without_ai():
    assert _plan(Recipe(resolve("monitor-4k")), 256, 144, "pixels").method == "pixels"
    assert _plan(Recipe(resolve("monitor-4k")), 1920, 1080, "screenshot").method == "smooth"


def test_a_picture_already_big_enough_is_only_made_smaller():
    made = _plan(Recipe(resolve("phone")), 8000, 6000)

    assert made.method == "shrink"
    assert made.model is None


def test_eight_k_from_a_small_picture_says_it_looks_painted():
    made = _plan(Recipe(resolve("tv-8k")), 640, 360)

    assert made.warning is not None
    assert "painted" in made.warning


def test_the_model_suits_the_kind_the_quality_and_cleaning():
    assert model_for("photo", "fast", clean=True) == FAST
    assert model_for("photo", "fast", clean=False) == FAST_GRAIN
    assert model_for("photo", "best", clean=False) == BEST_PHOTO
    assert model_for("drawing", "best", clean=True) == BEST_DRAWING
    assert model_for("drawing", "fast", clean=True) == FAST
    assert model_for("pixels", "best", clean=True) is None
