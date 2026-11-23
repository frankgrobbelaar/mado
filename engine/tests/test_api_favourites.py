"""Favourites through the API: the heart on a picture, the Library's Favourites, a favourite that
moves or is renamed, one from outside the library, and favourites in the export."""

import json
import zipfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mado import db, outside
from mado.config import DataPaths
from mado.export import export_data
from mado.scan import Scanner
from tests.conftest import add
from tests.drawn import draw, exif


def _library(client: TestClient, folder: Path) -> dict[str, int]:
    for name, when in {
        "Harbour at dusk.jpg": "2026:11:14 18:42:07",
        "Little sail.jpg": "2026:11:14 16:05:00",
        "Snowfield.jpg": "2026:11:13 10:02:00",
    }.items():
        draw(folder / name, described=exif(taken=when))
    add(client, folder)
    return {item["name"]: item["id"] for item in client.get("/pictures").json()["pictures"]}


def _heart(client: TestClient, picture: int, favourite: bool = True) -> dict[str, Any]:
    response = client.put(f"/pictures/{picture}/favourite", json={"favourite": favourite})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_picture_is_given_a_heart_and_its_tile_and_page_say_so(
    client: TestClient, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone")

    page = _heart(client, ids["Little sail.jpg"])

    assert page["favourite"] is True
    assert client.get(f"/pictures/{ids['Little sail.jpg']}").json()["favourite"] is True
    tiles = {item["name"]: item["favourite"] for item in client.get("/pictures").json()["pictures"]}
    assert tiles == {"Harbour at dusk.jpg": False, "Little sail.jpg": True, "Snowfield.jpg": False}
    assert client.get("/library").json()["favourites"] == 1
    assert _heart(client, ids["Little sail.jpg"], False)["favourite"] is False
    assert client.get("/library").json()["favourites"] == 0


def test_favourites_are_a_list_of_their_own_searched_and_ordered_as_the_library(
    client: TestClient, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone")
    for name in ("Harbour at dusk.jpg", "Snowfield.jpg"):
        _heart(client, ids[name])

    shown = client.get("/pictures", params={"favourites": "true"}).json()
    assert [item["name"] for item in shown["pictures"]] == ["Harbour at dusk.jpg", "Snowfield.jpg"]
    assert shown["total"] == 2
    oldest = client.get("/pictures", params={"favourites": "true", "order": "oldest"}).json()
    assert [item["name"] for item in oldest["pictures"]] == ["Snowfield.jpg", "Harbour at dusk.jpg"]
    found = client.get("/pictures", params={"favourites": "true", "q": "snow"}).json()
    assert [item["name"] for item in found["pictures"]] == ["Snowfield.jpg"]
    around = client.get(
        f"/pictures/{ids['Harbour at dusk.jpg']}/neighbours", params={"favourites": "true"}
    ).json()
    assert [item["name"] for item in around["after"]] == ["Snowfield.jpg"]
    assert around["before"] == []


def test_a_heart_on_a_picture_not_there_says_so(client: TestClient):
    response = client.put("/pictures/404/favourite", json={"favourite": True})

    assert response.status_code == 404
    assert "isn't in your library" in response.json()["detail"]


def test_a_favourite_renamed_in_its_folder_stays_one_after_the_scan(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Phone"
    ids = _library(client, folder)
    _heart(client, ids["Snowfield.jpg"])

    (folder / "Snowfield.jpg").rename(folder / "Snow on the hill.jpg")
    app: Any = client.app
    scanner: Scanner = app.state.scanner
    scanner.start()
    scanner.wait(timeout=30)

    shown = client.get("/pictures", params={"favourites": "true"}).json()["pictures"]
    assert [item["name"] for item in shown] == ["Snow on the hill.jpg"]


def test_a_picture_from_outside_the_library_can_be_a_favourite_and_is_never_forgotten(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    pier = draw(tmp_path / "Elsewhere" / "Pier at dawn.jpg", described=exif())
    opened = client.post("/open", json={"paths": [str(pier)], "how": "opened"}).json()
    picture = opened["picture"]["id"]

    _heart(client, picture)

    shown = client.get("/pictures", params={"favourites": "true"}).json()["pictures"]
    assert [(item["name"], item["outside"]) for item in shown] == [("Pier at dawn.jpg", True)]
    assert client.get("/pictures").json()["pictures"] == []  # not the library's, all the same
    later = datetime.now().astimezone() + timedelta(days=90)
    with closing(db.connect(paths.database)) as conn:
        assert outside.forget(conn, now=later, pasted=paths.pasted, copies=lambda _ids: None) == 0
    assert client.get(f"/pictures/{picture}").json()["favourite"] is True


def test_favourites_go_in_the_export_by_their_pictures_paths(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    folder = tmp_path / "Phone"
    ids = _library(client, folder)
    _heart(client, ids["Little sail.jpg"])

    zipped = export_data(paths, tmp_path / "Export")

    assert zipped is not None
    with zipfile.ZipFile(zipped) as archive:
        kept = json.loads(archive.read("favourites.json"))
    assert [each["path"] for each in kept] == [str(folder / "Little sail.jpg")]
    assert kept[0]["at"]


def test_many_at_once_starts_from_every_favourite_or_those_a_search_found(
    client: TestClient, tmp_path: Path
):
    ids = _library(client, tmp_path / "Phone")
    pier = draw(tmp_path / "Elsewhere" / "Pier at dawn.jpg", described=exif())
    outside_one = client.post("/open", json={"paths": [str(pier)], "how": "opened"}).json()
    for picture in (ids["Snowfield.jpg"], ids["Little sail.jpg"], outside_one["picture"]["id"]):
        _heart(client, picture)

    every = client.post("/batches/pictures", json={"how": "favourites"}).json()
    assert sorted(each["name"] for each in every["pictures"]) == [
        "Little sail.jpg",
        "Pier at dawn.jpg",
        "Snowfield.jpg",
    ]
    found = client.post("/batches/pictures", json={"how": "favourites", "q": "snow"}).json()
    assert [each["name"] for each in found["pictures"]] == ["Snowfield.jpg"]
