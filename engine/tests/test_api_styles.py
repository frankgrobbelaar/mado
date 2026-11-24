"""Painting styles through the API, end to end with tiny made-up pictures and made-up networks run
on the processor (the real ones are downloads CI never has): Mado's styles, a small copy in each,
a style planned, previewed and saved with a look and touches, on a part, in a picture's own
colours, a grey and a see-through picture, a picture's style read, kept, renamed and deleted (never
the picture itself), a style in a recipe and a batch, and one gone since saying so."""

import base64
import io
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from mado import db
from mado.jobs import Jobs
from tests.conftest import add, made
from tests.drawn import photo_like, scene
from tests.edit_models import part_at, with_editing_models
from tests.style_files import with_styles

type Library = dict[str, Any]

VAN_GOGH = {"style": "van-gogh", "strength": 0.8}
WARM = {"look": "warm-film", "strength": 0.6, "touches": {"grain": 20, "vignette": 35}}
FIT = {"width": 120, "height": 120}


@pytest.fixture
def library(client: TestClient, tmp_path: Path) -> Library:
    """Phone: a made-up photo, a grey one, a sticker with see-through parts, a tiny picture, a
    plain one (one colour all over), a long panorama, and two badges whose see-through parts hide
    different colours."""
    phone = tmp_path / "Phone"
    phone.mkdir()
    scene(3, (240, 180)).save(phone / "Harbour at dusk.jpg", quality=95)
    scene(4, (200, 150)).convert("L").save(phone / "Old pier.png")
    sticker = Image.new("RGBA", (96, 72), (0, 0, 0, 0))
    ImageDraw.Draw(sticker).ellipse([16, 12, 80, 60], fill=(200, 60, 40, 255))
    sticker.save(phone / "Sticker.png")
    photo_like((64, 48)).save(phone / "Tiny.png")
    Image.new("RGB", (400, 300), (120, 140, 160)).save(phone / "Plain wall.png")
    scene(5, (2000, 100)).save(phone / "Shore.png")
    for hidden, name in (((0, 255, 0, 0), "Badge green.png"), ((0, 0, 255, 0), "Badge blue.png")):
        badge = Image.new("RGBA", (240, 160), hidden)  # what the see-through parts hide
        drawn = ImageDraw.Draw(badge)
        drawn.ellipse([40, 20, 200, 140], fill=(200, 60, 40, 255))
        drawn.rectangle([100, 60, 140, 100], fill=(240, 220, 90, 255))
        badge.save(phone / name)
    add(client, phone)
    listed = client.get("/pictures").json()["pictures"]
    return {"folder": phone, "ids": {item["name"]: item["id"] for item in listed}}


@pytest.fixture
def styles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The painters and MicroAST, made up, as if downloaded."""
    return with_styles(monkeypatch, tmp_path / "models")


def _pixels(content: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(content)) as shown:
        return np.asarray(shown.convert("RGB"), np.int16)


def test_the_styles_are_mados_four_painters_and_four_classic_means(client: TestClient):
    listed = client.get("/styles").json()

    assert [style["name"] for style in listed["painters"]] == [
        "After Van Gogh",
        "After Hokusai",
        "After Monet",
        "After Seurat",
    ]
    assert listed["painters"][0]["download"] == "style-van-gogh-starry-night"
    assert listed["painters"][0]["painting"] == "Van Gogh's The Starry Night"
    assert [(style["name"], style["setting"]) for style in listed["classics"]] == [
        ("Pencil sketch", "Darkness"),
        ("Coloured pencil", "Darkness"),
        ("Oil paint", "Brush"),
        ("Cartoon", "Colours"),
    ]
    assert listed["yours"] == []
    assert listed["reader"] == "microast"


def test_a_small_copy_of_the_picture_in_each_style(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    painted = client.get(f"/pictures/{picture}/styles/van-gogh?v=1")
    other = client.get(f"/pictures/{picture}/styles/hokusai?v=1")
    pencil = client.get(f"/pictures/{picture}/styles/pencil?v=1")

    for answer in (painted, other, pencil):
        assert answer.status_code == 200, answer.text
        assert answer.headers["content-type"] == "image/webp"
        assert "immutable" in answer.headers["cache-control"]
        assert max(Image.open(io.BytesIO(answer.content)).size) <= 256
    assert painted.content != other.content  # each painter its own
    shown = _pixels(pencil.content)
    assert np.abs(shown[..., 0] - shown[..., 2]).max() <= 4  # grey, as WebP keeps grey
    assert client.get(f"/pictures/{picture}/styles/klimt?v=1").status_code == 404


def test_a_painter_not_downloaded_yet_says_so_and_the_classic_means_need_nothing(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    waiting = client.get(f"/pictures/{picture}/styles/van-gogh?v=1")
    plan = client.post(f"/pictures/{picture}/plan", json={"paint": VAN_GOGH})
    oil = client.post(f"/pictures/{picture}/plan", json={"paint": {"style": "oil"}})

    assert waiting.status_code == 409
    assert "isn't downloaded yet" in waiting.json()["detail"]
    assert [need["id"] for need in plan.json()["needs"]] == ["style-van-gogh-starry-night"]
    assert plan.json()["needs"][0]["size"] == 6887451 + 1520
    assert oil.json()["needs"] == []
    preview = client.post(
        f"/pictures/{picture}/preview", json={"recipe": {"paint": VAN_GOGH}, "fit": FIT}
    )
    assert preview.status_code == 409  # its after needs the network; before doesn't
    before = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": {"paint": VAN_GOGH}, "side": "before", "fit": FIT},
    )
    assert before.status_code == 200


def test_a_painting_is_planned_named_and_timed_with_a_look(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    plan = client.post(
        f"/pictures/{picture}/plan",
        json={"size": {"size": "other-480x360"}, "paint": VAN_GOGH, "look": WARM},
    ).json()

    assert plan["look"] == "After Van Gogh at 80% and Warm film at 60%"
    assert plan["needs"] == []
    assert plan["paintPlace"] == "processor"  # the tests run every model on the processor
    assert plan["paintNote"] is None
    assert plan["seconds"] > 3  # a painter on the processor takes seconds
    saving = client.post(
        f"/pictures/{picture}/saving",
        json={
            "recipe": {"size": {"size": "other-480x360"}, "paint": VAN_GOGH, "look": WARM},
            "format": "JPEG",
        },
    ).json()
    assert saving["name"] == "Harbour at dusk (480 × 360, After Van Gogh, Warm film).jpg"


def test_a_painting_made_far_bigger_than_its_painted_says_its_strokes_are_soft(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    plan = client.post(
        f"/pictures/{picture}/plan", json={"size": {"size": "tv-8k"}, "paint": VAN_GOGH}
    ).json()

    assert plan["paintNote"] is not None
    assert "soft" in plan["paintNote"]


def test_a_preview_shows_the_painting_its_strength_and_the_pictures_own_colours(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    def shown(paint: dict[str, Any] | None) -> np.ndarray:
        answer = client.post(
            f"/pictures/{picture}/preview", json={"recipe": {"paint": paint}, "fit": FIT}
        )
        assert answer.status_code == 200, answer.text
        return _pixels(answer.content)

    plain = shown(None)
    full = shown({"style": "van-gogh", "strength": 1.0})
    half = shown({"style": "van-gogh", "strength": 0.5})
    colours = shown({"style": "van-gogh", "strength": 1.0, "colours": True})

    assert np.abs(full - plain).mean() > 10
    assert np.abs(half - (plain + full) / 2).mean() < 3  # mixed with the picture as it was
    # In the picture's own colours: its colour, the painting's lightness.
    assert np.abs(_lightness(colours) - _lightness(full)).mean() < 4
    assert np.abs(colours - plain).mean() < np.abs(full - plain).mean()


def _lightness(image: np.ndarray) -> np.ndarray:
    weights = np.array([0.299, 0.587, 0.114])
    return image @ weights


def test_a_part_at_full_detail_shows_the_painting_too(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    region = {"x": 100, "y": 60, "width": 120, "height": 90}

    for paint in ({"style": "van-gogh"}, {"style": "oil", "setting": 70}):
        after = client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": {"size": {"size": "other-480x360"}, "paint": paint}, "region": region},
        )
        plain = client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": {"size": {"size": "other-480x360"}}, "region": region},
        )
        assert after.status_code == 200, after.text
        assert Image.open(io.BytesIO(after.content)).size == (120, 90)
        assert np.abs(_pixels(after.content) - _pixels(plain.content)).mean() > 2


def test_a_painting_with_a_look_and_touches_is_saved_and_history_names_the_style(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    original = library["folder"] / "Harbour at dusk.jpg"
    before = original.read_bytes()

    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": {"paint": VAN_GOGH, "look": WARM}, "saving": {"format": "JPEG"}},
    )

    assert job.status_code == 202, job.text
    done = made(client, job.json())
    assert done["state"] == "done", done["problem"]
    saved = library["folder"] / "Harbour at dusk (After Van Gogh, Warm film).jpg"
    assert done["result"] == str(saved)
    assert original.read_bytes() == before  # the original as it was
    with Image.open(saved) as written:
        assert written.size == (240, 180)
    line = client.get("/history").json()["entries"][0]
    assert line["look"] == "After Van Gogh at 80% and Warm film at 60%"


def test_a_grey_picture_in_its_own_colours_stays_grey_and_in_the_styles_takes_them(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Old pier.png"]

    def shown(colours: bool) -> np.ndarray:
        answer = client.post(
            f"/pictures/{picture}/preview",
            json={"recipe": {"paint": {"style": "van-gogh", "colours": colours}}, "fit": FIT},
        )
        assert answer.status_code == 200, answer.text
        return _pixels(answer.content)

    own = shown(True)
    styled = shown(False)

    assert np.abs(own[..., 0] - own[..., 2]).max() <= 2  # grey still
    assert np.abs(styled[..., 0] - styled[..., 2]).mean() > 3  # the painting's colours


def test_see_through_parts_stay_see_through(client: TestClient, library: Library, styles: Path):
    picture = library["ids"]["Sticker.png"]

    answer = client.post(
        f"/pictures/{picture}/preview", json={"recipe": {"paint": VAN_GOGH}, "fit": FIT}
    )

    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(answer.content)) as shown:
        alpha = np.asarray(shown.convert("RGBA"))[..., 3]
    assert alpha[0, 0] == 0  # a corner, see-through as it was
    assert alpha[alpha.shape[0] // 2, alpha.shape[1] // 2] == 255


def test_a_style_on_a_part_leaves_the_rest_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
    client: TestClient,
    library: Library,
    styles: Path,
    tmp_path: Path,
):
    with_editing_models(monkeypatch, app.state.ai, tmp_path / "editing")
    picture = library["ids"]["Harbour at dusk.jpg"]
    version = client.get(f"/pictures/{picture}").json()["version"]
    sky = {"style": "pencil", "parts": [part_at(0.1, 0.08)]}

    plain = client.post(f"/pictures/{picture}/preview", json={"recipe": {}, "fit": FIT})
    parted = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": {"edit": {"version": version, "edits": []}, "paint": sky}, "fit": FIT},
    )

    assert parted.status_code == 200, parted.text
    changed = np.abs(_pixels(parted.content) - _pixels(plain.content)).max(axis=-1)
    height = changed.shape[0]
    assert changed[: height // 8].mean() > changed[-height // 4 :].mean()  # the sky, not the rest
    plan = client.post(
        f"/pictures/{picture}/plan",
        json={"edit": {"version": version, "edits": []}, "paint": sky},
    ).json()
    assert plan["look"] == "Pencil sketch on a part"


def test_a_pictures_style_is_read_from_its_colours_and_textures(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    read = client.post(f"/pictures/{picture}/style")

    assert read.status_code == 200, read.text
    found = read.json()
    assert found["named"] == "Harbour at dusk"
    assert len(base64.b64decode(found["code"])) == 2048  # 512 numbers: 2 KB
    # Its version, as the small copy of it beside the style's tile is asked for.
    assert found["version"] == client.get(f"/pictures/{picture}").json()["version"]
    other = library["ids"]["Old pier.png"]
    step = {"style": "picture", "code": found["code"], "named": found["named"]}
    painted = client.post(
        f"/pictures/{other}/preview", json={"recipe": {"paint": step}, "fit": FIT}
    )
    plain = client.post(f"/pictures/{other}/preview", json={"recipe": {}, "fit": FIT})
    assert painted.status_code == 200, painted.text
    assert painted.content != plain.content
    plan = client.post(f"/pictures/{other}/plan", json={"paint": step}).json()
    assert plan["look"] == "Harbour at dusk style"


def test_a_style_picture_too_small_or_too_plain_says_so(
    client: TestClient, library: Library, styles: Path
):
    tiny = client.post(f"/pictures/{library['ids']['Tiny.png']}/style")
    plain = client.post(f"/pictures/{library['ids']['Plain wall.png']}/style")

    assert tiny.status_code == 422
    assert tiny.json()["detail"] == (
        "Tiny.png is too small to take a style from: pick a picture at least 96 pixels across."
    )
    assert plain.status_code == 422
    assert "nearly one colour" in plain.json()["detail"]


def test_reading_a_style_waits_for_microast(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, library: Library, tmp_path: Path
):
    with_styles(monkeypatch, tmp_path / "models", microast=False)

    read = client.post(f"/pictures/{library['ids']['Harbour at dusk.jpg']}/style")

    assert read.status_code == 409
    assert "MicroAST" in read.json()["detail"]


def test_a_style_is_kept_as_its_numbers_and_a_small_copy_never_the_picture(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    found = client.post(f"/pictures/{picture}/style").json()

    kept = client.post(
        "/styles", json={"name": "Dusk harbour", "code": found["code"], "picture": picture}
    )

    assert kept.status_code == 201, kept.text
    yours = kept.json()
    assert (yours["name"], yours["source"]) == ("Dusk harbour", "Harbour at dusk.jpg")
    assert client.get("/styles").json()["yours"] == [yours]
    small = client.get(f"/styles/{yours['id']}/thumbnail")
    assert small.status_code == 200
    with Image.open(io.BytesIO(small.content)) as copy:
        assert max(copy.size) <= 160  # a small copy to know it by, not the picture
    assert len(small.content) < (library["folder"] / "Harbour at dusk.jpg").stat().st_size
    app: Any = client.app
    with closing(db.connect(app.state.paths.database)) as conn:
        code, thumbnail, source = conn.execute(
            "SELECT code, thumbnail, source FROM styles"
        ).fetchone()
    assert len(code) == 2048  # its 512 numbers
    with Image.open(io.BytesIO(thumbnail)) as stored:
        assert max(stored.size) <= 160
    assert source == "Harbour at dusk.jpg"  # the picture by its name, not the picture
    painted = client.get(f"/pictures/{library['ids']['Old pier.png']}/styles/{yours['id']}?v=1")
    assert painted.status_code == 200
    taken = client.post(
        "/styles", json={"name": "dusk HARBOUR", "code": found["code"], "picture": picture}
    )
    assert taken.status_code == 422
    assert "already" in taken.json()["detail"]
    mados = client.post(
        "/styles", json={"name": "After Monet", "code": found["code"], "picture": picture}
    )
    assert mados.status_code == 422


def test_a_kept_style_is_renamed_and_deleted_but_not_while_a_recipe_paints_with_it(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    found = client.post(f"/pictures/{picture}/style").json()
    yours = client.post(
        "/styles", json={"name": "Dusk harbour", "code": found["code"], "picture": picture}
    ).json()

    renamed = client.put(f"/styles/{yours['id']}", json={"name": "Evening harbour"})
    recipe = client.post(
        "/recipes",
        json={
            "name": "Evening prints",
            "steps": [{"step": "paint", "style": yours["id"], "strength": 0.7}],
            "saving": {"format": "JPEG"},
        },
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Evening harbour"
    assert recipe.status_code == 201, recipe.text
    [paint, _save] = recipe.json()["words"]
    assert (paint["kind"], paint["chip"], paint["amount"]) == ("paint", "Evening harbour", "70")
    refused = client.delete(f"/styles/{yours['id']}")
    assert refused.status_code == 409
    assert "Evening prints" in refused.json()["detail"]
    client.delete(f"/recipes/{recipe.json()['id']}")
    assert client.delete(f"/styles/{yours['id']}").status_code == 204
    assert client.get("/styles").json()["yours"] == []


def test_a_batch_paints_in_a_style_and_says_so(client: TestClient, library: Library, styles: Path):
    picked = client.post(
        "/batches/pictures",
        json={"how": "ticked", "ids": [library["ids"]["Harbour at dusk.jpg"]]},
    ).json()
    steps = [
        {"step": "look", **WARM},
        {"step": "paint", "style": "hokusai", "strength": 0.9, "colours": True},
    ]

    takes = client.post(
        "/batches/takes",
        json={"pictures": picked["pictures"], "steps": steps, "saving": {"format": "JPEG"}},
    )

    assert takes.status_code == 200, takes.text
    words = takes.json()["words"]
    assert [each["kind"] for each in words] == ["paint", "look", "save"]  # in Mado's order
    assert words[0]["detail"] == "After Hokusai at 90%, in each picture's own colours"
    assert takes.json()["look"] == (
        "After Hokusai at 90%, in the picture's own colours, and Warm film at 60%"
    )
    assert takes.json()["example"] == "Name (After Hokusai, Warm film).jpg"


def test_a_job_whose_style_was_deleted_says_so_and_saves_nothing(
    app: FastAPI, client: TestClient, library: Library
):
    jobs: Jobs = app.state.jobs
    source = library["folder"] / "Harbour at dusk.jpg"
    order: dict[str, object] = {
        "recipe": {"paint": {"style": "yours-41", "strength": 1.0}},
        "saving": {"format": "JPEG"},
        "label": None,
        "look": "Gone",
    }

    with closing(db.connect(app.state.paths.database)) as conn:
        job_id = jobs.add(conn, library["ids"]["Harbour at dusk.jpg"], source, order)
    done = made(client, {"id": job_id})

    assert done["state"] == "failed"
    assert done["problem"] == (
        "Its painting style isn't in your styles any more, so nothing was made and the "
        "original is as it was. Pick another style, then save again."
    )
    assert not (library["folder"] / "Harbour at dusk (Gone).jpg").exists()


def test_the_queue_says_a_picture_being_painted_is_at_its_painting_step(
    app: FastAPI, client: TestClient, library: Library, styles: Path
):
    jobs: Jobs = app.state.jobs
    jobs.stop()  # nothing is made: each picture's stage is set by hand below
    put = _put_in(
        client,
        library["ids"]["Harbour at dusk.jpg"],
        [{"step": "size", "size": "other-256x192"}, {"step": "paint", "style": "monet"}],
    )
    said: dict[str, str] = {}
    for stage in ("reading", "making", "painting", "saving"):
        with closing(db.connect(app.state.paths.database)) as conn, conn:
            conn.execute(
                "UPDATE jobs SET state = 'running', stage = ? WHERE batch_id = ?",
                (stage, put["id"]),
            )
        said[stage] = client.get("/queue").json()["rows"][0]["step"]

    assert said == {
        "reading": "Make it for a screen 1/3",
        "making": "Make it for a screen 1/3",
        "painting": "A painting style 2/3",
        "saving": "Save 3/3",
    }


def test_a_kept_style_isnt_deleted_while_pictures_wait_to_be_painted_with_it(
    app: FastAPI, client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    found = client.post(f"/pictures/{picture}/style").json()
    yours = client.post(
        "/styles", json={"name": "Dusk harbour", "code": found["code"], "picture": picture}
    ).json()
    jobs: Jobs = app.state.jobs
    jobs.stop()  # they wait
    _put_in(client, picture, [{"step": "paint", "style": yours["id"]}])

    refused = client.delete(f"/styles/{yours['id']}")

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Pictures waiting in the queue are painted with it. Delete it once they're made, or "
        "take them out of the queue first."
    )
    assert client.get("/styles").json()["yours"][0]["id"] == yours["id"]


def test_a_small_copy_keeps_the_pictures_see_through_parts(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Sticker.png"]

    for style in ("van-gogh", "pencil"):
        small = client.get(f"/pictures/{picture}/styles/{style}?v=1")

        assert small.status_code == 200, small.text
        with Image.open(io.BytesIO(small.content)) as copy:
            assert copy.mode == "RGBA", style
            alpha = np.asarray(copy.getchannel("A"))
        assert alpha[0, 0] == 0, style  # its corner see-through, as it was
        assert alpha[alpha.shape[0] // 2, alpha.shape[1] // 2] == 255, style


def test_a_long_panorama_gives_its_style(client: TestClient, library: Library, styles: Path):
    read = client.post(f"/pictures/{library['ids']['Shore.png']}/style")

    assert read.status_code == 200, read.text
    assert read.json()["named"] == "Shore"


def test_a_style_is_read_from_what_a_picture_shows_not_what_its_see_through_parts_hide(
    client: TestClient, library: Library, styles: Path
):
    green = client.post(f"/pictures/{library['ids']['Badge green.png']}/style").json()
    blue = client.post(f"/pictures/{library['ids']['Badge blue.png']}/style").json()

    assert green["code"] == blue["code"]


def test_a_pictures_style_that_cant_be_read_says_so(
    client: TestClient, library: Library, styles: Path
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    damaged = {"style": "picture", "code": "bm90IGEgc3R5bGU=", "named": "Night market"}

    plan = client.post(f"/pictures/{picture}/plan", json={"paint": damaged})
    small = client.post(
        f"/pictures/{picture}/styles/picture",
        json={"code": damaged["code"], "named": "Night market"},
    )

    for answer in (plan, small):
        assert answer.status_code == 422, answer.text
        assert answer.json()["detail"] == (
            "Mado couldn't read that picture's style. Pick the picture again for its style."
        )


def _put_in(client: TestClient, picture: int, steps: list[dict[str, Any]]) -> dict[str, Any]:
    """A batch of one picture with these steps, put in the queue now."""
    picked = client.post("/batches/pictures", json={"how": "ticked", "ids": [picture]}).json()
    put = client.post(
        "/batches",
        json={
            "source": picked["source"],
            "shared": picked["shared"],
            "pictures": picked["pictures"],
            "steps": steps,
            "saving": {"how": "new", "format": "JPEG", "quality": 90, "folder": "Edited"},
            "starts": "now",
        },
    )
    assert put.status_code == 201, put.text
    return put.json()
