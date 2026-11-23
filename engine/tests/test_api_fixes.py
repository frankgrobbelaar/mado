"""The quick fixes through the API, end to end with the fixes' models' stand-ins
(tests/fix_models.py): what the Fix tab suggests, the plan with fixes (the models it waits for,
the words, the upscaler not cleaning twice), previews before and after, Save (a new picture named
for its fixes, History's words, the original untouched), grey, see-through and wide-colour
pictures kept as they are, and a batch with a fix step."""

import io
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db
from mado.api.making import Newest
from mado.core.fixes import FixModel
from mado.core.icc import display_p3
from tests.conftest import add, made
from tests.drawn import scene
from tests.fix_models import FixModels, with_fix_models

DARK = {"dark": {"contrast": 0}}


def _darkened(image: Image.Image, times: float) -> Image.Image:
    lin = (np.asarray(image.convert("RGB"), np.float64) / 255) ** 2.2 / times
    return Image.fromarray(np.clip(np.rint(lin ** (1 / 2.2) * 255), 0, 255).astype(np.uint8))


@pytest.fixture
def folder(client: TestClient, tmp_path: Path) -> Path:
    """Phone: made-up pictures, a dark one, a JPEG saved small, a grey one and one with
    see-through parts."""
    phone = tmp_path / "Phone"
    phone.mkdir()
    _darkened(scene(1, (480, 360)), 8).save(phone / "Night walk.png")
    scene(2, (480, 360)).save(phone / "Harbour.jpg", quality=18)
    scene(3, (480, 360)).save(phone / "Bright day.png")
    _darkened(scene(4, (320, 240)), 6).convert("L").save(phone / "Old street.png")
    sticker = _darkened(scene(5, (320, 240)), 6).convert("RGBA")
    alpha = np.full((240, 320), 255, np.uint8)
    alpha[:, :80] = 0
    sticker.putalpha(Image.fromarray(alpha))
    sticker.save(phone / "Sticker.png")
    add(client, phone)
    return phone


@pytest.fixture
def models(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FixModels:
    app: Any = client.app
    return with_fix_models(monkeypatch, app.state.ai, tmp_path / "models")


def _id(client: TestClient, name: str) -> int:
    pictures = client.get("/pictures").json()["pictures"]
    return next(each["id"] for each in pictures if each["name"] == name)


def _saved(client: TestClient, picture: int, recipe: dict[str, Any], **saving: object):
    body = {"recipe": recipe, "saving": {"how": "new", "format": "PNG", **saving}}
    response = client.post(f"/pictures/{picture}/make", json=body)
    assert response.status_code == 202, response.text
    return made(client, response.json())


def _image(response: Any) -> np.ndarray:
    assert response.status_code == 200, response.text
    return np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB"))


def test_the_fix_tab_suggests_only_what_mado_measures(client: TestClient, folder: Path):
    dark = client.get(f"/pictures/{_id(client, 'Night walk.png')}/fixes").json()
    small = client.get(f"/pictures/{_id(client, 'Harbour.jpg')}/fixes").json()
    bright = client.get(f"/pictures/{_id(client, 'Bright day.png')}/fixes").json()
    grey = client.get(f"/pictures/{_id(client, 'Old street.png')}/fixes").json()
    sticker = client.get(f"/pictures/{_id(client, 'Sticker.png')}/fixes").json()

    assert dark["dark"] is True
    assert dark["stops"] == pytest.approx(3.0, abs=0.6)
    assert dark["jpegQuality"] is None
    assert dark["blocks"] is False
    assert small["jpegQuality"] == 18
    assert small["blocks"] is True
    assert small["dark"] is False
    assert bright["dark"] is False
    assert bright["blocks"] is False
    assert grey["grey"] is True
    assert sticker["seeThrough"] is True
    assert bright["colour"] == "sRGB"


def test_the_plan_waits_for_the_fixes_models_till_theyre_downloaded(
    client: TestClient, folder: Path
):
    picture = _id(client, "Night walk.png")

    plan = client.post(
        f"/pictures/{picture}/plan", json={"fix": {"noise": {"strength": 1}, "blur": {}}}
    ).json()

    assert [need["id"] for need in plan["needs"]] == ["scunet", "nafnet"]
    assert plan["fix"] == "took out noise and mended the blur"
    assert plan["method"] == "keep"
    assert plan["fixSeconds"] > 0
    assert plan["seconds"] >= plan["fixSeconds"]
    fitted = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": {"fix": DARK}, "side": "after", "fit": {"width": 480, "height": 360}},
    )
    part = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": {"fix": DARK}, "side": "after", "region": _all(480, 360)},
    )
    before = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": {"fix": DARK}, "side": "before", "region": _all(480, 360)},
    )
    assert fitted.status_code == 200  # all of it shows the brightening, which needs no model
    assert part.status_code == 409  # a part at full detail shows the denoise too
    assert before.status_code == 200


def _all(width: int, height: int) -> dict[str, int]:
    return {"x": 0, "y": 0, "width": width, "height": height}


def test_jpeg_blocks_start_on_fast_till_fbcnn_is_downloaded(
    client: TestClient, folder: Path, models: FixModels, monkeypatch: pytest.MonkeyPatch
):
    picture = _id(client, "Harbour.jpg")
    asked = {"fix": {"jpeg": {"strength": 0.8}}}
    app: Any = client.app
    real = app.state.ai.fix_file

    def without_fbcnn(model: FixModel) -> Path | None:
        return None if model.id == "fbcnn" else real(model)

    monkeypatch.setattr(app.state.ai, "fix_file", without_fbcnn)

    fast = client.post(f"/pictures/{picture}/plan", json=asked).json()
    monkeypatch.setattr(app.state.ai, "fix_file", real)
    best = client.post(f"/pictures/{picture}/plan", json=asked).json()

    assert fast["fixQuality"] == "fast"
    assert fast["needs"] == []
    assert best["fixQuality"] == "best"
    assert best["fix"] == "took out JPEG blocks"


def test_a_picture_the_fixes_cleaned_isnt_cleaned_again_as_it_grows(
    client: TestClient, folder: Path, models: FixModels
):
    picture = _id(client, "Night walk.png")
    size = {"size": "monitor-4k", "quality": "fast"}

    cleaned = client.post(f"/pictures/{picture}/plan", json={"fix": DARK, "size": size}).json()
    sharpened = client.post(
        f"/pictures/{picture}/plan", json={"fix": {"blur": {"strength": 1}}, "size": size}
    ).json()

    assert cleaned["model"] == "Real-ESRGAN general, keeping grain"
    assert cleaned["cleanedFirst"] is True
    assert cleaned["cleanMatters"] is False
    assert sharpened["model"] == "Real-ESRGAN general"
    assert sharpened["cleanMatters"] is True


def test_a_picture_the_dark_photo_fix_finds_bright_is_cleaned_as_it_grows(
    client: TestClient, folder: Path, models: FixModels
):
    picture = _id(client, "Bright day.png")
    size = {"size": "monitor-4k", "quality": "fast"}

    plan = client.post(f"/pictures/{picture}/plan", json={"fix": DARK, "size": size}).json()
    alone = client.post(f"/pictures/{picture}/plan", json={"fix": DARK}).json()
    saved = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": {"fix": DARK}, "saving": {"how": "new", "format": "PNG"}},
    )

    assert plan["cleanedFirst"] is False
    assert plan["model"] == "Real-ESRGAN general"
    assert plan["fix"] is None
    assert plan["fixPlace"] is None
    assert alone["fix"] is None
    assert saved.status_code == 422
    assert saved.json()["detail"] == "It isn't dark, so there was nothing to fix."


def test_the_plan_says_where_the_fixes_run(client: TestClient, folder: Path, models: FixModels):
    picture = _id(client, "Night walk.png")

    plan = client.post(f"/pictures/{picture}/plan", json={"fix": DARK}).json()

    assert plan["fixPlace"] == plan["place"]  # the tests' PC: the processor


def test_a_newer_preview_of_a_picture_stops_the_one_before():
    newest = Newest()

    first = newest.started(Path("Pier.jpg"))
    assert not first()
    second = newest.started(Path("pier.JPG"))
    other = newest.started(Path("Dunes.jpg"))

    assert first()
    assert not second()
    assert not other()


def test_a_preview_of_all_of_it_runs_no_model(client: TestClient, folder: Path, models: FixModels):
    picture = _id(client, "Night walk.png")
    fit = {"width": 240, "height": 180}

    before = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": {"fix": {"noise": {"strength": 1}}}, "side": "before", "fit": fit},
        )
    )
    after = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": {"fix": {"noise": {"strength": 1}}}, "side": "after", "fit": fit},
        )
    )

    assert models.runs["scunet"] == 0
    assert np.abs(after.astype(int) - before.astype(int)).mean() < 2


def test_the_previews_show_a_dark_photo_brightened(
    client: TestClient, folder: Path, models: FixModels
):
    picture = _id(client, "Night walk.png")
    recipe = {"fix": DARK}

    before = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": recipe, "side": "before", "region": _all(480, 360)},
        )
    )
    fitted = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": recipe, "side": "after", "fit": {"width": 240, "height": 180}},
        )
    )
    part = _image(
        client.post(
            f"/pictures/{picture}/preview",
            json={
                "recipe": recipe,
                "side": "after",
                "region": {"x": 100, "y": 80, "width": 200, "height": 150},
            },
        )
    )

    assert fitted.shape == (180, 240, 3)
    assert part.shape == (150, 200, 3)
    assert fitted.mean() > before.mean() * 2
    assert part.mean() > before[80:230, 100:300].mean() * 2
    assert models.runs["scunet"] > 0


def test_the_looks_small_copies_show_a_dark_photo_brightened_as_the_stage_does(
    client: TestClient, folder: Path
):
    listed = client.get("/pictures").json()["pictures"]
    night = next(each for each in listed if each["name"] == "Night walk.png")
    plain: dict[str, Any] = {"version": night["version"], "edits": []}

    dark = _image(client.post(f"/pictures/{night['id']}/looks/original", json={"edit": plain}))
    lit = _image(
        client.post(f"/pictures/{night['id']}/looks/original", json={"edit": plain, "fix": DARK})
    )

    assert lit.mean() > dark.mean() * 2  # brightened, with no model downloaded


def test_save_makes_a_new_picture_named_for_its_fixes_and_history_says_what_they_did(
    client: TestClient, folder: Path, models: FixModels
):
    picture = _id(client, "Night walk.png")
    original = (folder / "Night walk.png").read_bytes()

    done = _saved(client, picture, {"fix": {**DARK, "noise": {"strength": 0.8}}})

    assert done["state"] == "done", done["problem"]
    assert done["fix"] == "took out noise and brightened it"
    assert done["resultName"] == "Night walk (Fixed).png"
    assert (folder / "Night walk.png").read_bytes() == original
    with (
        Image.open(folder / "Night walk (Fixed).png") as saved,
        Image.open(folder / "Night walk.png") as was,
    ):
        assert np.asarray(saved.convert("RGB")).mean() > np.asarray(was.convert("RGB")).mean() * 2
    line = client.get("/history").json()["entries"][0]
    assert (line["kind"], line["fix"]) == ("made", "took out noise and brightened it")
    today = client.get("/history/today").json()[0]
    assert today["fix"] == "took out noise and brightened it"


def test_a_grey_picture_stays_grey_and_see_through_parts_stay_see_through(
    client: TestClient, folder: Path, models: FixModels
):
    grey = _saved(client, _id(client, "Old street.png"), {"fix": DARK})
    sticker = _saved(client, _id(client, "Sticker.png"), {"fix": DARK})

    assert grey["state"] == "done", grey["problem"]
    assert sticker["state"] == "done", sticker["problem"]
    with Image.open(folder / grey["resultName"]) as saved:
        assert saved.mode == "L"
    with (
        Image.open(folder / sticker["resultName"]) as saved,
        Image.open(folder / "Sticker.png") as was,
    ):
        assert np.array_equal(np.asarray(saved.getchannel("A")), np.asarray(was.getchannel("A")))


def test_a_wide_colour_photo_keeps_its_colours(
    client: TestClient, tmp_path: Path, models: FixModels
):
    wide = tmp_path / "Wide"
    wide.mkdir()
    profile = display_p3()
    _darkened(scene(6, (320, 240)), 6).save(wide / "Lanterns.jpg", quality=95, icc_profile=profile)
    add(client, wide)

    done = _saved(client, _id(client, "Lanterns.jpg"), {"fix": DARK}, format="JPEG", quality=92)

    assert done["state"] == "done", done["problem"]
    with Image.open(wide / done["resultName"]) as saved:
        assert saved.info.get("icc_profile") == profile


def test_a_batch_fixes_its_pictures_before_it_makes_them_for_a_screen(
    client: TestClient, folder: Path, models: FixModels
):
    ids = [_id(client, "Night walk.png"), _id(client, "Bright day.png")]
    pictures = client.post("/batches/pictures", json={"how": "ticked", "ids": ids}).json()
    steps = [
        {"step": "size", "size": "monitor-4k", "shape": "crop", "quality": "fast"},
        {"step": "fix", "noise": {"strength": 0.7}, "blur": None, "jpeg": None, "dark": None},
    ]
    saving = {"how": "new", "format": "PNG"}

    takes = client.post(
        "/batches/takes", json={"pictures": pictures["pictures"], "steps": steps, "saving": saving}
    ).json()
    queued = client.post(
        "/batches",
        json={
            "name": "Night walks",
            "source": pictures["source"],
            "pictures": pictures["pictures"],
            "steps": steps,
            "saving": saving,
            "starts": "now",
        },
    )

    assert [each["kind"] for each in takes["words"]] == ["fix", "size", "save"]
    assert takes["words"][0]["detail"] == "Noise at 70%"
    assert takes["words"][0]["chip"] == "Noise"
    assert queued.status_code == 201, queued.text
    app: Any = client.app
    assert app.state.jobs.wait(120)
    names = sorted(each.name for each in folder.iterdir())
    assert "Night walk (Cleaned, Monitor 4K).png" in names
    lines = client.get("/history").json()["entries"]
    assert {line["fix"] for line in lines if line["kind"] == "made"} == {"took out noise"}


def test_a_batch_takes_out_jpeg_blocks_as_hard_as_each_jpeg_was_squeezed(
    client: TestClient, folder: Path, models: FixModels
):
    ids = [_id(client, "Harbour.jpg"), _id(client, "Bright day.png")]
    pictures = client.post("/batches/pictures", json={"how": "ticked", "ids": ids}).json()
    steps = [
        {
            "step": "fix",
            "noise": None,
            "blur": None,
            "jpeg": {"quality": "best", "strength": None},
            "dark": None,
        }
    ]
    saving = {"how": "new", "format": "PNG"}

    takes = client.post(
        "/batches/takes", json={"pictures": pictures["pictures"], "steps": steps, "saving": saving}
    ).json()
    queued = client.post(
        "/batches",
        json={
            "name": "Harbour",
            "source": pictures["source"],
            "pictures": pictures["pictures"],
            "steps": steps,
            "saving": saving,
            "starts": "now",
        },
    )

    assert takes["words"][0]["detail"] == "JPEG blocks as each JPEG was saved, Best"
    assert queued.status_code == 201, queued.text
    app: Any = client.app
    assert app.state.jobs.wait(120)
    names = sorted(each.name for each in folder.iterdir())
    assert "Harbour (Cleaned).png" in names
    assert not any(name.startswith("Bright day (") for name in names)
    with closing(db.connect(app.state.paths.database)) as conn:
        found = conn.execute("SELECT problem FROM jobs WHERE problem IS NOT NULL").fetchall()
    problems = [row[0] for row in found]
    assert problems == [
        "It isn't a JPEG, so it has no JPEG blocks: there was nothing to fix. Nothing was "
        "saved, and the original is as it was."
    ]
