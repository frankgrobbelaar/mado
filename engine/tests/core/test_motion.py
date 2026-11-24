"""3D photos' rules (mado/core/motion.py): the view's path, how points move by their nearness,
finding a frame backwards, what the view uncovers, the video's size and the encoders."""

import numpy as np
import pytest

from mado.core.motion import (
    ENCODERS,
    FPS,
    Moving,
    View,
    about_bytes,
    behind,
    bitrate,
    check_command,
    encode_command,
    encoder_args,
    margin,
    moving_words,
    own_share,
    path,
    pivot_of,
    sample,
    shown,
    sources,
    to_fill,
    video_size,
    view,
    webp_size,
)


@pytest.mark.parametrize("motion", ["push", "sway", "circle"])
def test_the_view_comes_back_where_it_started_so_the_video_loops(motion: str):
    start = view(motion, 0.0, 20.0, 0.1)  # type: ignore[arg-type]
    again = view(motion, 1.0, 20.0, 0.1)  # type: ignore[arg-type]
    assert again.across == pytest.approx(start.across, abs=1e-9)
    assert again.down == pytest.approx(start.down, abs=1e-9)
    assert again.push == pytest.approx(start.push, abs=1e-9)
    frames = path(Moving(motion, 3), 1000)  # type: ignore[arg-type]
    assert len(frames) == 3 * FPS
    # Gently: a frame is never far from the one before it.
    for before, after in zip(frames, [*frames[1:], frames[0]], strict=True):
        assert abs(after.across - before.across) < 2.0
        assert abs(after.push - before.push) < 0.01


def test_a_push_goes_in_and_back_a_sway_goes_side_to_side_and_a_circle_goes_round():
    assert view("push", 0.0, 20, 0.1).push == 0.0
    assert view("push", 0.5, 20, 0.1).push == pytest.approx(0.1)
    assert view("sway", 0.25, 20, 0.1).across == pytest.approx(20)
    assert view("sway", 0.75, 20, 0.1).across == pytest.approx(-20)
    quarter = view("circle", 0.25, 20, 0.1)
    assert quarter.across == pytest.approx(0, abs=1e-9)
    assert quarter.down == pytest.approx(12)


def test_the_whole_is_made_just_big_enough_that_the_edges_never_show_past_the_picture():
    views = path(Moving("sway", 3, 1.0), 1000)
    scale = margin(views, (1500, 1000), 0.5)
    assert 1.0 < scale < 1.2
    assert margin([View(0, 0, 0)], (1500, 1000), 0.5) == 1.0


def test_a_frame_found_backwards_moves_near_things_more_than_far_ones():
    near = np.zeros((60, 80), np.float32)
    near[:, 40:] = 1.0  # the right half near, the left far
    ys, xs = np.mgrid[0:60, 0:80].astype(np.float32)
    at = View(across=4.0, down=0.0, push=0.0)
    px, _py, missed = sources(near, at, 0.0, 1.0, (xs, ys), (80, 60))
    assert px[30, 10] == pytest.approx(10.0)  # far, at the pivot: stays put
    assert px[30, 70] == pytest.approx(66.0)  # near: it came from 4 pixels to the left
    assert missed[30, 10] < 0.01
    assert missed[30, 70] < 0.01


def test_nothing_moves_with_the_view_at_rest():
    near = np.random.default_rng(3).uniform(0, 1, (30, 40)).astype(np.float32)
    ys, xs = np.mgrid[0:30, 0:40].astype(np.float32)
    px, py, missed = sources(near, View(0, 0, 0), 0.5, 1.0, (xs, ys), (40, 30))
    assert np.allclose(px, xs)
    assert np.allclose(py, ys)
    assert missed.max() < 1e-4


def test_sampling_takes_each_place_between_its_four_nearest():
    values = np.array([[0.0, 10.0], [20.0, 30.0]], np.float32)
    found = sample(
        values, np.array([0.5, 0.0, 1.0], np.float32), np.array([0.5, 1.0, 1.0], np.float32)
    )
    assert found == pytest.approx([15.0, 20.0, 30.0])
    colours = np.zeros((2, 2, 3), np.uint8)
    colours[1, 1] = (255, 0, 0)
    assert sample(colours, np.array([1.0]), np.array([1.0]))[0] == pytest.approx([255, 0, 0])


def test_a_frame_stretched_over_what_the_view_uncovered_shows_the_layer_behind():
    ys, xs = np.mgrid[0:20, 0:20].astype(np.float32)
    assert own_share(xs, ys, 1.0) == pytest.approx(np.ones((20, 20)))
    squeezed = xs * 0.1  # the frame's points all from a sliver of the picture: stretched
    assert own_share(squeezed, ys, 1.0).max() < 0.2
    weight = shown(own_share(squeezed, ys, 1.0), np.zeros((20, 20), np.float32))
    assert weight.max() < 0.05
    weight = shown(np.ones((20, 20), np.float32), np.full((20, 20), 5.0, np.float32))
    assert weight.max() < 0.05  # never found where it came from


def test_what_the_view_can_uncover_is_the_edge_of_near_things_within_its_reach():
    near = np.full((40, 40), 0.1, np.float32)
    near[10:30, 10:30] = 0.9
    uncovers, back = behind(near, 3)
    assert uncovers[20, 11] == 1.0  # inside the near square, beside the far
    assert uncovers[20, 20] == 0.0  # deep inside it, out of reach
    assert uncovers[20, 5] == 0.0  # the far itself
    assert back[20, 11] < 0.3  # behind it, as far as what's beyond


def test_the_layer_behind_is_filled_three_times_the_reach_into_near_things():
    near = np.full((60, 60), 0.1, np.float32)
    near[10:50, 10:50] = 0.9
    filled = to_fill(near, 3)
    assert filled[30, 18]  # 9 pixels in: within three times the reach of the far
    assert not filled[30, 19]  # past it, so what's filled is nearer the far than this
    assert not filled[30, 5]  # the far itself
    assert not to_fill(np.full((20, 20), 0.5, np.float32), 3).any()  # nothing nearer: none


def test_what_stays_put_is_the_subject_or_the_pictures_middle():
    near = np.linspace(0, 1, 101, dtype=np.float32)[None, :]
    assert pivot_of(near, 0.9) == 0.9
    assert pivot_of(near, None) == pytest.approx(0.5)


def test_a_video_is_its_pictures_shape_even_and_never_bigger_than_it_or_4k():
    assert video_size(4032, 3024, "1080p") == (1920, 1440)
    assert video_size(3024, 4032, "1080p") == (1440, 1920)
    assert video_size(8000, 4500, "4k") == (3840, 2160)
    assert video_size(1001, 751, "4k") == (1000, 750)  # its own size, made even, never bigger
    assert webp_size(4032, 3024) == (1280, 960)


def test_about_how_big_a_3d_photo_comes_out():
    assert bitrate(1920, 1080) == 12_000_000
    assert bitrate(3840, 2160) == 40_000_000
    assert about_bytes(Moving(seconds=5), 1920, 1080) == 12_000_000 * 5 // 8
    assert about_bytes(Moving(seconds=5, format="webp"), 1280, 720) > 10_000_000


def test_only_encoders_that_come_with_their_licence_and_windows_own_first():
    assert list(ENCODERS) == ["h264_mf", "h264_nvenc", "h264_amf", "h264_qsv"]
    assert "libopenh264" not in ENCODERS  # Cisco's patent licence covers only its own builds
    for encoder in ENCODERS:
        args = encoder_args(encoder, 1920, 1080)
        assert args[:2] == ["-c:v", encoder]
    with pytest.raises(ValueError, match="openh264"):
        encoder_args("libopenh264", 1920, 1080)
    check = check_command(["ffmpeg"], "h264_mf")
    assert check[0] == "ffmpeg"
    assert "lavfi" in check
    made = encode_command(["ffmpeg"], "h264_nvenc", 1920, 1080, "out.mp4")
    assert made[-1] == "out.mp4"
    assert "+faststart" in made
    assert made[made.index("-s") + 1] == "1920x1080"
    assert "yuv420p" in made


def test_a_video_is_made_in_hd_colours_and_says_so():
    # sRGB frames turned to video's colours by HD's own matrix, and tagged, so a player shows
    # them as they were rather than guessing.
    made = encode_command(["ffmpeg"], "h264_mf", 1920, 1080, "out.mp4")
    assert made[made.index("-vf") + 1] == "scale=out_color_matrix=bt709:out_range=tv"
    assert made[made.index("-colorspace") + 1] == "bt709"
    assert made[made.index("-color_primaries") + 1] == "bt709"
    assert made[made.index("-color_trc") + 1] == "iec61966-2-1"
    assert made.index("-vf") > made.index("-i")
    # Written into the video itself, whichever encoder made it.
    assert made[made.index("-bsf:v") + 1] == (
        "h264_metadata=colour_primaries=1:transfer_characteristics=13:matrix_coefficients=1"
        ":video_full_range_flag=0"
    )


def test_history_says_what_3d_photo_was_made():
    assert moving_words(Moving("push", 5)) == "into a 3D photo, pushing in for 5 s"
    assert moving_words(Moving("circle", 3)) == "into a 3D photo, circling for 3 s"
