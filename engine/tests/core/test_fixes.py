"""The quick fixes by their rules: each fix's setting and words, the models they need, the order
they're made in, a JPEG's own quality from its tables, how dark a picture is, brightening it,
local contrast, the guard that holds the blur model back in flat places, and what Mado
suggests."""

import io
import math
from typing import cast

import numpy as np
import pytest
from PIL import Image

from mado.core.fixes import (
    FBCNN,
    NAFNET,
    SCUNET,
    FixError,
    Fixing,
    blocks_suggested,
    brightening,
    clahe_luts,
    cleans,
    contrasted,
    dark_suggested,
    debanded,
    detail,
    fixing_from,
    fixing_json,
    for_picture,
    guarded,
    jpeg_quality,
    label,
    linear,
    local_range,
    models_for,
    phrase,
    stages,
    strength_for,
    toned,
    unchanged,
)


def _tables(quality: int, subsampling: int = 2) -> dict[int, list[int]]:
    image = Image.new("RGB", (32, 32), (120, 80, 40))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality, subsampling=subsampling)
    out.seek(0)
    with Image.open(out) as saved:
        tables = cast("dict[int, list[int]]", getattr(saved, "quantization", {}))
        return {key: list(values) for key, values in tables.items()}


def test_a_fix_step_is_read_from_its_json_and_written_back():
    data = {
        "noise": {"strength": 0.8},
        "blur": None,
        "jpeg": {"quality": "best", "strength": 0.7},
        "dark": {"contrast": 0.25},
    }

    fixing = fixing_from(data)

    assert fixing == Fixing(noise=0.8, jpeg=0.7, jpeg_quality="best", dark=0.25)
    assert fixing_from(fixing_json(fixing)) == fixing
    assert fixing_from(None) is None
    assert fixing_from({}) is None  # nothing on is no step
    assert fixing_from({"jpeg": {"quality": None, "strength": 2}}) == Fixing(jpeg=1.0)


def test_a_batchs_jpeg_blocks_go_by_each_jpegs_own_quality():
    own = fixing_from({"jpeg": {"quality": "best", "strength": None}})

    assert own == Fixing(jpeg="own", jpeg_quality="best")
    assert fixing_json(own) == {
        "noise": None,
        "blur": None,
        "jpeg": {"quality": "best", "strength": None},
        "dark": None,
    }
    assert for_picture(own, 30) == Fixing(jpeg=0.7, jpeg_quality="best")
    assert for_picture(own, None) is None  # not a JPEG: no blocks to take out
    both = Fixing(noise=1.0, jpeg="own")
    assert for_picture(both, None) == Fixing(noise=1.0)
    assert for_picture(Fixing(jpeg=0.4), None) == Fixing(jpeg=0.4)  # set by hand: as it's set
    assert detail(Fixing(jpeg="own"), "best") == "JPEG blocks as each JPEG was saved, Best"


def test_jpeg_blocks_start_as_hard_as_the_jpeg_was_squeezed():
    assert strength_for(30) == pytest.approx(0.7)
    assert strength_for(98) == pytest.approx(0.1)  # never nothing, once it's asked for
    assert strength_for(2) == pytest.approx(0.9)


def test_a_fix_step_that_makes_no_sense_says_why():
    with pytest.raises(FixError, match="fix"):
        fixing_from({"noise": "lots"})
    with pytest.raises(FixError):
        fixing_from([1, 2])


def test_the_words_say_what_each_fix_does_in_history_and_in_a_name():
    assert phrase(Fixing(noise=1.0)) == "took out noise"
    assert phrase(Fixing(noise=1.0, jpeg=0.5)) == "took out noise and JPEG blocks"
    assert phrase(Fixing(blur=1.0, dark=0.0)) == "brightened it and mended the blur"
    assert (
        phrase(Fixing(noise=1.0, blur=1.0, jpeg=0.5, dark=0.0))
        == "took out noise and JPEG blocks, brightened it and mended the blur"
    )
    assert phrase(None) is None
    assert label(Fixing(noise=1.0, jpeg=0.4)) == "Cleaned"
    assert label(Fixing(blur=1.0)) == "Sharpened"
    assert label(Fixing(dark=0.0)) == "Brightened"
    assert label(Fixing(dark=0.0, noise=1.0)) == "Fixed"
    assert label(None) is None


def test_the_words_say_only_what_the_fixes_made_of_the_picture_as_it_measured():
    assert phrase(Fixing(dark=0.0), stops=0.6) is None  # not dark: left as it was
    assert phrase(Fixing(dark=0.0, noise=1.0), stops=0.0) == "took out noise"
    assert phrase(Fixing(dark=0.0), stops=3.0) == "brightened it"
    assert label(Fixing(dark=0.0), stops=0.0) is None
    assert label(Fixing(dark=0.0, blur=1.0), stops=0.0) == "Sharpened"
    assert phrase(Fixing(noise=0.0)) is None  # at 0%, nothing comes out
    assert label(Fixing(noise=0.0, blur=0.5)) == "Sharpened"


def test_why_the_fixes_change_nothing_is_said_in_a_sentence():
    assert unchanged(Fixing(dark=0.0)) == "It isn't dark, so there was nothing to fix."
    assert unchanged(Fixing(jpeg="own")) == (
        "It isn't a JPEG, so it has no JPEG blocks: there was nothing to fix."
    )
    assert unchanged(Fixing(dark=0.0, jpeg="own")) == (
        "It isn't dark and it isn't a JPEG, so there was nothing to fix."
    )
    assert unchanged(Fixing(noise=0.0)) == "The fixes are at 0%, so there was nothing to fix."


def test_each_fix_needs_its_model_and_one_model_is_never_run_twice():
    assert models_for(Fixing(noise=1.0), "best") == [SCUNET]
    assert models_for(Fixing(jpeg=0.5), "best") == [FBCNN]
    assert models_for(Fixing(jpeg=0.5), "fast") == [SCUNET]
    assert models_for(Fixing(jpeg=0.5, noise=1.0, dark=0.0), "fast") == [SCUNET]
    assert models_for(Fixing(jpeg=0.5, dark=0.0), "best") == [FBCNN, SCUNET]
    assert models_for(Fixing(blur=1.0), "best") == [NAFNET]
    assert models_for(None, "best") == []


def test_the_fixes_are_made_blocks_first_then_brightening_noise_blur_and_contrast():
    every = Fixing(noise=0.6, blur=1.0, jpeg=0.7, jpeg_quality="best", dark=0.3)

    made = stages(every, "best", stops=3.0)

    assert [stage.kind for stage in made] == ["blocks", "brighten", "noise", "blur", "contrast"]
    assert made[0].model == FBCNN
    assert made[0].amount == pytest.approx(0.7)
    assert made[2].model == SCUNET
    assert made[2].amount == pytest.approx(1.0)


def test_scunet_cleans_noise_and_blocks_in_one_pass_at_the_stronger_strength():
    made = stages(Fixing(noise=0.4, jpeg=0.3, jpeg_quality="fast"), "fast", stops=0.0)

    assert [stage.kind for stage in made] == ["noise"]
    assert made[0].amount == pytest.approx(0.6)  # Fast's blend: twice the JPEG strength


def test_a_fix_at_nothing_makes_nothing():
    assert stages(Fixing(noise=0.0), "best", stops=0.0) == []
    assert stages(Fixing(blur=0.0), "best", stops=0.0) == []
    assert stages(Fixing(jpeg=0.0, jpeg_quality="best"), "best", stops=0.0) == []
    assert stages(Fixing(jpeg=0.0, jpeg_quality="fast"), "fast", stops=0.0) == []


def test_a_picture_that_isnt_dark_is_left_as_it_is_by_the_dark_photo_fix():
    assert stages(Fixing(dark=0.6), "best", stops=0.8) == []  # no brightening, nor contrast
    made = stages(Fixing(dark=0.6), "best", stops=1.2)
    assert [stage.kind for stage in made] == ["brighten", "noise", "contrast"]


def test_the_upscaler_keeps_its_grain_only_where_the_fixes_cleaned_the_picture():
    assert cleans(Fixing(noise=0.5), stops=0.0)  # as much as asked: Fast mustn't take more
    assert cleans(Fixing(jpeg=0.4), stops=0.0)
    assert not cleans(Fixing(noise=0.0), stops=0.0)
    assert not cleans(Fixing(blur=1.0), stops=4.0)
    # A dark photo's denoise takes out only what brightening brought, till it runs in full.
    assert not cleans(Fixing(dark=0.0), stops=0.0)
    assert not cleans(Fixing(dark=0.0), stops=1.0)
    assert cleans(Fixing(dark=0.0), stops=2.0)
    assert not cleans(None, stops=4.0)


def test_a_dark_photo_is_denoised_as_much_as_brightening_brought_noise_out():
    assert stages(Fixing(dark=0.0), "best", stops=0.0) == []  # nothing to brighten or clean
    one = stages(Fixing(dark=0.0), "best", stops=1.0)
    assert [stage.kind for stage in one] == ["brighten", "noise"]
    assert one[1].amount == pytest.approx(0.5)
    assert stages(Fixing(dark=0.0), "best", stops=4.0)[1].amount == pytest.approx(1.0)
    # With the noise fix on, its own strength, never less than the brightening needs.
    assert stages(Fixing(dark=0.0, noise=0.3), "best", stops=4.0)[1].amount == pytest.approx(1.0)
    assert stages(Fixing(dark=0.0, noise=0.9), "best", stops=1.0)[1].amount == pytest.approx(0.9)


def test_a_jpegs_own_quality_comes_from_its_tables():
    for quality in (5, 10, 18, 30, 50, 75, 92, 100):
        assert jpeg_quality(_tables(quality)) == quality
    assert jpeg_quality(_tables(40, subsampling=0)) == 40
    assert jpeg_quality({}) is None


def test_tables_that_arent_the_standard_ones_are_read_as_the_nearest_quality():
    tables = _tables(30)
    tables[0] = [max(1, value + (1 if index % 3 else -1)) for index, value in enumerate(tables[0])]

    found = jpeg_quality(tables)

    assert found is not None
    assert abs(found - 30) <= 3


def test_blocks_are_suggested_only_for_a_jpeg_saved_small():
    assert blocks_suggested(20)
    assert blocks_suggested(50)
    assert not blocks_suggested(85)
    assert not blocks_suggested(None)


def test_brightening_puts_the_brightest_parts_just_under_white():
    luma = np.full((100, 100), 0.02, np.float32)
    luma[:2, :] = 0.1  # the brightest 2%

    gain, white = brightening(luma)

    assert gain == pytest.approx(0.95 / 0.1, rel=0.01)
    assert white == pytest.approx(0.95, rel=0.05)


def test_brightening_is_held_between_one_and_sixteen_times():
    assert brightening(np.full((10, 10), 0.99, np.float32))[0] == 1.0
    assert brightening(np.full((10, 10), 0.0001, np.float32))[0] == 16.0


def test_a_night_scene_with_lights_in_it_stays_a_night_scene():
    luma = np.full((200, 200), 0.004, np.float32)
    luma[50:60, 50:70] = 0.9  # street lights and their glow: 1% of the picture
    luma[120:130, 30:50] = 0.85

    gain, _white = brightening(luma)

    assert gain < 2.0


def test_dark_is_suggested_from_two_stops_under():
    assert not dark_suggested(0.0)
    assert not dark_suggested(1.0)
    assert dark_suggested(2.0)
    assert dark_suggested(4.0)


def test_the_tone_curve_keeps_shadows_as_they_are_and_rolls_off_into_white():
    lin = np.array([[[0.01, 0.01, 0.01], [0.5, 0.5, 0.5], [4.0, 4.0, 4.0]]], np.float32)

    out = toned(lin, white=4.0)

    assert out[0, 0, 0] == pytest.approx(0.01, rel=0.02)
    assert out[0, 1, 0] < 0.5
    assert out[0, 2, 0] == pytest.approx(1.0, abs=1e-5)


def test_srgb_to_linear_light_and_back():
    values = np.linspace(0, 1, 11, dtype=np.float32)

    assert np.allclose(linear(values, back=True)[0], 0)
    assert np.allclose(linear(linear(values), back=True), values, atol=1e-5)


def test_an_8_bit_pictures_own_steps_are_smoothed_where_its_flat_and_edges_keep_theirs():
    steps = np.repeat(np.repeat(np.arange(8, dtype=np.float32), 24)[None, :], 48, 0)
    picture = np.stack([steps, steps, steps], -1)  # a dark ramp, a level every 24 pixels
    picture[:, 96:, :] += 30.0  # and an edge thirty levels high

    smooth = debanded(picture)

    row = smooth[24, :, 0]
    assert len(np.unique(np.round(row[:90], 2))) > 20  # the steps became a ramp
    assert row[95] < 6
    assert row[97] > 33
    assert np.array_equal(smooth[..., 0], smooth[..., 1])  # grey stays grey


def test_debanding_goes_by_each_pixels_neighbourhood_so_a_part_matches_the_whole():
    rng = np.random.default_rng(3)
    picture = np.cumsum(rng.integers(0, 2, (80, 120, 1)), axis=1).repeat(3, -1).astype(np.float32)

    whole = debanded(picture)
    part = debanded(picture[20:60, 30:100])

    reach = 15  # the window's half and the mean's radius
    assert np.allclose(part[reach:-reach, reach:-reach], whole[35:45, 45:85], atol=1e-4)


def test_local_contrast_lifts_a_flat_dark_area_and_a_part_is_lifted_as_the_whole_is():
    rng = np.random.default_rng(1)
    lightness = np.clip(rng.normal(60, 4, (240, 320)), 0, 255).astype(np.uint8)
    lightness[:, 160:] = np.clip(rng.normal(30, 4, (240, 160)), 0, 255).astype(np.uint8)
    luts = clahe_luts(lightness)

    whole = contrasted(lightness.astype(np.float32), luts, (0.0, 0.0, 1.0, 1.0))
    part = contrasted(lightness[100:150, 200:260].astype(np.float32), luts, (200, 100, 1, 1))

    assert float(whole[:, 160:].std()) > float(lightness[:, 160:].std())
    assert np.allclose(part, whole[100:150, 200:260], atol=1e-3)


def test_the_local_range_is_each_pixels_square_of_neighbours_from_brightest_to_darkest():
    values = np.zeros((40, 40), np.float32)
    values[20, 20] = 1.0

    found = local_range(values, 7)

    assert found[20, 20] == 1.0
    assert found[17, 23] == 1.0  # three out each way
    assert found[16, 20] == 0.0
    assert found.shape == values.shape


def test_the_guard_holds_the_blur_model_back_in_flat_places_and_lets_it_sharpen_edges():
    before = np.full((1, 3, 64, 64), 0.5, np.float32)
    before[:, :, :, 32:] = 0.8  # an edge
    after = before.copy()
    after[:, :, 5, 5] = 1.0  # invented in a flat place
    after[:, :, 30, 31] = 0.45  # an edge made crisper
    after[:, :, 30, 32] = 0.85

    kept = guarded(before, after)

    assert kept[0, 0, 5, 5] == pytest.approx(0.5 + 2 / 255, abs=1e-6)
    assert kept[0, 0, 30, 31] == pytest.approx(0.45)
    assert kept[0, 0, 30, 32] == pytest.approx(0.85)


def test_a_tile_the_blur_model_broke_down_on_comes_back_as_it_was():
    before = np.full((1, 3, 64, 64), 0.3, np.float32)
    before[:, :, :, 40:] = 0.9  # a straight line beside a flat place, as a road's
    garbage = np.random.default_rng(3).random(before.shape, np.float32)  # colours anywhere
    mended = before.copy()
    mended[:, :, :, 39] = 0.25  # the line made crisper
    mended[:, :, :, 40] = 0.95

    assert np.array_equal(guarded(before, garbage), before)
    assert guarded(before, mended)[0, 0, 0, 39] == pytest.approx(0.25)


def test_stops_are_a_gains_doubling():
    assert math.log2(brightening(np.full((10, 10), 0.95 / 4, np.float32))[0]) == pytest.approx(
        2.0, abs=0.01
    )
