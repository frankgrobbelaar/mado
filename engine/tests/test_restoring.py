"""Restoring old photos in the engine: what the detector finds (kept in memory and in the cache by
the picture's version), scratches filled with only what the mask covers touched, colour put onto
the picture's own light, faded colours brought back, a part shown as the whole is made, and what a
batch's picture keeps (nothing). The detector, DDColor and LaMa are stand-ins
(tests/restore_models.py)."""

import io
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageDraw

from mado.ai import Ai
from mado.config import DataPaths
from mado.core.edits import Editing, Erase, Stroke
from mado.core.recipe import Recipe, plan
from mado.core.restore import Restoring, lab, lightness, mask_size
from mado.directml import Sessions
from mado.editing import Editor, picture_key
from mado.making import make
from mado.restoring import Restorer, RestoringError, fill_scratches
from mado.tools import Tools
from tests.conftest import ON_PROCESSOR
from tests.edit_models import fill_with_mean
from tests.restore_models import GRASS_AB, SKY_AB, RestoreModels, with_restore_models

KEY = picture_key(Path("D:/Scans/Grandad's boat.tif"), "1a2b-3c4d")
AT = "edits-none"


def _print(size: tuple[int, int] = (960, 720), mode: str = "L") -> Image.Image:
    """A made-up old print: a smooth sky over a sea, grey, with a bright scratch across it."""
    width, height = size
    rows = np.linspace(0.75, 0.35, height, dtype=np.float32)[:, None]
    grey = np.repeat(rows, width, axis=1)
    grey[height // 2 :] *= 0.7
    image = Image.fromarray((grey * 255).astype(np.uint8), "L")
    draw = ImageDraw.Draw(image)
    draw.line([(0, height // 3), (width, height // 3 + 40)], fill=250, width=max(2, width // 240))
    return image.convert(mode) if mode != "L" else image


@pytest.fixture
def models(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Ai, RestoreModels]:
    ai = Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR, room=lambda: None)
    return ai, with_restore_models(monkeypatch, ai, tmp_path / "models")


@pytest.fixture
def restorer(models: tuple[Ai, RestoreModels], paths: DataPaths) -> Restorer:
    return Restorer(models[0], paths.cache / "edits")


def test_the_detector_finds_a_scratch_and_not_the_smooth_sky(restorer: Restorer):
    image = _print()
    found = restorer.found(image, KEY, AT)
    assert found.mask.shape == (720, 960)  # under the mask's size: the picture's own
    row = 720 // 3 + 20  # the scratch, halfway across
    assert found.mask[row - 2 : row + 3, 480].max() == 255
    assert found.mask[60, 100] == 0
    assert found.mask[600, 800] == 0
    assert found.place == "processor"
    assert found.seconds > 0


def test_the_detector_reads_two_canvases_of_fixed_sizes(
    restorer: Restorer, models: tuple[Ai, RestoreModels]
):
    restorer.found(_print((1200, 900)), KEY, AT)
    assert models[1].canvases == [(1, 1, 256, 512), (1, 1, 512, 1024)]


def test_what_was_found_is_kept_in_the_cache_and_read_from_it_when_mado_starts_again(
    restorer: Restorer, models: tuple[Ai, RestoreModels], paths: DataPaths
):
    image = _print()
    first = restorer.found(image, KEY, AT)
    assert models[1].runs["oldphoto-scratch-detector"] == 2
    kept = list((paths.cache / "edits").rglob("scratches-*.png"))
    assert len(kept) == 1
    again = Restorer(models[0], paths.cache / "edits").found(image, KEY, AT)
    assert models[1].runs["oldphoto-scratch-detector"] == 2  # read from the cache, not found again
    assert np.array_equal(again.mask, first.mask)
    assert again.seconds == 0


def test_a_batchs_picture_keeps_nothing(restorer: Restorer, paths: DataPaths):
    restorer.found(_print(), KEY, AT, keep=False)
    assert not list((paths.cache / "edits").rglob("*.png"))


def test_a_big_scan_is_found_at_the_masks_size(restorer: Restorer):
    found = restorer.found(_print((3000, 2000)), KEY, AT)
    assert found.mask.shape[::-1] == mask_size(3000, 2000) == (1152, 768)


def test_strokes_paint_what_it_missed_and_take_away_what_isnt_a_scratch(restorer: Restorer):
    image = _print()
    missed = Stroke(((0.8, 0.6), (0.8, 0.9)), 0.02)
    wrong = Stroke(((0.0, 0.333), (0.4, 0.36)), 0.04, take=True)
    mask = restorer.mask(image, KEY, AT, Restoring(scratches=(missed, wrong)))
    assert mask[int(0.75 * 720), int(0.8 * 960)] == 255
    assert mask[720 // 3 + 4, 100] == 0  # taken away
    assert mask[720 // 3 + 32, 800] == 255  # the rest of the scratch, still found


def test_filling_touches_only_what_the_mask_covers():
    image = np.asarray(_print().convert("RGB"))
    mask = np.zeros(image.shape[:2], np.uint8)
    mask[240:250, 100:300] = 255
    made = fill_scratches(image, mask, fill_with_mean)
    assert np.array_equal(made[:200], image[:200])
    assert np.array_equal(made[300:], image[300:])
    assert not np.array_equal(made[240:250, 100:300], image[240:250, 100:300])


def test_filling_a_big_scan_works_on_a_smaller_copy_and_lays_it_back_at_full_size():
    image = np.asarray(_print((3200, 2400)).convert("RGB"))
    mask = np.zeros((768, 1024), np.uint8)  # at the mask's size
    mask[256:259, 0:1024] = 255  # the scratch, a third of the way down
    calls: list[tuple[int, ...]] = []

    def fill(picture: np.ndarray, hole: np.ndarray) -> np.ndarray:
        calls.append(picture.shape)
        return fill_with_mean(picture, hole)

    made = fill_scratches(image, mask, fill)
    assert made.shape == image.shape
    assert all(shape == (512, 512, 3) for shape in calls)
    assert len(calls) == 3  # one row of squares along the scratch, on the 1024 x 768 copy
    scratch = made[800:806, 1600].astype(np.int32)
    assert np.abs(scratch - made[700, 1600].astype(np.int32)).max() < 40  # filled like the sky
    assert np.array_equal(made[:700], image[:700])


def test_a_mask_over_most_of_the_picture_isnt_filled(restorer: Restorer):
    everything = Stroke(((0.0, 0.5), (1.0, 0.5)), 1.0)
    with pytest.raises(RestoringError, match="most of a picture"):
        restorer.prepared(_print(), KEY, AT, Restoring(scratches=(everything,)))


def test_a_grey_print_with_its_scratches_filled_stays_grey(restorer: Restorer):
    prepared = restorer.prepared(_print(), KEY, AT, Restoring(scratches=()))
    assert prepared.picture.mode == "L"
    assert 0 < prepared.filled < 0.1
    assert restorer.whole(prepared) is prepared.picture  # nothing more to lay on


def test_colour_goes_onto_the_pictures_own_light(
    restorer: Restorer, models: tuple[Ai, RestoreModels]
):
    image = _print()
    prepared = restorer.prepared(image, KEY, AT, Restoring(colour=1.0))
    made = restorer.whole(prepared)
    assert made.mode == "RGB"
    rgb = (np.asarray(made, np.float32) / np.float32(255)).astype(np.float32)
    own = (np.asarray(image.convert("RGB"), np.float32) / np.float32(255)).astype(np.float32)
    assert np.abs(lightness(rgb) - lightness(own)).mean() < 1.0  # its detail stays its own
    found = lab(rgb)
    assert np.abs(found[100, 480, 1:] - np.array(SKY_AB)).max() < 6  # the sky as the model said
    assert np.abs(found[600, 480, 1:] - np.array(GRASS_AB)).max() < 6
    assert models[1].runs["ddcolor-tiny"] == 1
    restorer.prepared(image, KEY, AT, Restoring(colour=0.4))  # another strength: no model again
    assert models[1].runs["ddcolor-tiny"] == 1


def test_colours_guessed_before_its_scratches_were_filled_arent_used_once_they_are(
    restorer: Restorer, models: tuple[Ai, RestoreModels]
):
    image = _print()
    restorer.prepared(image, KEY, AT, Restoring(colour=1.0, faded=1.0))
    restorer.prepared(image, KEY, AT, Restoring(scratches=(), colour=1.0, faded=1.0))
    # DDColor never sees a scratch: the picture filled is coloured afresh, its levels measured anew.
    assert models[1].runs["ddcolor-tiny"] == 2


def test_a_colour_at_nought_needs_no_model(restorer: Restorer, models: tuple[Ai, RestoreModels]):
    prepared = restorer.prepared(_print(), KEY, AT, Restoring(colour=0.0))
    assert prepared.ab is None
    assert models[1].runs["ddcolor-tiny"] == 0


def test_a_jobs_edits_are_made_once_when_it_restores_them(
    models: tuple[Ai, RestoreModels], paths: DataPaths, monkeypatch: pytest.MonkeyPatch
):
    ai = models[0]
    editor = Editor(ai, paths.cache / "edits")
    made: list[int] = []
    real = editor._edited  # pyright: ignore[reportPrivateUsage]

    def counted(*asked: Any) -> Any:
        made.append(1)
        return real(*asked)

    monkeypatch.setattr(editor, "_edited", counted)
    edits = (Erase(strokes=(Stroke(((0.1, 0.9),), 0.05),), quality="best"),)
    asked = plan(
        Recipe(editing=Editing(edits), restoring=Restoring(colour=1.0)),
        960,
        720,
        guessed_kind="photo",
        found_focus=(0.5, 0.5),
        starts_on={"photo": "fast", "drawing": "fast"},
    )

    done = make(
        _print(mode="RGB"),
        asked,
        ai,
        report=lambda _stage, _within: None,
        stop=lambda: False,
        editor=editor,
        key=KEY,
        keep=False,  # a batch's picture: nothing kept, so making them again would cost again
    )

    assert done.image.size == (960, 720)
    assert len(made) == 1


def test_a_part_is_shown_as_the_whole_picture_is_made(restorer: Restorer):
    image = _print()
    prepared = restorer.prepared(image, KEY, AT, Restoring(colour=0.8, faded=0.5))
    whole = np.asarray(restorer.whole(prepared), np.int32)
    part = restorer.shown(prepared, image.crop((300, 200, 500, 360)), (300, 200, 500, 360))
    assert np.abs(np.asarray(part, np.int32) - whole[200:360, 300:500]).max() <= 2
    small = restorer.shown(
        prepared, image.resize((240, 180), Image.Resampling.BOX), (0, 0, 960, 720)
    )
    shrunk = np.asarray(
        Image.fromarray(whole.astype(np.uint8)).resize((240, 180), Image.Resampling.BOX), np.int32
    )
    assert np.abs(np.asarray(small, np.int32) - shrunk).mean() < 2


def test_see_through_parts_stay_as_they_are(restorer: Restorer):
    image = _print().convert("RGBA")
    alpha = np.full((720, 960), 255, np.uint8)
    alpha[:, :200] = 0
    image.putalpha(Image.fromarray(alpha))
    prepared = restorer.prepared(image, KEY, AT, Restoring(scratches=(), colour=1.0))
    made = restorer.whole(prepared)
    assert made.mode == "RGBA"
    assert np.array_equal(np.asarray(made.getchannel("A")), alpha)


def test_a_grey_pictures_own_profile_goes_once_its_coloured(restorer: Restorer):
    image = _print()
    # A grey picture's profile: its header says it's for grey (the colour space at byte 16).
    image.info["icc_profile"] = bytes(16) + b"GRAY" + bytes(108)
    coloured = restorer.whole(restorer.prepared(image, KEY, AT, Restoring(colour=1.0)))
    assert "icc_profile" not in coloured.info
    filled = restorer.whole(restorer.prepared(image, KEY, AT, Restoring(scratches=())))
    assert filled.info.get("icc_profile") == image.info["icc_profile"]


def test_faded_colours_come_back_from_the_pictures_own_levels(restorer: Restorer):
    image = _print().convert("RGB")
    faded = (np.asarray(image, np.float32) * 0.6 + 60) * np.array([1.0, 0.92, 0.8])
    picture = Image.fromarray(np.clip(faded, 0, 255).astype(np.uint8))
    made = np.asarray(restorer.whole(restorer.prepared(picture, KEY, AT, Restoring(faded=1.0))))
    shown = np.asarray(picture)
    assert int(made.max()) - int(made.min()) > int(shown.max()) - int(shown.min())  # levels back
    cast = np.abs(made[..., 0].astype(np.int32) - made[..., 2]).mean()
    assert cast < np.abs(shown[..., 0].astype(np.int32) - shown[..., 2]).mean()  # less warm


def test_the_whole_picture_is_laid_on_a_band_at_a_time(restorer: Restorer):
    image = _print((640, 1300))  # taller than a band
    prepared = restorer.prepared(image, KEY, AT, Restoring(colour=0.7))
    whole = np.asarray(restorer.whole(prepared), np.int32)
    at_once = np.asarray(restorer.shown(prepared, image, (0, 0, 640, 1300)), np.int32)
    assert np.abs(whole - at_once).max() <= 1


def test_png_of_what_was_found_is_a_grey_picture_of_the_masks_size(
    restorer: Restorer, paths: DataPaths
):
    restorer.found(_print((1600, 1200)), KEY, AT)
    [kept] = list((paths.cache / "edits").rglob("scratches-*.png"))
    with Image.open(io.BytesIO(kept.read_bytes())) as png:
        assert png.mode == "L"
        assert png.size == (1024, 768)
