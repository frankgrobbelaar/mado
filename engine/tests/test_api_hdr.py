"""HDR photos through the API, from made-up HDR photos written by code: the grid's tag, a
picture's page, the plan, saving with the gain map kept (or not, where a format can't hold it),
saving as it is, and the copies the window shows."""

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from mado import hdr
from mado.config import DataPaths
from mado.making import AS_IS_NEW
from tests.conftest import add, made
from tests.dng_files import alike, dng
from tests.drawn import draw
from tests.hdr_files import damaged_avif, heic_with_gain_map, scene, ultra_hdr_jpeg

type Library = dict[str, Any]

SMALL = "other-256x192"


@pytest.fixture
def phone(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Library:
    """A phone's folder: an Ultra HDR photo, one whose gain map Mado doesn't know the version of,
    a HEIC with Apple's gain map, and an ordinary photo."""
    monkeypatch.setenv("MADO_FAKE_SIZE", "96x72")  # ffmpeg's stand-in draws the HEIC this big
    folder = tmp_path / "Phone"
    folder.mkdir()
    (folder / "PXL_1203.jpg").write_bytes(ultra_hdr_jpeg((96, 72)))
    (folder / "PXL_1204.jpg").write_bytes(ultra_hdr_jpeg((96, 72), version="2.0", pieces=("xmp",)))
    (folder / "IMG_2041.HEIC").write_bytes(heic_with_gain_map("apple", (96, 72)))
    draw(folder / "Still lake.jpg", size=(96, 72))
    add(client, folder)
    listed = client.get("/pictures").json()["pictures"]
    return {"folder": folder, "ids": {item["name"]: item["id"] for item in listed}, "items": listed}


def saved(client: TestClient, picture: int, recipe: dict[str, object], **saving: object) -> Path:
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": recipe, "saving": {"format": "JPEG", "quality": 92, **saving}},
    )
    assert job.status_code == 202, job.text
    done = made(client, job.json())
    assert done["state"] == "done", done["problem"]
    return Path(done["result"])


def test_the_grid_tags_an_hdr_photo(phone: Library):
    tagged = {item["name"]: item["hdr"] for item in phone["items"]}
    assert tagged == {
        "PXL_1203.jpg": True,
        "PXL_1204.jpg": False,  # a gain map Mado can't read: shown as an ordinary picture
        "IMG_2041.HEIC": True,
        "Still lake.jpg": False,
    }


def test_a_pictures_page_says_what_its_gain_map_says(client: TestClient, phone: Library):
    page = client.get(f"/pictures/{phone['ids']['PXL_1203.jpg']}").json()
    assert page["gainMap"] == {
        "readable": True,
        "stops": 3.0,
        "baseIsHdr": False,
        "colour": False,
        "width": 24,
        "height": 18,
        "why": None,
    }
    unknown = client.get(f"/pictures/{phone['ids']['PXL_1204.jpg']}").json()["gainMap"]
    assert unknown["readable"] is False
    assert unknown["why"] == "Its gain map is version 2.0, which Mado doesn't know yet."
    assert client.get(f"/pictures/{phone['ids']['Still lake.jpg']}").json()["gainMap"] is None


def test_a_picture_that_lost_its_gain_map_says_so_at_once(client: TestClient, phone: Library):
    # Saved over by another app without its gain map, before the scan has caught up.
    draw(phone["folder"] / "PXL_1203.jpg", size=(96, 72))
    page = client.get(f"/pictures/{phone['ids']['PXL_1203.jpg']}").json()
    assert page["gainMap"] is None
    assert page["hdr"] is False


def test_the_plan_says_whether_the_hdr_is_kept(client: TestClient, phone: Library):
    picture = phone["ids"]["PXL_1203.jpg"]
    sized = client.post(f"/pictures/{picture}/plan", json={"size": {"size": SMALL}}).json()
    assert (sized["hdr"], sized["hdrWhy"]) == ("kept", None)
    pencil = client.post(
        f"/pictures/{picture}/plan", json={"paint": {"style": "pencil", "strength": 1.0}}
    ).json()
    assert pencil["hdr"] == "lost"
    assert pencil["hdrWhy"].startswith("A pencil sketch is paper and lines")
    plain = client.post(f"/pictures/{phone['ids']['Still lake.jpg']}/plan", json={}).json()
    assert plain["hdr"] == "none"


def test_saving_an_hdr_photo_for_a_screen_keeps_its_gain_map(client: TestClient, phone: Library):
    result = saved(client, phone["ids"]["PXL_1203.jpg"], {"size": {"size": SMALL}})
    found = hdr.facts(result)
    assert found.state == "hdr"
    assert found.size == (64, 48)  # a quarter of the picture made, as the photo's was
    gain = hdr.read(result, ffmpeg=None, scratch=None)
    assert gain is not None
    assert gain.gains.max() > 2.0  # its sun still goes most of three stops brighter
    with Image.open(result) as written:
        assert written.size == (256, 192)


@pytest.mark.parametrize("format_", ["PNG", "WebP"])
def test_a_format_with_no_room_for_a_gain_map_saves_an_ordinary_picture(
    client: TestClient, phone: Library, format_: str
):
    result = saved(client, phone["ids"]["PXL_1203.jpg"], {"size": {"size": SMALL}}, format=format_)
    assert hdr.facts(result).state == "none"


def test_avif_keeps_the_gain_map_too(client: TestClient, phone: Library):
    result = saved(client, phone["ids"]["PXL_1203.jpg"], {"size": {"size": SMALL}}, format="AVIF")
    assert hdr.facts(result).state == "hdr"
    with Image.open(result) as written:
        written.load()  # libavif reads it whole, its tmap item and all
        assert written.size == (256, 192)


def test_its_hdr_not_kept_when_asked_not_to(client: TestClient, phone: Library):
    result = saved(client, phone["ids"]["PXL_1203.jpg"], {"size": {"size": SMALL}}, keepHdr=False)
    assert hdr.facts(result).state == "none"


class TestSavingAsItIs:
    def test_the_plan_for_nothing_never_decodes_the_picture_whole(
        self, client: TestClient, phone: Library, monkeypatch: pytest.MonkeyPatch
    ):
        # A picture's page asks for it as it opens: going through pictures with the arrow keys
        # mustn't decode each one whole (a camera RAW developed, a huge picture), holding up the
        # tools of the one being worked on. Its thumbnail and what the library read do instead.
        def whole(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("decoded whole")

        monkeypatch.setattr("mado.making.decode", whole)
        plan = client.post(f"/pictures/{phone['ids']['PXL_1203.jpg']}/plan", json={})
        assert plan.status_code == 200, plan.text
        said = plan.json()
        assert said["asIs"]
        assert (said["width"], said["height"]) == (96, 72)
        assert (said["format"], said["hdr"]) == ("JPEG", "kept")
        heic = client.post(f"/pictures/{phone['ids']['IMG_2041.HEIC']}/plan", json={}).json()
        assert heic["asIs"]
        assert (heic["width"], heic["height"], heic["hdr"]) == (96, 72, "kept")

    def test_an_hdr_photo_saved_as_it_is_keeps_its_gain_map(
        self, client: TestClient, phone: Library
    ):
        plan = client.post(f"/pictures/{phone['ids']['PXL_1203.jpg']}/plan", json={}).json()
        assert plan["asIs"]
        assert (plan["width"], plan["height"]) == (96, 72)
        result = saved(client, phone["ids"]["PXL_1203.jpg"], {})
        assert result.name == "PXL_1203 (2).jpg"  # a fresh copy, beside the original
        assert hdr.facts(result).state == "hdr"
        line = client.get("/history").json()["entries"][0]
        assert line["kind"] == "made"
        assert (line["madeFor"], line["look"], line["edit"], line["fix"]) == (None,) * 4

    def test_a_heic_saved_as_it_is_is_a_jpeg_with_its_hdr(self, client: TestClient, phone: Library):
        result = saved(client, phone["ids"]["IMG_2041.HEIC"], {})
        assert result.name == "IMG_2041.jpg"
        found = hdr.facts(result)
        assert found.state == "hdr"
        assert found.info is not None
        assert found.info.stops == pytest.approx(2.0, abs=0.01)  # Apple's headroom, four times

    def test_always_save_this_way_leaves_the_owners_way_as_it_was(
        self, client: TestClient, phone: Library
    ):
        # Saved as it is, it can only be a new picture: that's no choice of the owner's to keep.
        kept = client.get("/settings").json()
        client.put("/settings", json={**kept, "saveFirst": "replace"})
        saved(client, phone["ids"]["Still lake.jpg"], {}, always=True)
        assert client.get("/settings").json()["saveFirst"] == "replace"

    def test_a_camera_raw_comes_out_developed_at_full_size(
        self, raw_client: TestClient, tmp_path: Path
    ):
        shown = scene((600, 400))
        dng(tmp_path / "Camera" / "_MG_0042.dng", shown, preview=200)
        add(raw_client, tmp_path / "Camera")
        [listed] = raw_client.get("/pictures").json()["pictures"]
        kept = raw_client.get("/settings").json()
        raw_client.put("/settings", json={**kept, "saveFirst": "replace"})

        result = saved(raw_client, listed["id"], {}, always=True)

        assert result.name == "_MG_0042.jpg"
        assert (tmp_path / "Camera" / "_MG_0042.dng").is_file()
        with Image.open(result) as made_one:
            assert made_one.size == (600, 400)  # developed whole, not its camera's preview
            assert alike(made_one, shown) > 0.9
        assert raw_client.get("/settings").json()["saveFirst"] == "replace"
        # Nor does a RAW made for a screen: it can only be a new picture too.
        saved(raw_client, listed["id"], {"size": {"size": SMALL}}, always=True)
        assert raw_client.get("/settings").json()["saveFirst"] == "replace"

    def test_saving_as_it_is_never_replaces_the_original(self, client: TestClient, phone: Library):
        picture = phone["ids"]["Still lake.jpg"]
        refused = client.post(
            f"/pictures/{picture}/make",
            json={"recipe": {}, "saving": {"format": "PNG", "how": "replace"}},
        )
        assert refused.status_code == 409
        assert refused.json()["detail"] == AS_IS_NEW
        assert (phone["folder"] / "Still lake.jpg").is_file()

    def test_a_jpeg_starts_at_its_own_quality(self, client: TestClient, phone: Library):
        plan = client.post(f"/pictures/{phone['ids']['Still lake.jpg']}/plan", json={}).json()
        assert (plan["format"], plan["formatQuality"]) == ("JPEG", 75)  # Pillow's own, drawn

    def test_steps_that_change_nothing_still_say_so(self, client: TestClient, phone: Library):
        picture = phone["ids"]["Still lake.jpg"]
        nothing = client.post(
            f"/pictures/{picture}/make",
            json={"recipe": {"look": {"look": "original"}}, "saving": {"format": "JPEG"}},
        )
        assert nothing.status_code == 422  # a look asked for that changes nothing: no copy

    def test_a_batch_of_just_save_changes_their_format(self, client: TestClient, phone: Library):
        pictures = client.post(
            "/batches/pictures",
            json={
                "how": "ticked",
                "ids": [phone["ids"]["Still lake.jpg"], phone["ids"]["PXL_1203.jpg"]],
            },
        ).json()["pictures"]
        refused = client.post(
            "/batches",
            json={
                "source": "Phone",
                "pictures": pictures,
                "steps": [],
                "saving": {"how": "replace", "format": "PNG"},
            },
        )
        assert refused.status_code == 409  # as they are: always new pictures
        batch = client.post(
            "/batches",
            json={
                "source": "Phone",
                "pictures": pictures,
                "steps": [],
                "saving": {"format": "AVIF", "quality": 80},
            },
        )
        assert batch.status_code == 201, batch.text
        app: Any = client.app
        assert app.state.jobs.wait(120)
        assert (phone["folder"] / "Still lake.avif").is_file()
        hdr_made = phone["folder"] / "PXL_1203.avif"
        assert hdr.facts(hdr_made).state == "hdr"  # its gain map kept in the AVIF
        line = client.get("/history").json()["batches"][0]
        assert line["savedAs"] == "AVIF"
        [done] = client.get("/batches/done").json()  # Home's card says it too
        assert (done["savedAs"], done["madeFor"], done["look"]) == ("AVIF", None, None)


def test_the_view_of_an_hdr_photo_carries_its_gain_map(client: TestClient, phone: Library):
    item = next(each for each in phone["items"] if each["name"] == "PXL_1203.jpg")
    view = client.get(f"/pictures/{item['id']}/view", params={"v": item["version"]})
    assert view.status_code == 200
    assert view.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(view.content)) as shown:
        assert shown.size == (96, 72)
    found = hdr.facts(_written(view.content, phone["folder"].parent / "view.jpg"))
    assert found.state == "hdr"
    plain = next(each for each in phone["items"] if each["name"] == "Still lake.jpg")
    ordinary = client.get(f"/pictures/{plain['id']}/view", params={"v": plain["version"]})
    assert ordinary.headers["content-type"] == "image/webp"


def _written(data: bytes, path: Path) -> Path:
    path.write_bytes(data)
    return path


def test_a_gain_map_that_wont_decode_leaves_an_ordinary_picture(client: TestClient, tmp_path: Path):
    # Its numbers read, so it wears the tag; its pixels don't, so it's shown and saved plainly.
    folder = tmp_path / "Phone"
    folder.mkdir()
    (folder / "Night market.avif").write_bytes(damaged_avif())
    add(client, folder)
    item = client.get("/pictures").json()["pictures"][0]
    assert item["hdr"] is True
    view = client.get(f"/pictures/{item['id']}/view", params={"v": item["version"]})
    assert view.status_code == 200
    assert view.headers["content-type"] == "image/webp"  # an ordinary view
    result = saved(client, item["id"], {})
    assert result.name == "Night market.jpg"
    assert hdr.facts(result).state == "none"


def test_a_gain_map_that_wont_decode_is_tried_once_for_the_view(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    folder = tmp_path / "Phone"
    folder.mkdir()
    (folder / "Night market.avif").write_bytes(damaged_avif())
    add(client, folder)
    item = client.get("/pictures").json()["pictures"][0]
    tried: list[Path] = []
    reading = hdr.read

    def counted(path: Path, **kwargs: Any) -> hdr.GainMap | None:
        tried.append(path)
        return reading(path, **kwargs)

    monkeypatch.setattr(hdr, "read", counted)
    for _ in range(3):
        view = client.get(f"/pictures/{item['id']}/view", params={"v": item["version"]})
        assert view.status_code == 200
    assert len(tried) == 1  # its picture as it is, from then on


def test_an_hdr_photo_from_outside_the_library(client: TestClient, tmp_path: Path):
    outside = tmp_path / "Downloads"
    outside.mkdir()
    photo = outside / "PXL_1300.jpg"
    photo.write_bytes(ultra_hdr_jpeg((96, 72)))
    opened = client.post("/open", json={"paths": [str(photo)]})
    assert opened.status_code == 200, opened.text
    picture = opened.json()["picture"]
    assert picture["hdr"] is True
    assert picture["gainMap"]["readable"] is True
    result = saved(client, picture["id"], {})
    assert result.parent == outside
    assert hdr.facts(result).state == "hdr"


def test_a_heics_gain_map_a_stop_left_on_its_way_to_ffmpeg_goes_as_mado_starts(
    app: FastAPI, paths: DataPaths
):
    left = paths.cache / "hdr" / "gain-map-0a1b2c3d4e5f.heic"
    left.parent.mkdir(parents=True)
    left.write_bytes(b"part of a gain map")
    with TestClient(app, base_url="http://127.0.0.1"):
        pass
    assert not left.exists()
