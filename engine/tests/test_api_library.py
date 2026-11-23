"""The library through the API: its folders as a tree, adding and forgetting one, Home's
numbers, the pictures that won't open, and the room on the drives it uses."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mado import db
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
        "damaged": 0,
        "parts": [
            {"folderId": phone["id"], "name": "Phone", "pictures": 3},
            {"folderId": camera["id"], "name": "Camera", "pictures": 2},
        ],
        "favourites": 0,
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


def _broken_pictures(folder: Path) -> None:
    """Two pictures that will not open (one half copied, one no picture at all), one that does."""
    whole = draw(folder / "good.jpg", size=(400, 300))
    (folder / "Old pier.jpg").write_bytes(whole.read_bytes()[:900])
    (folder / "notes.jpg").write_text("not a picture", encoding="utf-8")


def test_the_pictures_that_wont_open_are_listed_with_why(client: TestClient, tmp_path: Path):
    _broken_pictures(tmp_path / "Scans")
    add(client, tmp_path / "Scans")

    found = client.get("/library/wont-open").json()

    assert found["damaged"] == 0
    assert sorted(each["name"] for each in found["pictures"]) == ["Old pier.jpg", "notes.jpg"]
    pier = next(each for each in found["pictures"] if each["name"] == "Old pier.jpg")
    assert "half copied" in pier["problem"]
    assert pier["folder"] == str(tmp_path / "Scans")
    assert pier["path"] == str(tmp_path / "Scans" / "Old pier.jpg")


def test_marking_one_as_damaged_takes_it_off_the_count_till_its_file_changes(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Scans"
    _broken_pictures(folder)
    add(client, folder)
    pier = next(
        each
        for each in client.get("/library/wont-open").json()["pictures"]
        if each["name"] == "Old pier.jpg"
    )
    good = next(
        each for each in client.get("/pictures").json()["pictures"] if each["name"] == "good.jpg"
    )

    marked = client.post(f"/pictures/{pier['id']}/damaged")
    refused = client.post(f"/pictures/{good['id']}/damaged")

    assert marked.status_code == 200, marked.text
    assert marked.json()["damaged"] is True
    assert refused.status_code == 409
    after = client.get("/library/wont-open").json()
    assert [each["name"] for each in after["pictures"]] == ["notes.jpg"]
    assert after["damaged"] == 1
    library = client.get("/library").json()
    assert (library["broken"], library["damaged"]) == (2, 1)
    assert (folder / "Old pier.jpg").exists()  # left exactly as it is

    whole = (folder / "good.jpg").read_bytes()
    (folder / "Old pier.jpg").write_bytes(whole[:1500])  # copied again, still half
    stamp = datetime(2026, 11, 23, 9, 0).timestamp()
    os.utime(folder / "Old pier.jpg", (stamp, stamp))
    app: Any = client.app
    app.state.scanner.request()
    app.state.scanner.wait(30)

    again = client.get("/library/wont-open").json()
    assert sorted(each["name"] for each in again["pictures"]) == ["Old pier.jpg", "notes.jpg"]


def test_trying_one_again_that_was_mended_brings_it_back(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Scans"
    _broken_pictures(folder)
    add(client, folder)
    notes = next(
        each
        for each in client.get("/library/wont-open").json()["pictures"]
        if each["name"] == "notes.jpg"
    )
    draw(folder / "notes.jpg", size=(64, 48))

    read = client.post(f"/pictures/{notes['id']}/read")

    assert read.json()["state"] == "ready"
    assert [each["name"] for each in client.get("/library/wont-open").json()["pictures"]] == [
        "Old pier.jpg"
    ]


def test_space_is_the_drive_most_of_the_library_is_on_then_each_other_one(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    draw(tmp_path / "Phone" / "a.jpg", size=(320, 240))
    draw(tmp_path / "Phone" / "b.jpg", size=(320, 240))
    add(client, tmp_path / "Phone")
    pictures = sum(each.stat().st_size for each in (tmp_path / "Phone").iterdir())
    aside = tmp_path / "Mado quarantine" / "2026-11-23" / "c.jpg"
    draw(aside, size=(64, 48))
    drive = Path(tmp_path).drive.upper()
    with closing(db.connect(paths.database)) as conn:
        conn.execute(
            "INSERT INTO folders (path, added_at) VALUES ('Q:\\Old scans', '2026-11-22T09:00')"
        )
        conn.execute(
            """INSERT INTO history (at, kind, name, original, aside, aside_at, kept, bytes)
               VALUES ('2026-11-23T09:00:00+02:00', 'aside', 'c.jpg', ?, ?,
                       '2026-11-23T09:00:00+02:00', ?, ?)""",
            (
                str(tmp_path / "Phone" / "c.jpg"),
                str(aside),
                str(tmp_path / "Phone" / "a.jpg"),
                aside.stat().st_size,
            ),
        )
        conn.commit()
        _queue_wants(conn, tmp_path / "Phone" / "a.jpg", 5_000_000)

    drives = client.get("/space").json()

    assert [each["drive"] for each in drives] == [drive, "Q:"]
    here, away = drives
    assert here["connected"] is True
    assert here["free"] > 0
    assert here["total"] >= here["free"]
    assert (here["pictures"], here["quarantine"], here["queue"]) == (
        pictures,
        aside.stat().st_size,
        5_000_000,
    )
    assert away == {
        "drive": "Q:",
        "connected": False,
        "free": None,
        "total": None,
        "pictures": 0,
        "quarantine": 0,
        "queue": 0,
    }


def _queue_wants(conn: sqlite3.Connection, source: Path, size: int) -> None:
    """A batch's picture waiting in the queue, to be saved beside its original."""
    with conn:
        conn.execute(
            """INSERT INTO batches (name, source, steps, starts, added_at)
               VALUES ('Holiday prints', 'Phone', '{}', 'now', '2026-11-23T09:00')"""
        )
        conn.execute(
            """INSERT INTO jobs (kind, source, recipe, state, queued_at, batch_id)
               VALUES ('make', ?, ?, 'queued', '2026-11-23T09:00', 1)""",
            (str(source), json.dumps({"saving": {"how": "new"}, "bytes": size})),
        )
