"""Making a picture for a size through the API, end to end on the processor with the shipped Fast
model and tiny made-up pictures: the sizes, the owner's screens, the plan, a preview, the name it
would be saved as, the job, and History's undo."""

import io
import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from mado import db, history, making
from mado.config import DataPaths
from mado.jobs import Jobs
from mado.pictures import InUseError, PictureGoneError
from mado.quarantine import MoveError, Quarantine
from tests.conftest import add, made
from tests.drawn import EXIF_IFD, GPS_IFD, TAKEN, draw, exif

type Library = dict[str, Any]

SMALL = "other-256x192"  # a size the processor makes in a moment


@pytest.fixture
def library(client: TestClient, tmp_path: Path) -> Library:
    """Phone: a made-up photo from a camera, with where it was taken, and a drawing."""
    phone = tmp_path / "Phone"
    described = exif(taken="2026:11:12 18:42:07", make="Pixelworks", model="PW-7", where=True)
    draw(phone / "Harbour at dusk.jpg", size=(96, 72), described=described)
    draw(phone / "Sunny hill.png", size=(96, 72))
    add(client, phone)
    listed = client.get("/pictures").json()["pictures"]
    return {"folder": phone, "ids": {item["name"]: item["id"] for item in listed}}


def _recipe(**overrides: object) -> dict[str, object]:
    """A recipe of one step, its size: the one the processor makes in a moment, unless said."""
    return {"size": {"size": SMALL, **overrides}}


def test_the_sizes_are_the_devices_the_prints_and_the_owners_screens(client: TestClient):
    sizes = client.get("/sizes").json()

    assert [size["name"] for size in sizes["screens"]] == [
        "Phone",
        "Tablet",
        "Laptop",
        "Monitor 4K",
        "Ultrawide",
        "TV 8K",
    ]
    assert sizes["screens"][-1] | {} == {
        "id": "tv-8k",
        "name": "TV 8K",
        "width": 7680,
        "height": 4320,
        "group": "screens",
        "purpose": "tv",
        "label": "TV 8K",
    }
    assert [size["name"] for size in sizes["prints"]] == ["10 × 15 cm", "A4", "A3"]
    assert sizes["yours"] == []


def test_this_pcs_screens_are_remembered(client: TestClient):
    seen = client.post(
        "/screens",
        json={
            "seen": [{"width": 3440, "height": 1440, "main": True}, {"width": 2560, "height": 1600}]
        },
    )

    assert [(each["name"], each["label"]) for each in seen.json()] == [
        ("Main screen", "3440 × 1440"),
        ("Screen 2", "2560 × 1600"),
    ]
    assert [each["id"] for each in client.get("/sizes").json()["yours"]] == [
        "yours-3440x1440",
        "yours-2560x1600",
    ]


def test_a_plan_says_the_shape_the_model_the_time_and_how_it_would_be_saved(
    client: TestClient, library: Library
):
    plan = client.post(
        f"/pictures/{library['ids']['Harbour at dusk.jpg']}/plan", json=_recipe(size="tv-8k")
    ).json()

    assert (plan["width"], plan["height"]) == (7680, 4320)
    assert plan["note"] == (
        "A TV is 16:9 and this picture is 4:3, so a little of the top and bottom goes."
    )
    assert plan["kept"]["width"] == pytest.approx(1.0)
    assert plan["kept"]["height"] == pytest.approx(0.75)
    assert plan["kind"] == "photo"  # it has a camera
    assert plan["kindGuessed"]
    assert plan["quality"] == "fast"  # the processor starts on Fast
    assert plan["method"] == "ai"
    assert plan["model"] == "Real-ESRGAN general"
    assert plan["place"] == "processor"
    assert plan["seconds"] > 0
    assert plan["format"] == "JPEG"
    assert plan["formatQuality"] == 95
    assert plan["fits"] == "What every TV shows."
    assert plan["needs"] == []
    assert plan["warning"] is not None  # 80 times bigger: it would look painted


def test_best_for_photos_and_extending_wait_for_their_downloads(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]

    best = client.post(f"/pictures/{picture}/plan", json=_recipe(quality="best")).json()
    extend = client.post(
        f"/pictures/{picture}/plan", json=_recipe(size="tv-8k", shape="extend")
    ).json()

    assert [need["id"] for need in best["needs"]] == ["realesrgan-x4plus"]
    assert best["needs"][0]["size"] == 67_074_951 + 11_350 + 1_519
    assert [need["id"] for need in extend["needs"]] == ["lama"]
    assert (
        extend["note"] == "A TV is 16:9 and this picture is 4:3, so Mado draws more at the sides."
    )
    refused = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(quality="best"), "saving": {"format": "JPEG"}},
    )
    assert refused.status_code == 409


def test_a_preview_shows_a_part_at_full_detail_before_and_after(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    region = {"x": 64, "y": 32, "width": 96, "height": 80}

    after = client.post(
        f"/pictures/{picture}/preview", json={"recipe": _recipe(), "region": region}
    )
    before = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": _recipe(), "region": region, "side": "before"},
    )

    assert after.status_code == 200, after.text
    assert after.headers["content-type"] == "image/webp"
    assert float(after.headers["x-made-in"]) >= 0
    assert Image.open(io.BytesIO(after.content)).size == (96, 80)
    assert Image.open(io.BytesIO(before.content)).size == (96, 80)
    fitted = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": _recipe(), "fit": {"width": 128, "height": 128}},
    )
    assert Image.open(io.BytesIO(fitted.content)).size == (128, 96)


def test_the_name_a_new_picture_would_have_says_when_its_taken(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    ask = {"recipe": _recipe(size="tv-8k"), "format": "JPEG", "quality": 95}

    first = client.post(f"/pictures/{picture}/saving", json=ask).json()
    draw(library["folder"] / "Harbour at dusk (TV 8K).jpg")
    second = client.post(f"/pictures/{picture}/saving", json=ask).json()

    assert first["name"] == "Harbour at dusk (TV 8K).jpg"
    assert first["taken"] is None
    assert second["name"] == "Harbour at dusk (TV 8K) (2).jpg"
    assert second["taken"] == "Harbour at dusk (TV 8K).jpg"
    assert second["takenAt"] is not None
    assert second["bytes"] == pytest.approx(18e6, rel=0.1)


def test_a_new_picture_is_made_beside_its_original_keeping_its_date_but_not_its_place(
    client: TestClient, library: Library, conn: sqlite3.Connection
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"format": "JPEG", "quality": 92}},
    )

    assert job.status_code == 202, job.text
    assert job.json()["madeFor"] == "256 × 192"
    done = made(client, job.json())
    assert done["state"] == "done", done["problem"]
    saved = library["folder"] / "Harbour at dusk (256 × 192).jpg"
    assert done["result"] == str(saved)
    assert done["resultName"] == saved.name
    assert done["progress"] == 1
    with Image.open(saved) as written:
        assert written.size == (256, 192)
        found = written.getexif()
        assert found.get_ifd(EXIF_IFD)[TAKEN] == "2026:11:12 18:42:07"
        assert not found.get_ifd(GPS_IFD)  # the location stays out unless it's kept
    assert (library["folder"] / "Harbour at dusk.jpg").is_file()  # the original as it was
    line = client.get("/history").json()["entries"][0]
    assert line["kind"] == "made"
    assert line["madeFor"] == "256 × 192"
    assert line["canUndo"]
    learned = conn.execute("SELECT value FROM settings WHERE key = 'pc_speeds'").fetchone()
    assert learned is not None  # the processor's speed, learned from this picture


def test_taking_a_new_picture_away_and_putting_it_back_from_history(
    client: TestClient, library: Library
):
    picture = library["ids"]["Sunny hill.png"]
    job = client.post(
        f"/pictures/{picture}/make", json={"recipe": _recipe(), "saving": {"format": "PNG"}}
    ).json()
    done = made(client, job)
    saved = Path(done["result"])
    line = client.get("/history").json()["entries"][0]

    taken = client.post(f"/history/{line['id']}/undo").json()

    assert not saved.exists()
    assert taken["canRedo"]
    assert taken["asideUntil"] is not None
    back = client.post(f"/history/{line['id']}/redo").json()
    assert saved.is_file()
    assert back["canUndo"]


def test_replacing_the_original_sets_it_aside_and_history_puts_it_back(
    client: TestClient, library: Library, quarantine: Quarantine
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    original = library["folder"] / "Harbour at dusk.jpg"
    before = original.read_bytes()

    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"how": "replace", "format": "JPEG", "quality": 90}},
    ).json()
    done = made(client, job)

    assert done["state"] == "done", done["problem"]
    assert done["result"] == str(original)
    with Image.open(original) as replaced:
        assert replaced.size == (256, 192)
    line = client.get("/history").json()["entries"][0]
    assert line["kind"] == "replaced"
    aside = Path(line["aside"])
    assert quarantine.holds(aside)
    assert aside.read_bytes() == before
    assert client.get("/quarantine").json()[0]["bytes"] == len(before)

    put_back = client.post(f"/history/{line['id']}/undo").json()

    assert original.read_bytes() == before
    assert put_back["aside"] is not None  # the picture made waits in quarantine now
    assert not put_back["canUndo"]
    assert put_back["canRedo"]  # "Replace it again"
    again = client.post(f"/history/{line['id']}/redo").json()
    with Image.open(original) as replaced:
        assert replaced.size == (256, 192)
    assert Path(again["aside"]).read_bytes() == before
    assert again["canUndo"]


def test_saving_this_way_always_becomes_what_save_offers_first(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"format": "JPEG", "always": True, "how": "new"}},
    ).json()
    made(client, job)

    assert client.get("/settings").json()["saveFirst"] == "new"


def test_a_job_can_be_cancelled_and_one_thats_over_says_so(client: TestClient, library: Library):
    picture = library["ids"]["Harbour at dusk.jpg"]
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"format": "JPEG"}},
    ).json()

    client.post(f"/jobs/{job['id']}/cancel")
    over = made(client, job)

    assert over["state"] in ("cancelled", "done")  # it may have finished first
    assert client.post("/jobs/999/cancel").status_code == 404
    listed = client.get(f"/jobs?picture={picture}").json()
    assert listed[0]["id"] == job["id"]
    assert client.get("/jobs?active=true").json() == []


def test_a_size_mado_cant_make_is_refused(client: TestClient, library: Library):
    picture = library["ids"]["Harbour at dusk.jpg"]

    refused = client.post(f"/pictures/{picture}/plan", json=_recipe(size="other-5x5"))

    assert refused.status_code == 422
    assert "too small" in refused.json()["detail"]


def test_this_pc_says_where_the_models_run_and_what_each_kind_starts_on(client: TestClient):
    pc = client.get("/pc").json()

    assert pc["place"] == "card"  # nothing tested yet: the card, till a test says otherwise
    assert pc["onCard"] is None
    assert pc["startsOn"] == {"photo": "fast", "drawing": "best"}  # Best for photos: a download
    assert [(each["kind"], each["quality"]) for each in pc["abilities"]] == [
        ("photo", "fast"),
        ("photo", "best"),
        ("drawing", "fast"),
        ("drawing", "best"),
    ]


def _lines(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM history").fetchall()


@pytest.mark.parametrize("how", ["new", "replace"])
def test_history_has_its_line_before_any_picture_moves(
    client: TestClient,
    library: Library,
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    how: str,
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    seen: list[int] = []
    real = making.move

    def watched(source: Path, target: Path) -> None:
        seen.append(len(_lines(conn)))
        real(source, target)

    monkeypatch.setattr("mado.making.move", watched)
    monkeypatch.setattr("mado.quarantine.move", watched)
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"how": how, "format": "JPEG"}},
    ).json()

    assert made(client, job)["state"] == "done"
    assert seen
    assert all(count == 1 for count in seen)  # a crash at any move finds the line


def test_an_undo_waits_till_the_picture_being_saved_is_in_place(
    client: TestClient,
    library: Library,
    paths: DataPaths,
    quarantine: Quarantine,
    monkeypatch: pytest.MonkeyPatch,
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    real = making.move
    asked: list[threading.Thread] = []
    undone: list[str] = []

    def undo(line: int) -> None:
        with closing(db.connect(paths.database)) as own:
            try:
                history.undo(own, quarantine, line, datetime.now().astimezone())
                undone.append("taken away")
            except history.UndoError as error:
                undone.append(str(error))

    def moving(source: Path, target: Path) -> None:
        if source.name.endswith(".mado-partial") and not asked:
            with closing(db.connect(paths.database)) as own:
                line: int = own.execute("SELECT id FROM history").fetchone()["id"]
            asked.append(threading.Thread(target=undo, args=(line,)))
            asked[0].start()  # Take it away, pressed as the picture goes into its place
            asked[0].join(0.3)
        real(source, target)

    monkeypatch.setattr("mado.making.move", moving)
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"how": "new", "format": "JPEG"}},
    ).json()
    assert made(client, job)["state"] == "done"
    asked[0].join(10)

    assert undone == ["taken away"]  # once it was in place, not before


@pytest.mark.parametrize("how", ["new", "replace"])
def test_a_made_picture_that_cant_go_in_leaves_the_original_and_no_line(
    client: TestClient,
    library: Library,
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    how: str,
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    original = library["folder"] / "Harbour at dusk.jpg"
    before = original.read_bytes()
    real = making.move

    def refused(source: Path, target: Path) -> None:
        if source.name.endswith(".mado-partial"):
            raise MoveError("Another app has the folder open.")
        real(source, target)

    monkeypatch.setattr("mado.making.move", refused)
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"how": how, "format": "JPEG"}},
    ).json()
    done = made(client, job)

    assert done["state"] == "failed"
    assert "Another app has the folder open." in done["problem"]
    assert original.read_bytes() == before
    assert _lines(conn) == []
    assert sorted(each.name for each in library["folder"].iterdir()) == [
        "Harbour at dusk.jpg",
        "Sunny hill.png",
    ]


@pytest.mark.parametrize("step", ["decode", "write"], ids=["reading", "saving"])
def test_a_drive_unplugged_as_a_picture_is_made_says_so_and_saves_nothing(
    client: TestClient,
    library: Library,
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    step: str,
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    original = library["folder"] / "Harbour at dusk.jpg"
    before = original.read_bytes()
    unplugged = {"yes": False}
    real = getattr(making, step)

    def unplugging(*args: Any, **kwargs: Any) -> Any:
        if threading.current_thread().name != "jobs":  # a preview's or a plan's
            return real(*args, **kwargs)
        unplugged["yes"] = True
        if step == "decode":
            raise PictureGoneError(original)  # as decode says of a file whose drive went
        raise OSError(21, "The device is not ready")

    monkeypatch.setattr(f"mado.making.{step}", unplugging)

    def there(_path: Path) -> bool:
        return not unplugged["yes"]

    monkeypatch.setattr("mado.making.drive_there", there)
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"how": "new", "format": "JPEG"}},
    ).json()
    done = made(client, job)

    drive = original.drive.upper()
    assert done["state"] == "failed"
    assert done["problem"] == (
        f"{drive} isn't connected any more, so nothing was saved and the original is as it was. "
        "Connect it and try again."
    )
    assert original.read_bytes() == before
    assert _lines(conn) == []


def _cancel_running(app: FastAPI, paths: DataPaths) -> None:
    """The owner pressing Cancel on the job under way, from the worker's own thread."""
    jobs: Jobs = app.state.jobs
    with closing(db.connect(paths.database)) as own:
        running = own.execute("SELECT id FROM jobs WHERE state = 'running'").fetchone()
        assert jobs.cancel(own, running["id"])


@pytest.mark.parametrize(
    ("step", "kind"), [("make", None), ("decode", "pixels")], ids=["last tile", "no model"]
)
def test_cancel_as_a_picture_is_made_saves_nothing(
    app: FastAPI,
    client: TestClient,
    library: Library,
    conn: sqlite3.Connection,
    paths: DataPaths,
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    kind: str | None,
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    real = getattr(making, step)

    def then_cancelled(*args: Any, **kwargs: Any) -> Any:
        done = real(*args, **kwargs)
        if threading.current_thread().name == "jobs":  # not a preview's or a plan's
            _cancel_running(app, paths)  # after its last check for Cancel
        return done

    monkeypatch.setattr(f"mado.making.{step}", then_cancelled)
    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(kind=kind), "saving": {"format": "JPEG"}},
    ).json()

    assert made(client, job)["state"] == "cancelled"
    assert _lines(conn) == []
    assert sorted(each.name for each in library["folder"].iterdir()) == [
        "Harbour at dusk.jpg",
        "Sunny hill.png",
    ]


def test_only_a_preview_that_needs_the_model_waits_for_its_download(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    region = {"x": 64, "y": 32, "width": 96, "height": 80}
    best = _recipe(quality="best")  # a download, not fetched here

    before = client.post(
        f"/pictures/{picture}/preview", json={"recipe": best, "region": region, "side": "before"}
    )
    fitted = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": best, "fit": {"width": 128, "height": 128}},
    )
    after = client.post(f"/pictures/{picture}/preview", json={"recipe": best, "region": region})
    extended = client.post(
        f"/pictures/{picture}/preview",
        json={"recipe": _recipe(shape="extend", size="tv-8k"), "region": region, "side": "before"},
    )

    assert before.status_code == 200, before.text
    assert fitted.status_code == 200, fitted.text
    assert after.status_code == 409
    assert extended.status_code == 409  # extending needs LaMa on either side


def test_a_job_keeps_what_the_plan_decided_so_it_makes_what_was_previewed(
    client: TestClient, library: Library, conn: sqlite3.Connection
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    plan = client.post(f"/pictures/{picture}/plan", json=_recipe()).json()

    job = client.post(
        f"/pictures/{picture}/make", json={"recipe": _recipe(), "saving": {"format": "JPEG"}}
    ).json()
    made(client, job)

    kept = json.loads(
        conn.execute("SELECT recipe FROM jobs WHERE id = ?", (job["id"],)).fetchone()[0]
    )["recipe"]["size"]
    assert kept["kind"] == plan["kind"]
    assert kept["quality"] == plan["quality"]
    assert kept["focus"] == plan["focus"]


def test_screens_the_window_couldnt_have_are_refused(client: TestClient):
    huge = client.post("/screens", json={"seen": [{"width": 10**9, "height": 1080}]})
    many = client.post("/screens", json={"seen": [{"width": 1920, "height": 1080}] * 100})

    assert huge.status_code == 422
    assert many.status_code == 422


def test_a_save_that_cant_replace_an_original_open_in_another_app_waits_and_tries_again(
    client: TestClient, library: Library
):
    picture = library["ids"]["Harbour at dusk.jpg"]
    original = library["folder"] / "Harbour at dusk.jpg"
    before = original.read_bytes()
    app: Any = client.app
    jobs: Jobs = app.state.jobs

    with original.open("rb"):  # held open, as another app would
        job = client.post(
            f"/pictures/{picture}/make",
            json={"recipe": _recipe(), "saving": {"how": "replace", "format": "JPEG"}},
        ).json()
        assert jobs.wait(120)
        waiting = client.get(f"/jobs/{job['id']}").json()
        held = client.get("/jobs/held").json()

    assert waiting["state"] == "queued"
    assert waiting["heldUntil"] is not None
    assert "open in another app. Mado can't replace it" in waiting["problem"]
    assert [(each["job"], each["name"], each["verb"]) for each in held] == [
        (job["id"], "Harbour at dusk.jpg", "replace")
    ]
    assert original.read_bytes() == before
    assert client.get("/history").json()["entries"] == []

    assert client.post(f"/jobs/{job['id']}/try-now").status_code == 204
    done = made(client, job)

    assert done["state"] == "done", done["problem"]
    assert client.get("/jobs/held").json() == []
    assert client.post(f"/jobs/{job['id']}/try-now").status_code == 409


def test_a_save_that_cant_read_its_picture_waits_and_can_be_skipped(
    client: TestClient, library: Library, monkeypatch: pytest.MonkeyPatch
):
    decode = making.decode

    def in_use(path: Path, *args: Any, **options: Any) -> Image.Image:
        if threading.current_thread().name != "jobs":  # the Size tab's own look at it
            return decode(path, *args, **options)
        raise InUseError(f"{path.name} is open in another app, so Mado can't read it.")

    monkeypatch.setattr(making, "decode", in_use)
    picture = library["ids"]["Sunny hill.png"]
    app: Any = client.app
    jobs: Jobs = app.state.jobs

    job = client.post(
        f"/pictures/{picture}/make",
        json={"recipe": _recipe(), "saving": {"how": "new", "format": "JPEG"}},
    ).json()
    assert jobs.wait(120)
    [held] = client.get("/jobs/held").json()

    assert (held["name"], held["verb"], held["batch"]) == ("Sunny hill.png", "read", None)
    assert client.post(f"/jobs/{job['id']}/skip").status_code == 204
    skipped = client.get(f"/jobs/{job['id']}").json()
    assert skipped["state"] == "failed"
    assert skipped["problem"].startswith("You skipped Sunny hill.png")
    assert client.post(f"/jobs/{job['id']}/skip").status_code == 409


def test_a_save_that_cant_replace_its_original_doesnt_make_it_first(
    client: TestClient, library: Library, monkeypatch: pytest.MonkeyPatch
):
    made: list[str] = []
    decode = making.decode

    def counted(path: Path, *args: Any, **options: Any) -> Image.Image:
        if threading.current_thread().name == "jobs":
            made.append(path.name)
        return decode(path, *args, **options)

    monkeypatch.setattr(making, "decode", counted)
    picture = library["ids"]["Harbour at dusk.jpg"]
    original = library["folder"] / "Harbour at dusk.jpg"
    app: Any = client.app
    jobs: Jobs = app.state.jobs

    with original.open("rb"):  # held open, as another app would
        job = client.post(
            f"/pictures/{picture}/make",
            json={"recipe": _recipe(), "saving": {"how": "replace", "format": "JPEG"}},
        ).json()
        assert jobs.wait(120)

    assert client.get(f"/jobs/{job['id']}").json()["heldUntil"] is not None
    assert made == []  # not made on the card for nothing, every 30 seconds
