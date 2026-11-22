"""How a picture is made to a recipe: the size step (the shape, the way of making it bigger and the
model), the look step, and the two together."""

import pytest

from mado.core.kind import Kind
from mado.core.looks import Look, mado_look
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST, FAST_GRAIN, model_for
from mado.core.recipe import Plan, Recipe, Sizing, Styling, plan
from mado.core.sizes import resolve
from mado.core.touches import Touches


def _plan(recipe: Recipe, width: int = 4032, height: int = 3024, kind: Kind = "photo") -> Plan:
    return plan(
        recipe,
        width,
        height,
        guessed_kind=kind,
        found_focus=(0.4, 0.6),
        starts_on={"photo": "best", "drawing": "best"},
    )


def _look(look_id: str) -> Look:
    found = mado_look(look_id)
    assert found is not None
    return found


def test_a_photo_made_for_a_tv_is_cropped_around_its_subject_and_made_with_the_photo_model():
    made = _plan(Recipe(Sizing(resolve("tv-8k"))))

    assert (made.width, made.height) == (7680, 4320)
    assert made.method == "ai"
    assert made.model == BEST_PHOTO
    assert made.focus == (0.4, 0.6)
    assert made.focus_found
    assert made.scale == pytest.approx(7680 / 4032)
    assert made.how == "Made with the photo model, guessed from the picture."
    assert made.warning is None
    assert made.made_for == made.named == "TV 8K"
    assert made.styling is None
    assert made.look is None


def test_the_owners_choices_win_over_mados_guesses():
    made = _plan(Recipe(Sizing(resolve("tv-8k"), focus=(0.5, 0.1), kind="drawing", quality="fast")))

    assert made.focus == (0.5, 0.1)
    assert not made.focus_found
    assert made.kind == "drawing"
    assert not made.kind_guessed
    assert made.model == FAST
    assert made.how == "Made with the drawing model."


def test_pixel_art_and_screenshots_are_made_bigger_without_ai():
    assert _plan(Recipe(Sizing(resolve("monitor-4k"))), 256, 144, "pixels").method == "pixels"
    assert _plan(Recipe(Sizing(resolve("monitor-4k"))), 1920, 1080, "screenshot").method == "smooth"


def test_a_picture_already_big_enough_is_only_made_smaller():
    made = _plan(Recipe(Sizing(resolve("phone"))), 8000, 6000)

    assert made.method == "shrink"
    assert made.model is None


def test_eight_k_from_a_small_picture_says_it_looks_painted():
    made = _plan(Recipe(Sizing(resolve("tv-8k"))), 640, 360)

    assert made.warning is not None
    assert "painted" in made.warning


def test_the_model_suits_the_kind_the_quality_and_cleaning():
    assert model_for("photo", "fast", clean=True) == FAST
    assert model_for("photo", "fast", clean=False) == FAST_GRAIN
    assert model_for("photo", "best", clean=False) == BEST_PHOTO
    assert model_for("drawing", "best", clean=True) == BEST_DRAWING
    assert model_for("drawing", "fast", clean=True) == FAST
    assert model_for("pixels", "best", clean=True) is None


def test_a_look_alone_keeps_the_pictures_pixels():
    warm = Styling(_look("warm-film"), 0.6, Touches(grain=20))

    made = _plan(Recipe(styling=warm))

    assert (made.width, made.height) == (4032, 3024)
    assert made.method == "keep"
    assert made.model is None
    assert made.frame.sides == "none"
    assert (made.frame.kept.width, made.frame.kept.height) == (4032, 3024)
    assert made.made_for is None
    assert made.styling == warm
    assert made.named == "Warm film"
    assert made.look == "Warm film at 60%"
    assert not made.empty


def test_a_size_and_a_look_are_made_by_one_recipe_named_after_both():
    made = _plan(Recipe(Sizing(resolve("tv-8k")), Styling(_look("silver"), 0.4)))

    assert (made.width, made.height) == (7680, 4320)
    assert made.method == "ai"
    assert made.made_for == "TV 8K"
    assert made.named == "TV 8K, Silver"
    assert made.look == "Silver at 40%"


def test_a_look_that_changes_nothing_isnt_a_step_and_alone_makes_nothing():
    nothing = _plan(Recipe(styling=Styling(_look("original"))))
    sized = _plan(Recipe(Sizing(resolve("tv-8k")), Styling(_look("faded"), 0.0)))

    assert nothing.empty
    assert nothing.styling is None
    assert sized.styling is None
    assert sized.named == "TV 8K"
    assert not sized.empty
