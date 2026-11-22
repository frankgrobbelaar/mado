"""Looks through the API, end to end with tiny made-up pictures: Mado's looks and the owner's, a
small copy in each, importing a .cube file, keeping a mix, renaming and deleting it, and a look
alone or with a size made by one Save, previewed first, named after both, and in History."""

import io
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageCms

from mado import db
from mado.core.grids import identity
from mado.jobs import Jobs
from mado.quarantine import Quarantine
from tests.conftest import add, made
from tests.drawn import photo_like

type Library = dict[str, Any]

WARM = {"look": "warm-film", "strength": 0.6, "touches": {"grain": 20, "vignette": 35}}


@pytest.fixture
def library(client: TestClient, tmp_path: Path) -> Library:
    """Phone: a made-up photo, and a sticker with see-through parts round it."""
    phone = tmp_path / "Phone"
    phone.mkdir()
    photo_like((120, 90)).save(phone / "Harbour at dusk.jpg", quality=95)
    sticker = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
    sticker.paste((200, 60, 40, 255), (16, 12, 48, 36))
    sticker.save(phone / "Sticker.png")
    add(client, phone)
    listed = client.get("/pictures").json()["pictures"]
    return {"folder": phone, "ids": {item["name"]: item["id"] for item in listed}}


def _cube(path: Path, title: str = "Holiday warm") -> Path:
    rows = "\n".join(
        f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in (identity(9) ** 0.8).reshape(-1, 3).tolist()
    )
    path.write_text(f'TITLE "{title}"\nLUT_3D_SIZE 9\n{rows}\n', encoding="utf-8")
    return path


def test_the_looks_are_mados_with_the_original_first_and_the_owners(client: TestClient):
    listed = client.get("/looks").json()

    assert [look["name"] for look in listed["looks"][:3]] == ["Original", "Warm film", "Cool film"]
    assert len(listed["looks"]) == 14
    assert all(len(look["version"]) == 8 for look in listed["looks"])
    assert listed["yours"] == []


def test_a_small_copy_of_the_picture_in_each_look(client: TestClient, library: Library):
    picture = library["ids"]["Harbour at dusk.jpg"]

    warm = client.get(f"/pictures/{picture}/looks/warm-film?v=1")
    original = client.get(f"/pictures/{picture}/looks/original?v=1")

    assert warm.status_code == 200, warm.text
    assert warm.headers["content-type"] == "image/webp"
    assert "immutable" in warm.headers["cache-control"]
    small = Image.open(io.BytesIO(warm.content))
    assert max(small.size) <= 256
    assert warm.content != original.content
    gone = client.get(f"/pictures/{picture}/looks/yours-99")
    assert gone.status_code == 404
    assert gone.json()["detail"] == "That look isn't in your looks any more."
    assert client.get("/pictures/999/looks/warm-film").status_code == 404


def test_a_cube_file_is_imported_and_one_mado_cant_use_says_why(client: TestClient, tmp_path: Path):
    imported = client.post("/looks/import", json={"path": str(_cube(tmp_path / "warm.cube"))})
    (tmp_path / "Notes.cube").write_text("my shopping list\n", encoding="utf-8")
    refused = client.post("/looks/import", json={"path": str(tmp_path / "Notes.cube")})

    assert imported.status_code == 201, imported.text
    look = imported.json()
    assert (look["name"], look["kind"], look["points"], look["source"]) == (
        "Holiday warm",
        "cube",
        9,
        "warm.cube",
    )
    assert [each["id"] for each in client.get("/looks").json()["yours"]] == [look["id"]]
    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "Notes.cube: It isn't a .cube file: it has no table of colours in it."
    )


def test_a_mix_is_kept_renamed_and_deleted(client: TestClient, library: Library):
    kept = client.post("/looks", json={"name": "Holiday warm", "look": WARM})
    taken = client.post("/looks", json={"name": "holiday WARM", "look": WARM})
    mados = client.post("/looks", json={"name": "Silver", "look": WARM})

    assert kept.status_code == 201, kept.text
    mine = kept.json()
    assert mine["kind"] == "mix"
    assert mine["source"] == "Warm film at 60%, grain 20, vignette 35"
    assert mine["touches"] == {
        "grain": 20,
        "vignette": 35,
        "glow": 0,
        "fade": 0,
        "leak": 0,
        "dust": 0,
    }
    assert taken.status_code == 422
    assert taken.json()["detail"] == (
        "You have a look called Holiday warm already. Pick another name."
    )
    assert mados.json()["detail"] == "Silver is one of Mado's own looks. Pick another name."
    copy = client.get(f"/pictures/{library['ids']['Harbour at dusk.jpg']}/looks/{mine['id']}")
    assert copy.status_code == 200

    renamed = client.put(f"/looks/{mine['id']}", json={"name": "Summer warm"})

    assert renamed.json()["name"] == "Summer warm"
    assert client.delete(f"/looks/{mine['id']}").status_code == 204
    assert client.delete(f"/looks/{mine['id']}").status_code == 404
    assert client.put(f"/looks/{mine['id']}", json={"name": "Again"}).status_code == 404
    assert client.get("/looks").json()["yours"] == []


def test_a_look_alone_is_planned_on_the_pictures_own_pixels(client: TestClient, library: Library):
    picture = library["ids"]["Harbour at dusk.jpg"]

    plan = client.post(f"/pictures/{picture}/plan", json={"look": WARM}).json()

    assert (plan["width"], plan["height"]) == (120, 90)
    assert plan["method"] == "keep"
    assert plan["label"] == ""
    assert plan["look"] == "Warm film at 60%"
    assert plan["model"] is None
    assert plan["needs"] == []
    assert plan["format"] == "JPEG"
    sized = client.post(
        f"/pictures/{picture}/plan", json={"size": {"size": "other-256x192"}, "look": WARM}
    ).json()
    assert (sized["label"], sized["look"]) == ("256 × 192", "Warm film at 60%")


def test_a_preview_shows_the_look_on_the_whole_picture_and_on_a_part(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    fit = {"width": 60, "height": 60}

    plain = client.post(f"/pictures/{picture}/preview", json={"recipe": {}, "fit": fit})
    warm = client.post(f"/pictures/{picture}/preview", json={"recipe": {"look": WARM}, "fit": fit})
    part = client.post(
        f"/pictures/{picture}/preview",
        json={
            "recipe": {"size": {"size": "other-240x180"}, "look": WARM},
            "region": {"x": 40, "y": 30, "width": 80, "height": 60},
        },
    )

    assert warm.status_code == 200, warm.text
    shown = Image.open(io.BytesIO(warm.content))
    assert shown.size == (60, 45)
    assert warm.content != plain.content
    assert float(warm.headers["x-made-in"]) >= 0
    assert Image.open(io.BytesIO(part.content)).size == (80, 60)
    gone = client.post(
        f"/pictures/{picture}/preview", json={"recipe": {"look": {"look": "yours-7"}}, "fit": fit}
    )
    assert gone.status_code == 404


def test_a_preview_bigger_than_the_screen_sized_view_comes_from_the_picture(
    client: TestClient, tmp_path: Path
):
    stripes = np.zeros((1200, 3000, 3), np.uint8)
    stripes[:, ::2] = 255  # columns a pixel wide, which a view made smaller would lose
    big = tmp_path / "Big"
    big.mkdir()
    Image.fromarray(stripes).save(big / "Stripes.png")
    add(client, big)
    picture = client.get("/pictures").json()["pictures"][0]["id"]

    preview = client.post(
        f"/pictures/{picture}/preview", json={"recipe": {}, "fit": {"width": 3000, "height": 3000}}
    )

    assert preview.status_code == 200, preview.text
    shown = np.asarray(Image.open(io.BytesIO(preview.content)).convert("L"), np.float32)
    assert shown.shape == (1200, 3000)
    assert np.abs(np.diff(shown[600, 1000:1100])).mean() > 150  # the stripes kept, sharp


def test_previews_keep_the_pictures_colour_profile(client: TestClient, tmp_path: Path):
    cms: Any = ImageCms  # Pillow's colour management, partly unknown to Pyright
    profile: bytes = cms.ImageCmsProfile(cms.createProfile("sRGB")).tobytes()
    wide = tmp_path / "Wide"
    wide.mkdir()
    photo_like((120, 90)).save(wide / "Lagoon.jpg", quality=95, icc_profile=profile)
    add(client, wide)
    picture = client.get("/pictures").json()["pictures"][0]["id"]

    fitted = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": {"look": WARM}, "fit": {"width": 60, "height": 60}},
    )
    part = client.post(
        f"/pictures/{picture}/preview",
        json={
            "recipe": {"size": {"size": "other-240x180"}, "look": WARM},
            "region": {"x": 40, "y": 30, "width": 80, "height": 60},
        },
    )
    before = client.post(
        f"/pictures/{picture}/preview",
        json={
            "recipe": {"size": {"size": "other-240x180"}},
            "region": {"x": 40, "y": 30, "width": 80, "height": 60},
            "side": "before",
        },
    )
    small = client.get(f"/pictures/{picture}/looks/warm-film")

    assert fitted.headers["content-type"] == "image/jpeg"
    for answer in (fitted, part, before, small):
        assert answer.status_code == 200, answer.text
        assert Image.open(io.BytesIO(answer.content)).info.get("icc_profile") == profile


def test_the_name_a_picture_would_have_says_its_look(client: TestClient, library: Library):
    picture = library["ids"]["Harbour at dusk.jpg"]

    alone = client.post(
        f"/pictures/{picture}/saving", json={"recipe": {"look": WARM}, "format": "JPEG"}
    ).json()
    both = client.post(
        f"/pictures/{picture}/saving",
        json={"recipe": {"size": {"size": "tv-8k"}, "look": WARM}, "format": "JPEG"},
    ).json()
    grain = client.post(
        f"/pictures/{picture}/saving",
        json={
            "recipe": {"look": {"look": "original", "touches": {"grain": 30}}},
            "format": "JPEG",
        },
    ).json()
    nothing = client.post(
        f"/pictures/{picture}/saving",
        json={"recipe": {"look": {"look": "original"}}, "format": "JPEG"},
    )

    assert alone["name"] == "Harbour at dusk (Warm film).jpg"
    assert both["name"] == "Harbour at dusk (TV 8K, Warm film).jpg"
    assert grain["name"] == "Harbour at dusk (Grain).jpg"
    assert nothing.status_code == 422
    assert nothing.json()["detail"] == (
        "Pick a size or a look first: as it is, there's nothing to make."
    )


def test_a_look_alone_is_saved_as_a_new_picture_and_history_says_so(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    original = library["folder"] / "Harbour at dusk.jpg"
    before = original.read_bytes()

    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": {"look": WARM}, "saving": {"format": "JPEG", "quality": 95}},
    )

    assert job.status_code == 202, job.text
    assert (job.json()["madeFor"], job.json()["look"]) == (None, "Warm film at 60%")
    done = made(client, job.json())
    assert done["state"] == "done", done["problem"]
    saved = library["folder"] / "Harbour at dusk (Warm film).jpg"
    assert done["result"] == str(saved)
    assert original.read_bytes() == before  # the original as it was
    with Image.open(saved) as written, Image.open(original) as first:
        assert written.size == (120, 90)
        warmer = np.asarray(written.convert("RGB"), np.int16) - np.asarray(
            first.convert("RGB"), np.int16
        )
    assert warmer[..., 0].mean() > warmer[..., 2].mean()
    line = client.get("/history").json()["entries"][0]
    assert (line["kind"], line["madeFor"], line["look"]) == ("made", None, "Warm film at 60%")


def test_a_size_and_a_look_are_made_by_one_save(client: TestClient, library: Library):
    picture = library["ids"]["Harbour at dusk.jpg"]

    job = client.post(
        f"/pictures/{picture}/make",
        json={
            "recipe": {"size": {"size": "other-240x180"}, "look": WARM},
            "saving": {"format": "PNG"},
        },
    ).json()
    done = made(client, job)

    assert done["state"] == "done", done["problem"]
    assert done["resultName"] == "Harbour at dusk (240 × 180, Warm film).png"
    with Image.open(done["result"]) as written:
        assert written.size == (240, 180)
    line = client.get("/history").json()["entries"][0]
    assert (line["madeFor"], line["look"]) == ("240 × 180", "Warm film at 60%")


def test_a_look_replacing_the_original_keeps_its_see_through_parts_and_sets_it_aside(
    client: TestClient, library: Library, quarantine: Quarantine
):
    picture = library["ids"]["Sticker.png"]
    original = library["folder"] / "Sticker.png"
    with Image.open(original) as first:
        alpha = np.asarray(first.getchannel("A")).copy()

    job = client.post(
        f"/pictures/{picture}/make",
        json={
            "recipe": {"look": {"look": "night-neon", "touches": {"dust": 50, "grain": 30}}},
            "saving": {"how": "replace", "format": "PNG"},
        },
    ).json()
    done = made(client, job)

    assert done["state"] == "done", done["problem"]
    with Image.open(original) as replaced:
        assert replaced.mode == "RGBA"
        assert np.array_equal(np.asarray(replaced.getchannel("A")), alpha)
    line = client.get("/history").json()["entries"][0]
    assert (line["kind"], line["look"]) == ("replaced", "Night neon")
    assert quarantine.holds(Path(line["aside"]))


def test_nothing_to_make_is_refused(client: TestClient, library: Library):
    picture = library["ids"]["Harbour at dusk.jpg"]

    refused = client.post(
        f"/pictures/{picture}/make",
        json={
            "recipe": {"look": {"look": "warm-film", "strength": 0}},
            "saving": {"format": "JPEG"},
        },
    )

    assert refused.status_code == 422
    assert client.get("/jobs").json() == []


def test_a_job_whose_look_was_deleted_says_so_and_saves_nothing(
    app: FastAPI, client: TestClient, library: Library
):
    jobs: Jobs = app.state.jobs
    source = library["folder"] / "Harbour at dusk.jpg"
    order: dict[str, object] = {
        "recipe": {"size": None, "look": {"look": "yours-41", "strength": 1.0, "touches": {}}},
        "saving": {"format": "JPEG"},
        "label": None,
        "look": "Gone",
    }

    with closing(db.connect(app.state.paths.database)) as conn:
        job_id = jobs.add(conn, library["ids"]["Harbour at dusk.jpg"], source, order)

    done = made(client, {"id": job_id})

    assert done["state"] == "failed"
    assert done["problem"] == (
        "Its look isn't in your looks any more, so nothing was made and the original is as it "
        "was. Pick another look, then save again."
    )
    assert sorted(path.name for path in library["folder"].iterdir()) == [
        "Harbour at dusk.jpg",
        "Sticker.png",
    ]


def test_a_job_mado_0_1_kept_is_still_made(app: FastAPI, client: TestClient, library: Library):
    jobs: Jobs = app.state.jobs
    source = library["folder"] / "Harbour at dusk.jpg"
    order = {  # as Mado 0.1 kept it: the size's fields, flat
        "recipe": {"size": "other-240x180", "shape": "crop", "focus": None, "kind": None,
                   "quality": None, "clean": True},
        "saving": {"format": "JPEG"},
        "label": "240 × 180",
    }  # fmt: skip

    with closing(db.connect(app.state.paths.database)) as conn:
        job_id = jobs.add(conn, library["ids"]["Harbour at dusk.jpg"], source, order)

    done = made(client, {"id": job_id})

    assert done["state"] == "done", done["problem"]
    assert (done["madeFor"], done["look"]) == ("240 × 180", None)
    assert done["resultName"] == "Harbour at dusk (240 × 180).jpg"
