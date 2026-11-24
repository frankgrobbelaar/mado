"""What each tool does to an HDR photo's gain map, through Mado's own making (mado/making.py), on
made-up HDR photos: the decisions in mado/core/gains.py and mado/depth.py, each tested on the HDR
rendition the gain map makes (its light, in linear terms), as an HDR screen shows it."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from mado import hdr
from mado.ai import Ai
from mado.config import DataPaths
from mado.core.depth import Depthing, Fog, Portrait, TiltShift, to_linear
from mado.core.edits import Editing, Erase, Stroke
from mado.core.fixes import Fixing
from mado.core.gainmap import GainMap, alternate
from mado.core.looks import mado_look
from mado.core.painting import CLASSICS, PAINTERS, Painting
from mado.core.recipe import Recipe, Styling
from mado.core.restore import Restoring
from mado.depth import Depths
from mado.directml import Sessions
from mado.editing import Editor
from mado.encode import with_gain_map
from mado.making import Made, Picture, make, planned, see
from mado.pictures import decode
from mado.tools import Tools
from tests.conftest import ON_PROCESSOR
from tests.depth_models import with_depth_model
from tests.depth_scenes import field
from tests.edit_models import with_editing_models
from tests.fix_models import with_fix_models
from tests.hdr_files import INFO, ultra_hdr_jpeg
from tests.restore_models import with_restore_models


@pytest.fixture
def ai(paths: DataPaths) -> Ai:
    return Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR)


def hdr_jpeg(path: Path, picture: Image.Image, gains: np.ndarray) -> Path:
    """A made-up HDR photo of `picture` with these gains (stops, at any size), as Mado writes
    one."""
    data = with_gain_map(picture, "JPEG", {"quality": 95}, GainMap(gains.astype(np.float32), INFO))
    path.write_bytes(data)
    return path


def made_with(
    path: Path,
    recipe: Recipe,
    ai: Ai,
    *,
    editor: Editor | None = None,
    depths: Depths | None = None,
) -> tuple[GainMap, Made]:
    """The photo at `path` made to `recipe`, its gain map with it: its own gain map, and what
    was made."""
    image = decode(path, "picture", longest=None)
    seen = see(image, Picture(path, "picture", "JPEG", None))
    plan = planned(recipe, seen, {"photo": "fast", "drawing": "fast"})
    gain = hdr.read(path, ffmpeg=None, scratch=None)
    assert gain is not None
    made = make(
        image,
        plan,
        ai,
        report=lambda _stage, _done: None,
        stop=lambda: False,
        editor=editor,
        key=f"{path}|1",
        depths=depths,
        found_focus=seen.focus,
        gain=gain,
    )
    return gain, made


def renditions(made: Made) -> tuple[np.ndarray, np.ndarray]:
    """The picture made in linear light at its gain map's size, and its HDR rendition there."""
    assert made.gain is not None
    small = made.image.convert("RGB").resize(made.gain.size, Image.Resampling.BOX)
    base = to_linear(np.asarray(small))
    return base, alternate(base, made.gain.gains, made.gain.info)


class TestLooks:
    def test_a_black_and_white_look_stays_black_and_white_on_an_hdr_screen(
        self, ai: Ai, tmp_path: Path
    ):
        path = tmp_path / "PXL_1203.jpg"
        path.write_bytes(ultra_hdr_jpeg((320, 240), colour=True))
        silver = mado_look("silver")
        assert silver is not None
        gain, made = made_with(path, Recipe(styling=Styling(silver)), ai)
        assert gain.gains.ndim == 3  # the photo's gain map is in colour
        assert made.gain is not None
        assert made.gain.gains.ndim == 2  # one channel, once given a look
        base, lit = renditions(made)
        assert np.abs(lit[..., 0] - lit[..., 2]).max() < 0.02  # grey on an HDR screen too
        # Its colour gain map kept as it was would bring colour back where the sun is:
        kept_colour = alternate(base, gain.gains, gain.info)
        assert np.abs(kept_colour[..., 0] - kept_colour[..., 2]).max() > 0.1

    def test_a_warm_look_stays_warm_in_the_hdr_rendition(self, ai: Ai, tmp_path: Path):
        path = tmp_path / "PXL_1204.jpg"
        path.write_bytes(ultra_hdr_jpeg((320, 240)))
        warm = mado_look("warm-film")
        assert warm is not None
        _gain, made = made_with(path, Recipe(styling=Styling(warm)), ai)
        assert made.gain is not None
        base, lit = renditions(made)
        bright = made.gain.gains > 1.0  # where the HDR rendition goes past a stop brighter
        assert bright.any()
        # Its colours in the same proportions: the look's warmth, made brighter.
        sdr_warmth = base[bright][:, 0] / np.maximum(base[bright][:, 2], 1e-3)
        hdr_warmth = lit[bright][:, 0] / np.maximum(lit[bright][:, 2], 1e-3)
        assert np.median(np.abs(hdr_warmth - sdr_warmth) / sdr_warmth) < 0.05


class TestFixesAndPainting:
    def test_a_fix_keeps_the_gain_map_as_it_is(
        self, ai: Ai, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        with_fix_models(monkeypatch, ai, tmp_path / "models")
        path = tmp_path / "PXL_1205.jpg"
        path.write_bytes(ultra_hdr_jpeg((320, 240)))
        gain, made = made_with(path, Recipe(fixing=Fixing(noise=1.0)), ai)
        assert made.gain is not None
        assert np.allclose(made.gain.gains, gain.gains, atol=1e-4)

    def test_a_painter_keeps_it_and_a_pencil_sketch_leaves_none(self, ai: Ai, tmp_path: Path):
        path = tmp_path / "PXL_1206.jpg"
        path.write_bytes(ultra_hdr_jpeg((320, 240)))
        pencil = next(each for each in CLASSICS if each.id == "pencil")
        oil = next(each for each in CLASSICS if each.id == "oil")
        _gain, sketched = made_with(path, Recipe(painting=Painting(pencil)), ai)
        assert sketched.gain is None  # paper and lines: no HDR left
        gain, oiled = made_with(path, Recipe(painting=Painting(oil)), ai)
        assert oiled.gain is not None
        assert np.allclose(oiled.gain.gains, gain.gains, atol=1e-4)  # the lamp still glows
        assert PAINTERS  # the networks keep it the same way (mado/core/gains.py)


class TestDepth:
    @pytest.fixture
    def depths(
        self, ai: Ai, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[Editor, Depths]:
        with_depth_model(monkeypatch, ai, tmp_path / "models")
        editor = Editor(ai, tmp_path / "edits")
        return editor, Depths(ai, editor, tmp_path / "depth")

    def test_fog_thins_the_gain_with_distance(
        self, ai: Ai, tmp_path: Path, depths: tuple[Editor, Depths]
    ):
        picture, _truth = field((400, 300))
        path = hdr_jpeg(tmp_path / "Field.jpg", picture, np.full((75, 100), 2.0, np.float32))
        editor, reading = depths
        recipe = Recipe(depthing=Depthing(fog=Fog(density=0.9)))
        _gain, made = made_with(path, recipe, ai, editor=editor, depths=reading)
        assert made.gain is not None
        far = float(made.gain.gains[: made.gain.size[1] // 4].mean())  # the sky: farthest
        near = float(made.gain.gains[-made.gain.size[1] // 8 :].mean())  # the ground at the foot
        assert far < 1.0  # through thick fog a far light barely brightens
        assert near > 1.5  # the nearest nearly as it was
        assert near > far

    def test_portrait_blur_spreads_a_far_lights_gain_as_its_light(
        self, ai: Ai, tmp_path: Path, depths: tuple[Editor, Depths]
    ):
        picture, _truth = field((400, 300))
        gains = np.zeros((300, 400), np.float32)
        gains[36:48, 74:86] = 3.0  # the sun, far away
        path = hdr_jpeg(tmp_path / "Field.jpg", picture, gains)
        editor, reading = depths
        recipe = Recipe(depthing=Depthing(portrait=Portrait(focus=(0.62, 0.86), aperture=1.4)))
        gain, made = made_with(path, recipe, ai, editor=editor, depths=reading)
        assert made.gain is not None
        before = gain.gains[20:64, 58:102]
        after = made.gain.gains[20:64, 58:102]
        assert after.max() < before.max()  # blurred: its peak lower
        assert (after > 0.3).sum() > (before > 0.3).sum()  # and its disc wider

    def test_tilt_shift_blurs_the_gain_above_and_below_its_band(
        self, ai: Ai, tmp_path: Path, depths: tuple[Editor, Depths]
    ):
        picture, _truth = field((400, 300))
        gains = np.zeros((300, 400), np.float32)
        gains[::10, ::10] = 3.0  # lights all over
        path = hdr_jpeg(tmp_path / "Field.jpg", picture, gains)
        editor, reading = depths
        recipe = Recipe(depthing=Depthing(tilt=TiltShift(centre=0.5, height=0.2, strength=1.0)))
        _gain, made = made_with(path, recipe, ai, editor=editor, depths=reading)
        assert made.gain is not None
        top = made.gain.gains[:40]
        band = made.gain.gains[140:160]
        assert top.max() < 2.0  # blurred out above the band
        assert band.max() > 2.5  # kept sharp in it


def test_an_erased_lamps_gain_is_filled_from_round_it(
    ai: Ai, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    with_editing_models(monkeypatch, ai, tmp_path / "models")
    picture = Image.new("RGB", (320, 240), (90, 90, 100))
    gains = np.full((60, 80), 0.5, np.float32)
    gains[24:32, 36:44] = 3.0  # a bright lamp in the middle
    path = hdr_jpeg(tmp_path / "Lamp.jpg", picture, gains)
    brush = Stroke(points=((0.5, 0.47),), size=0.2)
    recipe = Recipe(editing=Editing((Erase(strokes=(brush,)),)))
    _gain, made = made_with(path, recipe, ai, editor=Editor(ai, tmp_path / "edits"))
    assert made.gain is not None
    assert made.gain.gains[24:32, 36:44].max() == pytest.approx(0.5, abs=0.15)


class TestRestored:
    """Restoring an HDR photo of an old print: its scratches filled in the gain map too, and its
    colour brought in or back keeping the light where it was."""

    def test_a_filled_scratch_doesnt_glow_on_again(
        self, ai: Ai, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        with_editing_models(monkeypatch, ai, tmp_path / "models")
        with_restore_models(monkeypatch, ai, tmp_path / "models")
        grey = Image.new("L", (320, 240), 110)
        ImageDraw.Draw(grey).line([(0, 120), (320, 120)], fill=250, width=3)  # a white scratch
        gains = np.full((60, 80), 0.5, np.float32)
        gains[29:31, :] = 3.0  # it glows on an HDR screen
        path = hdr_jpeg(tmp_path / "Old print.jpg", grey.convert("RGB"), gains)
        recipe = Recipe(restoring=Restoring(scratches=()))
        _gain, made = made_with(path, recipe, ai, editor=Editor(ai, tmp_path / "edits"))
        assert made.plan.restoring is not None
        assert made.gain is not None
        assert made.gain.gains[29:31, 10:70].max() == pytest.approx(0.5, abs=0.2)

    def test_faded_colours_brought_back_keep_its_light_where_it_was(
        self, ai: Ai, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        with_restore_models(monkeypatch, ai, tmp_path / "models")
        picture = Image.new("RGB", (320, 240), (170, 150, 120))  # a faded print's cast
        picture.paste((230, 210, 180), (100, 80, 220, 160))
        gains = np.zeros((60, 80, 3), np.float32)
        gains[20:40, 25:55] = (2.0, 2.4, 2.8)  # a colour gain map: a window's glow
        path = hdr_jpeg(tmp_path / "Faded.jpg", picture, gains)
        recipe = Recipe(restoring=Restoring(faded=0.8))
        _gain, made = made_with(path, recipe, ai, editor=Editor(ai, tmp_path / "edits"))
        assert made.plan.restoring is not None
        assert made.gain is not None
        assert made.gain.gains.ndim == 2  # one channel, as a look's
        assert made.gain.gains[30, 40] > 2.0 > made.gain.gains[5, 5]
