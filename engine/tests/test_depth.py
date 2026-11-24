"""Reading a picture's depth and making the depth tools (mado/depth.py): the depth kept in the
cache for the picture's version, and the tools on a made-up field whose depth is known, at any
size and on a part of the picture made."""

import os
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mado.ai import Ai
from mado.config import DataPaths
from mado.core.depth import READ, Depthing, Fog, Portrait, TiltShift
from mado.depth import Depths, depthed, joined_on, work_out
from mado.directml import Sessions
from mado.editing import Editor
from mado.tools import Tools
from mado.upscale import StoppedError
from tests.conftest import ON_PROCESSOR
from tests.depth_models import DepthModel, with_depth_model
from tests.depth_scenes import field


@pytest.fixture
def ai(paths: DataPaths) -> Ai:
    return Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR)


@pytest.fixture
def model(ai: Ai, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DepthModel:
    return with_depth_model(monkeypatch, ai, tmp_path / "models")


def _truth(size: tuple[int, int]) -> tuple[Image.Image, np.ndarray]:
    image, truth = field(size)
    near = np.asarray(Image.fromarray(truth, "F").resize((READ, READ), Image.Resampling.BILINEAR))
    return image, near.astype(np.float32)


def test_a_pictures_depth_is_read_once_and_kept_for_its_version(
    ai: Ai, model: DepthModel, tmp_path: Path
):
    image, _ = field((240, 180))
    editor = Editor(ai, tmp_path / "edits")
    depths = Depths(ai, editor, tmp_path / "depth")

    first = depths.read(image, "c:\\garden\\ball.png|1")
    again = depths.read(image, "c:\\garden\\ball.png|1")
    after_a_restart = Depths(ai, editor, tmp_path / "depth").read(image, "c:\\garden\\ball.png|1")
    changed = depths.read(image, "c:\\garden\\ball.png|2")

    assert first.near.shape == (READ, READ)
    assert first.place == "processor"
    assert again.place is None  # kept
    assert model.runs["depth"] == 2  # its first version, then its second
    assert np.abs(after_a_restart.near - first.near).max() < 1 / 60000
    assert after_a_restart.spread == pytest.approx(first.spread, abs=1e-5)
    assert changed.place == "processor"
    kept = list((tmp_path / "depth").rglob("*.png"))
    assert len(kept) == 2  # one for each version
    with Image.open(kept[0]) as stored:
        assert stored.mode.startswith("I")  # 16-bit nearness


def test_a_batchs_picture_keeps_nothing_and_a_damaged_kept_one_is_read_again(
    ai: Ai, model: DepthModel, tmp_path: Path
):
    image, _ = field((240, 180))
    depths = Depths(ai, Editor(ai, tmp_path / "edits"), tmp_path / "depth")

    depths.read(image, "a|1", keep=False)
    assert not (tmp_path / "depth").exists()
    depths.read(image, "b|1")
    [stored] = list((tmp_path / "depth").rglob("*.png"))
    stored.write_bytes(b"not a picture")
    fresh = Depths(ai, Editor(ai, tmp_path / "edits"), tmp_path / "depth")
    assert fresh.read(image, "b|1").place == "processor"  # read again


def test_a_depth_used_lately_stays_however_long_ago_it_was_read(
    ai: Ai, model: DepthModel, tmp_path: Path
):
    image, _ = field((240, 180))
    depths = Depths(ai, Editor(ai, tmp_path / "edits"), tmp_path / "depth")
    depths.read(image, "c:\\garden\\ball.png|1")
    [stored] = list((tmp_path / "depth").rglob("*.png"))
    long_ago = time.time() - 40 * 86400
    os.utime(stored.parent, (long_ago, long_ago))  # read 40 days ago, used today

    Depths(ai, Editor(ai, tmp_path / "edits"), tmp_path / "depth").tidy()
    assert stored.is_file()
    os.utime(stored, (long_ago, long_ago))  # not used since
    Depths(ai, Editor(ai, tmp_path / "edits"), tmp_path / "depth").tidy()
    assert not stored.exists()


def test_portrait_blur_keeps_whats_in_focus_and_blurs_whats_farther():
    image, near = _truth((480, 360))
    whole = (0.0, 0.0, 480.0, 360.0)
    pixels = np.asarray(image, np.float32)

    on_ball = depthed(image, Depthing(portrait=Portrait((0.62, 0.8), 1.4)), near, whole, image.size)
    on_hills = depthed(
        image, Depthing(portrait=Portrait((0.5, 0.36), 1.4)), near, whole, image.size
    )

    near_ball = np.asarray(on_ball.image, np.float32)
    near_hills = np.asarray(on_hills.image, np.float32)
    ball = (slice(260, 280), slice(248, 268))  # the ball's left edge, on the grass
    hill_edge = (slice(115, 140), slice(0, 480))
    assert np.abs(near_ball[ball] - pixels[ball]).mean() < 3  # in focus
    assert np.abs(near_hills[ball] - pixels[ball]).mean() > 6  # nearer than the focus: blurred
    assert near_ball[hill_edge].std() < pixels[hill_edge].std()  # the far hills blurred
    assert on_ball.focus == pytest.approx((0.62, 0.8))


def test_a_subjects_crisp_edge_stays_crisp_through_a_cut_out_models_soft_mask():
    # The ball as a cut-out model finds it, on a picture bigger than the copy the blur is worked
    # out on: its mask jumps at the edge, from a quarter to four fifths, and fades on over a few
    # pixels each side, as U²-Net's does. In focus at the ball, its rim stays as it was (taken as
    # found, the rim came out 2.5 levels off, blurred), and the blur round it takes none of its red.
    image, near = _truth((2016, 1512))
    pixels = np.asarray(image, np.float32)
    radius = 1512 * 0.11
    centre = (0.62 * 2016, 0.86 * 1512 - radius)
    ys, xs = np.mgrid[0:1512, 0:2016].astype(np.float32)
    inside = radius - np.hypot(xs - centre[0], ys - centre[1])  # pixels in from the edge
    rising = (0.8 + 0.2 * (1 - np.exp(-np.maximum(inside, 0) / 6))).astype(np.float32)
    fading = (0.28 * np.exp(np.minimum(inside, 0) / 12)).astype(np.float32)
    within = (inside >= 0).astype(np.float32)
    mask = (255 * (within * rising + (1 - within) * fading)).astype(np.uint8)

    made = np.asarray(
        depthed(
            image,
            Depthing(portrait=Portrait(aperture=1.4)),
            near,
            (0.0, 0.0, 2016.0, 1512.0),
            image.size,
            mask=mask,
        ).image,
        np.float32,
    )

    rim = (inside > 0.5) & (inside < 4) & (ys < centre[1])  # the ball's top half, in its edge
    assert np.abs(made[rim] - pixels[rim]).mean() < 1
    beside = (inside < -0.5) & (inside > -4)
    assert ((made[beside][:, 0] - made[beside][:, 1]) > 80).mean() < 0.05  # the ball's red


def test_fog_hazes_the_far_and_leaves_the_near_and_a_colour_can_be_chosen():
    image, near = _truth((480, 360))
    whole = (0.0, 0.0, 480.0, 360.0)
    pixels = np.asarray(image, np.float32)

    own = np.asarray(
        depthed(image, Depthing(fog=Fog(0.6)), near, whole, image.size).image, np.float32
    )
    warm = np.asarray(
        depthed(image, Depthing(fog=Fog(1.0, (240, 200, 150))), near, whole, image.size).image,
        np.float32,
    )

    hills = (slice(125, 145), slice(0, 480))
    foot = (slice(345, 360), slice(0, 480))
    far_change = np.abs(own[hills] - pixels[hills]).mean()
    assert far_change > 10
    assert np.abs(own[foot] - pixels[foot]).mean() < far_change / 3  # thicker with distance
    assert warm[hills][..., 0].mean() > warm[hills][..., 2].mean()  # a warm haze


def test_tilt_shift_keeps_its_band_and_blurs_the_top_and_foot():
    image, near = _truth((480, 360))
    pixels = np.asarray(image, np.float32)

    made = np.asarray(
        depthed(
            image, Depthing(tilt=TiltShift(0.5, 0.2, 1.0)), near, (0, 0, 480, 360), image.size
        ).image,
        np.float32,
    )

    furrows = (slice(300, 360), slice(0, 480))
    assert made[furrows].std(axis=0).mean() < pixels[furrows].std(axis=0).mean()


def test_a_part_joined_at_full_detail_matches_the_same_part_of_the_whole():
    image, near = _truth((480, 360))
    step = Depthing(Portrait((0.62, 0.8), 2.0), Fog(0.5), TiltShift(0.55, 0.2, 0.8))
    worked = work_out(image, step, near, (0, 0, 480, 360), image.size)

    whole = np.asarray(joined_on(image, (0, 0, 480, 360), worked), np.float32)
    part = np.asarray(
        joined_on(image.crop((200, 100, 400, 300)), (200, 100, 480, 360), worked), np.float32
    )

    assert np.abs(part - whole[100:300, 200:400]).mean() < 1.0


def test_see_through_parts_stay_as_they_are_and_making_can_be_stopped():
    image, near = _truth((240, 180))
    sticker = image.convert("RGBA")
    alpha = np.full((180, 240), 255, np.uint8)
    alpha[:, :40] = 0
    sticker.putalpha(Image.fromarray(alpha))

    made = depthed(
        sticker, Depthing(fog=Fog(0.8), tilt=TiltShift()), near, (0, 0, 240, 180), (240, 180)
    )

    assert made.image.mode == "RGBA"
    assert np.array_equal(np.asarray(made.image.getchannel("A")), alpha)
    with pytest.raises(StoppedError):
        depthed(image, Depthing(fog=Fog()), near, (0, 0, 240, 180), (240, 180), stop=lambda: True)
