"""How a picture is made to a recipe: the size step (the shape, the way of making it bigger and the
model), the look step, and the two together."""

import pytest

from mado.core.edits import Click, Editing, Erase, Part, Subject
from mado.core.fixes import Fixing
from mado.core.kind import Kind
from mado.core.looks import Look, mado_look
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST, FAST_GRAIN, model_for
from mado.core.recipe import Plan, Recipe, Sizing, Styling, plan
from mado.core.sizes import resolve
from mado.core.touches import Touches


def _plan(
    recipe: Recipe,
    width: int = 4032,
    height: int = 3024,
    kind: Kind = "photo",
    *,
    stops: float | None = None,
    jpeg_saved_at: int | None = None,
) -> Plan:
    return plan(
        recipe,
        width,
        height,
        guessed_kind=kind,
        found_focus=(0.4, 0.6),
        starts_on={"photo": "best", "drawing": "best"},
        stops=stops,
        jpeg_saved_at=jpeg_saved_at,
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


BOAT = Part((Click(0.65, 0.46),))


def test_edits_alone_are_something_to_make_and_keep_the_pictures_size():
    made = _plan(Recipe(editing=Editing((Erase((BOAT,)),), version="1-2")))

    assert not made.empty
    assert made.method == "keep"
    assert (made.width, made.height) == (4032, 3024)
    assert made.named == "Erased"
    assert made.edit == "erased a part"
    assert not made.see_through
    assert made.editing is not None
    assert _plan(Recipe(editing=Editing(()))).empty  # no edits isn't a step


def test_a_cut_out_goes_first_in_the_name_and_leaves_see_through_parts():
    made = _plan(
        Recipe(
            Sizing(resolve("tv-8k")),
            Styling(_look("warm-film"), 0.6),
            Editing((Subject(behind="nothing"),)),
        )
    )

    assert made.named == "Cut out, TV 8K, Warm film"
    assert made.see_through
    assert made.edit == "cut out the subject"


def test_a_look_on_a_part_says_so():
    made = _plan(Recipe(styling=Styling(_look("warm-film"), 0.6, parts=(BOAT,))))

    assert made.look == "Warm film at 60% on a part"
    assert made.named == "Warm film"
    two = _plan(Recipe(styling=Styling(_look("warm-film"), 1.0, parts=(BOAT, BOAT))))
    assert two.look is not None
    assert two.look.endswith("on parts")


def test_fixes_alone_are_something_to_make_and_keep_the_pictures_size():
    made = _plan(Recipe(fixing=Fixing(noise=0.8)))

    assert not made.empty
    assert made.method == "keep"
    assert (made.width, made.height) == (4032, 3024)
    assert made.fix == "took out noise"
    assert made.named == "Cleaned"
    assert made.cleaned_first


def test_a_picture_the_fixes_cleaned_isnt_cleaned_again_as_it_grows():
    sized = Sizing(resolve("tv-8k"), quality="fast")

    cleaned = _plan(Recipe(sized, fixing=Fixing(jpeg=0.6)))
    sharpened = _plan(Recipe(sized, fixing=Fixing(blur=1.0)))

    assert cleaned.model == FAST_GRAIN
    assert cleaned.cleaned_first
    assert sharpened.model == FAST  # the blur fix cleans nothing: Fast still does
    assert not sharpened.cleaned_first
    assert cleaned.named == "Cleaned, TV 8K"


def test_a_dark_photos_fix_cleans_and_names_only_as_the_picture_measures():
    sized = Sizing(resolve("tv-8k"), quality="fast")
    asked = Recipe(sized, fixing=Fixing(dark=0.0))

    bright = _plan(asked, stops=0.0)
    dim = _plan(asked, stops=1.0)
    night = _plan(asked, stops=3.0)
    unmeasured = _plan(asked)

    assert bright.fixing is None  # not dark: nothing to fix
    assert bright.fix is None
    assert bright.named == "TV 8K"
    assert bright.model == FAST  # cleaned by no one else, so Fast cleans it
    assert not bright.cleaned_first
    assert dim.fix == "brightened it"
    assert dim.model == FAST  # its denoise took out only what brightening brought
    assert night.model == FAST_GRAIN
    assert night.cleaned_first
    assert night.named == "Brightened, TV 8K"
    assert unmeasured.fix == "brightened it"  # planned as if it's dark, till it's measured
    assert _plan(Recipe(fixing=Fixing(dark=0.0)), stops=0.2).empty


def test_a_fix_at_nothing_isnt_something_to_make():
    assert _plan(Recipe(fixing=Fixing(noise=0.0))).empty
    made = _plan(Recipe(Sizing(resolve("tv-8k"), quality="fast"), fixing=Fixing(noise=0.0)))
    assert made.model == FAST
    assert made.fix is None


def test_a_batchs_jpeg_blocks_go_as_hard_as_each_jpeg_was_squeezed():
    own = Recipe(fixing=Fixing(jpeg="own", jpeg_quality="best"))

    squeezed = _plan(own, jpeg_saved_at=30)
    not_jpeg = _plan(own)

    assert squeezed.fixing == Fixing(jpeg=0.7, jpeg_quality="best")
    assert squeezed.fix == "took out JPEG blocks"
    assert not_jpeg.fixing is None
    assert not_jpeg.empty


def test_jpeg_blocks_start_on_what_this_pc_has_unless_chosen():
    starts = plan(
        Recipe(fixing=Fixing(jpeg=0.5)),
        800,
        600,
        guessed_kind="photo",
        found_focus=(0.5, 0.5),
        starts_on={"photo": "fast", "drawing": "fast"},
        fix_starts_on="best",
    )
    chosen = _plan(Recipe(fixing=Fixing(jpeg=0.5, jpeg_quality="best")))

    assert starts.fix_quality == "best"
    assert _plan(Recipe(fixing=Fixing(jpeg=0.5))).fix_quality == "fast"
    assert chosen.fix_quality == "best"


def test_the_edits_then_the_fixes_then_the_size_name_a_new_picture():
    erase = Editing((Erase((Part((Click(0.5, 0.5),)),)),), "v1")

    made = _plan(Recipe(Sizing(resolve("tv-8k")), editing=erase, fixing=Fixing(dark=0.0)))

    assert made.named == "Erased, Brightened, TV 8K"
    assert made.fix == "brightened it"
