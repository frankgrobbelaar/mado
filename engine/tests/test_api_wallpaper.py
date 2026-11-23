"""The wallpaper studio through the API, on a made-up desktop: the monitors, the picture each has
or one across all, each part made at exactly its monitor's pixels into Mado's folder, setting it
with the owner's own kept first, saving as pictures, putting back, and the small things."""

import io
import json
import shutil
import threading
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db, history, outside
from mado.api import create_app
from mado.config import DataPaths
from mado.core.wallpaper import key_of
from mado.desktop import FILL, SPAN, Slideshow
from mado.jobs import PARTIAL, Jobs
from mado.libraw import Reader
from mado.quarantine import Quarantine
from mado.wallpaper import Studio, StudioError
from tests.conftest import FFMPEG, ON_PROCESSOR, TOKEN, add, fake_check
from tests.dng_files import dng
from tests.drawn import draw, photo_like, scene
from tests.fake_desktop import SIDE, STUDIO, TALL, FakeDesktop


@pytest.fixture
def owner(tmp_path: Path) -> dict[str, Path]:
    """The owner's own wallpapers, a file for each monitor, in a folder of theirs."""
    return {
        "beach": draw(tmp_path / "Owner" / "Beach.jpg", size=(160, 90)),
        "dunes": draw(tmp_path / "Owner" / "Dunes.png", size=(120, 68)),
    }


@pytest.fixture
def desktop(owner: dict[str, Path]) -> FakeDesktop:
    return FakeDesktop(
        [STUDIO, SIDE], {STUDIO.id: str(owner["beach"]), SIDE.id: str(owner["dunes"])}
    )


def _studio_client(
    paths: DataPaths,
    quarantine: Quarantine,
    desktop: FakeDesktop,
    tmp_path: Path,
    reader: Reader | None = None,
) -> Iterator[TestClient]:
    app = create_app(
        TOKEN,
        paths,
        ffmpeg=lambda: FFMPEG,
        quarantine=quarantine,
        here=lambda: ON_PROCESSOR,
        check=fake_check,
        desktop=desktop,
        reader=reader or Reader(lambda: None),  # a camera RAW's reader, never fetched unasked
    )
    studio: Studio = app.state.wallpaper
    studio.themes = tmp_path / "Themes"  # Windows' own copy of what it shows, made up
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as test_client:
        yield test_client


@pytest.fixture
def client(
    paths: DataPaths, quarantine: Quarantine, desktop: FakeDesktop, tmp_path: Path
) -> Iterator[TestClient]:
    yield from _studio_client(paths, quarantine, desktop, tmp_path)


@pytest.fixture
def raw_studio(
    paths: DataPaths, quarantine: Quarantine, desktop: FakeDesktop, tmp_path: Path, reader: Reader
) -> Iterator[TestClient]:
    """The studio with an engine that reads camera RAW with LibRaw."""
    yield from _studio_client(paths, quarantine, desktop, tmp_path, reader)


def _library(
    client: TestClient, folder: Path, pictures: dict[str, tuple[int, int]]
) -> dict[str, int]:
    folder.mkdir(parents=True, exist_ok=True)
    for name, size in pictures.items():
        photo_like(size, seed=len(name)).save(folder / name)
    add(client, folder)
    listed = client.get("/pictures").json()["pictures"]
    return {item["name"]: item["id"] for item in listed}


def _studio(client: TestClient) -> dict[str, Any]:
    response = client.get("/wallpaper")
    assert response.status_code == 200, response.text
    return response.json()


def _choose(
    client: TestClient, picture: int, monitor: str | None = None, **more: Any
) -> dict[str, Any]:
    response = client.put(
        "/wallpaper/pictures", json={"monitor": monitor, "pictureId": picture, **more}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _done(client: TestClient) -> dict[str, Any]:
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    assert jobs.wait(120), "the wallpaper wasn't made in time"
    return _studio(client)


def test_the_studio_draws_the_monitors_as_windows_arranges_them(client: TestClient):
    found = _studio(client)

    assert found["desktop"] is True
    assert [(m["name"], m["width"], m["height"], m["main"]) for m in found["monitors"]] == [
        ("Studio 27", 160, 90, True),
        ("Side 24", 120, 68, False),
    ]
    studio = found["monitors"][0]
    assert studio["key"] == key_of(STUDIO.id)
    assert (studio["x"], studio["y"], studio["scale"], studio["rotation"]) == (0, 0, 1.0, 0)
    assert studio["shown"] is True
    assert studio["mine"] is False
    assert (found["layout"], found["gap"], found["width"], found["height"]) == ("each", 0, 280, 90)
    assert found["choices"] == []
    assert found["parts"] == []
    assert found["daily"]["on"] is False
    assert found["daily"]["next"] is None
    assert found["yours"]["kept"] == []


def test_a_monitors_own_wallpaper_is_shown_small_and_its_file_left_as_it_was(
    client: TestClient, owner: dict[str, Path]
):
    before = owner["beach"].read_bytes()

    response = client.get(f"/wallpaper/monitors/{key_of(STUDIO.id)}/wallpaper")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert owner["beach"].read_bytes() == before
    assert client.get("/wallpaper/monitors/nothing/wallpaper").status_code == 404


def test_a_picture_for_a_monitor_is_cut_with_its_shape_and_made_as_size_does(
    client: TestClient, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (64, 48)})

    found = _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))

    [choice] = found["choices"]
    assert (choice["monitor"], choice["shape"], choice["zoom"], choice["connected"]) == (
        key_of(STUDIO.id),
        "crop",
        1.0,
        True,
    )
    assert choice["picture"]["focus"] is not None
    [part] = found["parts"]
    assert (part["width"], part["height"], part["method"]) == (160, 90, "ai")
    assert part["area"]["width"] == pytest.approx(1.0)
    assert part["area"]["height"] == pytest.approx(64 * 90 / 160 / 48)
    assert part["scale"] == pytest.approx(2.5)
    assert part["warning"] is None


def test_a_camera_raw_makes_a_wallpaper_as_any_picture_does(
    raw_studio: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    dng(tmp_path / "Camera" / "Harbour at dusk.dng", scene(4, (320, 180)))
    add(raw_studio, tmp_path / "Camera")
    [listed] = raw_studio.get("/pictures").json()["pictures"]

    found = _choose(raw_studio, listed["id"], key_of(STUDIO.id))

    [choice] = found["choices"]
    assert choice["problem"] is None
    [part] = found["parts"]
    assert (part["width"], part["height"]) == (160, 90)
    raw_studio.post("/wallpaper/set")
    assert _done(raw_studio)["making"]["state"] == "set"
    assert len(desktop.sets) == 1


def test_a_picture_far_too_small_says_it_will_look_painted(client: TestClient, tmp_path: Path):
    ids = _library(client, tmp_path / "Phone", {"Tiny.png": (20, 12)})

    [part] = _choose(client, ids["Tiny.png"], key_of(STUDIO.id))["parts"]

    assert part["warning"] is not None
    assert "8 times bigger" in part["warning"]


def test_setting_makes_each_part_at_its_monitors_pixels_in_mados_folder_keeping_the_owners_own(
    client: TestClient,
    desktop: FakeDesktop,
    owner: dict[str, Path],
    paths: DataPaths,
    tmp_path: Path,
):
    ids = _library(
        client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480), "Little sail.jpg": (64, 48)}
    )
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    _choose(client, ids["Little sail.jpg"], key_of(SIDE.id))
    owners = {name: path.read_bytes() for name, path in owner.items()}

    asked = client.post("/wallpaper/set")
    assert asked.status_code == 200, asked.text
    found = _done(client)

    assert found["making"]["state"] == "set", found["making"]
    assert [monitor for monitor, _path in desktop.sets] == [STUDIO.id, SIDE.id]
    for monitor, path in desktop.sets:
        written = Path(path)
        assert written.is_relative_to(paths.root / "wallpapers" / "made")
        expected = (160, 90) if monitor == STUDIO.id else (120, 68)
        with Image.open(written) as image:
            assert (image.format, image.size, image.mode) == ("PNG", expected, "RGB")
    assert {name: path.read_bytes() for name, path in owner.items()} == owners  # untouched
    kept = found["yours"]["kept"]
    assert sorted((each["name"], each["path"], each["there"]) for each in kept) == [
        ("Side 24", str(owner["dunes"]), True),
        ("Studio 27", str(owner["beach"]), True),
    ]
    copies = list((paths.root / "wallpapers" / "yours").iterdir())
    assert len(copies) == 2
    assert {copy.read_bytes() for copy in copies} == set(owners.values())
    assert all(monitor["mine"] for monitor in found["monitors"])
    assert found["yours"]["showingMine"] is True


def test_one_across_all_lays_one_picture_over_both_with_a_gap_for_the_bezels(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Wide shore.jpg": (600, 180)})
    response = client.put("/wallpaper", json={"layout": "across", "gap": 20})
    assert response.status_code == 200, response.text

    found = _choose(client, ids["Wide shore.jpg"])

    assert (found["width"], found["height"]) == (300, 90)
    places = {m["name"]: m["place"] for m in found["monitors"]}
    assert places["Side 24"] == {"x": 180, "y": 0, "width": 120, "height": 68}
    parts = {part["monitor"]: part for part in found["parts"]}
    studio, side = parts[key_of(STUDIO.id)], parts[key_of(SIDE.id)]
    assert studio["area"]["x"] == pytest.approx(0)
    assert studio["area"]["width"] == pytest.approx(160 / 300)
    assert side["area"]["x"] == pytest.approx(180 / 300)
    assert side["area"]["height"] == pytest.approx(68 / 90)
    assert studio["scale"] == pytest.approx(side["scale"])

    client.post("/wallpaper/set")
    assert _done(client)["making"]["state"] == "set"
    assert len(desktop.sets) == 2


def test_a_spanned_desktop_is_laid_to_fill_for_mados_and_spanned_again_when_put_back(
    client: TestClient, desktop: FakeDesktop, owner: dict[str, Path], tmp_path: Path
):
    desktop.position_now = SPAN
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))

    client.post("/wallpaper/set")
    _done(client)
    assert desktop.positions == [FILL]

    put = client.post("/wallpaper/put-back", json={})
    assert put.status_code == 200, put.text
    assert desktop.positions == [FILL, SPAN]
    assert desktop.papers[STUDIO.id] == str(owner["beach"])


def test_putting_back_gives_each_monitor_its_own_file_or_mados_copy_and_stops_the_daily_change(
    client: TestClient, desktop: FakeDesktop, owner: dict[str, Path], tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    for monitor in (STUDIO, SIDE):
        _choose(client, ids["Harbour at dusk.jpg"], key_of(monitor.id))
    client.post("/wallpaper/set")
    _done(client)
    client.put("/wallpaper/daily", json={"on": True, "at": "07:00"})
    owner["dunes"].unlink()  # the owner deleted their own file since: only Mado's copy has it

    put = client.post("/wallpaper/put-back", json={}).json()

    assert desktop.papers[STUDIO.id] == str(owner["beach"])
    side = Path(desktop.papers[SIDE.id] or "")
    assert side.parent.name == "yours"
    assert side.is_file()
    assert put["told"] == []
    assert put["studio"]["daily"]["on"] is False
    assert put["studio"]["yours"]["showingMine"] is False


def test_one_monitor_is_put_back_on_its_own(
    client: TestClient, desktop: FakeDesktop, owner: dict[str, Path], tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    for monitor in (STUDIO, SIDE):
        _choose(client, ids["Harbour at dusk.jpg"], key_of(monitor.id))
    client.post("/wallpaper/set")
    _done(client)
    made_side = desktop.papers[SIDE.id]

    client.post("/wallpaper/put-back", json={"monitor": key_of(STUDIO.id)})

    assert desktop.papers[STUDIO.id] == str(owner["beach"])
    assert desktop.papers[SIDE.id] == made_side


def test_windows_slideshow_is_told_of_kept_and_started_again_on_putting_back(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    slides = Slideshow(str(tmp_path / "Slides"), 600_000, True)
    desktop.slides = slides
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    assert _studio(client)["slideshow"] is True

    client.post("/wallpaper/set")
    found = _done(client)
    assert found["slideshow"] is False
    assert found["yours"]["slideshow"] is True

    client.post("/wallpaper/put-back", json={})
    assert desktop.started == [slides]


def test_spotlight_is_told_of_and_putting_back_says_how_to_have_it_again(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    desktop.spot = True
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    assert _studio(client)["spotlight"] is True
    client.post("/wallpaper/set")
    _done(client)

    told = client.post("/wallpaper/put-back", json={}).json()["told"]

    assert any("Windows spotlight" in each and "Personalisation" in each for each in told)


def test_saving_writes_each_part_as_a_new_picture_into_the_folder_picked_with_history(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    for monitor in (STUDIO, SIDE):
        _choose(client, ids["Harbour at dusk.jpg"], key_of(monitor.id))
    into = tmp_path / "Wallpapers"
    into.mkdir()

    saving = {"what": "parts", "folder": str(into), "format": "PNG"}
    asked = client.post("/wallpaper/save", json=saving)
    assert asked.status_code == 200, asked.text
    found = _done(client)

    assert found["making"]["state"] == "saved", found["making"]
    assert sorted(each.name for each in into.iterdir()) == [
        "Harbour at dusk (Side 24 wallpaper).png",
        "Harbour at dusk (Studio 27 wallpaper).png",
    ]
    with Image.open(into / "Harbour at dusk (Side 24 wallpaper).png") as image:
        assert image.size == (120, 68)
    lines = client.get("/history").json()["entries"]
    assert sorted(line["madeFor"] for line in lines) == [
        "a wallpaper on Side 24",
        "a wallpaper on Studio 27",
    ]
    assert not list(paths.root.glob("wallpapers/yours/*"))  # nothing set, nothing kept


def test_saving_the_whole_arrangement_writes_one_picture_its_size(
    client: TestClient, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Wide shore.jpg": (600, 180)})
    client.put("/wallpaper", json={"layout": "across", "gap": 20})
    _choose(client, ids["Wide shore.jpg"])
    into = tmp_path / "Wallpapers"
    into.mkdir()

    client.post("/wallpaper/save", json={"what": "whole", "folder": str(into), "format": "JPEG"})
    assert _done(client)["making"]["state"] == "saved"

    [saved] = list(into.iterdir())
    assert saved.name == "Wide shore (All monitors wallpaper).jpg"
    with Image.open(saved) as image:
        assert (image.format, image.size) == ("JPEG", (300, 90))


def test_a_monitor_unplugged_keeps_its_picture_for_when_its_back_and_isnt_set(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    for monitor in (STUDIO, SIDE):
        _choose(client, ids["Harbour at dusk.jpg"], key_of(monitor.id))

    desktop.shown = [STUDIO]  # unplugged
    found = _studio(client)

    assert [m["name"] for m in found["monitors"]] == ["Studio 27"]
    connected = {choice["monitor"]: choice["connected"] for choice in found["choices"]}
    assert connected == {key_of(STUDIO.id): True, key_of(SIDE.id): False}
    assert [part["monitor"] for part in found["parts"]] == [key_of(STUDIO.id)]
    client.post("/wallpaper/set")
    _done(client)
    assert [monitor for monitor, _path in desktop.sets] == [STUDIO.id]

    desktop.shown = [STUDIO, SIDE]  # and back
    assert len(_studio(client)["parts"]) == 2


def test_a_portrait_monitor_is_drawn_tall_and_its_part_cut_tall(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    desktop.shown = [STUDIO, TALL]
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})

    found = _choose(client, ids["Harbour at dusk.jpg"], key_of(TALL.id))

    tall = next(m for m in found["monitors"] if m["name"] == "Panel 24")
    assert (tall["width"], tall["height"], tall["rotation"]) == (68, 120, 90)
    [part] = found["parts"]
    assert part["area"]["height"] == pytest.approx(1.0)
    assert part["area"]["width"] * 640 / (part["area"]["height"] * 480) == pytest.approx(68 / 120)


def test_an_outside_picture_and_a_pasted_one_can_be_wallpapers(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    pier = draw(tmp_path / "Elsewhere" / "Pier at dawn.jpg", size=(320, 180))
    opened = client.post("/open", json={"paths": [str(pier)], "how": "opened"}).json()
    _choose(client, opened["picture"]["id"], key_of(STUDIO.id))
    written = io.BytesIO()
    photo_like((240, 136)).save(written, format="PNG")
    headers = {"Content-Type": "image/png"}
    pasted = client.post("/pasted", content=written.getvalue(), headers=headers)
    _choose(client, pasted.json()["id"], key_of(SIDE.id))

    client.post("/wallpaper/set")
    assert _done(client)["making"]["state"] == "set"
    assert len(desktop.sets) == 2


def test_nothing_chosen_or_a_picture_gone_is_said_in_words(client: TestClient):
    nothing = client.post("/wallpaper/set")
    assert nothing.status_code == 409
    assert "Pick a picture first" in nothing.json()["detail"]

    gone = client.put("/wallpaper/pictures", json={"monitor": None, "pictureId": 404})
    assert gone.status_code == 404


def test_windows_refusing_says_why_and_changes_nothing(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    desktop.refuse = "Windows wouldn't set the wallpaper."
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))

    client.post("/wallpaper/set")
    making = _done(client)["making"]

    assert making["state"] == "failed"
    assert making["problem"].startswith(desktop.refuse)
    assert "Your wallpaper is as it was" in making["problem"]
    assert desktop.sets == []


# The small things a wallpaper being made can meet.


def test_monitors_changed_while_it_was_made_it_isnt_set_and_says_so(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    app: Any = client.app
    studio: Studio = app.state.wallpaper
    desktop.then, desktop.reads = [replace(STUDIO, width=192, height=108), SIDE], 1  # resized

    with closing(db.connect(paths.database)) as conn:
        studio.ask(conn, "set")
    making = _done(client)["making"]

    assert making["state"] == "failed"
    assert "Your monitors changed" in making["problem"]
    assert desktop.sets == []


# The daily change.


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute).astimezone()


class Clock:
    """The studio's clock, the test's to move."""

    def __init__(self, client: TestClient) -> None:
        app: Any = client.app
        self.studio: Studio = app.state.wallpaper
        self.now = _at(22, 10)
        self.studio.now = lambda: self.now

    def tick(self, client: TestClient, moment: datetime) -> dict[str, Any]:
        self.now = moment
        self.studio.tick()
        return _done(client)


def _favourites(
    client: TestClient, folder: Path, sizes: dict[str, tuple[int, int]]
) -> dict[str, int]:
    ids = _library(client, folder, sizes)
    for name in sizes:
        response = client.put(f"/pictures/{ids[name]}/favourite", json={"favourite": True})
        assert response.status_code == 200, response.text
    return ids


def _daily(client: TestClient, **choices: Any) -> dict[str, Any]:
    response = client.put("/wallpaper/daily", json={"on": True, "at": "07:00", **choices})
    assert response.status_code == 200, response.text
    return response.json()


def _shown_on(paths: DataPaths) -> list[dict[str, int]]:
    """Each daily change set: which picture went on which monitor."""
    with closing(db.connect(paths.database)) as conn:
        rows = conn.execute(
            "SELECT plan FROM wallpapers WHERE purpose = 'daily' AND state = 'set' ORDER BY id"
        ).fetchall()
    return [
        {each["monitor"]: each["picture"] for each in json.loads(row["plan"])["choices"]}
        for row in rows
    ]


def test_the_daily_change_is_off_till_its_turned_on(client: TestClient, desktop: FakeDesktop):
    clock = Clock(client)

    found = clock.tick(client, _at(23, 7, 30))

    assert found["daily"]["on"] is False
    assert desktop.sets == []


def test_turned_on_after_its_time_it_first_changes_the_next_morning(client: TestClient):
    Clock(client)  # 10:00 on the 22nd

    found = _daily(client)

    assert found["daily"]["next"].startswith("2026-11-23T07:00")


def test_the_days_pictures_are_made_the_evening_before_and_set_at_seven_in_a_moment(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480), "Dunes.jpg": (640, 480)})
    _daily(client)

    evening = clock.tick(client, _at(22, 19, 30))
    assert evening["daily"]["ready"] is True
    assert desktop.sets == []  # made, not set

    morning = clock.tick(client, _at(23, 7, 0))

    assert sorted(monitor for monitor, _path in desktop.sets) == sorted([STUDIO.id, SIDE.id])
    assert morning["daily"]["changedOn"] == "2026-11-23"
    assert morning["daily"]["next"].startswith("2026-11-24T07:00")
    [shown] = _shown_on(paths)
    assert len(set(shown.values())) == 2  # a picture each, none twice


def test_mado_closed_at_the_change_time_changes_at_its_next_start(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480)})
    _daily(client)

    clock.tick(client, _at(23, 9, 15))  # Mado started at a quarter past nine

    assert {monitor for monitor, _path in desktop.sets} == {STUDIO.id, SIDE.id}


def test_each_monitor_gets_a_favourite_that_suits_its_way_round(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    desktop.shown = [STUDIO, TALL]
    clock = Clock(client)
    ids = _favourites(client, tmp_path / "Phone", {"Wide.jpg": (640, 360), "Tall.jpg": (360, 640)})
    _daily(client)

    clock.tick(client, _at(23, 7, 1))

    [shown] = _shown_on(paths)
    assert shown == {STUDIO.id: ids["Wide.jpg"], TALL.id: ids["Tall.jpg"]}


def test_no_favourites_yet_says_so_and_leaves_the_wallpaper_as_it_was(
    client: TestClient, desktop: FakeDesktop
):
    clock = Clock(client)
    _daily(client)

    found = clock.tick(client, _at(23, 7, 1))
    again = clock.tick(client, _at(23, 7, 2))

    assert "No favourites yet" in found["daily"]["problem"]
    assert again["daily"]["problem"] == found["daily"]["problem"]
    assert desktop.sets == []


def test_a_picture_isnt_shown_again_till_every_one_has_been(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    desktop.shown = [STUDIO]
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {f"Shore {n}.jpg": (640, 360) for n in range(1, 4)})
    _daily(client)

    for day in (23, 24, 25, 26):
        clock.tick(client, _at(day, 7, 1))

    shown = [each[STUDIO.id] for each in _shown_on(paths)]
    assert len(set(shown[:3])) == 3
    assert shown[3] == shown[0]


def test_monitors_changed_after_the_days_wallpaper_was_made_it_is_made_again(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480), "Dunes.jpg": (640, 480)})
    _daily(client)
    assert clock.tick(client, _at(22, 20, 0))["daily"]["ready"] is True

    desktop.shown = [STUDIO]  # unplugged overnight
    clock.tick(client, _at(23, 7, 0))

    assert [monitor for monitor, _path in desktop.sets] == [STUDIO.id]


def test_turning_the_daily_change_off_lets_what_was_made_ahead_go(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480)})
    _daily(client)
    clock.tick(client, _at(22, 20, 0))
    made = list((paths.root / "wallpapers" / "made").iterdir())
    assert made

    client.put("/wallpaper/daily", json={"on": False})
    found = clock.tick(client, _at(23, 0, 5))  # a new day's first look tidies

    assert found["daily"]["ready"] is False
    assert not any(each.exists() for each in made)


def test_only_mados_own_older_wallpapers_go_those_showing_and_the_last_three_days_stay(
    client: TestClient,
    desktop: FakeDesktop,
    owner: dict[str, Path],
    paths: DataPaths,
    tmp_path: Path,
):
    desktop.shown = [STUDIO]
    clock = Clock(client)
    ids = _library(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480), "Dunes.jpg": (640, 480)})
    made_on: list[Path] = []
    for day, name in (
        (14, "Harbour.jpg"),
        (15, "Dunes.jpg"),
        (21, "Harbour.jpg"),
        (22, "Dunes.jpg"),
    ):
        clock.now = _at(day, 12)
        _choose(client, ids[name], key_of(STUDIO.id))
        client.post("/wallpaper/set")
        _done(client)
        made_on.append(Path(desktop.sets[-1][1]).parent)

    with closing(db.connect(paths.database)) as conn:
        clock.studio.tidy(conn, _at(22, 13))

    assert [folder.exists() for folder in made_on] == [False, False, True, True]
    assert all(path.exists() for path in owner.values())
    assert list((paths.root / "wallpapers" / "yours").iterdir())


def test_a_monitor_showing_a_colour_keeps_no_copy_and_gets_its_colour_back(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    desktop.papers[SIDE.id] = None  # a colour, no picture
    (tmp_path / "Themes").mkdir()
    draw(tmp_path / "Themes" / "TranscodedWallpaper", size=(120, 68), format="JPEG")  # stale
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(SIDE.id))
    client.post("/wallpaper/set")
    _done(client)

    kept = {each["name"]: each for each in _studio(client)["yours"]["kept"]}
    assert kept["Side 24"]["path"] is None
    copies = list((paths.root / "wallpapers" / "yours").iterdir())
    assert len(copies) == 1  # the other monitor's picture only

    client.post("/wallpaper/put-back", json={})
    assert desktop.papers[SIDE.id] is None
    assert (SIDE.id, "") in desktop.sets


def test_favourites_on_a_drive_that_isnt_connected_are_skipped(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Here.jpg": (640, 360)})
    client.put(f"/pictures/{ids['Here.jpg']}/favourite", json={"favourite": True})
    with closing(db.connect(paths.database)) as conn, conn:
        away = conn.execute(
            """INSERT INTO pictures (path, dir, name, size, modified, found_at, seen_at, read_at,
                                     format, width, height, taken_at, taken_from, opened_at)
               VALUES (?, '', 'Away.jpg', 10, 1, 'x', 'x', 'x', 'JPEG', 640, 360, 'x', 'file', ?)
               RETURNING id""",
            (r"Q:\Nowhere at all\Away.jpg", datetime.now().astimezone().isoformat()),
        ).fetchone()[0]
        conn.execute("INSERT INTO favourites (picture_id, at) VALUES (?, 'x')", (away,))

    daily = _studio(client)["daily"]

    assert (daily["candidates"], daily["skipped"]) == (1, 1)


def test_putting_back_leaves_a_fit_the_owner_chose_since_mado_set_its_own(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    desktop.position_now = SPAN
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    client.post("/wallpaper/set")
    _done(client)
    desktop.position_now = 3  # the owner chose "fit" in Windows since

    client.post("/wallpaper/put-back", json={})

    assert desktop.positions == [FILL]  # Mado's fill, and nothing after it
    assert desktop.position_now == 3


# What the review found.


def _rows(paths: DataPaths) -> list[tuple[str, str | None, str]]:
    """Every wallpaper asked for: its purpose, its day and its state."""
    with closing(db.connect(paths.database)) as conn:
        return [
            (row["purpose"], row["day"], row["state"])
            for row in conn.execute("SELECT * FROM wallpapers ORDER BY id")
        ]


def _breaking(monkeypatch: pytest.MonkeyPatch, error: Exception) -> Callable[[bool], None]:
    """Making every part fails with `error` till it's told otherwise."""
    making = Studio._part_image  # pyright: ignore[reportPrivateUsage]
    broken = {"now": True}

    def part_image(self: Studio, *given: Any) -> Image.Image:
        if broken["now"]:
            raise error
        return making(self, *given)

    monkeypatch.setattr(Studio, "_part_image", part_image)

    def told(now: bool) -> None:
        broken["now"] = now

    return told


def test_a_days_wallpaper_failing_ahead_leaves_tonights_alone_and_is_tried_again_at_its_time(
    client: TestClient,
    desktop: FakeDesktop,
    paths: DataPaths,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    desktop.shown = [STUDIO]
    clock = Clock(client)  # 10:00 on the 22nd
    _favourites(client, tmp_path / "Phone", {f"Shore {n}.jpg": (640, 360) for n in range(1, 4)})
    _daily(client)  # turned on after 07:00: its first change is the 23rd's
    breaking = _breaking(monkeypatch, StudioError("The drive Mado's data folder is on is full."))

    for minute in range(30, 34):
        clock.tick(client, _at(22, 19, minute))

    assert desktop.sets == []  # tonight's wallpaper left as it was
    assert _rows(paths) == [("daily", "2026-11-23", "failed")]  # asked for once, not every look
    breaking(False)
    morning = clock.tick(client, _at(23, 7, 0))
    assert [monitor for monitor, _path in desktop.sets] == [STUDIO.id]
    assert morning["daily"]["changedOn"] == "2026-11-23"
    assert morning["daily"]["problem"] is None


def test_a_days_wallpaper_failing_inside_mado_is_tried_once_more_at_its_time_and_no_more(
    client: TestClient,
    desktop: FakeDesktop,
    paths: DataPaths,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    desktop.shown = [STUDIO]
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {f"Shore {n}.jpg": (640, 360) for n in range(1, 4)})
    _daily(client)
    _breaking(monkeypatch, RuntimeError("a fault inside Mado"))

    for minute in range(30, 36):
        clock.tick(client, _at(22, 19, minute))
    assert len(_rows(paths)) == 1
    morning = clock.tick(client, _at(23, 7, 0))
    clock.tick(client, _at(23, 7, 1))

    assert len(_rows(paths)) == 2  # once more at its time, then not till the next day
    assert "inside Mado" in morning["daily"]["problem"]
    assert desktop.sets == []


def test_setting_again_keeps_how_windows_showed_the_owners_own_the_first_time(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    slides = Slideshow(str(tmp_path / "Slides"), 60000, True)
    desktop.position_now = SPAN
    desktop.slides = slides
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))  # the side keeps the owner's
    for _again in range(2):
        client.post("/wallpaper/set")
        _done(client)

    client.post("/wallpaper/put-back", json={})

    assert desktop.started == [slides]
    assert desktop.position_now == SPAN


def test_a_wallpaper_a_monitor_still_shows_is_kept_however_old(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    clock = Clock(client)
    ids = _library(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480), "Dunes.jpg": (640, 480)})
    clock.now = _at(14, 12)
    _choose(client, ids["Harbour.jpg"], key_of(STUDIO.id))
    _choose(client, ids["Dunes.jpg"], key_of(SIDE.id))
    client.post("/wallpaper/set")
    _done(client)
    side_shows = Path(desktop.papers[SIDE.id] or "")
    clock.now = _at(15, 12)  # the next day, a picture for the main monitor alone
    client.delete("/wallpaper/pictures", params={"monitor": key_of(SIDE.id)})
    _choose(client, ids["Dunes.jpg"], key_of(STUDIO.id))
    client.post("/wallpaper/set")
    _done(client)
    assert desktop.papers[SIDE.id] == str(side_shows)

    with closing(db.connect(paths.database)) as conn:
        clock.studio.tidy(conn, _at(22, 13))

    assert side_shows.is_file()


def test_a_days_wallpaper_never_set_goes_once_its_day_has_passed(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    desktop.shown = [STUDIO]
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {f"Shore {n}.jpg": (640, 360) for n in range(1, 4)})
    _daily(client)
    clock.tick(client, _at(22, 19, 30))  # made ahead for the 23rd
    [made] = list((paths.root / "wallpapers" / "made").iterdir())

    clock.tick(client, _at(25, 8, 0))  # Mado closed from that evening till the 25th

    assert not made.exists()
    assert [(day, state) for _purpose, day, state in _rows(paths)] == [
        ("2026-11-23", "cancelled"),
        ("2026-11-25", "set"),
    ]


def test_turning_the_daily_change_off_while_its_wallpaper_is_made_lets_it_go(
    client: TestClient,
    desktop: FakeDesktop,
    paths: DataPaths,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480)})
    _daily(client)
    started, carry_on = threading.Event(), threading.Event()
    making = Studio._part_image  # pyright: ignore[reportPrivateUsage]

    def held(self: Studio, *given: Any) -> Image.Image:
        started.set()
        carry_on.wait(10)
        return making(self, *given)

    monkeypatch.setattr(Studio, "_part_image", held)
    clock.now = _at(22, 19, 30)
    clock.studio.tick()  # the 23rd's, made ahead
    assert started.wait(10)

    client.put("/wallpaper/daily", json={"on": False})
    carry_on.set()
    found = _done(client)

    assert found["daily"]["ready"] is False
    assert [state for _purpose, _day, state in _rows(paths)] == ["cancelled"]
    assert list((paths.root / "wallpapers" / "made").iterdir()) == []
    assert desktop.sets == []


def test_a_wallpaper_made_ahead_whose_files_went_is_made_again_at_its_time(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    desktop.shown = [STUDIO]
    clock = Clock(client)
    _favourites(client, tmp_path / "Phone", {f"Shore {n}.jpg": (640, 360) for n in range(1, 4)})
    _daily(client)
    clock.tick(client, _at(22, 19, 30))
    shutil.rmtree(paths.root / "wallpapers" / "made")

    clock.tick(client, _at(23, 7, 0))

    assert [monitor for monitor, _path in desktop.sets] == [STUDIO.id]
    assert [state for _purpose, _day, state in _rows(paths)] == ["cancelled", "set"]


def test_a_time_typed_through_an_earlier_one_keeps_todays_change(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    desktop.shown = [STUDIO]
    clock = Clock(client)
    clock.now = _at(22, 6, 0)
    _favourites(client, tmp_path / "Phone", {f"Shore {n}.jpg": (640, 360) for n in range(1, 4)})
    _daily(client)  # 07:00: today's change still to come
    for typed in ("00:00", "08:00"):  # typing 08:00, its hours pass through 00 first
        client.put("/wallpaper/daily", json={"on": True, "at": typed})

    assert _studio(client)["daily"]["next"].startswith("2026-11-22T08:00")
    clock.tick(client, _at(22, 8, 1))
    assert [monitor for monitor, _path in desktop.sets] == [STUDIO.id]


def test_a_time_set_once_its_passed_today_first_changes_the_next_day(client: TestClient):
    clock = Clock(client)
    clock.now = _at(22, 6, 30)
    _daily(client)  # 07:00, still to come today
    response = client.put("/wallpaper/daily", json={"on": True, "at": "06:00"})

    assert response.json()["daily"]["next"].startswith("2026-11-23T06:00")


def test_a_save_cut_short_clears_its_half_written_picture_and_its_line_in_history(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    clock = Clock(client)
    folder = tmp_path / "Wallpapers"
    landed = draw(folder / "Harbour (Studio 27 wallpaper).png", size=(160, 90))
    target = folder / "Harbour (Side 24 wallpaper).png"
    partial = target.with_name(target.name + PARTIAL)
    partial.write_bytes(b"half written")
    with closing(db.connect(paths.database)) as conn:
        line = history.made(
            conn,
            now=clock.now,
            job_id=None,
            name="Harbour.jpg",
            made_for="a wallpaper on Side 24",
            original=tmp_path / "Harbour.jpg",
            result=target,
        )
        plan = {"saving": {"what": "parts"}, "saved": [str(landed)], "writing": str(partial)}
        with conn:
            conn.execute(
                """INSERT INTO wallpapers (asked_at, purpose, arrangement, plan, state)
                   VALUES ('2026-11-22T10:00:00', 'save', '', ?, 'making')""",
                (json.dumps(plan),),
            )

        clock.studio.recover(conn)

        row = conn.execute("SELECT * FROM wallpapers").fetchone()
        assert row["state"] == "failed"
        assert "closed" in row["problem"]
        assert json.loads(row["plan"])["saved"] == [str(landed)]
        assert history.entry(conn, line) is None
    assert not partial.exists()
    assert landed.is_file()


def test_saving_notes_what_it_writes_and_lets_it_go_once_each_picture_is_in_place(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))

    client.post("/wallpaper/save", json={"what": "parts", "folder": str(tmp_path / "Saved")})
    _done(client)

    with closing(db.connect(paths.database)) as conn:
        plan = json.loads(conn.execute("SELECT plan FROM wallpapers").fetchone()["plan"])
    assert "writing" not in plan
    assert len(plan["saved"]) == 1


def test_a_set_or_save_cut_short_isnt_finished_at_the_next_start_but_a_days_change_is(
    client: TestClient, paths: DataPaths
):
    clock = Clock(client)  # the 22nd
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    jobs.stop()  # the queue's worker held: what's put back waits, rather than made at once
    with closing(db.connect(paths.database)) as conn:
        with conn:
            for purpose, day, state in (
                ("set", None, "making"),
                ("save", None, "waiting"),
                ("daily", "2026-11-23", "making"),
                ("daily", "2026-11-21", "ready"),
            ):
                conn.execute(
                    """INSERT INTO wallpapers (asked_at, purpose, day, arrangement, plan, state)
                       VALUES ('2026-11-22T10:00:00', ?, ?, '', '{}', ?)""",
                    (purpose, day, state),
                )

        clock.studio.recover(conn)

        rows = conn.execute("SELECT purpose, state, problem FROM wallpapers ORDER BY id").fetchall()
    assert [(row["purpose"], row["state"]) for row in rows] == [
        ("set", "failed"),
        ("save", "failed"),
        ("daily", "waiting"),
        ("daily", "cancelled"),
    ]
    assert "closed" in rows[0]["problem"]
    assert "closed" in rows[1]["problem"]


def test_putting_back_carries_on_past_a_monitor_windows_refuses_and_says_which(
    client: TestClient, desktop: FakeDesktop, owner: dict[str, Path], tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    _choose(client, ids["Harbour at dusk.jpg"], key_of(SIDE.id))
    _daily(client)
    client.post("/wallpaper/set")
    _done(client)
    desktop.refuse_on = {STUDIO.id}

    back = client.post("/wallpaper/put-back", json={})

    assert back.status_code == 200, back.text
    assert desktop.papers[SIDE.id] == str(owner["dunes"])
    told = back.json()["told"]
    assert any("Studio 27" in each for each in told)
    assert back.json()["studio"]["daily"]["on"] is False


def test_putting_back_every_monitor_leaves_one_the_owner_gave_a_wallpaper_of_their_own_since(
    client: TestClient, desktop: FakeDesktop, owner: dict[str, Path], tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    _choose(client, ids["Harbour at dusk.jpg"], key_of(SIDE.id))
    client.post("/wallpaper/set")
    _done(client)
    since = draw(tmp_path / "Owner" / "Meadow.jpg", size=(120, 68))
    desktop.papers[SIDE.id] = str(since)  # chosen in Windows since

    client.post("/wallpaper/put-back", json={})

    assert desktop.papers[STUDIO.id] == str(owner["beach"])
    assert desktop.papers[SIDE.id] == str(since)


def test_a_set_windows_refuses_leaves_a_spanned_desktop_spanned(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    desktop.position_now = SPAN
    desktop.refuse_on = {STUDIO.id}
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))

    client.post("/wallpaper/set")
    found = _done(client)

    assert found["making"]["state"] == "failed"
    assert "as it was" in found["making"]["problem"]
    assert desktop.position_now == SPAN


def test_the_studio_counts_the_daily_changes_pictures_from_mados_records_and_the_pick_looks(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    desktop.shown = [STUDIO]
    clock = Clock(client)
    ids = _favourites(client, tmp_path / "Phone", {"Here.jpg": (640, 360), "Gone.jpg": (640, 360)})
    (tmp_path / "Phone" / "Gone.jpg").unlink()  # gone, and no scan has looked yet

    found = _daily(client)

    assert (found["daily"]["candidates"], found["daily"]["skipped"]) == (2, 0)
    clock.tick(client, _at(23, 7, 1))
    assert _shown_on(paths) == [{STUDIO.id: ids["Here.jpg"]}]


def test_with_a_picture_of_its_own_on_each_monitor_windows_copy_isnt_taken_for_a_file_gone(
    client: TestClient, owner: dict[str, Path], tmp_path: Path
):
    (tmp_path / "Themes").mkdir()
    draw(tmp_path / "Themes" / "TranscodedWallpaper", size=(120, 68), format="JPEG")
    owner["beach"].unlink()  # the main monitor's own file went; the side shows another
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))

    client.post("/wallpaper/set")
    _done(client)

    kept = {each["name"]: each for each in _studio(client)["yours"]["kept"]}
    assert kept["Studio 27"]["there"] is False


def test_one_picture_on_every_monitor_whose_file_went_is_kept_from_windows_own_copy(
    client: TestClient, desktop: FakeDesktop, owner: dict[str, Path], tmp_path: Path
):
    desktop.papers = {STUDIO.id: str(owner["beach"]), SIDE.id: str(owner["beach"])}
    (tmp_path / "Themes").mkdir()
    draw(tmp_path / "Themes" / "TranscodedWallpaper", size=(160, 90), format="JPEG")
    owner["beach"].unlink()
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))

    client.post("/wallpaper/set")
    _done(client)

    kept = {each["name"]: each for each in _studio(client)["yours"]["kept"]}
    assert kept["Studio 27"]["there"] is True


def test_a_picture_mado_cant_read_says_so_rather_than_waiting(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Phone"
    folder.mkdir()
    (folder / "Broken.jpg").write_bytes(b"not a picture at all")
    add(client, folder)
    [item] = client.get("/pictures").json()["pictures"]

    found = _choose(client, item["id"], key_of(STUDIO.id))

    [choice] = found["choices"]
    assert choice["problem"]
    assert found["parts"] == []
    answer = client.post("/wallpaper/set")
    assert answer.status_code == 409
    assert answer.json()["detail"] == choice["problem"]


def test_the_daily_changes_folder_taken_out_of_the_library_turns_it_off_and_says_why(
    client: TestClient, tmp_path: Path
):
    _library(client, tmp_path / "Phone", {"Harbour.jpg": (640, 480)})
    [folder] = client.get("/folders").json()
    _daily(client, folder=folder["id"])

    client.delete(f"/folders/{folder['id']}")

    daily = _studio(client)["daily"]
    assert daily["on"] is False
    assert "taken out of the library" in daily["problem"]


def test_a_wallpaper_being_made_can_be_stopped_and_says_how_long_it_has_left(
    client: TestClient,
    desktop: FakeDesktop,
    paths: DataPaths,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    started, carry_on = threading.Event(), threading.Event()
    making = Studio._part_image  # pyright: ignore[reportPrivateUsage]

    def held(self: Studio, *given: Any) -> Image.Image:
        started.set()
        carry_on.wait(10)
        return making(self, *given)

    monkeypatch.setattr(Studio, "_part_image", held)
    client.post("/wallpaper/set")
    assert started.wait(10)
    assert "secondsLeft" in _studio(client)["making"]

    stopped = client.post("/wallpaper/cancel")
    carry_on.set()
    found = _done(client)

    assert stopped.status_code == 200, stopped.text
    assert found["making"]["state"] == "cancelled"
    assert desktop.sets == []
    assert list((paths.root / "wallpapers" / "made").iterdir()) == []


def test_putting_every_monitor_back_lets_the_record_of_windows_slideshow_go(
    client: TestClient, desktop: FakeDesktop, tmp_path: Path
):
    desktop.slides = Slideshow(str(tmp_path / "Slides"), 60000, True)
    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    client.post("/wallpaper/set")
    _done(client)

    back = client.post("/wallpaper/put-back", json={}).json()

    assert back["studio"]["yours"]["slideshow"] is False


def test_the_gap_for_the_bezels_is_one_across_alls_only(client: TestClient, tmp_path: Path):
    each = client.put("/wallpaper", json={"layout": "each", "gap": 40}).json()
    across = client.put("/wallpaper", json={"layout": "across", "gap": 40}).json()

    assert (each["width"], across["width"]) == (280, 320)


def test_saving_one_across_all_as_one_picture_makes_it_once(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone", {"Wide harbour.jpg": (1280, 400)})
    client.put("/wallpaper", json={"layout": "across", "gap": 0})
    _choose(client, ids["Wide harbour.jpg"])

    client.post("/wallpaper/save", json={"what": "whole", "folder": str(tmp_path / "Saved")})
    _done(client)

    [made] = list((paths.root / "wallpapers" / "made").iterdir())
    assert [each.name for each in made.iterdir()] == ["all.png"]


def test_a_monitors_wallpaper_shown_small_keeps_one_copy_for_it(
    client: TestClient, desktop: FakeDesktop, paths: DataPaths, tmp_path: Path
):
    address = f"/wallpaper/monitors/{key_of(STUDIO.id)}/wallpaper"
    assert client.get(address).status_code == 200
    desktop.papers[STUDIO.id] = str(draw(tmp_path / "Owner" / "Meadow.jpg", size=(160, 90)))

    assert client.get(address).status_code == 200

    copies = list((paths.cache / "wallpapers").glob(f"{key_of(STUDIO.id)}-*.webp"))
    assert len(copies) == 1


def test_a_copy_of_the_owners_own_that_failed_is_made_the_next_time(
    client: TestClient, paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    copying = shutil.copyfile
    failing = {"now": True}

    def copyfile(source: Any, target: Any) -> Any:
        if failing["now"]:
            raise OSError("the drive was busy")
        return copying(source, target)

    ids = _library(client, tmp_path / "Phone", {"Harbour at dusk.jpg": (640, 480)})
    _choose(client, ids["Harbour at dusk.jpg"], key_of(STUDIO.id))
    monkeypatch.setattr(shutil, "copyfile", copyfile)
    client.post("/wallpaper/set")
    _done(client)
    assert not (paths.root / "wallpapers" / "yours").exists() or not list(
        (paths.root / "wallpapers" / "yours").iterdir()
    )
    failing["now"] = False

    client.post("/wallpaper/set")
    _done(client)

    assert len(list((paths.root / "wallpapers" / "yours").iterdir())) == 2


def test_tidying_leaves_a_wallpaper_asked_for_while_it_looked(client: TestClient, paths: DataPaths):
    clock = Clock(client)
    made = paths.root / "wallpapers" / "made" / "7"
    draw(made / "1 abcdefghij.png", size=(16, 9))  # being made; its record came after the look

    with closing(db.connect(paths.database)) as conn:
        clock.studio.tidy(conn, _at(22, 13))

    assert (made / "1 abcdefghij.png").is_file()


def test_a_picture_from_outside_chosen_in_the_studio_isnt_forgotten(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    pier = draw(tmp_path / "Elsewhere" / "Pier at dawn.jpg", size=(640, 480))
    picture = client.post("/open", json={"paths": [str(pier)], "how": "opened"}).json()["picture"]
    _choose(client, picture["id"], key_of(STUDIO.id))

    later = datetime.now().astimezone() + timedelta(days=90)
    with closing(db.connect(paths.database)) as conn:
        assert outside.forget(conn, now=later, pasted=paths.pasted, copies=lambda _ids: None) == 0
