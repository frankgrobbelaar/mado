"""Restoring old photos by its rules: the restore step and its words, what a batch's step does to
each picture, telling a black-and-white or sepia print from a colour photo, putting colour onto a
picture's own light, faded colours brought back by classic means, and the scratch detector's
canvases and mask: found, united, grown, painted and taken away."""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from mado.core.edits import Stroke
from mado.core.restore import (
    CANVASES,
    GROW,
    MASK_SHORT,
    MOST_MASK,
    Colours,
    RestoreError,
    Restoring,
    canvas_for,
    coloured,
    colours_of,
    covers,
    detail,
    faded_back,
    for_picture,
    found_mask,
    grey_input,
    grown_round,
    lab,
    label,
    levels_of,
    lightness,
    marked,
    mask_size,
    models_for,
    phrase,
    restoring_from,
    restoring_json,
    rgb_of,
    uncanvassed,
    unchanged,
)

# Made-up pictures, drawn here: a landscape of sky, sea, sand and a red boat.


def _scene(width: int = 384, height: int = 256) -> np.ndarray:
    image = Image.new("RGB", (width, height), (110, 160, 225))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, height // 2, width, height], fill=(30, 90, 160))
    draw.rectangle([0, height * 3 // 4, width, height], fill=(220, 200, 140))
    draw.polygon(
        [(width // 3, height // 2), (width // 2, height // 2), (width * 5 // 12, height * 2 // 3)],
        fill=(200, 40, 30),
    )
    draw.ellipse([width - 80, 20, width - 30, 70], fill=(250, 220, 90))
    rng = np.random.default_rng(4)
    noise = rng.normal(0, 3, (height, width, 1))
    return np.clip(np.asarray(image, np.float32) + noise, 0, 255).astype(np.float32) / 255.0


def _toned(rgb: np.ndarray, tint: tuple[float, float, float]) -> np.ndarray:
    light = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    return np.clip(light[..., None] * np.array(tint, np.float32), 0, 1).astype(np.float32)


def _faded(rgb: np.ndarray) -> np.ndarray:
    """A colour print faded as old ones do: its colours washed out, gone warm, its blacks lifted
    and its whites dulled."""
    light = (rgb @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    washed = light + (rgb - light) * 0.5
    warm = washed * np.array([1.0, 0.92, 0.8], np.float32)
    return (0.12 + 0.76 * warm).astype(np.float32)


# The restore step.


def test_a_restore_step_is_read_from_its_json_and_written_back():
    data = {
        "version": "1a-2b",
        "scratches": {
            "strokes": [{"points": [[0.1, 0.2], [0.3, 0.4]], "size": 0.02, "take": True}]
        },
        "colour": {"strength": 0.8},
        "faded": None,
    }
    step = restoring_from(data)
    assert step == Restoring(
        scratches=(Stroke(((0.1, 0.2), (0.3, 0.4)), 0.02, True),),
        colour=0.8,
        version="1a-2b",
    )
    assert restoring_json(step) == {**data, "each": False}
    assert restoring_from(restoring_json(step)) == step


def test_a_restore_step_with_nothing_on_is_none_and_settings_are_held_to_0_to_1():
    assert restoring_from(None) is None
    assert restoring_from({"scratches": None, "colour": None, "faded": None}) is None
    step = restoring_from({"colour": {"strength": 3}, "faded": {"strength": -1}})
    assert step is not None
    assert (step.colour, step.faded) == (1.0, 0.0)


def test_a_step_that_isnt_a_restore_step_is_refused_with_a_sentence():
    with pytest.raises(RestoreError, match="Mado can't read"):
        restoring_from({"colour": "lots"})
    with pytest.raises(RestoreError, match="Mado can't read"):
        restoring_from(["colour"])


def test_the_steps_on_are_listed_in_the_order_theyre_made():
    step = Restoring(scratches=(), colour=0.5, faded=0.4)
    assert step.on == ("scratches", "colour", "faded")
    assert Restoring(faded=0.4).on == ("faded",)


def test_history_and_save_say_what_restoring_did():
    assert phrase(None) is None
    assert phrase(Restoring(scratches=())) == "filled its scratches and dust"
    assert phrase(Restoring(colour=0.8)) == "coloured it"
    assert phrase(Restoring(faded=0.6)) == "brought its faded colours back"
    assert (
        phrase(Restoring(scratches=(), colour=0.8))
        == "filled its scratches and dust and coloured it"
    )
    assert (
        phrase(Restoring(scratches=(), faded=0.6))
        == "filled its scratches and dust and brought its faded colours back"
    )
    assert phrase(Restoring(colour=0.0)) is None  # at 0% it changes nothing
    # A batch's, before each picture is read: it colours some, brings back others' colours.
    assert (
        phrase(Restoring(colour=0.8, faded=0.6, each=True))
        == "coloured it or brought its faded colours back"
    )


def test_a_new_picture_is_named_coloured_or_restored():
    assert label(None) is None
    assert label(Restoring(colour=0.8)) == "Coloured"
    assert label(Restoring(scratches=())) == "Restored"
    assert label(Restoring(faded=0.5)) == "Restored"
    assert label(Restoring(scratches=(), colour=0.8)) == "Restored"


def test_a_batch_says_its_restore_step_in_words():
    assert detail(Restoring(colour=0.8, each=True)) == "Black and white and sepia coloured at 80%"
    assert (
        detail(Restoring(colour=1.0, faded=0.6, each=True))
        == "Black and white and sepia coloured, faded colours brought back at 60%"
    )


def test_a_batch_colours_only_what_isnt_in_colour_and_brings_back_only_what_is():
    each = Restoring(colour=0.8, faded=0.6, each=True)
    assert for_picture(each, "grey") == Restoring(colour=0.8, each=True)
    assert for_picture(each, "toned") == Restoring(colour=0.8, each=True)
    assert for_picture(each, "colour") == Restoring(faded=0.6, each=True)
    assert for_picture(Restoring(colour=0.8, each=True), "colour") is None
    # A picture's own page does as the owner asks, whatever the picture is.
    asked = Restoring(colour=0.8)
    assert for_picture(asked, "colour") == asked


def test_a_batch_line_says_why_restoring_changed_nothing():
    assert "already in colour" in unchanged(Restoring(colour=0.8, each=True))
    assert "black and white or a toned print" in unchanged(Restoring(faded=0.5, each=True))


def test_the_models_a_restore_step_needs():
    assert models_for(None) == []
    assert models_for(Restoring(scratches=())) == ["oldphoto-scratch-detector", "lama"]
    assert models_for(Restoring(colour=0.5)) == ["ddcolor-tiny"]
    assert models_for(Restoring(faded=0.5)) == []  # classic means
    assert models_for(Restoring(scratches=(), colour=0.5)) == [
        "oldphoto-scratch-detector",
        "lama",
        "ddcolor-tiny",
    ]


# Telling them apart.


def test_a_black_and_white_picture_is_told_from_a_toned_print_and_a_colour_photo():
    scene = _scene()
    grey = np.repeat((scene @ np.array([0.299, 0.587, 0.114], np.float32))[..., None], 3, axis=2)
    assert colours_of(grey).kind == "grey"
    sepia = colours_of(_toned(scene, (1.0, 0.86, 0.66)))
    assert (sepia.kind, sepia.tone) == ("toned", "sepia")
    blue = colours_of(_toned(scene, (0.55, 0.78, 1.0)))
    assert (blue.kind, blue.tone) == ("toned", "toned")
    found = colours_of(scene)
    assert (found.kind, found.tone) == ("colour", None)


def test_a_faded_colour_print_is_still_a_colour_photo():
    assert colours_of(_faded(_scene())).kind == "colour"


def test_a_toned_print_with_a_scanners_colour_noise_is_still_toned():
    noisy = _toned(_scene(), (1.0, 0.86, 0.66))
    noisy = noisy + np.random.default_rng(2).normal(0, 0.01, noisy.shape).astype(np.float32)
    assert colours_of(np.clip(noisy, 0, 1)).kind == "toned"


def test_what_mado_measures_is_a_value_it_can_keep():
    found = colours_of(_scene())
    assert isinstance(found, Colours)
    assert found.chroma > 10
    assert found.spread > 2


# Colour onto light.


def test_lab_and_back_keep_the_colours():
    scene = _scene()
    assert np.abs(rgb_of(lab(scene)) - scene).max() < 1e-3
    assert np.allclose(lightness(scene), lab(scene)[..., 0], atol=1e-3)


def test_the_colouring_model_sees_the_picture_grey_at_its_own_size():
    shown = grey_input(_toned(_scene(512, 512), (1.0, 0.86, 0.66)))
    assert shown.shape == (1, 3, 512, 512)
    assert shown.dtype == np.float32
    assert np.abs(shown[0, 0] - shown[0, 1]).max() < 2e-3  # grey: its colours taken out
    assert float(shown.min()) >= 0.0
    assert float(shown.max()) <= 1.0


def test_colour_goes_onto_the_pictures_own_light():
    scene = _scene()
    grey = np.repeat((scene @ np.array([0.299, 0.587, 0.114], np.float32))[..., None], 3, axis=2)
    ab = lab(scene)[..., 1:]
    made = coloured(grey, ab, 1.0)
    assert np.abs(lightness(made) - lightness(grey)).mean() < 0.6  # its own light kept
    assert np.abs(lab(made)[..., 1:] - ab).mean() < 2.5  # the colours given
    assert np.abs(coloured(grey, ab, 0.0) - grey).max() < 1e-3  # at 0%: as it was


def test_a_sepia_print_coloured_halfway_mixes_its_tone_with_the_colours():
    scene = _scene()
    sepia = _toned(scene, (1.0, 0.86, 0.66))
    guessed = lab(scene)[..., 1:]
    half = lab(coloured(sepia, guessed, 0.5))[..., 1:]
    expected = (lab(sepia)[..., 1:] + guessed) / 2
    assert np.abs(half - expected).mean() < 2.5


# Faded colours back.


def test_faded_colours_come_back_nearer_the_truth():
    truth = _scene()
    faded = _faded(truth)
    levels = levels_of(faded)
    back = faded_back(faded, levels, 1.0)

    def apart(one: np.ndarray, other: np.ndarray) -> float:
        return float(np.sqrt(((lab(one) - lab(other)) ** 2).sum(-1)).mean())

    assert apart(back, truth) < apart(faded, truth) * 0.5
    assert np.abs(faded_back(faded, levels, 0.0) - faded).max() < 1e-6


def test_faded_colours_back_leave_a_grey_picture_grey():
    scene = _scene()
    grey = np.repeat((scene @ np.array([0.299, 0.587, 0.114], np.float32))[..., None], 3, axis=2)
    dull = 0.1 + 0.8 * grey
    back = faded_back(dull, levels_of(dull), 1.0)
    assert np.abs(back[..., 0] - back[..., 1]).max() < 2e-3
    assert np.abs(back[..., 1] - back[..., 2]).max() < 2e-3


def test_levels_from_a_picture_leave_out_its_see_through_parts():
    faded = _faded(_scene())
    shown = np.ones(faded.shape[:2], bool)
    shown[:, :40] = False
    with_black = faded.copy()
    with_black[:, :40] = 0.0  # what its see-through parts hide
    assert levels_of(with_black, shown) == levels_of(faded[:, 40:])


# Scratches: the detector's canvases and the mask.


def test_the_detector_sees_a_picture_grey_on_a_canvas_of_a_fixed_size():
    grey = np.full((300, 400), 128, np.uint8)
    for short in CANVASES:
        canvas, used, turned = canvas_for(grey, short)
        assert canvas.shape == (1, 1, *CANVASES[short])
        assert canvas.dtype == np.float32
        assert used[0] == short
        assert used[1] % 16 == 0
        assert not turned
        assert np.allclose(canvas, (128 / 255 - 0.5) / 0.5, atol=1e-5)


def test_a_portrait_picture_is_turned_onto_the_canvas_and_back():
    grey = np.zeros((400, 300), np.uint8)
    grey[:, :10] = 255  # a bright strip down its left side
    canvas, used, turned = canvas_for(grey, 256)
    assert turned
    assert canvas.shape == (1, 1, *CANVASES[256])
    answer = (canvas[0, 0] + 1) / 2  # what the detector says, as if it said what it saw
    back = uncanvassed(answer, used, turned)
    assert back.shape[0] > back.shape[1]  # the picture's own way round again
    assert back[:, :2].mean() > 0.9
    assert back[:, -10:].mean() < 0.1


def test_a_panorama_wider_than_the_canvas_fits_its_long_side():
    grey = np.zeros((100, 1000), np.uint8)
    canvas, used, _turned = canvas_for(grey, 256)
    assert canvas.shape == (1, 1, *CANVASES[256])
    assert used[1] == CANVASES[256][1]
    assert used[0] < 256


def test_the_mask_is_made_at_the_size_mado_measured_it_at():
    assert mask_size(4032, 3024) == (1024, MASK_SHORT)
    assert mask_size(3024, 4032) == (MASK_SHORT, 1024)
    assert mask_size(640, 480) == (640, 480)  # a small picture: its own size


def test_what_the_detector_finds_at_two_sizes_is_united_then_grown():
    coarse = np.zeros((48, 64), np.float32)
    coarse[10, 10] = 0.9  # one cell, sure enough
    coarse[30, 30] = 0.3  # one not
    fine = np.zeros((96, 128), np.float32)
    fine[80, 100] = 0.45
    mask = found_mask([coarse, fine], (128, 96))
    assert mask.shape == (96, 128)
    assert mask[21, 21] == 255
    assert mask[80, 100] == 255
    assert mask[60, 60] == 0  # 0.3 is under the line
    # grown by GROW pixels round each found pixel
    assert mask[80, 100 + GROW] == 255
    assert mask[80, 100 + GROW + 1] == 0


def test_a_mask_grows_round_not_square():
    mask = np.zeros((21, 21), np.uint8)
    mask[10, 10] = 255
    grown = grown_round(mask, 3)
    assert grown[10, 13] == 255
    assert grown[13, 10] == 255
    assert grown[13, 13] == 0  # a corner of the square isn't reached


def test_strokes_add_to_what_was_found_and_alt_takes_away_in_order():
    found = np.zeros((100, 200), np.uint8)
    found[50, 20:180] = 255  # a long scratch found across it
    painted = marked(
        found,
        (
            Stroke(((0.1, 0.1), (0.1, 0.9)), 0.04),  # a dark scratch it missed, down the left
            Stroke(((0.6, 0.5), (0.95, 0.5)), 0.1, take=True),  # a line that isn't a scratch
        ),
    )
    assert painted[50, 40] == 255  # still found
    assert painted[50, 150] == 0  # taken away
    assert painted[80, 20] == 255  # painted
    assert found[50, 150] == 255  # what was found is left as it was


def test_how_much_of_the_picture_a_mask_covers():
    mask = np.zeros((10, 10), np.uint8)
    mask[:5] = 255
    assert covers(mask) == 0.5
    assert MOST_MASK < 1.0
