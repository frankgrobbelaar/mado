"""Restoring old photos through the API, end to end with the models' stand-ins
(tests/restore_models.py): what the Fix tab learns of a picture's colours, the detector's mask
(kept by the picture's version, refused once it changed or while the detector isn't downloaded),
the plan with restoring (its words, the mask's share, the models it waits for), previews, Save (a
new picture named for it, History's words, the original untouched), a mask over most of the picture
refused, and a batch's Restore step, which colours each picture as it needs and never fills
scratches."""

import io
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from mado import db
from mado.ai import DETECTOR
from mado.core.restore import lab
from mado.hardware import Here
from tests.conftest import add, made
from tests.drawn import scene
from tests.restore_models import GRASS_AB, SKY_AB, RestoreModels, with_restore_models

COLOUR = {"colour": {"strength": 1.0}}
SCRATCHES: dict[str, dict[str, list[object]]] = {"scratches": {"strokes": []}}


def _scratched(size: tuple[int, int] = (640, 480)) -> Image.Image:
    """A made-up grey print: a sky over a sea, with a bright scratch across it."""
    width, height = size
    rows = np.linspace(0.75, 0.35, height, dtype=np.float32)[:, None]
    grey = np.repeat(rows, width, axis=1)
    grey[height // 2 :] *= 0.7
    image = Image.fromarray((grey * 255).astype(np.uint8), "L")
    draw = ImageDraw.Draw(image)
    draw.line([(0, height // 3), (width, height // 3 + 30)], fill=250, width=3)
    return image


def _sepia(image: Image.Image) -> Image.Image:
    light = np.asarray(image.convert("L"), np.float32)[..., None]
    return Image.fromarray(np.clip(light * np.array([1.0, 0.86, 0.66]), 0, 255).astype(np.uint8))


@pytest.fixture
def folder(client: TestClient, tmp_path: Path) -> Path:
    """Scans: a grey print with a scratch, a sepia print, a colour photo and one with
    see-through parts."""
    scans = tmp_path / "Scans"
    scans.mkdir()
    _scratched().save(scans / "Pier 1931.png")
    _sepia(scene(1, (480, 360))).save(scans / "Aunt's garden.png")
    scene(2, (480, 360)).save(scans / "Beach 1978.png")
    sticker = _scratched((320, 240)).convert("RGBA")
    alpha = np.full((240, 320), 255, np.uint8)
    alpha[:, :80] = 0
    sticker.putalpha(Image.fromarray(alpha))
    sticker.save(scans / "Cut out.png")
    add(client, scans)
    return scans


@pytest.fixture
def models(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RestoreModels:
    app: Any = client.app
    return with_restore_models(monkeypatch, app.state.ai, tmp_path / "models")


def _picture(client: TestClient, name: str) -> dict[str, Any]:
    pictures = client.get("/pictures").json()["pictures"]
    found = next(each for each in pictures if each["name"] == name)
    return client.get(f"/pictures/{found['id']}").json()


def _restore(picture: dict[str, Any], **steps: object) -> dict[str, Any]:
    return {"version": picture["version"], **steps}


def _saved(client: TestClient, picture: int, recipe: dict[str, Any]) -> dict[str, Any]:
    body = {"recipe": recipe, "saving": {"how": "new", "format": "PNG"}}
    response = client.post(f"/pictures/{picture}/make", json=body)
    assert response.status_code == 202, response.text
    return made(client, response.json())


def test_the_fix_tab_learns_what_a_pictures_colours_are(client: TestClient, folder: Path):
    grey = client.get(f"/pictures/{_picture(client, 'Pier 1931.png')['id']}/fixes").json()
    sepia = client.get(f"/pictures/{_picture(client, "Aunt's garden.png")['id']}/fixes").json()
    colour = client.get(f"/pictures/{_picture(client, 'Beach 1978.png')['id']}/fixes").json()
    assert (grey["colours"], grey["tone"]) == ("grey", None)
    assert (sepia["colours"], sepia["tone"]) == ("toned", "sepia")
    assert (colour["colours"], colour["tone"]) == ("colour", None)


def test_the_detector_finds_the_scratch_and_says_how_it_went(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Pier 1931.png")
    asked: dict[str, object] = {"version": picture["version"], "edits": []}
    response = client.post(f"/pictures/{picture['id']}/scratches", json=asked)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    mask = np.asarray(Image.open(io.BytesIO(response.content)))
    assert mask.shape == (480, 640)
    assert mask[160 + 15, 320] == 255  # the scratch, halfway across
    assert mask[40, 40] == 0
    assert 0 < float(response.headers["X-Found"]) < 0.1
    assert response.headers["X-Place"] == "processor"
    again = client.post(f"/pictures/{picture['id']}/scratches", json=asked)
    assert again.headers["X-Place"] == ""  # kept: not found again
    assert models.runs["oldphoto-scratch-detector"] == 2  # its two canvases, once


def test_the_detector_waits_for_its_download_and_for_the_picture_as_it_is(
    client: TestClient, folder: Path
):
    picture = _picture(client, "Pier 1931.png")
    path = f"/pictures/{picture['id']}/scratches"
    missing = client.post(path, json={"version": picture["version"], "edits": []})
    assert missing.status_code == 409
    assert "isn't downloaded" in missing.json()["detail"]
    changed = client.post(path, json={"version": "0-0", "edits": []})
    assert changed.status_code == 409
    assert "changed since Mado found its scratches" in changed.json()["detail"]


def test_the_plan_says_what_restoring_does_and_what_it_waits_for(client: TestClient, folder: Path):
    picture = _picture(client, "Pier 1931.png")
    recipe = {"restore": _restore(picture, **SCRATCHES, **COLOUR), "size": None, "look": None}
    plan = client.post(f"/pictures/{picture['id']}/plan", json=recipe).json()
    assert plan["restore"] == "filled its scratches and dust and coloured it"
    assert {need["id"] for need in plan["needs"]} >= {"oldphoto-scratch-detector", "ddcolor-tiny"}
    assert plan["restoreCovers"] is None  # the detector isn't here to find them
    assert plan["restoreSeconds"] > 0


def test_the_plan_says_where_the_models_in_use_run(
    client: TestClient, folder: Path, models: RestoreModels, monkeypatch: pytest.MonkeyPatch
):
    app: Any = client.app
    # A card with room for DDColor but not for the detector.
    monkeypatch.setattr(app.state.ai, "where", lambda: Here("card", None, {}))

    def placed(download: str) -> str:
        return "processor" if download == DETECTOR else "card"

    monkeypatch.setattr(app.state.ai, "restore_place", placed)
    picture = _picture(client, "Pier 1931.png")

    def planned(**steps: object) -> dict[str, Any]:
        recipe = {"restore": _restore(picture, **steps), "size": None, "look": None}
        return client.post(f"/pictures/{picture['id']}/plan", json=recipe).json()

    coloured, scratched = planned(**COLOUR), planned(**SCRATCHES)

    assert (coloured["restorePlace"], coloured["scratchPlace"]) == ("card", None)
    assert (scratched["restorePlace"], scratched["scratchPlace"]) == ("processor", "processor")


def test_the_plan_says_how_much_of_the_picture_the_mask_covers(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Pier 1931.png")
    recipe = {"restore": _restore(picture, **SCRATCHES), "size": None, "look": None}
    plan = client.post(f"/pictures/{picture['id']}/plan", json=recipe).json()
    assert 0 < plan["restoreCovers"] < 0.1
    assert plan["needs"] == []
    painted = {"strokes": [{"points": [[0.0, 0.5], [1.0, 0.5]], "size": 1.0, "take": False}]}
    most = {"restore": _restore(picture, scratches=painted), "size": None, "look": None}
    covered = client.post(f"/pictures/{picture['id']}/plan", json=most).json()
    assert covered["restoreCovers"] > 0.5


def test_saving_restores_it_as_a_new_picture_and_history_says_so(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Pier 1931.png")
    recipe = {"restore": _restore(picture, **SCRATCHES, **COLOUR), "size": None, "look": None}
    job = _saved(client, picture["id"], recipe)
    assert job["state"] == "done", job["problem"]
    saved = Path(job["result"])
    assert saved.name == "Pier 1931 (Restored).png"
    with Image.open(saved) as made_picture:
        rgb = np.asarray(made_picture.convert("RGB"), np.float32) / np.float32(255)
    colours = lab(rgb.astype(np.float32))
    assert np.abs(colours[40, 320, 1:] - np.array(SKY_AB)).max() < 8  # coloured as the model said
    assert np.abs(colours[400, 320, 1:] - np.array(GRASS_AB)).max() < 8
    scratch = np.asarray(Image.open(saved).convert("L"), np.int32)[160 + 15, 300:340]
    assert scratch.max() < 230  # filled
    with Image.open(folder / "Pier 1931.png") as original:
        assert original.mode == "L"  # untouched
    entries = client.get("/history").json()["entries"]
    assert entries[0]["restore"] == "filled its scratches and dust and coloured it"


def test_a_picture_coloured_alone_is_named_coloured(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Aunt's garden.png")
    job = _saved(client, picture["id"], {"restore": COLOUR, "size": None, "look": None})
    assert Path(job["result"]).name == "Aunt's garden (Coloured).png"


def test_a_mask_over_most_of_the_picture_isnt_filled(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Pier 1931.png")
    painted = {"strokes": [{"points": [[0.0, 0.5], [1.0, 0.5]], "size": 1.0, "take": False}]}
    recipe = {"restore": _restore(picture, scratches=painted), "size": None, "look": None}
    body = {"recipe": recipe, "saving": {"how": "new", "format": "PNG"}}
    refused = client.post(f"/pictures/{picture['id']}/make", json=body)
    assert refused.status_code == 422
    assert "most of a picture" in refused.json()["detail"]
    preview = client.post(
        f"/pictures/{picture['id']}/preview",
        json={"recipe": recipe, "side": "after", "fit": {"width": 320, "height": 240}},
    )
    assert preview.status_code == 422


def test_a_mask_covering_nothing_fills_nothing(
    client: TestClient, tmp_path: Path, models: RestoreModels
):
    plain = tmp_path / "Plain"
    plain.mkdir()
    rows = np.linspace(200, 120, 1200, dtype=np.float32)[:, None]
    smooth = np.repeat(rows, 1600, axis=1).astype(np.uint8)  # its mask 1024 x 768
    Image.fromarray(smooth, "L").save(plain / "Clean print.png")
    add(client, plain)
    picture = _picture(client, "Clean print.png")
    recipe = {"restore": _restore(picture, **SCRATCHES), "size": None, "look": None}

    plan = client.post(f"/pictures/{picture['id']}/plan", json=recipe).json()
    refused = client.post(
        f"/pictures/{picture['id']}/make",
        json={"recipe": recipe, "saving": {"how": "new", "format": "PNG"}},
    )

    # Nothing found and nothing painted: nothing to fill, and with nothing else on, no Save.
    assert plan["restoreCovers"] == 0
    assert plan["restore"] is None
    assert refused.status_code == 422
    # With colour on too, only the colouring is made, and History says only that.
    both = {"restore": _restore(picture, **SCRATCHES, **COLOUR), "size": None, "look": None}
    assert client.post(f"/pictures/{picture['id']}/plan", json=both).json()["restore"] == (
        "coloured it"
    )
    assert _saved(client, picture["id"], both)["restore"] == "coloured it"
    # One dab of the finest brush is something to fill, however little of the picture it covers.
    dab = {"strokes": [{"points": [[0.5, 0.5]], "size": 0.005, "take": False}]}
    dabbed = {"restore": _restore(picture, scratches=dab), "size": None, "look": None}
    plan = client.post(f"/pictures/{picture['id']}/plan", json=dabbed).json()
    assert 0 < plan["restoreCovers"] < 0.0001
    assert plan["restore"] == "filled its scratches and dust"


def test_scratches_painted_on_a_picture_that_changed_since_are_refused(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Pier 1931.png")
    stale = {"version": "0-0", **SCRATCHES}
    plan = client.post(
        f"/pictures/{picture['id']}/plan", json={"restore": stale, "size": None, "look": None}
    )
    assert plan.status_code == 409
    assert "Check them again" in plan.json()["detail"]


def test_colour_alone_isnt_tied_to_the_pictures_version(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Pier 1931.png")
    recipe = {"restore": {"version": "0-0", **COLOUR}, "size": None, "look": None}

    plan = client.post(f"/pictures/{picture['id']}/plan", json=recipe)
    job = _saved(client, picture["id"], recipe)

    # Only scratches' strokes are painted on the picture as it was: colouring a changed picture
    # colours it as it is now.
    assert plan.status_code == 200, plan.text
    assert job["state"] == "done", job
    assert job["restore"] == "coloured it"


def test_a_preview_shows_it_restored(client: TestClient, folder: Path, models: RestoreModels):
    picture = _picture(client, "Pier 1931.png")
    recipe = {"restore": _restore(picture, **COLOUR), "size": None, "look": None}
    response = client.post(
        f"/pictures/{picture['id']}/preview",
        json={"recipe": recipe, "side": "after", "fit": {"width": 320, "height": 240}},
    )
    assert response.status_code == 200, response.text
    shown = np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB"), np.float32)
    colours = lab((shown / np.float32(255)).astype(np.float32))
    assert np.abs(colours[20, 160, 1:] - np.array(SKY_AB)).max() < 8
    part = client.post(
        f"/pictures/{picture['id']}/preview",
        json={
            "recipe": recipe,
            "side": "after",
            "region": {"x": 0, "y": 0, "width": 64, "height": 64},
        },
    )
    assert part.status_code == 200, part.text


def test_a_part_at_full_detail_lays_colour_only_round_itself(
    client: TestClient, folder: Path, models: RestoreModels, monkeypatch: pytest.MonkeyPatch
):
    app: Any = client.app
    restorer = app.state.editor.restorer
    laid: list[int] = []
    whole = restorer.whole

    def counted(*asked: Any, **told: Any) -> Any:
        laid.append(1)
        return whole(*asked, **told)

    monkeypatch.setattr(restorer, "whole", counted)
    picture = _picture(client, "Pier 1931.png")

    def part(strength: float) -> np.ndarray:
        recipe = {"restore": _restore(picture, colour={"strength": strength}), "size": None}
        asked = {"x": 200, "y": 20, "width": 160, "height": 120}
        response = client.post(
            f"/pictures/{picture['id']}/preview",
            json={"recipe": recipe | {"look": None}, "side": "after", "region": asked},
        )
        assert response.status_code == 200, response.text
        return np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB"), np.float32)

    full, half = part(1.0), part(0.5)

    # Each strength's colour is laid on the part alone, from what's kept, never the whole picture.
    assert laid == []
    sky = lab((full / np.float32(255)).astype(np.float32))[60, 80, 1:]
    assert np.abs(sky - np.array(SKY_AB)).max() < 8  # the part's in the sky, as the whole is
    halfway = lab((half / np.float32(255)).astype(np.float32))[60, 80, 1:]
    assert np.abs(halfway - np.array(SKY_AB) / 2).max() < 6


def test_small_copies_show_it_restored_and_refuse_strokes_painted_before_it_changed(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Pier 1931.png")
    edit: dict[str, object] = {"version": picture["version"], "edits": []}
    fresh: dict[str, object] = {"edit": edit, "restore": _restore(picture, **SCRATCHES, **COLOUR)}
    stale: dict[str, object] = {"edit": edit, "restore": {"version": "0-0", **SCRATCHES}}
    looks = f"/pictures/{picture['id']}/looks/original"
    styles = f"/pictures/{picture['id']}/styles/pencil"

    shown = client.post(looks, json=fresh)
    assert shown.status_code == 200, shown.text
    assert client.post(styles, json=fresh).status_code == 200
    # Strokes painted on the picture as it was aren't painted on it as it is now.
    for address in (looks, styles):
        refused = client.post(address, json=stale)
        assert refused.status_code == 409, address
        assert "Check them again" in refused.json()["detail"]
    # Colour alone isn't tied to a version.
    coloured: dict[str, object] = {"edit": edit, "restore": {"version": "0-0", **COLOUR}}
    assert client.post(looks, json=coloured).status_code == 200


def test_see_through_parts_stay_as_they_are(
    client: TestClient, folder: Path, models: RestoreModels
):
    picture = _picture(client, "Cut out.png")
    job = _saved(client, picture["id"], {"restore": COLOUR, "size": None, "look": None})
    with Image.open(job["result"]) as saved:
        assert saved.mode == "RGBA"
        assert np.asarray(saved.getchannel("A"))[:, :80].max() == 0


def test_a_batch_colours_what_isnt_in_colour_and_leaves_scratches_to_each_page(
    client: TestClient, folder: Path, models: RestoreModels
):
    ids = [_picture(client, name)["id"] for name in ("Pier 1931.png", "Beach 1978.png")]
    pictures = client.post("/batches/pictures", json={"how": "ticked", "ids": ids}).json()
    step = {"step": "restore", "colour": {"strength": 1.0}, "faded": None}
    saving = {"how": "new", "format": "PNG"}
    takes = client.post(
        "/batches/takes", json={"pictures": pictures["pictures"], "steps": [step], "saving": saving}
    )
    assert takes.status_code == 200, takes.text
    scratched: dict[str, object] = {"step": "restore", "scratches": {"strokes": []}, "colour": None}
    refused = client.post(
        "/batches/takes",
        json={"pictures": pictures["pictures"], "steps": [scratched], "saving": saving},
    )
    assert refused.status_code == 422
    assert "one picture at a time" in refused.json()["detail"]


def test_history_keeps_what_restoring_did(client: TestClient, folder: Path, models: RestoreModels):
    picture = _picture(client, "Aunt's garden.png")
    _saved(client, picture["id"], {"restore": COLOUR, "size": None, "look": None})
    app: Any = client.app
    with closing(db.connect(app.state.paths.database)) as conn:
        row = conn.execute("SELECT restore FROM history ORDER BY id DESC LIMIT 1").fetchone()
    assert row["restore"] == "coloured it"
