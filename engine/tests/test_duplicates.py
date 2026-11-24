"""Duplicates and bursts: found in the background from the thumbnails the scan made, reviewed
through the API, and the rest of each group set aside, each picture checked first, into
quarantine with its History line, and put back from there."""

import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db, history
from mado.config import DataPaths
from mado.duplicates import Finder
from mado.library import add_folder
from mado.previews import Previews
from mado.scan import Scanner
from tests.conftest import FFMPEG, add
from tests.dng_files import dng
from tests.drawn import exif, scene
from tests.hdr_files import hdr_jpeg_of
from tests.heif_files import heif

STAMP = datetime(2026, 11, 14, 10, 0).timestamp()


def finder_of(client: TestClient) -> Finder:
    app: Any = client.app
    found: Finder = app.state.finder
    return found


def looked(client: TestClient, query: str = "") -> dict[str, Any]:
    """The review, once Mado has looked at everything."""
    assert finder_of(client).wait(60), "looking didn't finish in time"
    response = client.get(f"/duplicates{query}")
    assert response.status_code == 200, response.text
    return response.json()


def save(image: Image.Image, path: Path, *, at: float = STAMP, **options: Any) -> Path:
    """Saves a made-up picture with a file time of its own (seconds since 1970)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, **options)
    os.utime(path, (at, at))
    return path


def aside_all(client: TestClient, kind: str = "all") -> dict[str, Any]:
    """Sets aside the rest of every group, as the review last showed them."""
    seen = looked(client, f"?kind={kind}&limit=0")
    response = client.post(
        "/duplicates/aside", json={"groups": None, "kind": kind, "version": seen["version"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def shown(group: dict[str, Any]) -> dict[str, Any]:
    """A group as the review showed it: its pictures, and those kept."""
    return {
        "key": group["key"],
        "members": [each["id"] for each in group["pictures"]],
        "keep": [each["id"] for each in group["pictures"] if each["keep"]],
    }


def names(group: dict[str, Any]) -> list[str]:
    return [each["name"] for each in group["pictures"]]


def kept_names(group: dict[str, Any]) -> list[str]:
    return [each["name"] for each in group["pictures"] if each["keep"]]


def harbour(folder: Path) -> None:
    """A picture saved three ways (big, small, and as a PNG), and another scene."""
    big = scene(1)
    save(big, folder / "Harbour.jpg", quality=92, at=STAMP)
    save(big.resize((800, 600)), folder / "Harbour small.jpg", quality=70, at=STAMP + 60)
    save(big, folder / "Harbour.png", at=STAMP + 120)
    save(scene(2), folder / "Red canyon.jpg", quality=90)


def test_a_picture_saved_again_is_one_group_keeping_the_most_pixels(
    client: TestClient, tmp_path: Path
):
    harbour(tmp_path / "Pictures")
    add(client, tmp_path / "Pictures")

    found = looked(client)

    assert found["looking"] is None
    assert (found["duplicates"], found["bursts"]) == (1, 0)
    [group] = found["groups"]
    assert group["kind"] == "duplicates"
    assert not group["exact"]
    assert set(names(group)) == {"Harbour.jpg", "Harbour small.jpg", "Harbour.png"}
    assert kept_names(group) == ["Harbour.jpg"]  # most pixels; of two, the older file
    assert group["aside"] == 2
    assert group["ready"]
    assert found["pictures"] == 2
    assert found["bytes"] == group["bytes"] > 0
    assert all(each["there"] == "there" for each in group["pictures"])


def test_exact_copies_are_told_by_their_bytes(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    save(scene(3), folder / "Pier.jpg", quality=90)
    shutil.copy2(folder / "Pier.jpg", folder / "Pier (2).jpg")
    add(client, folder)

    [group] = looked(client)["groups"]

    assert group["exact"]
    assert kept_names(group) == ["Pier.jpg"]  # the name that isn't a copy's


def test_shots_of_one_moment_are_a_burst_keeping_the_sharpest(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures" / "Trip"
    for at, blur in enumerate((2.5, 0.0, 1.2)):
        save(
            scene(4, shift=(0.004 * at, 0.0), grain_seed=40 + at, blur=blur),
            folder / f"IMG_{2041 + at}.jpg",
            quality=92,
            exif=exif(taken=f"2026:11:14 10:02:{14 + at}", make="Pixelworks", model="PW-7"),
        )
    add(client, tmp_path / "Pictures")

    found = looked(client)

    [group] = found["groups"]
    assert (group["kind"], found["bursts"]) == ("burst", 1)
    assert names(group) == ["IMG_2041.jpg", "IMG_2042.jpg", "IMG_2043.jpg"]  # in time
    assert kept_names(group) == ["IMG_2042.jpg"]  # the sharp one
    assert all(each["takenFrom"] == "camera" for each in group["pictures"])


def test_different_scenes_and_a_gentle_crop_arent_duplicates(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    picture = scene(5)
    save(picture, folder / "Meadow.jpg", quality=90)
    save(picture.crop((48, 36, 1552, 1164)), folder / "Meadow cropped.jpg", quality=90)
    for seed in (6, 7, 8):
        save(scene(seed), folder / f"Scene {seed}.jpg", quality=90)
    add(client, folder)

    assert looked(client)["groups"] == []


def test_camera_raw_waiting_for_its_reader_and_a_quarantine_are_never_grouped(
    client: TestClient, tmp_path: Path
):
    raw = tmp_path / "Pictures"
    raw.mkdir()
    (raw / "_MG_0042.CR3").write_bytes(b"raw" * 1000)
    (raw / "_MG_0042 (2).CR3").write_bytes(b"raw" * 1000)
    aside = tmp_path / "Mado quarantine" / "2026-11-20"
    save(scene(9), aside / "Pier.jpg", quality=90)
    shutil.copy2(aside / "Pier.jpg", aside / "Pier (2).jpg")
    add(client, raw)
    add(client, aside)

    assert looked(client)["groups"] == []


def test_copies_of_a_camera_raw_group_but_never_with_its_jpeg(
    raw_client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Camera"
    shown = scene(9, (900, 600))
    dng(folder / "_MG_0042.dng", shown)
    (folder / "Backup").mkdir()
    shutil.copy2(folder / "_MG_0042.dng", folder / "Backup" / "_MG_0042.dng")
    save(shown, folder / "_MG_0042.jpg", quality=92)  # the camera's JPEG of the same moment
    add(raw_client, folder)

    [group] = looked(raw_client)["groups"]

    assert sorted(each["name"] for each in group["pictures"]) == ["_MG_0042.dng", "_MG_0042.dng"]
    assert all(each["path"].endswith(".dng") for each in group["pictures"])


def test_what_mado_made_from_a_picture_is_never_its_duplicate(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    folder = tmp_path / "Pictures"
    picture = scene(10)
    save(picture.resize((800, 600)), folder / "Beach.jpg", quality=90)
    save(picture, folder / "Beach (TV 8K).jpg", quality=95)
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        history.made(
            conn,
            now=datetime(2026, 11, 22, 14, 0).astimezone(),
            job_id=None,
            name="Beach.jpg",
            made_for="TV 8K",
            original=folder / "Beach.jpg",
            result=folder / "Beach (TV 8K).jpg",
        )
    add(client, folder)

    assert looked(client)["groups"] == []


def test_not_the_same_is_remembered_till_a_file_changes(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    [group] = looked(client)["groups"]

    response = client.post(f"/duplicates/{group['key']}/not-same")

    assert response.status_code == 204
    assert looked(client)["groups"] == []
    save(scene(1).resize((800, 600)), folder / "Harbour small.jpg", quality=60, at=STAMP + 900)
    app: Any = client.app
    app.state.scanner.request()
    app.state.scanner.wait(30)
    [again] = looked(client)["groups"]
    assert "Harbour small.jpg" in names(again)


def test_the_owner_can_keep_another_or_more_than_one(client: TestClient, tmp_path: Path):
    harbour(tmp_path / "Pictures")
    add(client, tmp_path / "Pictures")
    [group] = looked(client)["groups"]
    ids = {each["name"]: each["id"] for each in group["pictures"]}

    members = list(ids.values())
    changed = client.put(
        f"/duplicates/{group['key']}/keep", json={"keep": [ids["Harbour.png"]], "members": members}
    )
    both = client.put(
        f"/duplicates/{group['key']}/keep",
        json={"keep": [ids["Harbour.png"], ids["Harbour.jpg"]], "members": members},
    )
    none = client.put(f"/duplicates/{group['key']}/keep", json={"keep": [], "members": members})
    stranger = client.put(
        f"/duplicates/{group['key']}/keep", json={"keep": [99_999], "members": members}
    )

    assert changed.status_code == 200, changed.text
    assert kept_names(changed.json()) == ["Harbour.png"]
    assert changed.json()["chosen"]
    assert set(kept_names(both.json())) == {"Harbour.png", "Harbour.jpg"}
    assert both.json()["aside"] == 1
    assert none.status_code == 422
    assert stranger.status_code == 400
    assert "isn't in this group" in stranger.json()["detail"]
    assert looked(client)["pictures"] == 1


def test_setting_aside_moves_the_rest_into_quarantine_under_one_line_of_history(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    freed = sum((folder / name).stat().st_size for name in ("Harbour small.jpg", "Harbour.png"))

    done = aside_all(client)
    assert (done["pictures"], done["bytes"], done["left"]) == (2, freed, [])
    assert (folder / "Harbour.jpg").exists()
    assert not (folder / "Harbour small.jpg").exists()
    assert not (folder / "Harbour.png").exists()
    aside = sorted(path.name for path in (tmp_path / "Mado quarantine").rglob("*.*"))
    assert aside == ["Harbour small.jpg", "Harbour.png"]
    assert looked(client)["groups"] == []  # a group left with one picture goes away
    listed = client.get("/pictures").json()["pictures"]
    assert sorted(each["name"] for each in listed) == ["Harbour.jpg", "Red canyon.jpg"]
    shown = client.get("/history").json()
    [review] = shown["reviews"]
    assert (review["pictures"], review["back"], review["duplicates"], review["bursts"]) == (
        2,
        0,
        1,
        0,
    )
    assert review["canUndo"]
    assert review["bytes"] == done["bytes"]
    lines = [each for each in shown["entries"] if each["kind"] == "aside"]
    assert {each["name"] for each in lines} == {"Harbour small.jpg", "Harbour.png"}
    assert all(each["keptName"] == "Harbour.jpg" and each["canUndo"] for each in lines)
    assert all(each["review"] == review["id"] and each["asideUntil"] for each in lines)


def test_a_picture_put_back_is_back_in_the_library_and_its_group(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    aside_all(client)
    line = next(
        each for each in client.get("/history").json()["entries"] if each["name"] == "Harbour.png"
    )

    response = client.post(f"/history/{line['id']}/undo")

    assert response.status_code == 200, response.text
    assert response.json()["undoneAt"]
    assert not response.json()["canUndo"]
    assert (folder / "Harbour.png").exists()
    app: Any = client.app
    app.state.scanner.wait(30)
    [group] = looked(client)["groups"]
    assert set(names(group)) == {"Harbour.jpg", "Harbour.png"}


def test_a_whole_review_is_put_back_at_once(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    review = aside_all(client)["review"]

    response = client.post(f"/history/reviews/{review}/undo")

    assert response.json() == {"done": 2, "problems": []}
    assert (folder / "Harbour small.jpg").exists()
    assert (folder / "Harbour.png").exists()
    [line] = client.get("/history").json()["reviews"]
    assert (line["back"], line["canUndo"]) == (2, False)
    app: Any = client.app
    app.state.scanner.wait(30)
    found = looked(client)
    assert found["putBack"]["pictures"] == 2
    assert len(found["groups"]) == 1


def test_only_the_groups_asked_for_are_set_aside(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    harbour(folder)
    save(scene(3), folder / "Pier.jpg", quality=90)
    shutil.copy2(folder / "Pier.jpg", folder / "Pier (2).jpg")
    add(client, folder)
    groups = looked(client)["groups"]
    pier = next(group for group in groups if "Pier.jpg" in names(group))

    done = client.post("/duplicates/aside", json={"groups": [shown(pier)]}).json()

    assert done["pictures"] == 1
    assert not (folder / "Pier (2).jpg").exists()
    assert (folder / "Harbour.png").exists()
    assert [set(names(group)) for group in looked(client)["groups"]] == [
        {"Harbour.jpg", "Harbour small.jpg", "Harbour.png"}
    ]


def test_a_picture_that_changed_since_it_was_compared_is_left_as_it_is(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    save(scene(11).resize((800, 600)), folder / "Harbour small.jpg", quality=80, at=STAMP + 999)

    done = aside_all(client)

    assert done["pictures"] == 1
    [left] = done["left"]
    assert left["name"] == "Harbour small.jpg"
    assert "changed since Mado compared it" in left["why"]
    assert (folder / "Harbour small.jpg").exists()


def test_a_picture_open_in_another_app_is_left_as_it_is(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)

    with (folder / "Harbour.png").open("rb"):  # held open, as another app would
        done = aside_all(client)

    assert done["pictures"] == 1
    [left] = done["left"]
    assert "open in another app" in left["why"]
    assert "set it aside again" in left["why"]
    assert (folder / "Harbour.png").exists()
    lines = [each["name"] for each in client.get("/history").json()["entries"]]
    assert lines == ["Harbour small.jpg"]  # the one that didn't move has no line


def test_a_picture_on_a_drive_thats_gone_and_one_gone_since_are_left_as_they_are(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    (folder / "Harbour small.jpg").unlink()
    unplugged = str(folder / "Harbour.png").casefold()

    def connected(path: Path) -> bool:
        return str(path).casefold() != unplugged

    monkeypatch.setattr("mado.duplicates.drive_there", connected)

    done = aside_all(client)

    assert done["pictures"] == 0
    assert done["review"] is None
    why = {each["name"]: each["why"] for each in done["left"]}
    assert "isn't there any more" in why["Harbour small.jpg"]
    assert "which isn't connected" in why["Harbour.png"]
    assert client.get("/history").json()["reviews"] == []


def test_the_rest_stay_when_the_one_kept_isnt_there(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    (folder / "Harbour.jpg").unlink()

    done = aside_all(client)

    assert done["pictures"] == 0
    assert len(done["left"]) == 2
    assert all(
        "Harbour.jpg, the one kept, isn't there any more" in each["why"] for each in done["left"]
    )
    assert (folder / "Harbour.png").exists()
    assert (folder / "Harbour small.jpg").exists()


def test_the_review_says_which_pictures_arent_there_as_they_were(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    (folder / "Harbour small.jpg").unlink()
    found = looked(client)
    [group] = found["groups"]
    there = {each["name"]: each["there"] for each in group["pictures"]}
    assert there["Harbour small.jpg"] == "gone"

    def unplugged(_self: object, _path: str) -> bool:
        return False

    monkeypatch.setattr("mado.api.duplicates._Drives.connected", unplugged)
    away = looked(client)

    assert not away["groups"][0]["ready"]
    assert "isn't connected" in away["groups"][0]["problem"]
    assert (away["pictures"], away["away"]) == (0, 2)


def test_looking_says_how_far_it_has_got(paths: DataPaths, tmp_path: Path):
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        conn.execute("INSERT INTO folders (path, added_at) VALUES (?, 'x')", (str(tmp_path),))
        for at in range(3):
            conn.execute(
                """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at,
                                         seen_at, read_at, taken_at, taken_from)
                   VALUES (1, ?, '', ?, 10, 1, 'x', 'x', 'x', 'x', 'file')""",
                (str(tmp_path / f"{at}.jpg"), f"{at}.jpg"),
            )
        conn.commit()
        finder = Finder(paths, None, lambda: None, now=datetime.now)  # type: ignore[arg-type]

        conn.execute(  # one the scan hasn't read: not one to look at yet
            """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at,
                                     seen_at, taken_at, taken_from)
               VALUES (1, ?, '', 'unread.jpg', 10, 1, 'x', 'x', 'x', 'file')""",
            (str(tmp_path / "unread.jpg"),),
        )
        conn.commit()

        progress = finder.progress(conn, scanning=True)

        assert progress is not None
        assert (progress.looked, progress.of) == (0, 3)
        assert finder.progress(conn) is None  # resting, it isn't looking, whatever's left
        _print(conn, 1)
        _print(conn, 2)
        _print(conn, 3)
        assert finder.progress(conn, scanning=True) is None


def _print(conn: sqlite3.Connection, picture: int) -> None:
    with conn:
        conn.execute(
            "INSERT INTO prints (picture_id, size, modified, hash, at) VALUES (?, 10, 1, 0, 'x')",
            (picture,),
        )


def test_a_picture_whose_file_changed_is_looked_at_again(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    save(scene(12), folder / "Pier.jpg", quality=90)
    save(scene(13), folder / "Shore.jpg", quality=90)
    add(client, folder)
    assert looked(client)["groups"] == []

    save(scene(12).resize((800, 600)), folder / "Shore.jpg", quality=85, at=STAMP + 500)
    app: Any = client.app
    app.state.scanner.request()
    app.state.scanner.wait(30)

    [group] = looked(client)["groups"]
    assert set(names(group)) == {"Pier.jpg", "Shore.jpg"}


def test_a_picture_taken_out_of_the_library_meanwhile_isnt_looked_at(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    folder = tmp_path / "Pictures"
    save(scene(14), folder / "Pier.jpg", quality=90)
    added = add(client, folder)
    looked(client)
    with closing(db.connect(paths.database)) as conn:
        row = conn.execute("SELECT * FROM pictures").fetchone()
        conn.execute("DELETE FROM prints")
        conn.commit()
    for copy in paths.cache.rglob("*-thumbnail.webp"):
        copy.unlink()
    client.delete(f"/folders/{added['id']}")

    assert finder_of(client)._print(row) is None  # pyright: ignore[reportPrivateUsage]

    assert list(paths.cache.rglob("*-thumbnail.webp")) == []  # not made again


def test_heic_pictures_are_looked_at_once_ffmpeg_is_there(paths: DataPaths, tmp_path: Path):
    folder = tmp_path / "Phone"
    folder.mkdir()
    (folder / "IMG_2041.HEIC").write_bytes(heif(width=4032, height=3024))
    (folder / "IMG_2041 (2).HEIC").write_bytes(heif(width=4032, height=3024, exif=b"x" * 64))
    tools: dict[str, Any] = {"ffmpeg": None}
    previews = Previews(paths, lambda: tools["ffmpeg"])
    finder = Finder(paths, previews, lambda: tools["ffmpeg"], now=datetime.now)
    scanner = Scanner(paths, previews, ended=finder.wake)
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        add_folder(conn, folder, now=datetime.now())
    finder.start()
    try:
        scanner.start()
        scanner.wait(30)
        assert finder.wait(30)
        assert finder.found().groups == ()  # their thumbnails wait for ffmpeg

        tools["ffmpeg"] = FFMPEG  # Setup's download finished
        finder.wake()
        assert finder.wait(60)

        [group] = finder.found().groups
        names = {finder.found().pictures[member].name for member in group.members}
        assert names == {"IMG_2041.HEIC", "IMG_2041 (2).HEIC"}
    finally:
        finder.stop()


def test_a_picture_thats_the_kept_one_under_another_name_is_left_as_it_is(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    save(scene(15), folder / "Pier.jpg", quality=90)
    (folder / "Shared").mkdir()
    os.link(folder / "Pier.jpg", folder / "Shared" / "Pier.jpg")  # one file, two names
    add(client, folder)
    [group] = looked(client)["groups"]

    done = aside_all(client)

    assert done["pictures"] == 0
    [left] = done["left"]
    assert "the same file as Pier.jpg" in left["why"]
    assert (folder / "Pier.jpg").exists()
    assert (folder / "Shared" / "Pier.jpg").exists()
    assert group["exact"]


def _bigger_copy_arrives(client: TestClient, folder: Path) -> None:
    """A bigger copy of Harbour is saved beside it, and the library notices."""
    save(scene(1).resize((2400, 1800)), folder / "Harbour export.jpg", quality=95, at=STAMP + 300)
    app: Any = client.app
    app.state.scanner.request()
    app.state.scanner.wait(30)
    looked(client)


def test_a_group_that_changed_since_it_was_seen_is_left_as_it_is(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    [group] = looked(client)["groups"]
    _bigger_copy_arrives(client, folder)

    done = client.post("/duplicates/aside", json={"groups": [shown(group)]}).json()

    assert done["pictures"] == 0
    assert done["review"] is None
    assert all("changed since you looked" in each["why"] for each in done["left"])
    for name in ("Harbour.jpg", "Harbour small.jpg", "Harbour.png", "Harbour export.jpg"):
        assert (folder / name).exists()


def test_setting_every_group_aside_asks_that_none_changed_since_they_were_seen(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    before = looked(client, "?limit=0")["version"]
    _bigger_copy_arrives(client, folder)

    stale = client.post("/duplicates/aside", json={"groups": None, "version": before})
    missing = client.post("/duplicates/aside", json={"groups": None})

    assert stale.status_code == 409
    assert "changed since you looked" in stale.json()["detail"]
    assert missing.status_code == 409
    assert (folder / "Harbour.jpg").exists()
    assert aside_all(client)["pictures"] == 3  # all but the export, now the biggest


def test_bursts_and_duplicates_are_set_aside_apart(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    harbour(folder)
    for at, blur in enumerate((0.0, 2.0)):
        save(
            scene(16, shift=(0.004 * at, 0.0), grain_seed=60 + at, blur=blur),
            folder / "Trip" / f"IMG_{3041 + at}.jpg",
            quality=92,
            exif=exif(taken=f"2026:11:14 11:00:{10 + at}", make="Pixelworks", model="PW-7"),
        )
    add(client, folder)
    looked(client)

    bursts = looked(client, "?kind=bursts&limit=0")
    done = aside_all(client, "bursts")

    assert (bursts["pictures"], done["pictures"]) == (1, 1)
    assert not (folder / "Trip" / "IMG_3042.jpg").exists()
    assert (folder / "Harbour small.jpg").exists()
    assert (folder / "Harbour.png").exists()


def test_keeping_one_says_nothing_of_a_picture_that_joined_unseen(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    [group] = looked(client)["groups"]
    seen = shown(group)
    ids = {each["name"]: each["id"] for each in group["pictures"]}
    _bigger_copy_arrives(client, folder)

    changed = client.put(
        f"/duplicates/{group['key']}/keep",
        json={"keep": [ids["Harbour.png"]], "members": seen["members"]},
    ).json()

    keep = {each["name"]: each["keep"] for each in changed["pictures"]}
    assert keep["Harbour.png"] is True
    assert keep["Harbour export.jpg"] is True  # Mado's pick still: the owner never saw it
    assert keep["Harbour.jpg"] is False


def test_a_group_says_why_it_keeps_the_one_it_keeps(client: TestClient, tmp_path: Path):
    harbour(tmp_path / "Pictures")
    add(client, tmp_path / "Pictures")

    [group] = looked(client)["groups"]

    assert group["reason"] == "older"  # Harbour.jpg and Harbour.png: the same pixels, both plain


def test_a_picture_put_back_on_its_own_is_kept(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Pictures"
    harbour(folder)
    add(client, folder)
    looked(client)
    aside_all(client)
    line = next(
        each for each in client.get("/history").json()["entries"] if each["name"] == "Harbour.png"
    )

    client.post(f"/history/{line['id']}/undo")
    app: Any = client.app
    app.state.scanner.wait(30)

    found = looked(client)
    [group] = found["groups"]
    assert {each["name"]: each["keep"] for each in group["pictures"]} == {
        "Harbour.jpg": True,
        "Harbour.png": True,
    }
    assert found["pictures"] == 0  # set aside all again, it stays


def test_an_hdr_photo_is_grouped_by_its_picture_and_kept_over_its_ordinary_copy(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Pictures"
    big = scene(4)
    hdr_photo = folder / "PXL_1203.jpg"
    folder.mkdir(parents=True)
    hdr_photo.write_bytes(hdr_jpeg_of(big))
    os.utime(hdr_photo, (STAMP, STAMP))
    save(big, folder / "PXL_1203 copy.jpg", quality=92, at=STAMP + 60)  # its picture alone
    add(client, folder)

    [group] = looked(client)["groups"]

    assert set(names(group)) == {"PXL_1203.jpg", "PXL_1203 copy.jpg"}
    assert kept_names(group) == ["PXL_1203.jpg"]  # the same pixels, and its gain map besides
