"""Depth's rules (mado/core/depth.py): the depth step and its words, the model's numbers made
nearness, a flat picture told apart, placing nearness on what's made, and the tools' maths on
made-up pictures whose depth is known."""

import itertools

import numpy as np
import pytest

from mado.core.depth import (
    APERTURES,
    FLAT_EDGES,
    FLAT_SPREAD,
    READ,
    DepthError,
    Depthing,
    Fog,
    Portrait,
    TiltShift,
    at_point,
    behind_subject,
    bright,
    depthing_from,
    depthing_json,
    detail,
    disc,
    f_radius,
    firm,
    fog_clear,
    fogged,
    in_focus,
    joined,
    label,
    layers,
    lens_blur,
    lifted,
    linear_to_stored,
    membership,
    middle_of,
    nearness,
    on_canvas,
    own_haze,
    phrase,
    placed,
    readable,
    spread,
    stack_blur,
    stop_words,
    subject_near,
    subject_only,
    tilt_radius,
    to_linear,
    with_subject,
)

Floats = np.ndarray


def test_a_depth_step_is_kept_and_read_back_as_it_was():
    step = Depthing(
        Portrait((0.3, 0.6), 2.0, "best"), Fog(0.4, (220, 228, 236)), TiltShift(0.5, 0.25, 0.7)
    )
    assert depthing_from(depthing_json(step)) == step
    assert depthing_from(None) is None
    assert depthing_from({"portrait": None, "fog": None, "tilt": None}) is None
    assert depthing_from({"fog": {}}) == Depthing(fog=Fog())
    assert depthing_from({"portrait": {"aperture": 100}}) == Depthing(Portrait(aperture=16.0))
    assert depthing_from({"fog": {"density": 2, "colour": "teal"}}) == Depthing(fog=Fog(1.0))
    with pytest.raises(DepthError, match="can't read"):
        depthing_from({"portrait": {"focus": [1]}})
    with pytest.raises(DepthError):
        depthing_from(["portrait"])


def test_history_and_a_new_pictures_name_say_each_tool():
    portrait = Depthing(portrait=Portrait(aperture=2.8))
    assert phrase(portrait) == "portrait blur at f/2.8"
    assert label(portrait) == "Portrait blur"
    assert label(Depthing(fog=Fog())) == "Fog"
    assert label(Depthing(tilt=TiltShift())) == "Tilt-shift"
    every = Depthing(Portrait(aperture=1.4), Fog(), TiltShift())
    assert phrase(every) == "portrait blur at f/1.4, fog and tilt-shift"
    assert label(every) == "Depth"
    assert phrase(None) is None
    assert detail(every) == "Portrait blur at f/1.4 on each subject, fog at 50%, tilt-shift at 60%"
    assert [stop_words(each) for each in APERTURES] == [
        "f/1.4", "f/2", "f/2.8", "f/4", "f/5.6", "f/8", "f/11", "f/16",
    ]  # fmt: skip


def test_the_model_reads_the_picture_squeezed_to_its_square_as_imagenet_numbers():
    pixels = np.full((READ, READ, 3), 255, np.uint8)
    values = readable(pixels)
    assert values.shape == (1, 3, READ, READ)
    assert values.dtype == np.float32
    assert values[0, :, 0, 0] == pytest.approx(
        [(1 - 0.485) / 0.229, (1 - 0.456) / 0.224, (1 - 0.406) / 0.225]
    )


def test_nearness_goes_from_the_farthest_to_the_nearest_and_a_flat_picture_says_so():
    rows = np.linspace(0, 1, 200, dtype=np.float32)[:, None] * np.ones((1, 200), np.float32)
    deep = 6.0 * rows  # a ground running away to a sky at nothing
    found = nearness(deep)
    assert found.near.min() == 0.0
    assert found.near.max() == 1.0
    assert found.near[-1, 0] > found.near[100, 0] > found.near[0, 0]
    assert not found.flat
    page = 2.0 + 0.4 * rows  # a page facing the camera, a little tilted
    assert nearness(page).flat
    assert nearness(page).spread < FLAT_SPREAD
    stepped = np.where(rows > 0.5, 3.0, 2.2).astype(np.float32)  # a subject before a wall
    assert nearness(stepped).edges > FLAT_EDGES
    assert not nearness(stepped).flat
    assert nearness(np.full((10, 10), 3.0, np.float32)).flat


def test_nearness_is_placed_on_a_crop_and_on_extended_edges_where_the_edge_carries_on():
    near = np.tile(np.linspace(0, 1, 100, dtype=np.float32), (50, 1))  # nearer to the right
    cropped = placed(near, (50.0, 0.0, 50.0, 50.0), (100, 50), (25, 10))
    assert cropped.shape == (10, 25)
    assert cropped[:, 0].min() >= 0.49
    extended = placed(near, (-50.0, 0.0, 200.0, 50.0), (100, 50), (40, 10))
    assert extended[:, 0] == pytest.approx(0.0, abs=1e-6)  # the picture's left edge, carried on
    assert extended[:, -1] == pytest.approx(1.0, abs=1e-6)
    assert on_canvas((0.75, 0.5), (50.0, 0.0, 50.0, 50.0), (100, 50)) == (0.5, 0.5)
    assert on_canvas((0.1, 0.5), (50.0, 0.0, 50.0, 50.0), (100, 50)) == (0.0, 0.5)


def test_the_focus_is_how_near_the_picture_is_where_it_was_clicked():
    near = np.zeros((100, 100), np.float32)
    near[40:60, 40:60] = 0.9
    assert at_point(near, (0.5, 0.5)) == pytest.approx(0.9)
    assert at_point(near, (0.1, 0.1)) == 0.0
    mask = np.zeros((100, 100), np.float32)
    mask[40:60, 40:60] = 1.0
    assert subject_near(near, mask) == pytest.approx(0.9)
    assert subject_near(near, np.zeros_like(mask)) is None
    assert middle_of(mask) == pytest.approx((0.5, 0.5), abs=0.01)


def test_a_far_thing_the_cut_out_model_also_picked_isnt_kept_with_the_subject():
    near = np.zeros((100, 100), np.float32)
    near[60:90, 40:70] = 0.9  # the ball, near
    mask = np.zeros_like(near)
    mask[60:90, 40:70] = 1.0
    mask[5:15, 10:20] = 1.0  # a sun in the sky, which a cut-out model picks too
    at = subject_near(near, mask)
    assert at is not None
    only = subject_only(near, mask, at)
    assert only[70, 50] == 1.0
    assert only[10, 15] == 0.0


def test_a_cut_out_models_fading_edge_is_made_firm_and_hairs_in_between_stays_between():
    mask = np.array([0.0, 0.2, 0.3, 0.5, 0.7, 0.8, 1.0], np.float32)
    assert firm(mask) == pytest.approx([0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0])


def test_behind_the_subject_is_what_was_beyond_its_edge_never_nearer_than_the_model_said():
    near = np.full((60, 60), 0.2, np.float32)
    near[20:40, 20:40] = 0.9
    near[18:42, 18:42] = np.maximum(near[18:42, 18:42], 0.55)  # the model's soft edge
    mask = np.zeros_like(near)
    mask[20:40, 20:40] = 1.0
    behind = behind_subject(near, mask)
    assert behind[19, 30] == pytest.approx(0.2, abs=0.15)  # the soft edge goes to what's behind
    assert (behind <= near + 1e-6).all()
    made = with_subject(behind, mask, 0.9)
    assert made[30, 30] == pytest.approx(0.9)
    assert made[19, 30] < 0.4


def test_a_wider_aperture_blurs_more_and_layers_are_close_enough_to_join_smoothly():
    assert f_radius(1.4, 1000) == pytest.approx(30.0)
    assert f_radius(2.8, 1000) == pytest.approx(15.0)
    planned = layers(0.8, 30.0)
    radii = [radius for _near, radius in planned]
    assert planned[0][0] == 1.0  # nearest first
    assert planned[-1][0] == 0.0
    assert (0.8, 0.0) in planned  # what's in focus is wholly in one layer, never blurred
    # Twelve layers at most: neighbours' circles a twelfth of the way apart, a third more beside
    # the focus.
    assert all(abs(a - b) <= 30.0 / 11 * 4 / 3 + 1e-6 for a, b in itertools.pairwise(radii))
    near = np.random.default_rng(1).uniform(0, 1, (20, 20)).astype(np.float32)
    centres = [centre for centre, _ in planned]
    total = sum(membership(near, centres, at) for at in range(len(centres)))
    assert np.allclose(total, 1.0, atol=1e-5)


def test_a_disc_keeps_the_light_it_spreads_and_is_round():
    shape = disc(6.0)
    assert shape.sum() == pytest.approx(1.0, abs=1e-5)
    middle = shape.shape[0] // 2
    assert shape[middle, middle + 6] > 0
    assert shape[middle + 5, middle + 5] == 0  # the corner of its square is outside it
    point = np.zeros((101, 101), np.float32)
    point[50, 50] = 1.0
    for radius in (2.0, 12.0):
        blurred = spread(point, radius)
        assert blurred.sum() == pytest.approx(1.0, abs=0.02)


def _scene() -> tuple[Floats, Floats, Floats]:
    """A red square (the subject, near) on a striped far wall, with a small bright lamp on the
    wall; its truth and its mask."""
    lin = np.zeros((160, 160, 3), np.float32)
    stripes = (np.arange(160) // 4) % 2
    lin[:, :, 1] = 0.2 + 0.3 * stripes[None, :]
    lin[:, :, 2] = 0.3
    lin[60:100, 60:100] = (0.8, 0.05, 0.05)
    lin[20:23, 20:23] = (1.0, 1.0, 1.0)
    near = np.full((160, 160), 0.1, np.float32)
    near[60:100, 60:100] = 0.9
    mask = np.zeros((160, 160), np.float32)
    mask[60:100, 60:100] = 1.0
    return lin, near, mask


def test_a_lens_blur_keeps_whats_in_focus_and_blurs_whats_behind_without_its_colour():
    lin, near, _mask = _scene()
    blurred = lens_blur(lin, near, focus=0.9, most=10.0)
    sharp = in_focus((np.abs(near - 0.9) * 10.0).astype(np.float32))
    made = joined(lin, sharp, blurred.behind, blurred.front, blurred.nearer)
    assert np.allclose(made[70:90, 70:90], lin[70:90, 70:90])  # the subject, as it was
    wall = made[120:150, 10:50, 1]
    assert wall.std() < lin[120:150, 10:50, 1].std() / 3  # the stripes behind, blurred away
    beside = blurred.behind[80, 54]  # just outside the subject: the wall, never its red
    assert beside[0] < 0.2


def test_a_lens_focused_far_blurs_the_near_subject_over_the_sharp_wall():
    lin, near, _mask = _scene()
    blurred = lens_blur(lin, near, focus=0.1, most=10.0)
    sharp = in_focus((np.abs(near - 0.1) * 10.0).astype(np.float32))
    made = joined(lin, sharp, blurred.behind, blurred.front, blurred.nearer)
    assert np.allclose(made[130:150, 10:30], lin[130:150, 10:30], atol=1e-3)  # far, in focus
    assert made[80, 57, 0] > lin[80, 57, 0] + 0.05  # the near red spreads over the wall beside it


def test_small_bright_places_bloom_into_round_discs_and_a_bright_sky_doesnt():
    lin = np.full((120, 120, 3), 0.05, np.float32)
    lin[58:62, 58:62] = 1.0  # a lamp
    lin[:20] = 0.9  # a pale sky, bright all along the top
    light = bright(lin, 8.0)
    assert light[60, 60] > 0.9
    assert light[5, 60] == 0.0
    near = np.full((120, 120), 0.0, np.float32)
    blurred = lens_blur(lin, near, focus=1.0, most=12.0).behind
    across, down, aslant = blurred[60, 66], blurred[66, 60], blurred[64, 64]
    assert across == pytest.approx(down, rel=0.05)  # as far each way: round
    assert aslant[0] == pytest.approx(across[0], rel=0.35)


def test_fog_thickens_with_distance_in_the_pictures_own_haze_or_a_colour():
    near = np.array([[0.0, 0.5, 1.0]], np.float32)
    clear = fog_clear(near, 0.6)
    assert clear[0, 0] < clear[0, 1] < clear[0, 2] == pytest.approx(1.0)
    assert fog_clear(near, 0.0) == pytest.approx(1.0)
    lin = np.zeros((1, 3, 3), np.float32)
    haze = np.array([0.8, 0.8, 0.8], np.float32)
    made = fogged(lin, near, 1.0, haze)
    assert made[0, 0, 0] > 0.7  # the farthest nearly all haze
    assert made[0, 2, 0] == pytest.approx(0.0, abs=1e-6)  # the nearest as it was
    sky = np.zeros((10, 10, 3), np.float32)
    sky[:3] = (0.2, 0.4, 0.9)
    depth = np.full((10, 10), 0.8, np.float32)
    depth[:3] = 0.0
    own = own_haze(sky, depth)
    assert own[2] > own[0]  # the sky's blue, made paler


def test_tilt_shift_keeps_its_band_sharp_and_blurs_more_away_from_it():
    radius = tilt_radius(100, 10, TiltShift(0.5, 0.2, 1.0), 100)
    assert radius.shape == (100, 10)
    assert (radius[41:59] == 0).all()
    assert radius[0, 0] > radius[30, 0] > 0
    assert radius[99, 0] == pytest.approx(radius[0, 0], rel=0.05)
    lin = np.random.default_rng(2).uniform(0, 1, (100, 100, 3)).astype(np.float32)
    made = stack_blur(lin, tilt_radius(100, 100, TiltShift(0.5, 0.2, 1.0), 100))
    assert np.allclose(made[45:55], lin[45:55])
    assert made[0:10].std() < lin[0:10].std() / 2


def test_tilt_shifts_band_is_where_it_was_dragged_on_the_picture_whatever_is_kept_of_it():
    # Dragged on the whole picture, its middle half way down; made, only the picture's lower
    # half is kept (a crop): the band is the top fifth of what's made, and the blur grows to its
    # most at the picture's foot, as on the whole picture.
    whole = tilt_radius(200, 1, TiltShift(0.5, 0.2, 1.0), 100)
    lower = tilt_radius(100, 1, TiltShift(0.5, 0.2, 1.0), 100, span=(0.5, 0.5))
    assert (lower[:19] == 0).all()
    assert lower[25, 0] > 0
    assert lower[:, 0] == pytest.approx(whole[100:, 0], abs=1e-4)


def test_tilt_shift_lifts_colours_a_little_keeping_their_light():
    lin = np.array([[[0.5, 0.3, 0.2]]], np.float32)
    made = lifted(lin)
    luma = np.array([0.2126, 0.7152, 0.0722], np.float32)
    assert float(made[0, 0] @ luma) == pytest.approx(float(lin[0, 0] @ luma), abs=1e-4)
    assert made[0, 0, 0] - made[0, 0, 2] > lin[0, 0, 0] - lin[0, 0, 2]
    grey = np.full((1, 1, 3), 0.4, np.float32)
    assert np.allclose(lifted(grey), grey)


def test_light_goes_to_linear_and_back_by_tables():
    pixels = np.arange(256, dtype=np.uint8)
    back = linear_to_stored(to_linear(pixels))
    assert np.abs(back * 255 - pixels).max() < 0.6
