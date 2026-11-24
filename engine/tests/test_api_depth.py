"""Depth through the API, end to end with the depth model's stand-in (tests/depth_models.py): what
the Depth tab reads of a picture (flat, its subject, the model to download first), the plan with
the depth tools, previews of all of it and of a part, Save (a new picture named for them,
History's words), see-through and grey pictures kept as they are, a batch with a depth step, and
3D photos made, played and saved (the encoders through tests/fake_ffmpeg.py)."""

import io
import shutil
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db, making
from mado.editing import Editor
from tests.conftest import add, made
from tests.depth_models import DepthModel, with_depth_model
from tests.depth_scenes import field, scan

PORTRAIT = {"portrait": {"focus": None, "aperture": 1.4, "quality": "fast"}}
FOG = {"fog": {"density": 0.8, "colour": None}}
TILT = {"tilt": {"centre": 0.6, "height": 0.2, "strength": 1.0}}


@pytest.fixture
def folder(client: TestClient, tmp_path: Path) -> Path:
    """Garden: a made-up field with a red ball near the camera, a page scanned, the field as a
    sticker (see-through on its left) and in black and white."""
    garden = tmp_path / "Garden"
    garden.mkdir()
    picture, _truth = field((480, 360))
    picture.save(garden / "Red ball.png")
    scan((360, 480)).save(garden / "Old letter.png")
    sticker = picture.convert("RGBA")
    alpha = np.full((360, 480), 255, np.uint8)
    alpha[:, :60] = 0
    sticker.putalpha(Image.fromarray(alpha))
    sticker.save(garden / "Sticker.png")
    picture.convert("L").save(garden / "Grey field.png")
    add(client, garden)
    return garden


@pytest.fixture
def model(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DepthModel:
    app: Any = client.app
    return with_depth_model(monkeypatch, app.state.ai, tmp_path / "models")


def _id(client: TestClient, name: str) -> int:
    pictures = client.get("/pictures").json()["pictures"]
    return next(each["id"] for each in pictures if each["name"] == name)


def _version(client: TestClient, picture: int) -> str:
    return client.get(f"/pictures/{picture}").json()["version"]


def _image(response: Any) -> np.ndarray:
    assert response.status_code == 200, response.text
    return np.asarray(Image.open(io.BytesIO(response.content)).convert("RGBA"))


def _saved(client: TestClient, picture: int, recipe: dict[str, Any]) -> dict[str, Any]:
    body = {"recipe": recipe, "saving": {"how": "new", "format": "PNG"}}
    response = client.post(f"/pictures/{picture}/make", json=body)
    assert response.status_code == 202, response.text
    return made(client, response.json())


def test_the_depth_tab_says_the_model_comes_first(client: TestClient, folder: Path):
    picture = _id(client, "Red ball.png")

    read = client.post(f"/pictures/{picture}/depth", json={"version": _version(client, picture)})

    assert read.status_code == 200, read.text
    found = read.json()
    assert found["read"] is False
    assert [need["id"] for need in found["needs"]] == ["depth-anything-v2-small"]
    assert found["needs"][0]["size"] == 99072196
    plan = client.post(f"/pictures/{picture}/plan", json={"depth": PORTRAIT}).json()
    assert [need["id"] for need in plan["needs"]] == ["depth-anything-v2-small"]
    assert plan["depth"] == "portrait blur at f/1.4"
    # Tilt-shift goes by place alone: it needs no depth.
    tilt = client.post(f"/pictures/{picture}/plan", json={"depth": TILT}).json()
    assert tilt["needs"] == []
    preview = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": {"depth": PORTRAIT}, "side": "after", "fit": {"width": 480, "height": 360}},
    )
    assert preview.status_code == 409


def test_the_depth_tab_reads_a_pictures_depth_once_and_finds_its_subject(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")
    letter = _id(client, "Old letter.png")

    first = client.post(f"/pictures/{picture}/depth", json={"version": _version(client, picture)})
    again = client.post(f"/pictures/{picture}/depth", json={"version": _version(client, picture)})
    page = client.post(f"/pictures/{letter}/depth", json={"version": _version(client, letter)})

    assert first.status_code == 200, first.text
    found = first.json()
    assert found["read"] is True
    assert found["flat"] is False
    assert found["seconds"] is not None
    assert found["subject"] is True
    focus = found["focus"]
    assert 0.5 < focus[0] < 0.75  # the ball, low and right of the middle
    assert 0.6 < focus[1] < 0.95
    assert again.json()["seconds"] is None  # kept
    assert model.runs["depth"] == 2  # once each picture
    assert page.json()["flat"] is True  # a page has no depth to speak of
    changed = client.post(f"/pictures/{picture}/depth", json={"version": "elsewhen"})
    assert changed.status_code == 409


def test_the_plan_says_what_the_depth_tools_do_and_how_long_they_take(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")

    plan = client.post(
        f"/pictures/{picture}/plan", json={"depth": {**PORTRAIT, **FOG, **TILT}}
    ).json()

    assert plan["depth"] == "portrait blur at f/1.4, fog and tilt-shift"
    assert plan["needs"] == []
    assert plan["method"] == "keep"
    assert plan["depthSeconds"] > 0
    assert plan["seconds"] >= plan["depthSeconds"]
    assert plan["depthPlace"] == "processor"


def test_previews_show_the_depth_tools_on_all_of_it_and_on_a_part(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")
    fit = {"width": 480, "height": 360}

    before = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": {"depth": PORTRAIT}, "side": "before", "fit": fit},
        )
    )
    after = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": {"depth": PORTRAIT}, "side": "after", "fit": fit},
        )
    )
    part = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={
                "recipe": {"depth": PORTRAIT},
                "side": "after",
                "region": {"x": 0, "y": 0, "width": 480, "height": 360},
            },
        )
    )

    sky_before = before[20:100, 200:400, :3].astype(np.float32)
    assert np.abs(after[20:100, 200:400, :3] - sky_before).mean() < 6  # blurred, still the sky
    hills = slice(120, 160)
    assert after[hills, :, :3].std() < before[hills, :, :3].std()  # the far hills, blurred
    ball = (slice(250, 300), slice(280, 320))
    assert np.abs(after[ball].astype(int) - before[ball].astype(int)).mean() < 4  # in focus
    assert np.abs(part[:, :, :3].astype(int) - after[:, :, :3].astype(int)).mean() < 6


def test_save_makes_a_new_picture_named_for_its_depth_tools_and_history_says_them(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")

    job = _saved(client, picture, {"depth": {**PORTRAIT, **FOG}})

    assert job["state"] == "done", job["problem"]
    assert job["resultName"] == "Red ball (Depth).png"
    assert job["depth"] == "portrait blur at f/1.4 and fog"
    line = client.get("/history").json()["entries"][0]
    assert line["depth"] == "portrait blur at f/1.4 and fog"
    assert (folder / "Red ball.png").is_file()  # the original as it was
    made_ = np.asarray(Image.open(folder / "Red ball (Depth).png").convert("RGB"), np.float32)
    original = np.asarray(Image.open(folder / "Red ball.png").convert("RGB"), np.float32)
    assert made_[130:150].mean() > original[130:150].mean()  # the far hills in pale haze
    today = client.get("/history/today").json()
    assert today[0]["depth"] == "portrait blur at f/1.4 and fog"


def test_the_depth_tools_are_made_before_a_painting_style_and_both_are_named(
    client: TestClient, folder: Path, model: DepthModel, monkeypatch: pytest.MonkeyPatch
):
    # A lens and the air come before a painter paints what they saw: the depth tools first.
    made_in: list[str] = []
    real_depth, real_paint = making.depth_made, making.paint

    def depth_made(*given: Any, **asked: Any) -> Any:
        made_in.append("depth")
        return real_depth(*given, **asked)

    def paint(*given: Any, **asked: Any) -> Any:
        made_in.append("paint")
        return real_paint(*given, **asked)

    monkeypatch.setattr(making, "depth_made", depth_made)
    monkeypatch.setattr(making, "paint", paint)
    picture = _id(client, "Red ball.png")

    job = _saved(
        client,
        picture,
        {"depth": TILT, "paint": {"style": "pencil", "strength": 1.0, "parts": []}},
    )

    assert job["state"] == "done", job["problem"]
    assert made_in == ["depth", "paint"]
    assert job["resultName"] == "Red ball (Tilt-shift, Pencil sketch).png"
    assert job["depth"] == "tilt-shift"


def test_see_through_parts_and_a_grey_picture_stay_as_they_are(
    client: TestClient, folder: Path, model: DepthModel
):
    sticker = _id(client, "Sticker.png")
    grey = _id(client, "Grey field.png")

    clear = _saved(client, sticker, {"depth": {**PORTRAIT, **TILT}})
    black_and_white = _saved(client, grey, {"depth": PORTRAIT})

    assert clear["state"] == "done", clear["problem"]
    made_ = Image.open(folder / clear["resultName"])
    assert made_.mode == "RGBA"
    alpha = np.asarray(made_.getchannel("A"))
    assert (alpha[:, :60] == 0).all()
    assert (alpha[:, 60:] == 255).all()
    assert black_and_white["state"] == "done", black_and_white["problem"]
    assert Image.open(folder / black_and_white["resultName"]).mode == "L"


def test_a_batchs_cut_out_is_made_once_on_the_picture_before_its_depth_tools(
    client: TestClient, folder: Path, model: DepthModel, monkeypatch: pytest.MonkeyPatch
):
    # The depth and the subject come from the picture as its edits left it, made once: never
    # by making the edits again on the picture already cut out.
    given: list[str] = []
    real = Editor.state

    def state(self: Editor, image: Image.Image, key: str, edits: Any, **asked: Any) -> Any:
        if edits:
            given.append(image.mode)
        return real(self, image, key, edits, **asked)

    monkeypatch.setattr(Editor, "state", state)
    picture = _id(client, "Red ball.png")
    steps = [
        {"step": "cutout", "quality": "fast", "behind": "nothing"},
        {"step": "depth", **PORTRAIT},
    ]
    saving = {"how": "new", "format": "PNG", "folder": "Cut and blurred"}
    pictures = client.post("/batches/pictures", json={"how": "ticked", "ids": [picture]}).json()

    put = client.post(
        "/batches",
        json={
            "name": "Cut and blurred",
            "source": pictures["source"],
            "pictures": pictures["pictures"],
            "steps": steps,
            "saving": saving,
            "starts": "now",
        },
    )

    assert put.status_code == 201, put.text
    app: Any = client.app
    assert app.state.jobs.wait(120)
    assert [each.name for each in (folder / "Cut and blurred").iterdir()] == [
        "Red ball (Cut out, Portrait blur).png"
    ]
    assert given == ["RGB"]  # made once, on the picture itself


def test_a_batch_gives_each_picture_its_depth_tools_and_history_says_so(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")
    letter = _id(client, "Old letter.png")
    steps = [
        {
            "step": "depth",
            **{**PORTRAIT, "portrait": {**PORTRAIT["portrait"], "focus": [0.1, 0.1]}},
            **TILT,
        }
    ]
    saving = {"how": "new", "format": "PNG", "folder": "Depth"}

    pictures = client.post(
        "/batches/pictures", json={"how": "ticked", "ids": [picture, letter]}
    ).json()
    takes = client.post(
        "/batches/takes", json={"pictures": pictures["pictures"], "steps": steps, "saving": saving}
    )
    put = client.post(
        "/batches",
        json={
            "name": "Garden depth",
            "source": pictures["source"],
            "pictures": pictures["pictures"],
            "steps": steps,
            "saving": saving,
            "starts": "now",
        },
    )

    assert takes.status_code == 200, takes.text
    words = takes.json()["words"]
    depth = next(each for each in words if each["kind"] == "depth")
    assert depth["detail"] == "Portrait blur at f/1.4 on each subject, tilt-shift at 100%"
    assert depth["chip"] == "Portrait blur and tilt-shift"
    assert put.status_code == 201, put.text
    app: Any = client.app
    assert app.state.jobs.wait(120)
    made_ = sorted(each.name for each in (folder / "Depth").iterdir())
    assert made_ == ["Old letter (Depth).png", "Red ball (Depth).png"]
    line = client.get("/history").json()["batches"][0]
    assert line["depth"] == "portrait blur at f/1.4 and tilt-shift"


def _motion(client: TestClient, picture: int, **asked: object) -> dict[str, Any]:
    body = {"version": _version(client, picture), **asked}
    response = client.post(f"/pictures/{picture}/motion", json=body)
    assert response.status_code == 202, response.text
    found = response.json()
    for _ in range(600):
        found = client.get(f"/motion/{found['id']}").json()
        if found["state"] in ("done", "failed"):
            return found
        time.sleep(0.05)
    raise AssertionError("the 3D photo didn't finish in time")


def test_a_3d_photo_is_made_played_and_saved_with_its_line_in_history(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")

    facts = client.get(f"/pictures/{picture}/motion").json()
    made_ = _motion(client, picture, motion="sway", seconds=3, size="1080p")
    video = client.get(f"/motion/{made_['id']}/video")
    saved = client.post(f"/motion/{made_['id']}/save", json={"folder": None})

    assert facts["encoder"] == "h264_mf"  # Windows' own first
    assert facts["encoderName"] == "Windows' own video encoder"
    assert facts["needs"] == []
    assert [each["size"] for each in facts["sizes"]] == ["1080p"]  # 4K would only stretch it
    assert made_["state"] == "done", made_["problem"]
    assert (made_["width"], made_["height"]) == (480, 360)
    assert made_["encoderName"] == "Windows' own video encoder"
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert video.content.endswith(b"frames=90")  # 3 s at 30 frames a second
    assert saved.status_code == 200, saved.text
    assert saved.json()["name"] == "Red ball (3D photo).mp4"
    assert (folder / "Red ball (3D photo).mp4").read_bytes() == video.content
    line = client.get("/history").json()["entries"][0]
    assert line["depth"] == "into a 3D photo, swaying for 3 s"
    assert line["resultName"] == "Red ball (3D photo).mp4"
    again = client.post(f"/motion/{made_['id']}/save", json={"folder": None})
    assert again.json()["name"] == "Red ball (3D photo) (2).mp4"


def test_a_3d_photo_saved_beside_a_picture_whose_folder_has_gone_says_so_and_makes_none(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")
    made_ = _motion(client, picture, seconds=3)
    assert made_["state"] == "done", made_["problem"]
    shutil.rmtree(folder)  # its drive unplugged, say

    saved = client.post(f"/motion/{made_['id']}/save", json={"folder": None})

    assert saved.status_code == 422
    assert "isn't there any more" in saved.json()["detail"]
    assert not folder.exists()  # not made again


def test_a_3d_photo_as_an_animated_webp_needs_no_encoder(
    client: TestClient, folder: Path, model: DepthModel, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MADO_FAKE_ENCODERS", "none")  # no H.264 encoder works here
    picture = _id(client, "Red ball.png")

    facts = client.get(f"/pictures/{picture}/motion").json()
    mp4 = _motion(client, picture, seconds=3)
    webp = _motion(client, picture, seconds=3, format="webp")

    assert facts["encoder"] is None
    assert mp4["state"] == "failed"
    assert "animated WebP" in mp4["problem"]
    assert webp["state"] == "done", webp["problem"]
    shown = Image.open(io.BytesIO(client.get(f"/motion/{webp['id']}/video").content))
    assert getattr(shown, "is_animated", False)
    assert shown.info.get("loop") == 0  # round and round
    assert not list(folder.glob("*.webp"))  # nothing written beside the picture till it's saved


def test_a_3d_photo_of_a_picture_past_what_mado_reads_asks_for_a_smaller_copy(
    client: TestClient, folder: Path, model: DepthModel
):
    picture = _id(client, "Red ball.png")
    app: Any = client.app
    with closing(db.connect(app.state.paths.database)) as conn, conn:
        conn.execute("UPDATE pictures SET width = 12000, height = 9000 WHERE id = ?", (picture,))

    refused = client.post(
        f"/pictures/{picture}/motion", json={"version": _version(client, picture)}
    )

    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("It's 108 megapixels")
    assert "Size tab" in refused.json()["detail"]


def test_a_3d_photo_waits_for_the_depth_model_and_one_let_go_is_gone(
    client: TestClient, folder: Path
):
    picture = _id(client, "Red ball.png")

    refused = client.post(
        f"/pictures/{picture}/motion", json={"version": _version(client, picture)}
    )

    assert refused.status_code == 409
    assert client.get("/motion/nothing").status_code == 404
    assert client.delete("/motion/nothing").status_code == 204
