"""Pictures from anywhere through the API: one picture outside the library opening on its page,
several or a folder opening Many at once, what's left out and why, a picture in a quarantine,
saving one, a picture pasted from the clipboard, and outside pictures kept out of the library."""

import io
import json
import os
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db, outside, pasting
from mado.config import DataPaths
from mado.export import export_data
from tests.conftest import add, made
from tests.drawn import draw, exif, picture, scene

SMALL = "other-256x192"  # a size the processor makes in a moment


def opened(client: TestClient, *paths: Path | str, how: str = "opened") -> dict[str, Any]:
    response = client.post("/open", json={"paths": [str(path) for path in paths], "how": how})
    assert response.status_code == 200, response.text
    return response.json()


def png(size: tuple[int, int] = (80, 60), colour: tuple[int, int, int] = (40, 90, 160)) -> bytes:
    written = io.BytesIO()
    Image.new("RGB", size, colour).save(written, format="PNG")
    return written.getvalue()


def paste(client: TestClient, data: bytes) -> Any:
    return client.post("/pasted", content=data, headers={"Content-Type": "image/png"})


def test_one_picture_outside_the_library_opens_on_its_own_page(client: TestClient, tmp_path: Path):
    pier = draw(tmp_path / "Elsewhere" / "Pier at dawn.jpg", described=exif(make="Pixelworks"))

    found = opened(client, pier)

    page = found["picture"]
    assert found["picked"] is None
    assert found["leftOut"] == []
    assert (page["name"], page["state"], page["width"], page["height"]) == (
        "Pier at dawn.jpg",
        "ready",
        64,
        48,
    )
    assert (page["outside"], page["folderId"], page["folder"]) == (
        True,
        None,
        str(tmp_path / "Elsewhere"),
    )
    assert (page["pasted"], page["aside"], page["savesTo"]) == (False, False, None)
    shown = client.get(f"/pictures/{page['id']}")
    assert shown.status_code == 200
    assert shown.json()["outside"] is True
    assert client.get(f"/pictures/{page['id']}/thumbnail").status_code == 200
    assert client.get(f"/pictures/{page['id']}/neighbours").json() == {"before": [], "after": []}


def test_the_same_picture_opened_twice_is_one_page(client: TestClient, tmp_path: Path):
    pier = draw(tmp_path / "Elsewhere" / "Pier.jpg")

    first = opened(client, pier)["picture"]["id"]
    again = opened(client, str(pier).upper(), how="dropped")["picture"]["id"]

    assert again == first


def test_an_outside_picture_is_never_listed_counted_or_exported(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    (tmp_path / "Phone").mkdir()
    add(client, tmp_path / "Phone")  # an empty library folder
    opened(client, draw(tmp_path / "Elsewhere" / "Pier.jpg"))

    assert client.get("/pictures").json()["total"] == 0
    library = client.get("/library").json()
    assert (library["pictures"], library["size"], library["reading"]) == (0, 0, 0)
    assert client.get("/scan").json()["toRead"] == 0
    made_zip = export_data(paths, tmp_path, datetime(2026, 11, 23, 9, 0).astimezone())
    assert made_zip is not None
    with zipfile.ZipFile(made_zip) as archive:
        assert "Pier.jpg" not in archive.read("pictures.csv").decode()


def test_a_picture_in_a_library_folder_is_simply_that_library_picture(
    client: TestClient, tmp_path: Path
):
    phone = tmp_path / "Phone"
    draw(phone / "Harbour.jpg")
    add(client, phone)
    listed = client.get("/pictures").json()["pictures"][0]

    found = opened(client, phone / "Harbour.jpg")["picture"]

    assert (found["id"], found["outside"], found["folderId"]) == (listed["id"], False, 1)
    # One not read yet (just copied there) is the library's at once, as a scan would find it.
    draw(phone / "2026" / "Fresh.jpg")
    fresh = opened(client, phone / "2026" / "Fresh.jpg")["picture"]
    assert (fresh["outside"], fresh["dir"], fresh["state"]) == (False, "2026", "ready")


def test_its_folder_added_later_makes_it_the_librarys_with_its_jobs_and_history(
    client: TestClient, tmp_path: Path
):
    folder = tmp_path / "Trip"
    pier = draw(folder / "Pier.jpg", size=(96, 72))
    page = opened(client, pier)["picture"]
    job = client.post(
        f"/pictures/{page['id']}/make",
        json={"recipe": {"size": {"size": SMALL}}, "saving": {"format": "JPEG"}},
    ).json()
    done = made(client, job)
    assert done["state"] == "done", done

    add(client, folder)

    listed = {item["name"]: item["id"] for item in client.get("/pictures").json()["pictures"]}
    assert listed["Pier.jpg"] == page["id"]
    assert client.get(f"/pictures/{page['id']}").json()["outside"] is False
    jobs = client.get(f"/jobs?picture={page['id']}").json()
    assert [each["id"] for each in jobs] == [job["id"]]
    assert client.get("/scan").json()["added"] == 2  # it, and the one made beside it
    history = client.get("/history").json()["entries"]
    assert [entry["name"] for entry in history] == ["Pier.jpg"]


def test_several_pictures_or_a_folder_open_many_at_once(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Holiday"
    first, second = draw(folder / "Dunes.jpg"), draw(folder / "Lake.png")

    found = opened(client, first, second)
    assert found["picture"] is None
    assert [each["name"] for each in found["picked"]["pictures"]] == ["Dunes.jpg", "Lake.png"]
    assert found["picked"]["words"] == "opened from Holiday"

    pasted = opened(client, folder, how="pasted")
    assert len(pasted["picked"]["pictures"]) == 2
    assert pasted["picked"]["words"] == "pasted from Holiday"


def test_one_picture_among_other_files_opens_and_says_what_was_left_out(
    client: TestClient, tmp_path: Path
):
    pier = draw(tmp_path / "Mixed" / "Pier.jpg")
    notes = tmp_path / "Mixed" / "notes.txt"
    notes.write_text("made up", encoding="utf-8")

    found = opened(client, pier, notes, tmp_path / "Mixed" / "Gone.jpg")

    assert found["picture"]["name"] == "Pier.jpg"
    assert [(each["name"], each["why"].split(".")[0]) for each in found["leftOut"]] == [
        ("notes.txt", "notes"),
        ("Gone.jpg", "Gone"),
    ]
    assert "isn't a picture Mado reads" in found["leftOut"][0]["why"]
    assert "moved or deleted" in found["leftOut"][1]["why"]


def test_what_isnt_a_picture_or_isnt_there_is_said_not_opened(client: TestClient, tmp_path: Path):
    notes = tmp_path / "notes.txt"
    notes.write_text("made up", encoding="utf-8")

    not_picture = client.post("/open", json={"paths": [str(notes)]})
    gone = client.post("/open", json={"paths": [str(tmp_path / "Gone.jpg")]})
    unplugged = client.post("/open", json={"paths": [r"Q:\Trip\Pier.jpg"]})

    assert not_picture.status_code == 422
    assert "JPEG, PNG, HEIC, WebP, AVIF, TIFF, BMP and GIF" in not_picture.json()["detail"]
    assert gone.status_code == 404
    assert "moved or deleted" in gone.json()["detail"]
    assert unplugged.status_code == 404
    assert unplugged.json()["detail"] == (
        "Pier.jpg is on Q:, which isn't connected. Connect it, then open it again."
    )


def test_an_outside_pictures_page_shows_its_file_as_it_is_now(client: TestClient, tmp_path: Path):
    pier = draw(tmp_path / "Elsewhere" / "Pier.jpg", size=(64, 48))
    page = opened(client, pier)["picture"]

    draw(pier, size=(96, 72))  # changed elsewhere, or replaced by a Save
    os.utime(pier, (pier.stat().st_atime, pier.stat().st_mtime + 30))
    now = client.get(f"/pictures/{page['id']}").json()

    assert (now["width"], now["height"]) == (96, 72)
    assert now["version"] != page["version"]
    pier.unlink()
    gone = client.get(f"/pictures/{page['id']}")
    assert gone.status_code == 404
    assert gone.json()["detail"] == "Pier.jpg isn't there any more: it was moved or deleted."


def test_several_paths_on_a_drive_not_connected_say_so(client: TestClient):
    asked = client.post("/open", json={"paths": [r"Q:\Trip\a.jpg", r"Q:\Trip\b.jpg"]})

    assert asked.status_code == 404
    assert asked.json()["detail"] == (
        "Those are on Q:, which isn't connected. Connect it, then open them again."
    )


def test_a_file_in_mados_own_folder_is_opened_only_when_its_a_paste(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    # A paste whose record was let go, dropped back on the window: a paste again.
    kept = paths.pasted / "Pasted 2026-11-20 09.00.png"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(png())
    again = opened(client, kept)["picture"]
    assert (again["pasted"], again["outside"]) == (True, True)
    # One of Mado's own files, never the owner's: not opened.
    cached = paths.cache / "pictures" / "0" / "7-1-thumbnail.png"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(png())
    refused = client.post("/open", json={"paths": [str(cached)]})
    assert refused.status_code == 422
    assert "Mado's own" in refused.json()["detail"]


def test_a_paste_stays_a_paste_when_mados_data_folder_is_in_the_library(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    page = paste(client, png()).json()
    add(client, tmp_path)  # the folder holding Mado's data folder

    again = opened(client, page["path"])["picture"]

    assert (again["id"], again["pasted"], again["outside"]) == (page["id"], True, True)


def test_a_pasted_picture_can_be_saved_as_it_is(client: TestClient, tmp_path: Path):
    page = paste(client, png((96, 72))).json()
    nothing = {"edit": None, "size": None, "look": None}
    into = tmp_path / "Saved"
    into.mkdir()

    plan = client.post(f"/pictures/{page['id']}/plan", json=nothing)
    name = client.post(
        f"/pictures/{page['id']}/saving",
        json={"recipe": nothing, "format": "PNG", "folder": str(into)},
    ).json()
    job = client.post(
        f"/pictures/{page['id']}/make",
        json={"recipe": nothing, "saving": {"format": "PNG", "folder": str(into)}},
    ).json()

    assert plan.status_code == 200
    assert (plan.json()["width"], plan.json()["height"]) == (96, 72)
    assert name["name"] == page["name"]
    done = made(client, job)
    assert done["state"] == "done", done
    assert [each.name for each in into.iterdir()] == [page["name"]]
    assert Image.open(into / page["name"]).size == (96, 72)


def test_a_library_picture_still_needs_something_to_make(client: TestClient, tmp_path: Path):
    pier = draw(tmp_path / "Elsewhere" / "Pier.jpg", size=(96, 72))
    page = opened(client, pier)["picture"]

    refused = client.post(
        f"/pictures/{page['id']}/make",
        json={"recipe": {"edit": None, "size": None, "look": None}, "saving": {"format": "PNG"}},
    )

    assert refused.status_code == 422


def test_paths_are_taken_as_given_with_spaces_quotes_and_other_alphabets(
    client: TestClient, tmp_path: Path
):
    night = draw(tmp_path / "Fotos del viaje" / "Ōsaka 夜景.png")

    found = opened(client, f'  "{night}"  ')

    assert found["picture"]["name"] == "Ōsaka 夜景.png"


def test_a_long_path_opens(client: TestClient, tmp_path: Path):
    deep = tmp_path / ("a long folder name " * 6).strip() / ("another long one " * 6).strip()
    target = Path(rf"\\?\{deep}") / "Pier at dawn.jpg"
    target.parent.mkdir(parents=True)
    Image.new("RGB", (32, 24), (10, 20, 30)).save(target, format="JPEG")
    assert len(str(deep / "Pier at dawn.jpg")) > 260

    found = opened(client, deep / "Pier at dawn.jpg")

    assert found["picture"]["name"] == "Pier at dawn.jpg"
    assert client.get(f"/pictures/{found['picture']['id']}/view").status_code == 200


def test_camera_raw_and_a_picture_that_wont_open_open_on_their_page_as_they_are(
    client: TestClient, tmp_path: Path
):
    raw = tmp_path / "Camera" / "IMG_2041.CR3"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"made-up camera raw")
    broken = tmp_path / "Camera" / "Half.jpg"
    broken.write_bytes(b"\xff\xd8\xff not really a picture")

    assert opened(client, raw)["picture"]["state"] == "raw"
    half = opened(client, broken)["picture"]
    assert half["state"] == "broken"
    assert half["problem"]


def test_a_picture_in_a_quarantine_opens_to_look_at_only(client: TestClient, tmp_path: Path):
    aside = draw(tmp_path / "Mado quarantine" / "2026-11-22" / "Pier.jpg", size=(96, 72))

    page = opened(client, aside)["picture"]

    assert page["aside"] is True
    assert client.get(f"/pictures/{page['id']}/view").status_code == 200
    refused = client.post(
        f"/pictures/{page['id']}/make",
        json={"recipe": {"size": {"size": SMALL}}, "saving": {"format": "JPEG"}},
    )
    assert refused.status_code == 409
    assert "quarantine" in refused.json()["detail"]
    assert sorted(path.name for path in aside.parent.iterdir()) == ["Pier.jpg"]


def test_saving_an_outside_picture_beside_it_writes_in_its_own_folder(
    client: TestClient, tmp_path: Path
):
    pier = draw(tmp_path / "Elsewhere" / "Pier.jpg", size=(96, 72))
    page = opened(client, pier)["picture"]

    job = client.post(
        f"/pictures/{page['id']}/make",
        json={"recipe": {"size": {"size": SMALL}}, "saving": {"format": "JPEG"}},
    ).json()

    done = made(client, job)
    assert done["state"] == "done", done
    assert Path(done["result"]).parent == tmp_path / "Elsewhere"
    assert sorted(path.name for path in pier.parent.iterdir()) == [
        "Pier (256 × 192).jpg",
        "Pier.jpg",
    ]


def test_replacing_an_outside_picture_sets_the_original_aside_and_history_puts_it_back(
    client: TestClient, tmp_path: Path
):
    pier = draw(tmp_path / "Elsewhere" / "Pier.jpg", size=(96, 72))
    before = pier.read_bytes()
    page = opened(client, pier)["picture"]

    job = client.post(
        f"/pictures/{page['id']}/make",
        json={
            "recipe": {"size": {"size": SMALL}},
            "saving": {"how": "replace", "format": "JPEG"},
        },
    ).json()
    done = made(client, job)
    assert done["state"] == "done", done
    line = client.get("/history").json()["entries"][0]
    assert line["kind"] == "replaced"
    assert Image.open(pier).size == (256, 192)
    waiting = list((tmp_path / "Mado quarantine").rglob("Pier.jpg"))
    assert [path.read_bytes() for path in waiting] == [before]

    assert client.post(f"/history/{line['id']}/undo").status_code == 200
    assert pier.read_bytes() == before


def test_a_pasted_picture_is_kept_in_madas_data_folder_and_opens_on_its_page(
    client: TestClient, paths: DataPaths, tmp_path: Path
):
    response = paste(client, png())

    assert response.status_code == 200, response.text
    page = response.json()
    assert page["name"].startswith("Pasted ")
    assert page["name"].endswith(".png")
    assert (page["pasted"], page["outside"], page["format"], page["width"]) == (
        True,
        True,
        "PNG",
        80,
    )
    assert page["savesTo"]
    kept = list(paths.pasted.iterdir())
    assert [path.name for path in kept] == [page["name"]]
    assert client.get("/pictures").json()["total"] == 0
    # The same picture pasted again is the one kept; another is a picture of its own.
    assert paste(client, png()).json()["id"] == page["id"]
    assert paste(client, png(colour=(200, 30, 30))).json()["id"] != page["id"]


def test_a_paste_that_isnt_a_picture_or_is_too_big_is_refused(
    client: TestClient, paths: DataPaths, monkeypatch: pytest.MonkeyPatch
):
    not_picture = paste(client, b"words, not a picture")
    monkeypatch.setattr(pasting, "MOST_PIXELS", 100 * 100)
    too_big = paste(client, png((200, 200)))

    assert not_picture.status_code == 422
    assert "isn't a picture Mado can read" in not_picture.json()["detail"]
    assert too_big.status_code == 413
    assert "too big to paste (200 × 200)" in too_big.json()["detail"]
    assert not paths.pasted.exists() or not any(paths.pasted.iterdir())


def test_a_paste_mado_was_given_as_another_format_is_kept_as_png(
    client: TestClient, paths: DataPaths
):
    written = io.BytesIO()
    picture((40, 30)).save(written, format="BMP")

    page = paste(client, written.getvalue()).json()

    assert page["format"] == "PNG"
    assert Image.open(paths.pasted / page["name"]).format == "PNG"


def test_a_pasted_picture_is_saved_only_as_a_new_picture_into_a_folder_chosen(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    page = paste(client, png((96, 72))).json()
    recipe = {"size": {"size": SMALL}}

    replaced = client.post(
        f"/pictures/{page['id']}/make",
        json={"recipe": recipe, "saving": {"how": "replace", "format": "PNG"}},
    )
    beside = client.post(
        f"/pictures/{page['id']}/make", json={"recipe": recipe, "saving": {"format": "PNG"}}
    )
    name = client.post(
        f"/pictures/{page['id']}/saving", json={"recipe": recipe, "format": "PNG"}
    ).json()
    into = tmp_path / "Saved"
    into.mkdir()
    job = client.post(
        f"/pictures/{page['id']}/make",
        json={"recipe": recipe, "saving": {"format": "PNG", "folder": str(into)}},
    ).json()

    assert replaced.status_code == 409
    assert beside.status_code == 422
    assert name["folder"] == page["savesTo"]
    done = made(client, job)
    assert done["state"] == "done", done
    assert [path.parent for path in into.iterdir()] == [into]
    assert [path.name for path in paths.pasted.iterdir()] == [page["name"]]


def test_outside_pictures_not_opened_for_a_month_are_forgotten_unless_still_needed(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    old = opened(client, draw(tmp_path / "Elsewhere" / "Old.jpg"))["picture"]
    queued = opened(client, draw(tmp_path / "Elsewhere" / "Queued.jpg"))["picture"]
    recent = opened(client, draw(tmp_path / "Elsewhere" / "Recent.jpg"))["picture"]
    pasted = paste(client, png()).json()
    client.get(f"/pictures/{old['id']}/thumbnail")
    later = datetime.now().astimezone() + timedelta(days=31)
    with closing(db.connect(paths.database)) as conn:
        conn.execute(
            """INSERT INTO jobs (kind, picture_id, source, recipe, state, queued_at)
               VALUES ('make', ?, ?, '{}', 'queued', ?)""",
            (queued["id"], queued["path"], later.isoformat()),
        )
        conn.execute(
            "INSERT INTO history (at, kind, name, original, result) VALUES (?, 'made', ?, ?, ?)",
            (later.isoformat(), "Recent.jpg", recent["path"], recent["path"] + ".made.jpg"),
        )
        conn.commit()
        let_go: list[int] = []

        forgotten = outside.forget(conn, now=later, pasted=paths.pasted, copies=let_go.extend)

        left = {row["id"] for row in conn.execute("SELECT id FROM pictures")}
    assert forgotten == 2
    assert sorted(let_go) == sorted([old["id"], pasted["id"]])
    assert left == {queued["id"], recent["id"]}
    assert not any(paths.pasted.iterdir())
    assert (tmp_path / "Elsewhere" / "Old.jpg").exists()  # the owner's own picture stays


def test_a_pasted_file_whose_record_went_is_cleared_out_after_its_month(
    client: TestClient, paths: DataPaths
):
    paths.pasted.mkdir(parents=True)
    orphan = paths.pasted / "Pasted 2026-10-01 09.00.png"
    orphan.write_bytes(png())
    recent = paths.pasted / "Pasted 2026-11-22 09.00.png"
    recent.write_bytes(png(colour=(9, 9, 9)))
    old = (datetime.now() - timedelta(days=40)).timestamp()
    os.utime(orphan, (old, old))
    stray = paths.pasted / "notes.txt"  # never Mado's to delete: not a paste of its own
    stray.write_text("made up", encoding="utf-8")
    os.utime(stray, (old, old))

    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        outside.forget(
            conn, now=datetime.now().astimezone(), pasted=paths.pasted, copies=lambda _ids: None
        )

    assert sorted(each.name for each in paths.pasted.iterdir()) == [recent.name, "notes.txt"]


def test_opening_a_picture_again_starts_its_month_afresh(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    page = opened(client, draw(tmp_path / "Elsewhere" / "Pier.jpg"))["picture"]
    with closing(db.connect(paths.database)) as conn:
        conn.execute("UPDATE pictures SET opened_at = '2026-01-01T09:00:00+02:00'")
        conn.commit()

    client.get(f"/pictures/{page['id']}")

    with closing(db.connect(paths.database)) as conn:
        stamp = conn.execute("SELECT opened_at FROM pictures").fetchone()[0]
    assert datetime.fromisoformat(stamp) > datetime(2026, 2, 1).astimezone()


def test_a_kept_picture_of_a_group_wears_its_tag_in_the_grid(
    client: TestClient, tmp_path: Path, conn: sqlite3.Connection
):
    phone = tmp_path / "Phone"
    phone.mkdir()
    scene(3, (320, 240)).save(phone / "Dunes.jpg", quality=95)
    scene(3, (320, 240)).save(phone / "Dunes copy.jpg", quality=70)
    scene(8, (320, 240)).save(phone / "Lake.png")
    add(client, phone)
    app: Any = client.app
    assert app.state.finder.wait(60)

    listed = {item["name"]: item for item in client.get("/pictures").json()["pictures"]}

    group = client.get("/duplicates").json()["groups"][0]
    assert listed["Dunes.jpg"]["group"] == {
        "key": group["key"],
        "kind": "duplicates",
        "pictures": 2,
    }
    assert listed["Dunes copy.jpg"]["group"] is None
    reached = client.get(f"/duplicates?limit=1&reach={group['key']}").json()
    assert [each["key"] for each in reached["groups"]] == [group["key"]]


def test_mados_own_data_folder_is_never_read_into_the_library(
    client: TestClient, tmp_path: Path, paths: DataPaths
):
    paste(client, png())  # in the data folder, which sits inside the folder added
    draw(tmp_path / "Pier.jpg")

    add(client, tmp_path)

    assert [item["name"] for item in client.get("/pictures").json()["pictures"]] == ["Pier.jpg"]


def test_a_picture_is_opened_by_the_paths_the_window_sends(client: TestClient):
    asked = client.post("/open", json={"paths": []})
    assert asked.status_code == 422
    assert json.loads(asked.text)["detail"]
