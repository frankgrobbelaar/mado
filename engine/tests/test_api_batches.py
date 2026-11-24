"""Many at once through the API, end to end on the processor with the shipped Fast model and tiny
made-up pictures: choosing the pictures, what a batch takes, See it first, the queue and what can
be done with it, History's one line for a batch and its undo, Home's batches done, and recipes."""

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db, watching
from mado import samples as samples_module
from mado.batches import Picture
from mado.config import DataPaths
from mado.core.batch import KEPT_SECONDS, MARGIN, recipe_of
from mado.jobs import Jobs
from mado.previews import version
from mado.quarantine import Quarantine
from mado.upscale import StoppedError
from tests.conftest import add, made
from tests.dng_files import dng
from tests.drawn import draw, scene
from tests.fix_models import with_fix_models

type Library = dict[str, Any]

SMALL = "other-256x192"  # a size the processor makes in a moment
NOW = datetime(2026, 11, 22, 14, 2).astimezone()
SAVING = {"how": "new", "format": "JPEG", "quality": 90, "folder": "Edited"}
STEPS = [{"step": "size", "size": SMALL}]


@pytest.fixture
def library(client: TestClient, tmp_path: Path) -> Library:
    """Holiday: three made-up photos, a camera RAW waiting for Mado's RAW reader and one that
    won't open."""
    holiday = tmp_path / "Holiday"
    for name in ("Warm dunes.jpg", "Still lake.png", "Night market.jpg"):
        draw(holiday / name, size=(96, 72))
    (holiday / "Green sky.CR3").write_bytes(b"raw")
    (holiday / "Old pier.jpg").write_bytes(b"not a picture at all")
    folder = add(client, holiday)
    listed = client.get("/pictures").json()["pictures"]
    return {
        "folder": holiday,
        "id": folder["id"],
        "ids": {item["name"]: item["id"] for item in listed},
    }


def _wait(client: TestClient, timeout: float = 120) -> None:
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    assert jobs.wait(timeout), "the queue didn't settle in time"


def _picked(client: TestClient, **pick: Any) -> dict[str, Any]:
    response = client.post("/batches/pictures", json=pick)
    assert response.status_code == 200, response.text
    return response.json()


def _put_in(client: TestClient, picked: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body = {
        "source": picked["source"],
        "shared": picked["shared"],
        "pictures": picked["pictures"],
        "steps": STEPS,
        "saving": SAVING,
        "starts": "now",
        **overrides,
    }
    response = client.post("/batches", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_ticked_pictures_are_picked_with_those_mado_cant_make_left_out_saying_why(
    client: TestClient, library: Library
):
    ids = library["ids"]
    picked = _picked(
        client,
        how="ticked",
        ids=[ids["Still lake.png"], ids["Warm dunes.jpg"], ids["Green sky.CR3"]],
    )

    assert [each["name"] for each in picked["pictures"]] == ["Still lake.png", "Warm dunes.jpg"]
    assert picked["source"] == "Holiday"
    assert picked["words"] == "ticked in Holiday"
    assert picked["shared"] == str(library["folder"])
    assert picked["leftOut"] == [
        {
            "name": "Green sky.CR3",
            "why": "It's a camera RAW, and Mado is getting its RAW reader: it joins once that's "
            "here.",
            "waiting": True,  # it joins once the reader's here, so the page shows it coming
        }
    ]
    assert picked["bytes"] == sum(each["size"] for each in picked["pictures"])


def test_a_batch_takes_camera_raw_and_saves_it_as_new_pictures_only(
    raw_client: TestClient, tmp_path: Path
):
    holiday = tmp_path / "Holiday"
    dng(holiday / "Green sky.dng", scene(4, (240, 160)), preview=None, thumbnail=False)
    draw(holiday / "Warm dunes.jpg", size=(96, 72))
    add(raw_client, holiday)

    picked = _picked(raw_client, how="folder", folder=1)

    assert {each["name"]: each["raw"] for each in picked["pictures"]} == {
        "Green sky.dng": True,
        "Warm dunes.jpg": False,
    }
    body = {
        "source": picked["source"],
        "shared": picked["shared"],
        "pictures": picked["pictures"],
        "steps": STEPS,
        "saving": {**SAVING, "how": "replace"},
        "starts": "now",
    }
    refused = raw_client.post("/batches", json=body)
    assert refused.status_code == 409
    assert "can't write camera RAW" in refused.json()["detail"]
    before = (holiday / "Green sky.dng").read_bytes()
    _put_in(raw_client, picked)
    _wait(raw_client)

    [made] = (holiday / "Edited").glob("Green sky*")
    with Image.open(made) as picture:
        assert picture.format == "JPEG"  # a developed RAW saves as a photo
    assert (holiday / "Green sky.dng").read_bytes() == before  # the RAW exactly as it was


def test_a_job_never_puts_a_picture_in_a_raws_place_not_even_one_see_it_first_made(
    raw_client: TestClient, tmp_path: Path
):
    camera = tmp_path / "Camera"
    raw = dng(camera / "Green sky.dng", scene(4, (240, 160)))
    add(raw_client, camera)
    [listed] = raw_client.get("/pictures").json()["pictures"]
    before = raw.read_bytes()
    seen = draw(tmp_path / "Seen" / "Green sky.jpg", size=(240, 160))
    stat = raw.stat()
    order = {  # as a batch's job would carry it, had anything let Replace through
        "recipe": recipe_of([{"step": "size", "size": SMALL}]),
        "saving": {**SAVING, "how": "replace"},
        "label": "256 × 192",
        "look": None,
        "edit": None,
        "made": {
            "source": str(raw),
            "path": str(seen),
            "version": f"{stat.st_mtime_ns:x}-{stat.st_size:x}",
            "width": 240,
            "height": 160,
            "named": "Green sky",
        },
    }
    app: Any = raw_client.app
    with closing(db.connect(app.state.paths.database)) as conn:
        conn.row_factory = sqlite3.Row
        job_id = app.state.jobs.add(conn, listed["id"], raw, order)

    done = made(raw_client, {"id": job_id})

    assert done["state"] == "failed"
    assert "can't write camera RAW" in done["problem"]
    assert raw.read_bytes() == before
    assert not (tmp_path / "Mado quarantine").exists()  # nothing set aside in its place


def test_a_camera_raw_mado_is_still_reading_waits_to_join_saying_so(
    raw_client: TestClient, tmp_path: Path
):
    camera = tmp_path / "Camera"
    dng(camera / "Green sky.dng", scene(4, (240, 160)))
    add(raw_client, camera)
    app: Any = raw_client.app
    with closing(db.connect(app.state.paths.database)) as conn, conn:
        # As a scan leaves a RAW it listed before the reader came, not yet read again.
        conn.execute("UPDATE pictures SET width = NULL, height = NULL WHERE raw = 1")

    picked = _picked(raw_client, how="folder", folder=1)

    # The reader's there: it's the scan's turn to read it, and the page asks again till it has.
    assert picked["leftOut"] == [
        {
            "name": "Green sky.dng",
            "why": "It's a camera RAW Mado is reading now: it joins once it's read.",
            "waiting": True,
        }
    ]


def test_a_whole_folder_and_what_a_search_found_are_picked_too(
    client: TestClient, library: Library
):
    whole = _picked(client, how="folder", folder=library["id"])
    found = _picked(client, how="search", q="lake")

    assert len(whole["pictures"]) == 3
    assert whole["words"] == "in Holiday"
    assert [each["name"] for each in found["pictures"]] == ["Still lake.png"]
    assert found["words"] == "found by “lake”"


def test_a_batch_too_big_or_a_folder_too_full_says_what_was_left_out(
    client: TestClient, library: Library, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("mado.batches.MOST", 2)
    whole = _picked(client, how="folder", folder=library["id"])
    assert len(whole["pictures"]) == 2
    assert {
        "name": "1 more picture",
        "why": "A batch holds 2 at most: make it in another.",
        "waiting": False,
    } in whole["leftOut"]

    monkeypatch.setattr("mado.batches.MOST", 10_000)
    monkeypatch.setattr("mado.batches._WALKED", 3)
    desk = tmp_path / "Desktop"
    for each in range(5):
        draw(desk / "Trip" / f"Sail {each}.png", size=(40, 30))
    dropped = _picked(client, how="dropped", paths=[str(desk / "Trip")])
    assert len(dropped["pictures"]) == 3
    assert dropped["leftOut"] == [
        {
            "name": "The rest of Trip",
            "why": "Mado looks through 3 files at most in a folder dropped or picked: drop the "
            "folders inside it one at a time.",
            "waiting": False,
        }
    ]


def test_pictures_dropped_from_outside_the_library_are_made_too(client: TestClient, tmp_path: Path):
    desk = tmp_path / "Desktop"
    draw(desk / "Rose.jpg", size=(80, 60))
    draw(desk / "Trip" / "Sail.png", size=(80, 60))
    (desk / "notes.txt").write_text("not a picture", encoding="utf-8")

    picked = _picked(client, how="dropped", paths=[str(desk / "Rose.jpg"), str(desk / "Trip")])

    assert {each["name"] for each in picked["pictures"]} == {"Rose.jpg", "Sail.png"}
    assert all(each["id"] is None for each in picked["pictures"])
    assert picked["words"] == "dropped from Desktop"

    batch = _put_in(client, picked, saving={**SAVING, "folder": None})
    _wait(client)

    assert (desk / "Rose (256 × 192).jpg").is_file()
    assert (desk / "Trip" / "Sail (256 × 192).jpg").is_file()
    assert client.get("/queue").json()["batch"] is None
    done = client.get("/batches/done").json()
    assert [each["id"] for each in done] == [batch["id"]]


def test_what_a_batch_takes_says_its_steps_time_space_and_where_its_pictures_go(
    client: TestClient, library: Library
):
    picked = _picked(client, how="folder", folder=library["id"])
    steps = [*STEPS, {"step": "look", "look": "warm-film", "strength": 0.6}]

    response = client.post(
        "/batches/takes",
        json={
            "pictures": picked["pictures"],
            "steps": steps,
            "saving": SAVING,
            "shared": picked["shared"],
        },
    )

    assert response.status_code == 200, response.text
    takes = response.json()
    assert [(each["kind"], each["chip"], each["amount"]) for each in takes["words"]] == [
        ("size", "256 × 192", None),
        ("look", "Warm film", "60"),
        ("save", "JPEG 90 into Edited", None),
    ]
    assert takes["words"][0]["title"] == "Make it for a screen"
    assert takes["seconds"] > 0
    assert takes["bytes"] > 0
    assert takes["free"] > 0
    assert takes["fits"]
    assert takes["example"] == "Name (256 × 192, Warm film).jpg"
    assert takes["into"] == "Holiday › Edited"
    assert takes["needs"] == []


def test_steps_mado_cant_make_are_refused_with_a_sentence(client: TestClient, library: Library):
    picked = _picked(client, how="folder", folder=library["id"])

    response = client.post(
        "/batches/takes",
        json={
            "pictures": picked["pictures"],
            "steps": [{"step": "fix", "noise": None}],
            "saving": SAVING,
        },
    )

    assert response.status_code == 422
    assert "no fix turned on" in response.json()["detail"]


def test_just_save_is_a_batch_of_pictures_saved_as_they_are(client: TestClient, library: Library):
    picked = _picked(client, how="folder", folder=library["id"])

    takes = client.post(
        "/batches/takes",
        json={"pictures": picked["pictures"], "steps": [], "saving": SAVING},
    )

    assert takes.status_code == 200, takes.text
    assert [each["kind"] for each in takes.json()["words"]] == ["save"]


def test_see_it_first_makes_three_in_full_unsaved_and_the_batch_keeps_them(
    client: TestClient, library: Library
):
    picked = _picked(client, how="folder", folder=library["id"])
    asked = client.post(
        "/batches/samples",
        json={"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING},
    )
    assert asked.status_code == 202, asked.text
    _wait(client)
    shown = client.get(f"/batches/samples/{asked.json()['id']}").json()

    assert [each["state"] for each in shown["samples"]] == ["done", "done", "done"]
    assert all(each["madeBytes"] for each in shown["samples"])
    assert shown["seconds"] is not None
    assert not (library["folder"] / "Edited").exists()  # nothing saved yet
    full = client.get(f"/batches/samples/{shown['id']}/0/full")
    assert full.status_code == 200
    assert full.headers["content-type"] == "image/jpeg"
    for side in ("before", "after"):
        assert client.get(f"/batches/samples/{shown['id']}/0/{side}").status_code == 200

    reckoned = client.post(
        "/batches/takes",
        json={
            "pictures": picked["pictures"],
            "steps": STEPS,
            "saving": SAVING,
            "sample": shown["id"],
        },
    ).json()
    assert reckoned["reckoned"]

    _put_in(client, picked, sample=shown["id"])
    _wait(client)

    made = sorted(path.name for path in (library["folder"] / "Edited").iterdir())
    assert made == [
        "Night market (256 × 192).jpg",
        "Still lake (256 × 192).jpg",
        "Warm dunes (256 × 192).jpg",
    ]


def test_see_it_first_keeps_each_picture_with_its_own_whatever_order_the_batch_lists_them(
    client: TestClient, library: Library, conn: sqlite3.Connection
):
    picked = _picked(client, how="folder", folder=library["id"])
    body = {"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING}
    asked = client.post("/batches/samples", json=body).json()
    _wait(client)
    turned = {**picked, "pictures": list(reversed(picked["pictures"]))}  # Change which, say

    reckoned = client.post(
        "/batches/takes", json={**body, "pictures": turned["pictures"], "sample": asked["id"]}
    ).json()
    batch = _put_in(client, turned, sample=asked["id"])

    assert reckoned["seconds"] == pytest.approx(3 * KEPT_SECONDS)  # still all three, kept
    kept = [
        (row["source"], json.loads(row["recipe"]).get("made"))
        for row in conn.execute(
            "SELECT source, recipe FROM jobs WHERE batch_id = ?", (batch["id"],)
        )
    ]
    assert len(kept) == 3
    assert all(made is not None and made["source"] == source for source, made in kept)


def test_see_it_first_let_go_as_a_picture_is_made_leaves_nothing_behind(
    client: TestClient, library: Library, paths: DataPaths, monkeypatch: pytest.MonkeyPatch
):
    app: Any = client.app
    picked = _picked(client, how="folder", folder=library["id"])
    asked: dict[str, str] = {}
    ready = threading.Event()
    real = samples_module.make

    def let_go_as_the_second_is_made(*args: Any, **kwargs: Any) -> Any:
        ready.wait(10)
        if asked.get("made"):  # the first is made in full; the second is let go part way
            app.state.samples.drop(asked["id"])
            raise StoppedError
        asked["made"] = "yes"
        return real(*args, **kwargs)

    monkeypatch.setattr("mado.samples.make", let_go_as_the_second_is_made)
    body = {"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING}
    asked["id"] = client.post("/batches/samples", json=body).json()["id"]
    ready.set()
    _wait(client)

    assert list((paths.cache / "samples").glob(f"{asked['id']}-*")) == []


def test_a_picture_see_it_first_made_is_let_go_once_its_saved(
    client: TestClient, library: Library, paths: DataPaths
):
    picked = _picked(client, how="folder", folder=library["id"])
    body = {"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING}
    asked = client.post("/batches/samples", json=body).json()
    _wait(client)

    _put_in(client, picked, sample=asked["id"])
    _wait(client)

    assert len(list((library["folder"] / "Edited").glob("*.jpg"))) == 3
    assert list((paths.cache / "samples" / "kept").glob("*")) == []


def test_three_others_are_seen_on_asking_and_the_last_ones_let_go(
    client: TestClient, tmp_path: Path
):
    desk = tmp_path / "Desktop"
    for each in range(6):
        draw(desk / f"Pic {each}.png", size=(64, 48))
    picked = _picked(client, how="picked", paths=[str(desk)])
    body = {"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING}

    first = client.post("/batches/samples", json=body).json()
    again = client.post("/batches/samples", json={**body, "round": 1}).json()
    _wait(client)
    seen_first = {each["index"] for each in first["samples"]}
    seen_again = {each["index"] for each in again["samples"]}

    assert not seen_first & seen_again
    assert client.delete(f"/batches/samples/{again['id']}").status_code == 204
    assert client.get(f"/batches/samples/{again['id']}").status_code == 404


def test_a_batch_is_one_line_in_history_and_take_them_away_undoes_all_of_it(
    client: TestClient, library: Library
):
    picked = _picked(client, how="folder", folder=library["id"])
    batch = _put_in(client, picked)
    _wait(client)

    history = client.get("/history").json()
    lines = [each for each in history["entries"] if each["batch"] == batch["id"]]
    assert len(lines) == 3
    [line] = history["batches"]
    assert line["made"] == 3
    assert line["canUndo"]
    assert line["into"] == "Holiday › Edited"
    assert line["madeFor"] == "256 × 192"

    undone = client.post(f"/history/batches/{batch['id']}/undo").json()
    assert undone == {"done": 3, "problems": []}
    assert not list((library["folder"] / "Edited").glob("*.jpg"))
    [line] = client.get("/history").json()["batches"]
    assert (line["made"], line["undone"], line["canRedo"]) == (0, 3, True)

    redone = client.post(f"/history/batches/{batch['id']}/redo").json()
    assert redone["done"] == 3
    assert len(list((library["folder"] / "Edited").glob("*.jpg"))) == 3


def test_a_batch_still_being_made_is_undone_as_a_whole_only_once_its_done(
    client: TestClient, library: Library, conn: sqlite3.Connection
):
    picked = _picked(client, how="folder", folder=library["id"])
    batch = _put_in(client, picked)
    _wait(client)
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    jobs.stop()
    last = conn.execute(
        "SELECT id, result FROM jobs WHERE batch_id = ? ORDER BY id DESC LIMIT 1", (batch["id"],)
    ).fetchone()
    Path(last["result"]).unlink()
    with conn:  # as if its last picture still waited in the queue
        conn.execute("DELETE FROM history WHERE job_id = ?", (last["id"],))
        conn.execute("UPDATE jobs SET state = 'queued', result = NULL WHERE id = ?", (last["id"],))

    [line] = client.get("/history").json()["batches"]
    assert line["working"] is True
    refused = client.post(f"/history/batches/{batch['id']}/undo")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Some of its pictures are still in the queue. Once they're made, or taken out of the "
        "queue, this undoes all of it."
    )
    assert len(list((library["folder"] / "Edited").glob("*.jpg"))) == 2  # nothing changed

    jobs.start()
    _wait(client)
    [line] = client.get("/history").json()["batches"]
    assert line["working"] is False
    assert client.post(f"/history/batches/{batch['id']}/undo").json()["done"] == 3


def test_a_replace_batch_puts_each_original_in_quarantine_and_puts_them_all_back(
    client: TestClient, library: Library, quarantine: Quarantine
):
    picked = _picked(client, how="folder", folder=library["id"])
    original = library["folder"] / "Warm dunes.jpg"
    batch = _put_in(client, picked, saving={**SAVING, "how": "replace", "folder": None})
    _wait(client)

    with Image.open(original) as made:
        assert made.size == (256, 192)
    [line] = client.get("/history").json()["batches"]
    assert line["how"] == "replace"
    assert line["drive"] is not None

    back = client.post(f"/history/batches/{batch['id']}/undo").json()
    assert back["done"] == 3
    with Image.open(original) as put_back:
        assert put_back.size == (96, 72)
    assert quarantine.root(original).is_dir()  # the pictures made wait there now


def test_the_queue_says_what_waits_and_ticked_pictures_go_next_last_or_out(
    client: TestClient, library: Library
):
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    jobs.stop()  # nothing is made: everything waits
    picked = _picked(client, how="folder", folder=library["id"])
    batch = _put_in(client, picked, starts="after")

    queue = client.get("/queue").json()
    assert queue["batch"]["id"] == batch["id"]
    assert queue["batch"]["total"] == 3
    rows = queue["rows"]
    assert [row["state"] for row in rows] == ["queued", "queued", "queued"]
    last = rows[-1]["job"]

    assert client.post("/queue/next", json={"jobs": [last]}).json() == {"moved": 1}
    assert client.get("/queue").json()["rows"][0]["job"] == last
    assert client.post("/queue/last", json={"jobs": [last]}).json() == {"moved": 1}
    assert client.get("/queue").json()["rows"][-1]["job"] == last
    assert client.post("/queue/remove", json={"jobs": [last]}).json() == {"moved": 1}
    assert client.get("/queue").json()["batch"]["total"] == 2

    paused = client.post("/queue/pause").json()
    assert paused["paused"]
    assert client.post("/queue/resume").json()["paused"] is False
    assert client.get("/queue/now").json()["waiting"] == 2

    assert client.post("/queue/cancel").json() == {"moved": 2}
    assert client.get("/queue").json()["batch"] is None


def test_a_pictures_own_saves_and_the_status_bars_leave_out_the_queues(
    client: TestClient, library: Library
):
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    jobs.stop()
    _put_in(client, _picked(client, how="folder", folder=library["id"]))

    picture = library["ids"]["Warm dunes.jpg"]
    assert client.get(f"/jobs?picture={picture}").json() == []  # its page follows its own Save
    assert client.get("/jobs?active=true").json() == []  # the queue's line says the batch's
    assert client.get("/queue/now").json()["waiting"] == 3
    jobs.start()
    _wait(client)


def test_a_drive_without_room_says_how_much_more_it_needs_keeping_its_margin(
    client: TestClient, library: Library, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    jobs.stop()
    _put_in(client, _picked(client, how="folder", folder=library["id"]))
    drive = library["folder"].drive.upper()
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('queue_room', ?)",
            (json.dumps({"drive": drive, "fit": False}),),
        )

    def nearly_full(_path: object) -> SimpleNamespace:
        return SimpleNamespace(free=MARGIN + 1000)

    monkeypatch.setattr("mado.api.queue.shutil.disk_usage", nearly_full)

    room = client.get("/queue").json()["room"]

    assert room["drive"] == drive
    assert room["needed"] > 1000
    assert room["more"] == room["needed"] - 1000  # what it needs past the 256 MB kept free


def _one_moved_away(client: TestClient, library: Library) -> tuple[dict[str, Any], Path]:
    """A batch of Holiday's three, Still lake moved away before Mado gets to it, made: Still
    lake didn't work. Returns the batch and where Still lake went."""
    picked = _picked(client, how="folder", folder=library["id"])
    gone = library["folder"] / "Still lake.png"
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    jobs.stop()
    batch = _put_in(client, picked)
    moved = gone.with_name("Still lake (away).png")
    gone.rename(moved)
    jobs.start()
    _wait(client)
    return batch, moved


def test_a_picture_that_didnt_work_says_why_in_the_queue_and_can_be_tried_again(
    client: TestClient, library: Library
):
    batch, moved = _one_moved_away(client, library)

    queue = client.get("/queue").json()
    assert queue["finished"] is True  # done, but what didn't work stays, saying why
    assert queue["batch"]["id"] == batch["id"]
    assert (queue["batch"]["done"], queue["batch"]["failed"]) == (2, 1)
    failed = next(row for row in queue["rows"] if row["state"] == "failed")
    assert failed["name"] == "Still lake.png"
    assert "isn't there" in failed["problem"]
    assert client.get("/history").json()["batches"][0]["failed"] == ["Still lake.png"]

    moved.rename(moved.with_name("Still lake.png"))
    assert client.post(f"/queue/{failed['job']}/retry").status_code == 200
    _wait(client)
    assert (library["folder"] / "Edited" / "Still lake (256 × 192).jpg").is_file()
    assert client.get("/queue").json()["batch"] is None  # nothing left that didn't work
    assert client.post(f"/batches/{batch['id']}/seen").status_code == 204
    assert client.get("/batches/done").json() == []


def test_what_didnt_work_leaves_the_queue_once_cleared(client: TestClient, library: Library):
    _one_moved_away(client, library)
    assert client.get("/queue").json()["finished"] is True

    assert client.post("/queue/clear").status_code == 200

    queue = client.get("/queue").json()
    assert (queue["batch"], queue["finished"]) == (None, False)
    assert client.get("/history").json()["batches"][0]["failed"] == ["Still lake.png"]


def test_home_says_what_was_made_today_with_a_thumbnail_of_each(client: TestClient, tmp_path: Path):
    desk = tmp_path / "Desktop"
    draw(desk / "Rose.jpg", size=(80, 60))
    picked = _picked(client, how="dropped", paths=[str(desk / "Rose.jpg")])
    _put_in(client, picked, saving={**SAVING, "folder": None})
    _wait(client)

    [made] = client.get("/history/today").json()
    assert made["name"] == "Rose"
    assert made["madeFor"] == "256 × 192"
    thumbnail = client.get(f"/history/{made['id']}/thumbnail")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"


def test_recipes_are_kept_used_on_batches_and_said_as_a_line(client: TestClient, library: Library):
    kept = client.post(
        "/recipes",
        json={"name": "Holiday prints", "steps": STEPS, "saving": SAVING},
    )
    assert kept.status_code == 201, kept.text
    recipe = kept.json()
    assert [each["chip"] for each in recipe["words"]] == ["256 × 192", "JPEG 90 into Edited"]
    assert recipe["used"] == 0

    taken = client.post(
        "/recipes", json={"name": "holiday PRINTS", "steps": STEPS, "saving": SAVING}
    )
    assert taken.status_code == 422
    assert "already" in taken.json()["detail"]

    picked = _picked(client, how="folder", folder=library["id"])
    batch = _put_in(client, picked, recipe=recipe["id"])
    assert batch["name"] == "Holiday prints"
    _wait(client)
    [used] = client.get("/recipes").json()
    assert used["used"] == 1
    assert used["usedAt"] is not None

    changed = client.put(
        f"/recipes/{recipe['id']}",
        json={"name": "TV prints", "steps": STEPS, "saving": {**SAVING, "quality": 95}},
    )
    assert changed.json()["words"][-1]["chip"] == "JPEG 95 into Edited"
    assert client.delete(f"/recipes/{recipe['id']}").status_code == 204
    assert client.get("/recipes").json() == []


def test_a_recipe_a_watch_folder_runs_isnt_deleted_from_under_it(
    client: TestClient, tmp_path: Path
):
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    recipe = client.post(
        "/recipes", json={"name": "Holiday prints", "steps": STEPS, "saving": SAVING}
    ).json()
    added = client.post(
        "/watch-folders",
        json={"path": str(inbox), "recipe": recipe["id"], "results": "Done"},
    )
    assert added.status_code == 201, added.text
    watch = added.json()
    assert watch["results"] == str(inbox / "Done")
    assert watch["watching"]
    assert watch["recipeName"] == "Holiday prints"

    refused = client.delete(f"/recipes/{recipe['id']}")
    assert refused.status_code == 409
    assert "watch folder" in refused.json()["detail"]

    off = client.put(
        f"/watch-folders/{watch['id']}",
        json={"path": str(inbox), "recipe": recipe["id"], "results": "Done", "watching": False},
    )
    assert off.json()["watching"] is False
    itself = client.put(
        f"/watch-folders/{watch['id']}",
        json={"path": str(inbox), "recipe": recipe["id"], "results": str(inbox)},
    )
    assert itself.status_code == 422
    assert client.delete(f"/watch-folders/{watch['id']}").status_code == 204


def test_a_watch_folders_pictures_join_its_batch_and_a_big_one_waits_for_the_night(
    client: TestClient, tmp_path: Path
):
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    jobs.stop()  # everything waits
    inbox = tmp_path / "To TV"
    inbox.mkdir()
    recipe = client.post(
        "/recipes", json={"name": "Holiday prints", "steps": STEPS, "saving": SAVING}
    ).json()
    added = client.post(
        "/watch-folders", json={"path": str(inbox), "recipe": recipe["id"], "results": "Done"}
    ).json()
    settings = client.get("/settings").json()
    client.put("/settings", json={**settings, "bigBatchesAtNight": True})

    def arrived(name: str) -> Picture:
        path = draw(inbox / name, size=(64, 48))
        stat = path.stat()
        return Picture(
            None, path, name, stat.st_size, 64, 48, version(stat.st_mtime_ns, stat.st_size)
        )

    with closing(db.connect(app.state.paths.database)) as conn:
        watch = watching.found(conn, added["id"])
        assert watch is not None
        first = watching.queue_up(conn, jobs, app.state.ai, watch, [arrived("A.jpg")], NOW)
        more = [arrived(f"B{each}.jpg") for each in range(watching.BIG)]
        again = watching.queue_up(conn, jobs, app.state.ai, watch, more, NOW)
        starts = conn.execute("SELECT starts FROM batches WHERE id = ?", (first,)).fetchone()[0]

    assert again == first  # its new pictures joined the batch not yet done
    assert starts == "tonight"  # more than a daytime batch should hold
    [line] = client.get("/watch-folders").json()
    assert line["ranOn"] == watching.BIG + 1
    queue = client.get("/queue").json()
    assert queue["batch"]["watch"] == str(inbox)
    assert queue["batch"]["into"] == "To TV › Done"  # said from the folder it watches


def test_see_it_first_counts_for_its_batch_wherever_the_new_pictures_go(
    client: TestClient, library: Library
):
    picked = _picked(client, how="folder", folder=library["id"])
    asked = client.post(
        "/batches/samples",
        json={"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING},
    ).json()
    _wait(client)

    elsewhere = {**SAVING, "folder": None}
    reckoned = client.post(
        "/batches/takes",
        json={
            "pictures": picked["pictures"],
            "steps": STEPS,
            "saving": elsewhere,
            "sample": asked["id"],
        },
    ).json()

    assert reckoned["reckoned"]  # where they go doesn't change the pictures made


def test_see_it_first_is_its_batchs_no_longer_once_an_hdr_photos_hdr_is_left_out(
    client: TestClient, library: Library
):
    picked = _picked(client, how="folder", folder=library["id"])
    asked = client.post(
        "/batches/samples",
        json={"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING},
    ).json()
    _wait(client)

    reckoned = client.post(
        "/batches/takes",
        json={
            "pictures": picked["pictures"],
            "steps": STEPS,
            "saving": {**SAVING, "keepHdr": False},
            "sample": asked["id"],
        },
    ).json()

    assert not reckoned["reckoned"]  # its three were written with their gain maps


def test_what_a_batch_takes_counts_the_pictures_see_it_first_made_as_done(
    client: TestClient, library: Library
):
    picked = _picked(client, how="folder", folder=library["id"])
    body = {"pictures": picked["pictures"], "steps": STEPS, "saving": SAVING}
    guessed = client.post("/batches/takes", json=body).json()
    asked = client.post("/batches/samples", json=body).json()
    _wait(client)

    reckoned = client.post("/batches/takes", json={**body, "sample": asked["id"]}).json()

    # All three were seen first, so what's left is keeping them: moments each, not making them.
    assert reckoned["seconds"] == pytest.approx(3 * KEPT_SECONDS)
    assert guessed["seconds"] > 0


CUT_OUT = [{"step": "cutout", "quality": "fast", "behind": "nothing"}]
AS_PNG = {"how": "new", "format": "PNG", "folder": "Cut-outs"}


def test_cutting_out_the_subject_is_a_step_said_first_and_reckoned_in_what_it_takes(
    client: TestClient, library: Library
):
    picked = _picked(client, how="ticked", ids=[library["ids"]["Warm dunes.jpg"]])
    takes = client.post(
        "/batches/takes",
        json={"pictures": picked["pictures"], "steps": [*STEPS, *CUT_OUT], "saving": AS_PNG},
    ).json()

    assert [(each["kind"], each["title"]) for each in takes["words"]] == [
        ("cutout", "Cut out the subject"),
        ("size", "Make it for a screen"),
        ("save", "Save"),
    ]
    assert takes["words"][0]["detail"] == "Fast, with nothing behind it"
    assert takes["words"][0]["chip"] == "Cut out the subject"
    assert takes["words"][-1]["chip"] == "PNG into Cut-outs"
    assert takes["seconds"] > 0
    assert takes["needs"] == []  # Fast's model ships inside Mado


def test_the_queue_says_which_step_a_picture_being_made_is_at(
    client: TestClient, library: Library, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app: Any = client.app
    with_fix_models(monkeypatch, app.state.ai, tmp_path / "models")  # as if SCUNet is here
    jobs: Jobs = app.state.jobs
    jobs.stop()  # nothing is made: each picture's stage is set by hand below
    picked = _picked(client, how="ticked", ids=[library["ids"]["Warm dunes.jpg"]])
    fix = {"step": "fix", "noise": {"strength": 1}, "blur": None, "jpeg": None, "dark": None}
    batch = _put_in(client, picked, steps=[*STEPS, fix, *CUT_OUT], saving=AS_PNG)
    said: dict[str, str] = {}
    for stage in ("reading", "editing", "fixing", "making", "saving"):
        with closing(db.connect(app.state.paths.database)) as conn, conn:
            conn.execute(
                "UPDATE jobs SET state = 'running', stage = ? WHERE batch_id = ?",
                (stage, batch["id"]),
            )
        rows = client.get("/queue").json()["rows"]
        said[stage] = rows[0]["step"]

    assert said == {
        "reading": "Cut out the subject 1/4",
        "editing": "Cut out the subject 1/4",
        "fixing": "Fix 2/4",
        "making": "Make it for a screen 3/4",
        "saving": "Save 4/4",
    }


def test_a_batch_of_cut_outs_keeps_their_nothing_as_png_and_history_says_what_was_done(
    client: TestClient, library: Library
):
    picked = _picked(client, how="ticked", ids=[library["ids"]["Still lake.png"]])
    body = {
        "source": picked["source"],
        "shared": picked["shared"],
        "pictures": picked["pictures"],
        "steps": CUT_OUT,
        "starts": "now",
    }

    refused = client.post("/batches", json={**body, "saving": SAVING})
    response = client.post("/batches", json={**body, "saving": AS_PNG})
    _wait(client)

    assert refused.status_code == 422
    assert "PNG or WebP" in refused.json()["detail"]
    assert response.status_code == 201, response.text
    made = library["folder"] / "Cut-outs" / "Still lake (Cut out).png"
    with Image.open(made) as saved:
        assert saved.mode == "RGBA"
    line = client.get("/history").json()["batches"][0]
    assert line["edit"] == "cut out the subject"
    app: Any = client.app
    assert not list((app.state.paths.cache / "edits").rglob("*.png"))  # no mask kept for them


def test_a_recipe_of_cut_outs_for_cards_is_kept_and_said_as_its_line(client: TestClient):
    kept = client.post(
        "/recipes", json={"name": "Cut-outs for cards", "steps": CUT_OUT, "saving": AS_PNG}
    )
    refused = client.post(
        "/recipes", json={"name": "Cut-outs as JPEG", "steps": CUT_OUT, "saving": SAVING}
    )

    assert kept.status_code == 201, kept.text
    assert [each["chip"] for each in kept.json()["words"]] == [
        "Cut out the subject",
        "PNG into Cut-outs",
    ]
    assert refused.status_code == 422
