"""The library through the API: its folders as a tree, adding and forgetting one, and Home's
numbers."""

from pathlib import Path

from fastapi.testclient import TestClient

from mado.config import DataPaths
from tests.conftest import add
from tests.drawn import draw, exif


def test_a_new_library_has_no_folders(client: TestClient):
    assert client.get("/folders").json() == []


def test_adding_a_folder_reads_its_pictures_and_shows_them_as_a_tree(
    client: TestClient, tmp_path: Path
):
    phone = tmp_path / "Pictures" / "Phone"
    draw(phone / "IMG_2041.jpg", described=exif(taken="2026:11:14 18:42:07"))
    draw(phone / "2025" / "IMG_1001.jpg", described=exif(taken="2025:06:01 12:00:00"))
    draw(phone / "2026" / "Trip" / "beach.png")
    draw(phone / "2026" / "IMG_2042.jpg", described=exif(taken="2026:11:13 10:00:00"))
    (phone / "2026" / "_MG_0042.CR3").write_bytes(b"raw")

    added = add(client, phone)
    [folder] = client.get("/folders").json()

    assert added["path"] == str(phone)
    assert folder["name"] == "Phone"
    assert folder["available"] is True
    assert folder["looked"] is True
    assert (folder["pictures"], folder["reading"], folder["raw"], folder["broken"]) == (5, 0, 1, 0)
    assert [(node["name"], node["dir"], node["pictures"]) for node in folder["children"]] == [
        ("2026", "2026", 3),  # the newest pictures first
        ("2025", "2025", 1),
    ]
    [trip] = folder["children"][0]["children"]
    assert (trip["name"], trip["dir"], trip["pictures"], trip["children"]) == (
        "Trip",
        "2026/Trip",
        1,
        [],
    )


def test_a_folder_that_cant_be_added_says_why(client: TestClient, tmp_path: Path):
    missing = client.post("/folders", json={"path": str(tmp_path / "Unplugged")})
    blank = client.post("/folders", json={"path": "  "})

    assert missing.status_code == 400
    assert "isn't there" in missing.json()["detail"]
    assert blank.status_code == 400
    assert blank.json()["detail"] == "Choose a folder to add."


def test_forgetting_a_folder_leaves_its_pictures_where_they_are(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    picture = draw(tmp_path / "Phone" / "IMG.jpg")
    folder = add(client, tmp_path / "Phone")

    response = client.delete(f"/folders/{folder['id']}")

    assert response.status_code == 204
    assert client.get("/folders").json() == []
    assert picture.is_file()
    assert list(paths.cache.rglob("*.webp")) == []  # its thumbnails went with it
    assert client.delete(f"/folders/{folder['id']}").status_code == 404


def test_home_gets_the_library_in_numbers(client: TestClient, tmp_path: Path):
    draw(tmp_path / "Phone" / "a.jpg")
    draw(tmp_path / "Phone" / "b.png")
    (tmp_path / "Phone" / "broken.jpg").write_text("not a picture", encoding="utf-8")
    draw(tmp_path / "Camera" / "c.jpg")
    (tmp_path / "Camera" / "d.nef").write_bytes(b"raw")
    phone = add(client, tmp_path / "Phone")
    camera = add(client, tmp_path / "Camera")
    sizes = sum(
        each.stat().st_size
        for folder in ("Phone", "Camera")
        for each in (tmp_path / folder).iterdir()
    )

    library = client.get("/library").json()

    assert library == {
        "folders": 2,
        "pictures": 5,
        "size": sizes,
        "reading": 0,
        "raw": 1,
        "broken": 1,
        "parts": [
            {"folderId": phone["id"], "name": "Phone", "pictures": 3},
            {"folderId": camera["id"], "name": "Camera", "pictures": 2},
        ],
    }


def test_a_folder_whose_drive_isnt_connected_says_so(client: TestClient, tmp_path: Path):
    draw(tmp_path / "Phone" / "IMG.jpg")
    add(client, tmp_path / "Phone")
    (tmp_path / "Phone").rename(tmp_path / "Unplugged")

    [folder] = client.get("/folders").json()

    assert folder["available"] is False
    assert folder["pictures"] == 1  # still listed, till it's back


def test_the_scan_says_how_it_went(client: TestClient, tmp_path: Path):
    assert client.get("/scan").json()["state"] == "idle"
    draw(tmp_path / "Phone" / "IMG.jpg")
    add(client, tmp_path / "Phone")

    scan = client.get("/scan").json()

    assert scan["state"] == "done"
    assert (scan["found"], scan["toRead"], scan["read"], scan["added"], scan["gone"]) == (
        1,
        1,
        1,
        1,
        0,
    )
    assert scan["finishedAt"] is not None
    assert scan["unavailable"] == []
