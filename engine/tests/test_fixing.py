"""Fixing a picture through Mado's own tiles and sessions, with the fixes' models' stand-ins
(tests/fix_models.py): how dark a picture measures, each fix made, a part made alone matching the
whole, grey pictures staying grey, smooth dark gradients not banding, the guard, and stopping."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mado.ai import HELD, Ai
from mado.config import DataPaths
from mado.core.fixes import NAFNET, SCUNET, Fixing
from mado.core.framing import Box
from mado.core.recipe import Recipe, plan
from mado.directml import Sessions
from mado.fixing import fixed, measure
from mado.hardware import Here
from mado.making import fixed_part, make
from mado.tools import Tools
from mado.upscale import StoppedError
from tests.conftest import ON_PROCESSOR
from tests.drawn import photo_like, scene
from tests.fix_models import FixModels, with_fix_models


@pytest.fixture
def ai(tmp_path: Path) -> Ai:
    return Ai(Sessions(), Tools(DataPaths(tmp_path / "Mado")), lambda: ON_PROCESSOR)


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch, ai: Ai, tmp_path: Path) -> FixModels:
    return with_fix_models(monkeypatch, ai, tmp_path / "models")


def _darkened(pixels: np.ndarray, times: float) -> np.ndarray:
    """An exposure cut `times` over in linear light, then 8 bits again."""
    lin = (pixels.astype(np.float64) / 255) ** 2.2 / times
    return np.clip(np.rint(lin ** (1 / 2.2) * 255), 0, 255).astype(np.uint8)


def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    error = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 10 * np.log10(255**2 / max(error, 1e-9))


def test_a_picture_measures_as_dark_as_it_was_made():
    bright = np.asarray(scene(4, (480, 320)))

    normal = measure(Image.fromarray(bright))
    dark = measure(Image.fromarray(_darkened(bright, 8)))

    assert normal.stops < 0.5
    assert dark.stops == pytest.approx(3.0, abs=0.5)
    assert (dark.width, dark.height) == (480, 320)


def test_see_through_parts_dont_count_in_how_dark_a_picture_is():
    pixels = _darkened(np.asarray(scene(2, (200, 200))), 4)
    image = Image.fromarray(pixels).convert("RGBA")
    alpha = np.full((200, 200), 255, np.uint8)
    alpha[:, :100] = 0
    image.putalpha(Image.fromarray(alpha))
    bright = np.asarray(image).copy()
    bright[:, :100, :3] = 255  # hidden white: never counted
    hidden = Image.fromarray(bright, "RGBA")

    assert measure(hidden).stops == pytest.approx(measure(image).stops, abs=0.2)
    assert measure(hidden).stops > 1.5


def test_noise_comes_out_as_strongly_as_asked(ai: Ai, models: FixModels):
    clean = np.asarray(scene(3, (400, 300)))
    noisy = np.clip(clean + np.random.default_rng(1).normal(0, 12, clean.shape), 0, 255)
    noisy = noisy.astype(np.uint8)
    measured = measure(Image.fromarray(noisy))

    full = fixed(noisy, Fixing(noise=1.0), measured, "best", ai)
    half = fixed(noisy, Fixing(noise=0.5), measured, "best", ai)

    assert _psnr(full, clean) > _psnr(half, clean) > _psnr(noisy, clean)
    assert models.runs["scunet"] > 0


def test_jpeg_blocks_go_through_fbcnn_at_best_and_scunet_at_fast(ai: Ai, models: FixModels):
    pixels = np.asarray(photo_like((300, 200)))
    measured = measure(Image.fromarray(pixels))

    fixed(pixels, Fixing(jpeg=0.7), measured, "best", ai)
    assert models.runs == {"fbcnn": 1}
    fixed(pixels, Fixing(jpeg=0.7, noise=0.5), measured, "fast", ai)
    assert models.runs["scunet"] == 1  # one pass cleans both


def test_a_dark_photo_is_brightened_then_cleaned(ai: Ai, models: FixModels):
    bright = np.asarray(scene(5, (400, 300)))
    dark = _darkened(bright, 8)
    measured = measure(Image.fromarray(dark))

    out = fixed(dark, Fixing(dark=0.0), measured, "best", ai)

    assert out.mean() > dark.mean() * 2
    assert _psnr(out, bright) > _psnr(dark, bright) + 5
    assert models.runs["scunet"] > 0


def test_local_contrast_is_laid_on_after_brightening(ai: Ai, models: FixModels):
    dark = _darkened(np.asarray(scene(6, (400, 300))), 4)
    measured = measure(Image.fromarray(dark))

    plain = fixed(dark, Fixing(dark=0.0), measured, "best", ai)
    lifted = fixed(dark, Fixing(dark=1.0), measured, "best", ai)

    assert not np.array_equal(plain, lifted)


def test_a_part_fixed_alone_matches_the_same_part_of_the_whole(ai: Ai, models: FixModels):
    dark = _darkened(np.asarray(scene(7, (640, 480))), 6)
    measured = measure(Image.fromarray(dark))
    asked = Fixing(dark=0.5)
    whole = fixed(dark, asked, measured, "best", ai)

    part = fixed(dark[100:300, 200:500], asked, measured, "best", ai, at=(200, 100))

    # Brightening, its debanding and local contrast go by the picture's own places, so a part
    # matches; the denoise's tiles meet differently only near the part's edges.
    inner = np.abs(part[20:-20, 20:-20].astype(int) - whole[120:280, 220:480].astype(int))
    assert inner.max() <= 2


def test_a_crop_is_fixed_with_the_picture_round_it_so_its_edges_match_the_whole(
    ai: Ai, models: FixModels
):
    picture = np.ascontiguousarray(np.asarray(scene(9, (640, 480))))
    asked = Fixing(noise=1.0)
    made = plan(
        Recipe(fixing=asked),
        640,
        480,
        guessed_kind="photo",
        found_focus=(0.5, 0.5),
        starts_on={"photo": "fast", "drawing": "fast"},
    )
    whole = fixed(picture, asked, None, "best", ai)

    part, moved, cut = fixed_part(picture, Box(160, 120, 320, 240), made, None, ai)

    assert cut == (160, 120, 480, 360)
    assert (moved.x, moved.y) == (0, 0)
    assert part.shape == (240, 320, 3)
    # Its edges saw what's beside them, as a preview of a part sees them, not edges repeated.
    edges = [part[:, :2], part[:, -2:], part[:2], part[-2:]]
    wanted = [whole[120:360, 160:162], whole[120:360, 478:480], whole[120:122, 160:480]]
    wanted.append(whole[358:360, 160:480])
    for seen, kept in zip(edges, wanted, strict=True):
        assert np.abs(seen.astype(int) - kept.astype(int)).max() <= 2


def test_a_picture_only_fixed_says_it_is_fixed_and_never_that_it_grows(ai: Ai, models: FixModels):
    picture = scene(11, (320, 240))
    made = plan(
        Recipe(fixing=Fixing(noise=1.0)),
        320,
        240,
        guessed_kind="photo",
        found_focus=(0.5, 0.5),
        starts_on={"photo": "fast", "drawing": "fast"},
    )
    stages: list[str] = []

    done = make(
        picture, made, ai, report=lambda stage, _within: stages.append(stage), stop=lambda: False
    )

    assert set(stages) == {"fixing"}
    assert done.image.size == (320, 240)


def test_a_preview_of_all_of_it_makes_only_the_brightening_and_contrast(ai: Ai, models: FixModels):
    dark = _darkened(np.asarray(scene(10, (320, 240))), 6)
    measured = measure(Image.fromarray(dark))

    light = fixed(dark, Fixing(noise=1.0, dark=0.3), measured, "best", ai, light_only=True)
    noise_only = fixed(dark, Fixing(noise=1.0), None, "best", ai, light_only=True)

    assert light.mean() > dark.mean() * 2
    assert np.array_equal(noise_only, dark)
    assert models.runs["scunet"] == 0


def test_the_fixes_go_on_the_card_only_where_it_has_room(tmp_path: Path):
    on_card = Here("card", None, {})
    roomy = Ai(Sessions(), Tools(DataPaths(tmp_path / "A")), lambda: on_card, lambda: 6 * 2**30)
    full = Ai(Sessions(), Tools(DataPaths(tmp_path / "B")), lambda: on_card, lambda: 2**28)

    assert roomy.fix_place([SCUNET, NAFNET]) == "card"
    assert full.fix_place([SCUNET]) == "processor"
    assert full.fix_place([]) == "card"
    assert HELD[SCUNET.id] > HELD[NAFNET.id]


def test_a_grey_picture_stays_grey(ai: Ai, models: FixModels):
    grey = np.asarray(scene(8, (300, 200)).convert("L"))
    dark = np.repeat(_darkened(np.repeat(grey[..., None], 3, -1), 6)[..., :1], 3, -1)
    measured = measure(Image.fromarray(dark))

    out = fixed(np.ascontiguousarray(dark), Fixing(dark=0.4), measured, "best", ai)

    assert np.array_equal(out[..., 0], out[..., 1])
    assert np.array_equal(out[..., 1], out[..., 2])


def test_a_smooth_dark_gradient_brightened_a_lot_doesnt_band(ai: Ai, models: FixModels):
    ramp = np.linspace(0, 10, 512)[None, :, None].repeat(64, 0).repeat(3, 2)
    dark = np.rint(ramp).astype(np.uint8)  # eleven steps across: an 8-bit file's own banding
    measured = measure(Image.fromarray(dark))

    out = fixed(dark, Fixing(dark=0.0), measured, "best", ai)

    row = out[32, :, 1]
    assert measured.stops > 3
    assert len(np.unique(row)) > 3 * len(np.unique(dark[32, :, 1]))
    assert np.abs(np.diff(row.astype(int))).max() < 12  # no step of a whole band's height


def test_the_guard_holds_back_what_the_blur_model_invents_in_a_flat_place(
    ai: Ai, models: FixModels
):
    flat = np.full((200, 300, 3), 120, np.uint8)
    measured = measure(Image.fromarray(flat))

    out = fixed(flat, Fixing(blur=1.0), measured, "best", ai)

    assert np.abs(out.astype(int) - 120).max() <= 2
    assert models.runs["nafnet"] > 0


def test_nothing_on_or_nothing_dark_leaves_the_picture_as_it_is(ai: Ai, models: FixModels):
    pixels = np.asarray(scene(9, (200, 150)))
    measured = measure(Image.fromarray(pixels))

    assert fixed(pixels, Fixing(dark=0.0), measured, "best", ai) is pixels
    assert not models.runs


def test_fixing_stops_when_asked(ai: Ai, models: FixModels):
    pixels = np.asarray(photo_like((900, 700)))
    measured = measure(Image.fromarray(pixels))
    asked = iter([False, False, True])

    with pytest.raises(StoppedError):
        fixed(pixels, Fixing(noise=1.0), measured, "best", ai, stop=lambda: next(asked, True))


def test_fixing_says_how_far_it_has_got(ai: Ai, models: FixModels):
    pixels = np.asarray(photo_like((900, 700)))
    measured = measure(Image.fromarray(pixels))
    heard: list[tuple[int, int]] = []

    def told(done: int, total: int) -> None:
        heard.append((done, total))

    fixed(pixels, Fixing(noise=1.0, blur=0.5), measured, "best", ai, told=told)

    assert heard[-1][0] == heard[-1][1]
    assert [done for done, _ in heard] == sorted(done for done, _ in heard)
