"""Making a 3D photo (mado/motion.py): the encoder Mado uses, the frames of a made-up scene whose
depth is known, and a 3D photo that can't be made as an MP4 saying why."""

import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
from PIL import Image

from mado.ai import Ai
from mado.config import DataPaths
from mado.core.icc import display_p3
from mado.core.motion import Moving
from mado.depth import Depths
from mado.directml import ModelError, Sessions
from mado.editing import Editor
from mado.encode import in_srgb
from mado.motion import Encoders, Frames, MotionError, Motions, encoded
from mado.tools import Tools
from tests.conftest import ON_PROCESSOR
from tests.depth_models import with_depth_model
from tests.depth_scenes import layers

FFMPEG = [sys.executable, str(Path(__file__).parent / "fake_ffmpeg.py")]


def test_windows_own_encoder_goes_first_then_the_cards_and_never_openh264(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MADO_FAKE_ENCODERS", "h264_amf,h264_qsv,libopenh264")
    assert Encoders().first(FFMPEG) == "h264_amf"
    monkeypatch.setenv("MADO_FAKE_ENCODERS", "h264_mf,h264_nvenc")
    assert Encoders().first(FFMPEG) == "h264_mf"
    monkeypatch.setenv("MADO_FAKE_ENCODERS", "libopenh264")
    assert Encoders().first(FFMPEG) is None
    assert Encoders().first(["no-such-ffmpeg"]) is None


def test_an_encoder_that_failed_once_is_tried_again(monkeypatch: pytest.MonkeyPatch):
    found = Encoders()
    monkeypatch.setenv("MADO_FAKE_ENCODERS", "none")
    assert found.first(FFMPEG) is None
    monkeypatch.setenv("MADO_FAKE_ENCODERS", "h264_mf")  # a driver came back, say
    assert found.first(FFMPEG) == "h264_mf"


def _frames(count: int) -> Iterator[np.ndarray]:
    return (np.zeros((48, 64, 3), np.uint8) for _ in range(count))


def test_ffmpeg_that_refuses_the_frames_says_why_and_leaves_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MADO_FAKE_REFUSE", "1")
    out = tmp_path / "made.mp4"

    with pytest.raises(MotionError, match="can't make video this size"):
        encoded(_frames(400), FFMPEG, "h264_mf", (64, 48), out)
    assert not out.exists()


def test_ffmpeg_saying_a_lot_as_it_works_never_holds_the_frames_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MADO_FAKE_CHATTY", "1")
    out = tmp_path / "made.mp4"
    done = threading.Event()

    def make() -> None:
        encoded(_frames(30), FFMPEG, "h264_mf", (64, 48), out)
        done.set()

    threading.Thread(target=make, daemon=True).start()
    assert done.wait(60)
    assert out.read_bytes().endswith(b"frames=30")


def test_frames_that_go_wrong_stop_ffmpeg_and_leave_no_file(tmp_path: Path):
    out = tmp_path / "made.mp4"

    def frames() -> Iterator[np.ndarray]:
        yield np.zeros((48, 64, 3), np.uint8)
        raise RuntimeError("a frame went wrong")

    with pytest.raises(RuntimeError):
        encoded(frames(), FFMPEG, "h264_mf", (64, 48), out)
    assert not out.exists()


def test_a_3d_photo_is_in_srgb_whatever_colours_its_picture_has():
    picture, near, _post = layers((240, 135))
    wide = picture.copy()
    wide.info["icc_profile"] = display_p3()
    square = np.asarray(Image.fromarray(near, "F").resize((518, 518), Image.Resampling.NEAREST))
    nothing = np.zeros((10, 10), np.uint8)

    frames = Frames(wide, square.astype(np.float32), nothing, Moving(seconds=3), (240, 135), None)

    expected = np.asarray(in_srgb(picture, display_p3()), np.float32)
    assert np.abs(frames.pixels.astype(np.float32) - expected).mean() < 1.5
    assert np.abs(frames.pixels.astype(np.float32) - np.asarray(picture, np.float32)).mean() > 3


def test_near_things_move_more_than_far_ones_and_what_they_uncover_is_filled():
    picture, near, post = layers((480, 270))
    square = np.asarray(Image.fromarray(near, "F").resize((518, 518), Image.Resampling.NEAREST))
    nothing = np.zeros((10, 10), np.uint8)

    frames = Frames(
        picture, square.astype(np.float32), nothing, Moving("sway", 3, 1.0), (480, 270), None
    )
    rest = frames.frame(0)
    swayed = frames.frame(len(frames.views) // 4)  # the view as far to one side as it goes

    assert len(frames.views) == 90
    red = (rest[..., 0] > 120) & (rest[..., 1] < 80)
    moved = (swayed[..., 0] > 120) & (swayed[..., 1] < 80)
    columns_rest = np.flatnonzero(red.any(axis=0))
    columns_moved = np.flatnonzero(moved.any(axis=0))
    shift = abs(columns_moved.mean() - columns_rest.mean())
    assert shift > 4  # the near post moved
    wall = rest[20:60, 20:60].astype(np.float32)
    assert (
        np.abs(swayed[20:60, 20:60].astype(np.float32) - wall).mean()
        < np.abs(
            swayed[100:200, int(columns_rest.min()) - 6 : int(columns_rest.max()) + 6].astype(
                np.float32
            )
            - rest[100:200, int(columns_rest.min()) - 6 : int(columns_rest.max()) + 6].astype(
                np.float32
            )
        ).mean()
    )
    assert post.any()
    assert frames.back.shape == (270, 480, 3)


type Pixels = npt.NDArray[np.uint8]


def _nearest_across(pixels: Pixels, hole: npt.NDArray[np.bool_]) -> Pixels:
    """A stand-in for LaMa: each place it fills takes the colour nearest it across its row, of
    what it was shown."""
    made = pixels.copy()
    for row in range(hole.shape[0]):
        missing = np.flatnonzero(hole[row])
        known = np.flatnonzero(~hole[row])
        if missing.size == 0 or known.size == 0:
            continue
        at = np.searchsorted(known, missing)
        left = known[np.clip(at - 1, 0, known.size - 1)]
        right = known[np.clip(at, 0, known.size - 1)]
        picked = np.where(np.abs(missing - left) <= np.abs(right - missing), left, right)
        made[row, missing] = pixels[row, picked]
    return made


@pytest.mark.parametrize("fill", [None, _nearest_across], ids=["fast", "best"])
def test_what_the_view_uncovers_is_filled_from_farther_away_never_from_the_near_thing(
    fill: Callable[[Pixels, npt.NDArray[np.bool_]], Pixels] | None,
):
    # A red post near the view on a blue ground far from it: behind the post's edges, as far as
    # the view moves, the layer behind is the ground's blue, stretched (Fast) or drawn (Best),
    # not the post's red: what a moving view uncovers there is ground. (Filled from only the
    # post's edge, Fast's came out as red as blue there, Best's purple.)
    pixels = np.empty((150, 200, 3), np.uint8)
    pixels[...] = (40, 80, 200)
    pixels[:, 40:160] = (200, 30, 30)
    truth = np.full((150, 200), 0.1, np.float32)
    truth[:, 40:160] = 0.9
    square = np.asarray(
        Image.fromarray(truth, "F").resize((518, 518), Image.Resampling.NEAREST), np.float32
    )
    nothing = np.zeros((10, 10), np.uint8)

    frames = Frames(
        Image.fromarray(pixels), square, nothing, Moving("sway", 3, 1.0), (200, 150), fill
    )

    band = (truth > 0.5) & (frames.back_near < 0.3)  # the post's edges, the ground behind
    assert band.sum() > 300
    behind = frames.back[band].astype(np.float32)
    bluer = behind[:, 2] - behind[:, 0]  # the ground's is 160 bluer than red, the post's -170
    assert bluer.mean() > 100
    assert bluer.min() > 50
    assert (frames.back[75, 90:110] == (200, 30, 30)).all()  # deep inside, out of reach: kept


def test_an_mp4_without_ffmpeg_says_how_to_get_it(
    paths: DataPaths,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ai = Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR)
    with_depth_model(monkeypatch, ai, tmp_path / "models")
    editor = Editor(ai, tmp_path / "edits")
    picture, _near, _post = layers((240, 135))
    source = tmp_path / "Wall.png"
    picture.save(source)
    motions = Motions(
        tmp_path / "motion",
        ai,
        Depths(ai, editor, tmp_path / "depth"),
        editor,
        image=lambda path, _version: Image.open(path).convert("RGB"),
        ffmpeg=lambda: None,
    )

    asked = motions.ask(1, source, "1", Moving(seconds=3), ())
    found = motions.get(asked.id)
    for _ in range(200):
        found = motions.get(asked.id)
        if found is not None and found.state in ("done", "failed"):
            break
        time.sleep(0.05)
    motions.stop()

    assert found is not None
    assert found.state == "failed"
    assert found.problem is not None
    assert "needs ffmpeg" in found.problem
    assert not motions.ffmpeg_ready()


def _motions(
    ai: Ai,
    tmp_path: Path,
    depths: object | None = None,
    image: Callable[..., Image.Image] | None = None,
) -> tuple[Motions, Path]:
    editor = Editor(ai, tmp_path / "edits")
    picture, _near, _post = layers((240, 135))
    source = tmp_path / "Wall.png"
    picture.save(source)
    motions = Motions(
        tmp_path / "motion",
        ai,
        cast(Depths, depths) if depths is not None else Depths(ai, editor, tmp_path / "depth"),
        editor,
        image=image or (lambda path, _version: Image.open(path).convert("RGB")),
        ffmpeg=lambda: FFMPEG,
    )
    return motions, source


def _finished(motions: Motions, asked_id: str) -> str | None:
    for _ in range(400):
        found = motions.get(asked_id)
        if found is None or found.state in ("done", "failed"):
            return None if found is None else found.state
        time.sleep(0.05)
    return "still going"


class _FailingDepths:
    """Depths whose model can't run."""

    def read(self, *_given: object, **_asked: object) -> object:
        raise ModelError("The depth model couldn't run: the graphics card ran out of memory.")


def test_a_model_that_cant_run_says_so_in_its_own_words(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ai = Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR)
    with_depth_model(monkeypatch, ai, tmp_path / "models")
    motions, source = _motions(ai, tmp_path, _FailingDepths())

    asked = motions.ask(1, source, "1", Moving(seconds=3), ())
    assert _finished(motions, asked.id) == "failed"
    found = motions.get(asked.id)
    motions.stop()

    assert found is not None
    assert found.problem == "The depth model couldn't run: the graphics card ran out of memory."


def test_one_asked_for_again_stops_the_one_before_which_says_so(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ai = Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR)
    with_depth_model(monkeypatch, ai, tmp_path / "models")

    def slowly(path: Path, _version: str) -> Image.Image:
        time.sleep(0.4)
        return Image.open(path).convert("RGB")

    motions, source = _motions(ai, tmp_path, image=slowly)

    first = motions.ask(1, source, "1", Moving(seconds=3), ())
    time.sleep(0.1)  # being made
    second = motions.ask(1, source, "1", Moving("sway", 3), ())
    assert _finished(motions, second.id) == "done"
    assert _finished(motions, first.id) == "failed"
    before = motions.get(first.id)
    motions.stop()

    assert before is not None
    assert before.file is None
    assert sorted(each.name for each in (tmp_path / "motion").iterdir()) == [f"{second.id}.mp4"]


def test_one_let_go_just_as_it_was_made_leaves_no_file(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ai = Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR)
    with_depth_model(monkeypatch, ai, tmp_path / "models")
    motions, source = _motions(ai, tmp_path)
    making = vars(Motions)["_made"]

    def made_then_let_go(self: Motions, asked: Any, stop: Any, report: Any) -> Any:
        result = making(self, asked, stop, report)
        self.drop(asked.id)  # let go as it finished
        return result

    monkeypatch.setattr(Motions, "_made", made_then_let_go)
    asked = motions.ask(1, source, "1", Moving(seconds=3), ())
    assert _finished(motions, asked.id) is None
    time.sleep(0.3)
    motions.stop()

    assert not list((tmp_path / "motion").glob("*.mp4"))
