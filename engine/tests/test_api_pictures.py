"""The pictures through the API: the grid by the day they were taken, a picture's details, its
neighbours, and the copies the window shows."""

import errno
import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps

from mado.api import create_app
from mado.config import DataPaths
from mado.libraw import SESSION, LibRaw, RawError, Reader
from mado.pictures import InUseError
from mado.quarantine import Quarantine
from mado.scan import RAW_NOTES, STOPPED_ON
from tests.conftest import TOKEN, add, made_app
from tests.dng_files import alike, dng, truncated
from tests.drawn import draw, exif, scene
from tests.heif_files import exif_item, heif

type Library = dict[str, Any]


@pytest.fixture
def library(client: TestClient, tmp_path: Path) -> Library:
    """Phone: three days of pictures, one in a folder of its own; Camera: one picture."""
    phone, camera = tmp_path / "Phone", tmp_path / "Camera"
    taken = {
        "Harbour at dusk.jpg": "2026:11:14 18:42:07",
        "Little sail.jpg": "2026:11:14 16:05:00",
        "Snowfield.jpg": "2026:11:13 10:02:00",
        "Trip/Red canyon.jpg": "2026:11:13 12:30:00",
        "Green sky.jpg": "2026:11:11 23:51:00",
    }
    for name, when in taken.items():
        draw(phone / name, described=exif(taken=when, make="Pixelworks", model="PW-7"))
    draw(camera / "Still lake.jpg", described=exif(taken="2026:11:12 07:58:00"))
    found = {"phone": add(client, phone), "camera": add(client, camera)}
    listed = client.get("/pictures").json()["pictures"]
    found["ids"] = {item["name"]: item["id"] for item in listed}
    return found


def names(page: dict[str, Any]) -> list[str]:
    return [item["name"] for item in page["pictures"]]


def test_the_grid_lists_pictures_by_the_day_they_were_taken_newest_first(
    client: TestClient, library: Library
):
    page = client.get("/pictures").json()

    assert names(page) == [
        "Harbour at dusk.jpg",
        "Little sail.jpg",
        "Red canyon.jpg",
        "Snowfield.jpg",
        "Still lake.jpg",
        "Green sky.jpg",
    ]
    assert page["days"] == [
        {"day": "2026-11-14", "pictures": 2},
        {"day": "2026-11-13", "pictures": 2},
        {"day": "2026-11-12", "pictures": 1},
        {"day": "2026-11-11", "pictures": 1},
    ]
    assert (page["total"], page["next"]) == (6, None)
    first = page["pictures"][0]
    assert (first["format"], first["state"], first["width"], first["height"]) == (
        "JPEG",
        "ready",
        64,
        48,
    )
    assert first["takenAt"] == "2026-11-14T18:42:07"
    assert first["version"]


def test_the_grid_comes_a_page_at_a_time_each_day_counted_whole(
    client: TestClient, library: Library
):
    first = client.get("/pictures", params={"limit": 3}).json()
    second = client.get("/pictures", params={"limit": 3, "after": first["next"]}).json()

    assert names(first) == ["Harbour at dusk.jpg", "Little sail.jpg", "Red canyon.jpg"]
    assert names(second) == ["Snowfield.jpg", "Still lake.jpg", "Green sky.jpg"]
    assert first["days"][-1] == {"day": "2026-11-13", "pictures": 2}  # though one is on page 2
    assert second["next"] is None


def test_the_grid_can_go_oldest_first(client: TestClient, library: Library):
    page = client.get("/pictures", params={"order": "oldest"}).json()

    assert names(page)[:2] == ["Green sky.jpg", "Still lake.jpg"]
    assert page["days"][0] == {"day": "2026-11-11", "pictures": 1}


def test_a_folder_shows_its_pictures_and_those_in_the_folders_inside_it(
    client: TestClient, library: Library
):
    phone = library["phone"]["id"]

    whole = client.get("/pictures", params={"folder": phone}).json()
    trip = client.get("/pictures", params={"folder": phone, "dir": "Trip"}).json()

    assert whole["total"] == 5
    assert "Still lake.jpg" not in names(whole)
    assert names(trip) == ["Red canyon.jpg"]


def test_a_search_finds_pictures_with_every_word_in_their_name(
    client: TestClient, library: Library
):
    page = client.get("/pictures", params={"q": "DUSK harb"}).json()
    none = client.get("/pictures", params={"q": "100%_"}).json()

    assert names(page) == ["Harbour at dusk.jpg"]
    assert none["total"] == 0


def test_raw_and_pictures_that_wont_open_are_listed_as_what_they_are(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "Camera").mkdir()
    (tmp_path / "Camera" / "_MG_0042.CR3").write_bytes(b"raw")
    (tmp_path / "Camera" / "Old pier.tif").write_text("not a picture", encoding="utf-8")
    add(client, tmp_path / "Camera")

    listed = {item["name"]: item for item in client.get("/pictures").json()["pictures"]}

    # Without Mado's RAW reader, a camera RAW is listed as it is, waiting for it.
    assert {name: item["state"] for name, item in listed.items()} == {
        "_MG_0042.CR3": "waiting",
        "Old pier.tif": "broken",
    }
    assert (listed["_MG_0042.CR3"]["raw"], listed["Old pier.tif"]["raw"]) == (True, False)


def test_a_camera_raw_is_read_its_thumbnail_its_cameras_and_its_view_developed(
    raw_client: TestClient, tmp_path: Path
):
    shown = scene(4, (600, 400))
    dng(tmp_path / "Camera" / "_MG_0042.dng", shown, preview=ImageOps.invert(shown))
    add(raw_client, tmp_path / "Camera")
    [listed] = raw_client.get("/pictures").json()["pictures"]
    page = raw_client.get(f"/pictures/{listed['id']}").json()

    thumbnail = picture_of(raw_client.get(f"/pictures/{listed['id']}/thumbnail"))
    view = picture_of(raw_client.get(f"/pictures/{listed['id']}/view"))
    full = raw_client.get(f"/pictures/{listed['id']}/full")

    assert (listed["state"], listed["raw"], listed["format"]) == ("ready", True, "DNG")
    assert (page["width"], page["height"], page["camera"]) == (600, 400, "Lumen X100")
    assert page["takenAt"] == "2026-11-12T18:42:07"
    assert alike(thumbnail, ImageOps.invert(shown)) > 0.9  # from the preview its camera kept
    assert alike(view, shown) > 0.95  # developed, as Save makes it
    assert full.headers["content-type"] == "image/png"
    assert picture_of(full).size == (600, 400)


def test_a_camera_raw_that_wont_develop_joins_the_pictures_that_wont_open(
    raw_client: TestClient, tmp_path: Path
):
    # Half copied: what it says of itself and its camera's preview are there, its pixels aren't.
    truncated(dng(tmp_path / "Camera" / "_MG_0042.dng", scene(4, (600, 400))), keep=0.5)
    add(raw_client, tmp_path / "Camera")
    [listed] = raw_client.get("/pictures").json()["pictures"]
    assert listed["state"] == "ready"

    view = raw_client.get(f"/pictures/{listed['id']}/view")

    assert view.status_code == 422
    assert "only half copied" in view.json()["detail"]
    after = raw_client.get(f"/pictures/{listed['id']}").json()
    assert after["state"] == "broken"
    [wont] = raw_client.get("/library/wont-open").json()["pictures"]
    assert wont["id"] == listed["id"]


def test_opening_a_camera_raw_that_waits_asks_for_mados_raw_reader(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    asked: list[int] = []
    reader = Reader(lambda: None, lambda: asked.append(1), retry_after=0)
    (tmp_path / "Camera").mkdir()
    (tmp_path / "Camera" / "_MG_0042.CR3").write_bytes(b"raw")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(
        made_app(paths, quarantine, reader), base_url="http://127.0.0.1", headers=headers
    ) as client:
        add(client, tmp_path / "Camera")
        [listed] = client.get("/pictures").json()["pictures"]
        before = len(asked)

        page = client.get(f"/pictures/{listed['id']}").json()

    assert page["state"] == "waiting"
    assert len(asked) == before + 1  # its page asks for the reader too, as a scan does


def test_a_camera_raw_too_big_for_the_memory_free_now_is_left_as_it_was(
    raw_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dng(tmp_path / "Camera" / "_MG_0042.dng", scene(4, (600, 400)))
    add(raw_client, tmp_path / "Camera")
    [listed] = raw_client.get("/pictures").json()["pictures"]

    def short(*_args: object, **_options: object) -> None:
        raise RawError(-100007, "develop", "Not enough memory")

    monkeypatch.setattr(LibRaw, "develop", short)
    view = raw_client.get(f"/pictures/{listed['id']}/view")

    assert view.status_code == 422
    assert "memory free now" in view.json()["detail"]
    after = raw_client.get(f"/pictures/{listed['id']}").json()
    assert (after["state"], after["problem"]) == ("ready", None)  # it passes: not won't open


def test_a_camera_raw_an_engine_stopped_on_is_left_as_one_that_wont_open_as_the_next_starts(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path, libraw_folder: Path
):
    camera = tmp_path / "Camera"
    stopped = dng(camera / "_MG_0042.dng", scene(4, (600, 400)))
    notes = paths.root / RAW_NOTES
    headers = {"Authorization": f"Bearer {TOKEN}"}

    def engine() -> TestClient:
        reader = Reader(lambda: libraw_folder, notes=notes)
        return TestClient(
            made_app(paths, quarantine, reader), base_url="http://127.0.0.1", headers=headers
        )

    with engine() as client:
        add(client, camera)
        # As this engine stops cleanly, a RAW it was reading didn't stop it: its note goes.
        (notes / f"{SESSION}-8.txt").write_text(str(stopped), encoding="utf-8")
    assert list(notes.glob("*.txt")) == []
    (notes / "0123456789ab-7.txt").write_text(str(stopped), encoding="utf-8")  # a crash's

    with engine() as client:
        [listed] = client.get("/pictures").json()["pictures"]
        page = client.get(f"/pictures/{listed['id']}").json()

    assert (page["state"], page["problem"]) == ("broken", STOPPED_ON)
    assert list(notes.glob("*.txt")) == []


def test_a_pictures_details_say_everything_mado_read_of_it(client: TestClient, tmp_path: Path):
    described = exif(
        taken="2026:11:12 18:42:07", make="Pixelworks", model="PW-7", orientation=6, where=True
    )
    picture = draw(tmp_path / "Phone" / "2026" / "IMG_2041.jpg", described=described)
    folder = add(client, tmp_path / "Phone")
    [item] = client.get("/pictures").json()["pictures"]

    details = client.get(f"/pictures/{item['id']}").json()

    assert details["folderId"] == folder["id"]
    assert (details["folder"], details["dir"]) == (str(tmp_path / "Phone"), "2026")
    assert (details["path"], details["size"]) == (str(picture), picture.stat().st_size)
    assert (details["width"], details["height"], details["orientation"]) == (48, 64, 6)
    assert (details["takenAt"], details["takenFrom"]) == ("2026-11-12T18:42:07", "camera")
    assert (details["camera"], details["located"], details["problem"]) == (
        "Pixelworks PW-7",
        True,
        None,
    )
    assert details["modifiedAt"].startswith("20")


def test_a_picture_not_in_the_library_says_so(client: TestClient):
    response = client.get("/pictures/404")

    assert response.status_code == 404
    assert response.json()["detail"] == "That picture isn't in your library any more."


def test_a_pictures_neighbours_come_in_the_grids_order(client: TestClient, library: Library):
    ids = library["ids"]
    middle = ids["Red canyon.jpg"]

    near = client.get(f"/pictures/{middle}/neighbours", params={"count": 2}).json()
    in_phone = client.get(
        f"/pictures/{ids['Snowfield.jpg']}/neighbours",
        params={"folder": library["phone"]["id"], "count": 1},
    ).json()

    assert [item["name"] for item in near["before"]] == ["Harbour at dusk.jpg", "Little sail.jpg"]
    assert [item["name"] for item in near["after"]] == ["Snowfield.jpg", "Still lake.jpg"]
    assert [item["name"] for item in in_phone["after"]] == ["Green sky.jpg"]  # not Camera's


def picture_of(response: Any) -> Image.Image:
    return Image.open(io.BytesIO(response.content))


def test_a_pictures_thumbnail_and_view_are_webp_kept_by_the_window(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    thumbnail = client.get(f"/pictures/{picture}/thumbnail")
    view = client.get(f"/pictures/{picture}/view")

    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    assert "immutable" in thumbnail.headers["cache-control"]
    assert picture_of(thumbnail).size == (64, 48)
    assert view.headers["content-type"] == "image/webp"


def test_full_size_is_the_picture_itself_or_a_copy_the_window_can_show(
    client: TestClient, tmp_path: Path
):
    jpeg = draw(tmp_path / "Scans" / "page.jpg", size=(90, 60))
    draw(tmp_path / "Scans" / "page.tif", size=(90, 60))
    add(client, tmp_path / "Scans")
    ids = {item["name"]: item["id"] for item in client.get("/pictures").json()["pictures"]}

    as_is = client.get(f"/pictures/{ids['page.jpg']}/full")
    copy = client.get(f"/pictures/{ids['page.tif']}/full")

    assert as_is.content == jpeg.read_bytes()
    assert as_is.headers["content-type"] == "image/jpeg"
    assert copy.headers["content-type"] == "image/png"
    assert picture_of(copy).size == (90, 60)


def test_a_picture_that_wont_open_or_waits_for_its_reader_has_no_copies_and_says_why(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "Camera").mkdir()
    (tmp_path / "Camera" / "_MG_0042.CR3").write_bytes(b"raw")
    (tmp_path / "Camera" / "Old pier.jpg").write_text("not a picture", encoding="utf-8")
    add(client, tmp_path / "Camera")
    ids = {item["name"]: item["id"] for item in client.get("/pictures").json()["pictures"]}

    raw = client.get(f"/pictures/{ids['_MG_0042.CR3']}/view")
    broken = client.get(f"/pictures/{ids['Old pier.jpg']}/thumbnail")

    assert raw.status_code == 503  # on its way, not the picture's fault
    assert "RAW reader" in raw.json()["detail"]
    assert client.get(f"/pictures/{ids['_MG_0042.CR3']}").json()["state"] == "waiting"
    assert broken.status_code == 422
    assert "not a picture" in broken.json()["detail"]


def test_a_picture_gone_from_its_folder_says_so_rather_than_that_its_damaged(
    client: TestClient, library: Library, tmp_path: Path
):
    (tmp_path / "Phone" / "Snowfield.jpg").unlink()

    response = client.get(f"/pictures/{library['ids']['Snowfield.jpg']}/view")

    assert response.status_code == 404
    assert "isn't there any more" in response.json()["detail"]


def test_a_copy_that_cant_be_kept_says_why_and_reading_again_still_reads(
    client: TestClient, library: Library, monkeypatch: pytest.MonkeyPatch
):
    def full(*_: object, **__: object) -> None:
        raise OSError(errno.ENOSPC, "There is not enough space on the disk")

    monkeypatch.setattr("mado.previews.save_copy", full)
    picture = library["ids"]["Snowfield.jpg"]

    view = client.get(f"/pictures/{picture}/view")
    read = client.post(f"/pictures/{picture}/read")

    assert view.status_code == 503
    assert "not enough space" in view.json()["detail"]
    assert read.status_code == 200
    assert read.json()["problem"] is None


def test_a_heic_is_shown_through_ffmpeg(client: TestClient, tmp_path: Path):
    (tmp_path / "Phone").mkdir()
    item = exif_item(exif(taken="2026:11:12 18:42:07"))
    (tmp_path / "Phone" / "IMG_2041.HEIC").write_bytes(heif(width=64, height=48, exif=item))
    add(client, tmp_path / "Phone")
    [listed] = client.get("/pictures").json()["pictures"]

    thumbnail = client.get(f"/pictures/{listed['id']}/thumbnail")

    assert listed["format"] == "HEIC"
    assert thumbnail.status_code == 200
    assert picture_of(thumbnail).size == (64, 48)


def test_a_heic_without_ffmpeg_says_what_it_needs(paths: DataPaths, tmp_path: Path):
    (tmp_path / "Phone").mkdir()
    (tmp_path / "Phone" / "IMG_2041.HEIC").write_bytes(heif(width=64, height=48))
    app = create_app(TOKEN, paths, ffmpeg=lambda: None)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, tmp_path / "Phone")
        [listed] = client.get("/pictures").json()["pictures"]
        response = client.get(f"/pictures/{listed['id']}/thumbnail")

    assert response.status_code == 503
    assert "needs ffmpeg" in response.json()["detail"]


def test_reading_a_picture_again_picks_up_a_file_mended_since(client: TestClient, tmp_path: Path):
    path = tmp_path / "Phone" / "Old pier.jpg"
    path.parent.mkdir()
    path.write_text("half a picture", encoding="utf-8")
    add(client, tmp_path / "Phone")
    [listed] = client.get("/pictures").json()["pictures"]
    assert listed["state"] == "broken"
    draw(path)

    read = client.post(f"/pictures/{listed['id']}/read")

    assert read.status_code == 200
    mended = read.json()
    assert (mended["state"], mended["problem"], mended["format"]) == ("ready", None, "JPEG")
    assert (mended["size"], mended["version"]) != (listed["size"], listed["version"])
    assert client.get(f"/pictures/{listed['id']}/thumbnail").status_code == 200


def test_trying_again_a_picture_open_in_another_app_says_so_and_leaves_it_as_it_was(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draw(tmp_path / "Phone" / "Pier.jpg")
    add(client, tmp_path / "Phone")
    [listed] = client.get("/pictures").json()["pictures"]

    def in_use(path: Path, _kind: object, *_reader: object) -> object:
        raise InUseError(f"{path.name} is open in another app, so Mado can't read it.")

    monkeypatch.setattr("mado.api.pictures.read_facts", in_use)
    response = client.post(f"/pictures/{listed['id']}/read")

    assert response.status_code == 409
    assert "open in another app" in response.json()["detail"]
    after = client.get(f"/pictures/{listed['id']}").json()
    assert (after["state"], after["problem"]) == ("ready", None)
