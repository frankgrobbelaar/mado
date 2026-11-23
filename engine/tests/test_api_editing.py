"""Editing by clicking through the API, end to end with the editing models' stand-ins
(tests/edit_models.py) and the shipped U²-Net on the processor: picking parts, making edits, the
plan and the previews of a recipe with edits, Save (a new picture, or the original replaced into
quarantine and put back), cut-outs' formats, a look only on a part, and a picture that changed
since it was edited."""

import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db
from mado.api import making as making_api
from mado.extend import Filler
from mado.jobs import Jobs
from tests.conftest import add, made
from tests.drawn import sailboat
from tests.edit_models import FakeSam, part_at, with_editing_models

SAIL = (0.6375, 0.517)
SEA = (0.5, 0.95)


@pytest.fixture
def boat(client: TestClient, tmp_path: Path) -> dict[str, Any]:
    """Phone: a made-up little sail."""
    phone = tmp_path / "Phone"
    phone.mkdir()
    image, _mask = sailboat((800, 600))
    image.save(phone / "Little sail.png")
    add(client, phone)
    picture = client.get("/pictures").json()["pictures"][0]
    return {"folder": phone, "id": picture["id"], "version": picture["version"]}


@pytest.fixture
def sam(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeSam:
    app: Any = client.app
    return with_editing_models(monkeypatch, app.state.ai, tmp_path / "models")


def _erase(boat: dict[str, Any]) -> dict[str, Any]:
    return {"version": boat["version"], "edits": [{"kind": "erase", "parts": [part_at(*SAIL, 1)]}]}


def test_the_first_click_reads_the_picture_and_parts_get_plain_names(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    first = client.post(
        f"/pictures/{boat['id']}/select",
        json={"version": boat["version"], "click": {"x": SAIL[0], "y": SAIL[1]}},
    )
    assert first.status_code == 200, first.text
    picked = first.json()
    again = client.post(
        f"/pictures/{boat['id']}/select",
        json={
            "version": boat["version"],
            "parts": [
                {"clicks": part["clicks"], "choice": part["choice"]} for part in picked["parts"]
            ],
            "click": {"x": SEA[0], "y": SEA[1]},
        },
    ).json()

    assert [part["name"] for part in picked["parts"]] == ["Part 1"]
    assert picked["parts"][0]["choices"] == 3
    assert picked["read"] is not None
    assert picked["outline"].startswith("M")
    assert [part["name"] for part in again["parts"]] == ["Part 1", "Part 2"]
    assert again["read"] is None
    assert sam.reads == 1


def test_an_alt_click_outside_every_part_says_so(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    missed = client.post(
        f"/pictures/{boat['id']}/select",
        json={
            "version": boat["version"],
            "parts": [part_at(*SAIL, 1)],
            "click": {"x": SEA[0], "y": SEA[1], "keep": False},
        },
    ).json()

    assert missed["missed"]
    assert len(missed["parts"]) == 1


def test_picking_waits_for_sam_to_be_downloaded(client: TestClient, boat: dict[str, Any]):
    refused = client.post(
        f"/pictures/{boat['id']}/select",
        json={"version": boat["version"], "click": {"x": SAIL[0], "y": SAIL[1]}},
    )

    assert refused.status_code == 409
    assert "SAM 2.1" in refused.json()["detail"]
    assert "Download it first" in refused.json()["detail"]


def test_a_picture_changed_since_it_was_read_lets_its_edits_go(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    for path, body in (
        ("select", {"version": "0-0", "click": {"x": 0.5, "y": 0.5}}),
        ("edit", {**_erase(boat), "version": "0-0"}),
        ("plan", {"edit": {**_erase(boat), "version": "0-0"}}),
    ):
        refused = client.post(f"/pictures/{boat['id']}/{path}", json=body)
        assert refused.status_code == 409, path
        assert "changed since Mado read it" in refused.json()["detail"]
    look = {"look": "silver", "strength": 1, "parts": [part_at(*SEA, 1)]}
    picked_only: list[tuple[str, dict[str, Any]]] = [
        ("select", {"version": "0-0", "click": {"x": 0.5, "y": 0.5}}),
        ("plan", {"edit": {"version": "0-0", "edits": []}, "look": look}),
    ]
    for path, body in picked_only:  # parts picked, but nothing edited yet: no edits to let go
        refused = client.post(f"/pictures/{boat['id']}/{path}", json=body)
        assert refused.status_code == 409, path
        said = refused.json()["detail"]
        assert "changed since Mado read it" in said
        assert "edits" not in said
        assert "Pick them again" in said


def test_an_edit_is_made_and_says_how_it_went(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    edited = client.post(f"/pictures/{boat['id']}/edit", json=_erase(boat))

    assert edited.status_code == 200, edited.text
    assert edited.json()["smeared"] is False
    assert edited.json()["place"] == "processor"


def test_a_plan_with_edits_says_what_they_do_and_a_cut_out_saves_as_png(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    erased = client.post(f"/pictures/{boat['id']}/plan", json={"edit": _erase(boat)}).json()
    cut = client.post(
        f"/pictures/{boat['id']}/plan",
        json={"edit": {"version": boat["version"], "edits": [{"kind": "subject"}]}},
    ).json()

    assert erased["edit"] == "erased a part"
    assert erased["method"] == "keep"
    assert (erased["width"], erased["height"]) == (800, 600)
    assert erased["needs"] == []
    assert cut["edit"] == "cut out the subject"
    assert cut["format"] == "PNG"
    assert cut["seeThrough"] is True
    assert cut["nothingBehind"] is True
    assert erased["nothingBehind"] is False


def test_the_preview_shows_the_picture_as_its_edits_leave_it(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    response = client.post(
        f"/pictures/{boat['id']}/preview",
        json={"recipe": {"edit": _erase(boat)}, "fit": {"width": 800, "height": 600}},
    )

    assert response.status_code == 200, response.text
    shown = np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB")).astype(int)
    assert shown.shape == (600, 800, 3)
    assert shown[300, 512].min() < 230  # the sail is gone
    original = np.asarray(sailboat((800, 600))[0]).astype(int)
    away = np.abs(shown[:, :150] - original[:, :150])  # the rest as it was, as JPEG shows it
    assert np.percentile(away, 99) <= 4


def _saved(
    client: TestClient, boat: dict[str, Any], recipe: dict[str, Any], **saving: object
) -> dict[str, Any]:
    body = {"recipe": recipe, "saving": {"how": "new", "format": "PNG", **saving}}
    response = client.post(f"/pictures/{boat['id']}/make", json=body)
    assert response.status_code == 202, response.text
    return made(client, response.json())


def test_save_makes_the_edits_as_a_new_picture_and_the_original_is_untouched(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    original = (boat["folder"] / "Little sail.png").read_bytes()

    done = _saved(client, boat, {"edit": _erase(boat)})

    assert done["state"] == "done", done["problem"]
    assert done["edit"] == "erased a part"
    assert done["resultName"] == "Little sail (Erased).png"
    assert (boat["folder"] / "Little sail.png").read_bytes() == original
    with Image.open(boat["folder"] / "Little sail (Erased).png") as saved:
        assert np.asarray(saved.convert("RGB"))[300, 512].min() < 230
    line = client.get("/history").json()["entries"][0]
    assert (line["kind"], line["edit"]) == ("made", "erased a part")


def test_replacing_with_edits_sets_the_original_aside_and_history_puts_it_back(
    client: TestClient, boat: dict[str, Any], sam: FakeSam, tmp_path: Path
):
    original = (boat["folder"] / "Little sail.png").read_bytes()

    done = _saved(client, boat, {"edit": _erase(boat)}, how="replace")

    assert done["state"] == "done", done["problem"]
    assert (boat["folder"] / "Little sail.png").read_bytes() != original
    line = client.get("/history").json()["entries"][0]
    assert line["kind"] == "replaced"
    assert Path(line["aside"]).read_bytes() == original  # waiting in quarantine
    undone = client.post(f"/history/{line['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert (boat["folder"] / "Little sail.png").read_bytes() == original


def test_a_cut_out_with_nothing_behind_it_keeps_its_nothing_as_png_and_wont_be_jpeg(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    recipe = {
        "edit": {
            "version": boat["version"],
            "edits": [{"kind": "cutout", "parts": [part_at(*SAIL, 1)], "behind": "nothing"}],
        }
    }
    refused = client.post(
        f"/pictures/{boat['id']}/make",
        json={"recipe": recipe, "saving": {"how": "new", "format": "JPEG", "quality": 92}},
    )

    done = _saved(client, boat, recipe)

    assert refused.status_code == 422
    assert "PNG or WebP" in refused.json()["detail"]
    assert done["resultName"] == "Little sail (Cut out).png"
    with Image.open(boat["folder"] / "Little sail (Cut out).png") as saved:
        assert saved.mode == "RGBA"
        alpha = np.asarray(saved.getchannel("A"))
    assert alpha[300, 512] > 200
    assert alpha[30, 80] == 0


def test_a_look_on_a_part_changes_only_that_part(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    recipe = {"look": {"look": "silver", "strength": 1, "parts": [part_at(*SEA, 1)]}}

    plan = client.post(f"/pictures/{boat['id']}/plan", json=recipe).json()
    done = _saved(client, boat, recipe)

    assert plan["look"] == "Silver on a part"
    assert done["state"] == "done", done["problem"]
    with Image.open(boat["folder"] / done["resultName"]) as saved:
        made_ = np.asarray(saved.convert("RGB")).astype(int)
    original = np.asarray(sailboat((800, 600))[0]).astype(int)
    assert np.abs(made_[20:200, :] - original[20:200, :]).max() <= 1  # the sky as it was
    sea = made_[560:590, 300:500]
    assert np.abs(sea[..., 0] - sea[..., 2]).max() <= 2  # the sea in silver: grey


def test_a_job_whose_picture_changed_after_it_was_edited_saves_nothing(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    picture = boat["folder"] / "Little sail.png"
    order = {
        "recipe": {"edit": {**_erase(boat), "version": "0-0"}},
        "saving": {"how": "new", "format": "PNG"},
        "label": None,
        "look": None,
        "edit": "erased a part",
    }
    with closing(db.connect(app.state.paths.database)) as conn:
        conn.row_factory = sqlite3.Row
        job_id = jobs.add(conn, boat["id"], picture, order)

    done = made(client, {"id": job_id})

    assert done["state"] == "failed"
    assert "changed since you edited it" in done["problem"]
    assert sorted(each.name for each in boat["folder"].iterdir()) == ["Little sail.png"]
    assert json.loads(json.dumps(done))["resultName"] is None


def test_a_look_on_a_part_is_tied_to_the_picture_as_it_was_so_a_changed_one_saves_nothing(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    look = {"look": "silver", "strength": 1, "parts": [part_at(*SEA, 1)]}
    asked = client.post(
        f"/pictures/{boat['id']}/make",
        json={"recipe": {"look": look}, "saving": {"how": "new", "format": "PNG"}},
    )
    assert asked.status_code == 202, asked.text
    made(client, asked.json())
    with closing(db.connect(app.state.paths.database)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT recipe FROM jobs WHERE id = ?", (asked.json()["id"],)).fetchone()
        kept: dict[str, Any] = json.loads(row["recipe"])
        recipe: dict[str, Any] = {**kept["recipe"], "edit": {"version": "0-0", "edits": []}}
        later: dict[str, Any] = {**kept, "recipe": recipe}
        job_id = jobs.add(conn, boat["id"], boat["folder"] / "Little sail.png", later)

    done = made(client, {"id": job_id})

    assert kept["recipe"]["edit"] == {"version": boat["version"], "edits": []}
    assert done["state"] == "failed"
    assert "changed since you edited it" in done["problem"]


def test_the_previews_of_a_cut_out_show_only_what_was_cut_out(
    client: TestClient, boat: dict[str, Any], sam: FakeSam, monkeypatch: pytest.MonkeyPatch
):
    app: Any = client.app

    def filler(_timer: object = None) -> Filler:  # LaMa's stand-in: the new edges grey
        return lambda image, mask: np.where(mask > 0, np.float32(0.5), image).astype(np.float32)

    monkeypatch.setattr(app.state.ai, "filler", filler)
    edit = {
        "version": boat["version"],
        "edits": [{"kind": "cutout", "parts": [part_at(*SAIL, 1)], "behind": "nothing"}],
    }
    sky = {"x": 0, "y": 0, "width": 200, "height": 150}  # the top left, far from the boat
    clear: dict[str, np.ndarray] = {}
    for side in ("before", "after"):
        shown = client.post(
            f"/pictures/{boat['id']}/preview",
            json={"recipe": {"edit": edit}, "region": sky, "side": side},
        )
        assert shown.status_code == 200, shown.text
        clear[side] = np.asarray(Image.open(io.BytesIO(shown.content)).convert("RGBA"))[..., 3]
    wider = client.post(
        f"/pictures/{boat['id']}/preview",
        json={
            "recipe": {"edit": edit, "size": {"size": "tv-8k", "shape": "extend"}},
            "fit": {"width": 640, "height": 360},
        },
    )

    assert clear["before"].max() == 0
    assert clear["after"].max() == 0
    assert wider.status_code == 200, wider.text
    whole = Image.open(io.BytesIO(wider.content))
    assert whole.mode == "RGBA"
    seen = np.asarray(whole.getchannel("A"))
    assert seen[180:192, 380:392].max() > 200  # the sail, in the middle of the canvas
    assert seen[10, 10] == 0  # the sky
    assert seen[180, 20] == 0  # what was drawn at the side


def test_the_looks_small_copies_show_the_picture_as_its_edits_leave_it(
    client: TestClient, boat: dict[str, Any], sam: FakeSam
):
    plain = client.get(f"/pictures/{boat['id']}/looks/original")
    edited = client.post(f"/pictures/{boat['id']}/looks/original", json={"edit": _erase(boat)})
    changed = client.post(
        f"/pictures/{boat['id']}/looks/original", json={"edit": {**_erase(boat), "version": "0-0"}}
    )

    assert edited.status_code == 200, edited.text
    assert edited.headers["content-type"] == "image/webp"
    before = np.asarray(Image.open(io.BytesIO(plain.content)).convert("RGB")).astype(int)
    after = np.asarray(Image.open(io.BytesIO(edited.content)).convert("RGB")).astype(int)
    assert after.shape == before.shape
    sail = (int(SAIL[1] * before.shape[0]), int(SAIL[0] * before.shape[1]))
    assert before[sail].min() > 200  # the sail
    assert after[sail].min() < 200  # erased
    assert changed.status_code == 409


def test_this_pc_says_where_each_editing_model_runs(client: TestClient):
    pc = client.get("/pc").json()

    assert pc["editing"] == {  # the tests' Mado runs its models on the processor
        "select": "processor",
        "eraseFast": "processor",
        "eraseBest": "processor",
        "cutFast": "processor",
        "cutBest": "processor",
    }


def test_a_preview_of_a_part_works_out_only_whats_round_it(
    client: TestClient, boat: dict[str, Any], sam: FakeSam, monkeypatch: pytest.MonkeyPatch
):
    """A cut-out's colours are carried into its see-through parts only round the part shown:
    over the whole picture it took a second and more for every look at 100%."""
    bled_over: list[tuple[int, ...]] = []
    real = vars(making_api)["bled"]

    def bled(pixels: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        bled_over.append(pixels.shape)
        return real(pixels, alpha)

    monkeypatch.setattr(making_api, "bled", bled)
    edit = {
        "version": boat["version"],
        "edits": [{"kind": "cutout", "parts": [part_at(*SAIL, 1)], "behind": "nothing"}],
    }
    sail = {"x": 480, "y": 260, "width": 96, "height": 80}

    for side in ("before", "after"):
        shown = client.post(
            f"/pictures/{boat['id']}/preview",
            json={"recipe": {"edit": edit}, "region": sail, "side": side},
        )
        assert shown.status_code == 200, shown.text
        part = np.asarray(Image.open(io.BytesIO(shown.content)).convert("RGBA"))
        assert part.shape == (80, 96, 4)
        assert part[..., 3].max() > 200  # the sail shows
        assert part[..., 3].min() == 0  # the sky beside it doesn't

    assert bled_over  # the part made shows what the cut-out hides carried in
    assert all(shape[0] < 600 and shape[1] < 800 for shape in bled_over)  # never all of it
