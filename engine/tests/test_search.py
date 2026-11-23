"""Search: the library read in the background (what each picture shows, by SigLIP, and its words,
by a reader of words), never a picture from outside it, in a quarantine or damaged, again once a
picture changes, kept while its drive is away; paused and taking turns; and what a search finds
through the API: words matched however they're written, descriptions past SigLIP's cut, names,
each picture once; More like this; its neighbours and Many at once from its results. The readers
are stand-ins (tests/fake_search.py): a picture is its colour, and what it shows is set by it."""

import sqlite3
import threading
import time
import zipfile
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mado import db, search
from mado.api import search as search_api
from mado.config import DataPaths
from mado.directml import ModelError
from mado.export import export_data
from mado.ocr import Read
from mado.previews import Previews
from mado.quarantine import Quarantine
from mado.search import Search, Vector, Vectors
from tests.conftest import TOKEN, add, made_app
from tests.fake_search import (
    FakeSiglip,
    FakeWords,
    colour_of,
    flat,
    nearest_name,
    vector_of,
)

WORDS = {"red": "ZUMI 73\nOpen daily", "yellow": "Café Tréval"}


@pytest.fixture
def siglip() -> FakeSiglip:
    return FakeSiglip()


@pytest.fixture
def windows() -> FakeWords:
    return FakeWords(WORDS)


@pytest.fixture
def searching_client(
    paths: DataPaths, quarantine: Quarantine, siglip: FakeSiglip, windows: FakeWords
) -> Iterator[TestClient]:
    """An engine that reads the library for search with the stand-ins, its words at Fast."""
    app = made_app(paths, quarantine, describer=siglip, words=windows)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        yield client


def searcher(client: TestClient) -> Search:
    app: Any = client.app
    found: Search = app.state.search
    return found


def read_all(client: TestClient) -> None:
    assert searcher(client).wait(30), "reading for search didn't finish in time"


def rescan(client: TestClient) -> None:
    app: Any = client.app
    app.state.scanner.request()
    app.state.scanner.wait(timeout=30)


def library(root: Path, *colours: str) -> Path:
    """A folder of flat made-up pictures, one of each colour, named after it."""
    root.mkdir(parents=True, exist_ok=True)
    for colour in colours:
        flat(colour).save(root / f"{colour.title()} wall.png")
    return root


def ids_by_name(client: TestClient) -> dict[str, int]:
    pictures = client.get("/pictures").json()["pictures"]
    return {each["name"]: each["id"] for each in pictures}


def found(client: TestClient, words: str, **more: str | int) -> dict[str, Any]:
    response = client.get("/search", params={"q": words, **more})
    assert response.status_code == 200, response.text
    return response.json()


def kinds(results: dict[str, Any]) -> dict[str, list[str]]:
    return {
        group["kind"]: [each["name"] for each in group["pictures"]] for group in results["groups"]
    }


# Reading.


def test_each_library_picture_is_read_once_its_vector_and_its_words_kept(
    searching_client: TestClient, tmp_path: Path, siglip: FakeSiglip, paths: DataPaths
):
    add(searching_client, library(tmp_path / "Phone", "red", "green", "yellow"))
    read_all(searching_client)

    state = searching_client.get("/search/state").json()
    assert (state["read"], state["of"]) == (3, 3)
    assert siglip.pictures == 3
    with closing(db.connect(paths.database)) as conn:
        rows = conn.execute(
            "SELECT p.name, r.reader, r.lines, w.text FROM words_read AS r"
            " JOIN pictures AS p ON p.id = r.picture_id"
            " LEFT JOIN words AS w ON w.rowid = r.picture_id ORDER BY p.name"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("Green wall.png", "fast", 0, None),
        ("Red wall.png", "fast", 2, "ZUMI 73\nOpen daily"),
        ("Yellow wall.png", "fast", 1, "Café Tréval"),
    ]
    with closing(sqlite3.connect(paths.search)) as side:
        assert side.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 3

    searcher(searching_client).wake()  # nothing new: nothing's read again
    read_all(searching_client)
    assert siglip.pictures == 3


def test_a_picture_is_read_again_once_its_file_changes(
    searching_client: TestClient, tmp_path: Path, siglip: FakeSiglip
):
    folder = library(tmp_path / "Phone", "red")
    add(searching_client, folder)
    read_all(searching_client)
    assert kinds(found(searching_client, "red")) == {"described": ["Red wall.png"]}

    flat("blue").save(folder / "Red wall.png")  # the same name, another picture
    rescan(searching_client)
    read_all(searching_client)

    assert siglip.pictures == 2
    assert kinds(found(searching_client, "blue")) == {"described": ["Red wall.png"]}
    assert "described" not in kinds(found(searching_client, "red"))


def test_never_read_a_picture_from_outside_the_library_one_set_aside_or_one_damaged(
    searching_client: TestClient, tmp_path: Path, siglip: FakeSiglip
):
    folder = library(tmp_path / "Phone", "red")
    aside = folder / "Mado quarantine" / "2026-11-20"
    aside.mkdir(parents=True)
    flat("green").save(aside / "Green wall.png")
    (folder / "Broken.jpg").write_bytes(b"not a picture")
    outside = library(tmp_path / "Elsewhere", "blue") / "Blue wall.png"
    add(searching_client, folder)
    opened = searching_client.post("/open", json={"paths": [str(outside)]})
    assert opened.status_code == 200, opened.text
    read_all(searching_client)

    assert siglip.pictures == 1  # the red wall alone
    assert searching_client.get("/search/state").json()["of"] == 1
    assert kinds(found(searching_client, "blue")) == {}


def test_a_drive_away_keeps_its_pictures_readings_and_they_show_as_away(
    searching_client: TestClient, tmp_path: Path
):
    folder = library(tmp_path / "Camera", "red", "green")
    add(searching_client, folder)
    read_all(searching_client)

    away = tmp_path / "Camera unplugged"
    folder.rename(away)  # as a drive unplugged: its folder isn't there
    try:
        results = found(searching_client, "zumi")
    finally:
        away.rename(folder)

    [hit] = results["groups"][0]["pictures"]
    assert hit["name"] == "Red wall.png"
    assert hit["away"] is True


def test_reading_pauses_and_goes_on_and_a_pause_is_kept(
    searching_client: TestClient, tmp_path: Path, siglip: FakeSiglip, paths: DataPaths
):
    paused = searching_client.post("/search/pause").json()
    assert paused["paused"] is True

    add(searching_client, library(tmp_path / "Phone", "red", "green"))
    read_all(searching_client)
    assert siglip.pictures == 0
    assert searching_client.get("/search/state").json()["read"] == 0
    with closing(db.connect(paths.database)) as conn:
        assert searcher(searching_client).paused(conn)

    searching_client.post("/search/resume")
    read_all(searching_client)
    assert siglip.pictures == 2


def test_reading_waits_for_its_models_and_reads_once_they_come(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    siglip = FakeSiglip(ready=False)
    app = made_app(paths, quarantine, describer=siglip)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, library(tmp_path / "Phone", "red"))
        read_all(client)
        assert siglip.pictures == 0
        assert kinds(found(client, "red")) == {"name": ["Red wall.png"]}  # names still find

        siglip.is_ready = True
        searcher(client).wake()
        read_all(client)
        assert kinds(found(client, "red")) == {"described": ["Red wall.png"]}


def test_a_picture_that_cant_be_read_is_left_and_the_others_are_read(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    class Fussy(FakeSiglip):
        def picture(self, image: Image.Image, *, threads: int | None = 2) -> Vector:
            if nearest_name(colour_of(image)) == "red":
                raise RuntimeError("a picture the model can't take")
            return super().picture(image, threads=threads)

    app = made_app(paths, quarantine, describer=Fussy())
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, library(tmp_path / "Phone", "red", "green", "blue"))
        read_all(client)

        state = client.get("/search/state").json()
        assert (state["read"], state["of"], state["failed"]) == (2, 3, 1)
        assert kinds(found(client, "green")) == {"described": ["Green wall.png"]}


def test_a_picture_that_couldnt_be_read_is_tried_again_after_the_next_scan(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    class OnceFussy(FakeSiglip):
        def __init__(self) -> None:
            super().__init__()
            self.fussy = True

        def picture(self, image: Image.Image, *, threads: int | None = 2) -> Vector:
            if self.fussy and nearest_name(colour_of(image)) == "red":
                raise RuntimeError("a picture the model can't take now")
            return super().picture(image, threads=threads)

    siglip = OnceFussy()
    app = made_app(paths, quarantine, describer=siglip)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, library(tmp_path / "Phone", "red", "green"))
        read_all(client)
        assert client.get("/search/state").json()["failed"] == 1

        siglip.fussy = False
        rescan(client)
        read_all(client)
        state = client.get("/search/state").json()
        assert (state["read"], state["failed"]) == (2, 0)


def test_a_model_that_cant_run_rests_reading_till_its_next_woken(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    class Broken(FakeSiglip):
        def picture(self, image: Image.Image, *, threads: int | None = 2) -> Vector:
            self.pictures += 1
            raise ModelError("The processor couldn't run the AI model (made up).")

    broken = Broken()
    app = made_app(paths, quarantine, describer=broken)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, library(tmp_path / "Phone", "red", "green", "blue"))
        read_all(client)

        assert broken.pictures == 1  # not tried on every picture


def test_a_reader_that_cant_run_says_so_and_the_other_reads_on(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    class Stuck(FakeWords):
        stuck = True

        def read(self, picture: Image.Image) -> Read:
            if self.stuck:
                raise ModelError("Windows couldn't read words now (made up).")
            return super().read(picture)

    siglip, windows = FakeSiglip(), Stuck(WORDS)
    app = made_app(paths, quarantine, describer=siglip, words=windows)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, library(tmp_path / "Phone", "red", "green", "blue"))
        read_all(client)

        state = client.get("/search/state").json()
        assert state["problem"] == {
            "reader": "words",
            "said": "Windows couldn't read words now (made up).",
        }
        assert siglip.pictures == 3  # what each shows read all the same
        assert kinds(found(client, "green")) == {"described": ["Green wall.png"]}

        windows.stuck = False
        resumed = client.post("/search/resume").json()  # Try again
        assert resumed["problem"] is None
        read_all(client)
        assert kinds(found(client, "zumi")) == {"words": ["Red wall.png"]}


def test_the_progress_counts_pictures_the_scan_hasnt_read_yet(
    searching_client: TestClient, tmp_path: Path, paths: DataPaths
):
    add(searching_client, library(tmp_path / "Phone", "red", "green", "blue"))
    read_all(searching_client)
    with closing(db.connect(paths.database)) as conn, conn:
        conn.execute("UPDATE pictures SET read_at = NULL WHERE name = 'Blue wall.png'")

    state = searching_client.get("/search/state").json()
    assert (state["read"], state["of"]) == (2, 3)  # not "all read" while the scan reads


def test_vectors_kept_by_two_at_once_are_numbered_apart(tmp_path: Path):
    vectors = Vectors(tmp_path / "search.db")
    started, release = threading.Event(), threading.Event()

    def slowly() -> Iterator[tuple[int, int, int, Vector]]:
        started.set()
        release.wait(5)
        yield (1, 100, 200, vector_of((220, 30, 30)))

    def first() -> None:
        with closing(vectors.connect()) as conn:
            vectors.keep(conn, slowly())

    worker = threading.Thread(target=first)
    worker.start()
    assert started.wait(5)
    with closing(vectors.connect()) as conn:
        vectors.keep(conn, [(2, 100, 200, vector_of((30, 160, 60)))])
    release.set()
    worker.join(5)

    with closing(sqlite3.connect(tmp_path / "search.db")) as side:
        numbers = [row[0] for row in side.execute("SELECT seq FROM vectors")]
    assert sorted(numbers) == [1, 2]


def test_words_in_greek_and_japanese_are_found_however_written_and_inside_a_line(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    windows = FakeWords(
        {"blue": "東京タワーへようこそ", "green": "Καφές Ζούμι"}, languages=("ja", "el")
    )
    app = made_app(paths, quarantine, describer=FakeSiglip(), words=windows)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, library(tmp_path / "Phone", "blue", "green"))
        read_all(client)

        for written in ("タワー", "東京", "ようこそ"):
            assert kinds(found(client, written)) == {"words": ["Blue wall.png"]}
        assert kinds(found(client, "カラス")) == {}  # a crow is no glass, nor a tower
        for written in ("καφές", "ΚΑΦΕΣ", "καφες"):
            assert kinds(found(client, written)) == {"words": ["Green wall.png"]}


# Finding.


def test_a_search_finds_by_words_by_description_and_by_name_each_picture_once(
    searching_client: TestClient, tmp_path: Path
):
    folder = library(tmp_path / "Phone", "red", "green", "yellow", "blue")
    flat("green").save(folder / "Zumi beach.png")  # found by name only
    add(searching_client, folder)
    read_all(searching_client)

    results = found(searching_client, "zumi")
    assert kinds(results) == {"words": ["Red wall.png"], "name": ["Zumi beach.png"]}
    assert results["total"] == 2
    [hit] = results["groups"][0]["pictures"]
    assert [piece for piece in hit["words"] if piece["marked"]] == [
        {"text": "ZUMI", "marked": True}
    ]

    described = found(searching_client, "green")
    assert kinds(described).keys() == {"described"}
    assert sorted(kinds(described)["described"]) == ["Green wall.png", "Zumi beach.png"]
    assert all(each["score"] > 0.9 for each in described["groups"][0]["pictures"])


def test_words_match_however_theyre_written(searching_client: TestClient, tmp_path: Path):
    add(searching_client, library(tmp_path / "Phone", "yellow"))
    read_all(searching_client)

    for written in ("cafe treval", "CAFÉ", "trév"):
        assert kinds(found(searching_client, written)) == {"words": ["Yellow wall.png"]}


def test_a_search_for_something_not_there_finds_nothing(
    searching_client: TestClient, tmp_path: Path
):
    add(searching_client, library(tmp_path / "Phone", "red", "green", "blue"))
    read_all(searching_client)

    results = found(searching_client, "giraffe")
    assert results["groups"] == []
    assert results["total"] == 0


def test_a_search_in_another_language_says_so_and_isnt_described(
    searching_client: TestClient, tmp_path: Path, siglip: FakeSiglip
):
    add(searching_client, library(tmp_path / "Phone", "red"))
    read_all(searching_client)

    results = found(searching_client, "der Hund im Schnee")
    assert results["english"] is False
    assert siglip.searches == []


def test_a_writing_windows_cant_read_here_is_said(searching_client: TestClient, tmp_path: Path):
    add(searching_client, library(tmp_path / "Phone", "red"))
    read_all(searching_client)

    assert found(searching_client, "Βάρκα")["unreadable"] == "Greek"
    assert found(searching_client, "harbour")["unreadable"] is None


def test_a_search_keeps_to_the_folder_shown(searching_client: TestClient, tmp_path: Path):
    add(searching_client, library(tmp_path / "Phone", "red"))
    camera = add(searching_client, library(tmp_path / "Camera", "red"))
    read_all(searching_client)

    results = found(searching_client, "red", folder=camera["id"])
    [hit] = results["groups"][0]["pictures"]
    assert hit["path"] == str(tmp_path / "Camera" / "Red wall.png")


def test_more_like_this_finds_the_nearest_never_the_picture_itself(
    searching_client: TestClient, tmp_path: Path
):
    folder = library(tmp_path / "Phone", "red", "blue", "green")
    flat("red", (120, 80)).save(folder / "Red again.png")
    add(searching_client, folder)
    read_all(searching_client)
    ids = ids_by_name(searching_client)

    response = searching_client.get(f"/search/like/{ids['Red wall.png']}")
    assert response.status_code == 200, response.text
    results = response.json()
    assert results["search"] == "Red wall.png"
    assert kinds(results) == {"like": ["Red again.png"]}


def test_more_like_this_reads_a_picture_not_read_yet(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    siglip = FakeSiglip()
    app = made_app(paths, quarantine, describer=siglip)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        client.post("/search/pause")  # nothing read in the background
        folder = library(tmp_path / "Phone", "red")
        flat("red", (120, 80)).save(folder / "Red again.png")
        add(client, folder)
        ids = ids_by_name(client)

        results = client.get(f"/search/like/{ids['Red wall.png']}").json()

        assert siglip.pictures == 1  # itself, read now; the other has no vector yet
        assert results["groups"] == []


def test_more_like_this_never_reads_a_picture_from_outside_the_library(
    searching_client: TestClient, tmp_path: Path, siglip: FakeSiglip
):
    add(searching_client, library(tmp_path / "Phone", "red"))
    outside = library(tmp_path / "Elsewhere", "blue") / "Blue wall.png"
    opened = searching_client.post("/open", json={"paths": [str(outside)]}).json()
    read_all(searching_client)
    before = siglip.pictures
    outside_id = opened["picture"]["id"]

    assert searching_client.get(f"/search/like/{outside_id}").status_code == 404
    searching_client.post("/batches/pictures", json={"how": "search", "like": outside_id})
    assert siglip.pictures == before


def test_more_like_this_is_only_for_the_librarys_pictures(searching_client: TestClient):
    assert searching_client.get("/search/like/999").status_code == 404


def test_a_pictures_neighbours_follow_a_searchs_results(
    searching_client: TestClient, tmp_path: Path
):
    folder = library(tmp_path / "Phone", "red", "green")
    flat("green").save(folder / "Zumi beach.png")
    add(searching_client, folder)
    read_all(searching_client)
    ids = ids_by_name(searching_client)

    around = searching_client.get(
        f"/pictures/{ids['Zumi beach.png']}/neighbours", params={"q": "zumi"}
    ).json()

    assert [each["name"] for each in around["before"]] == ["Red wall.png"]
    assert around["after"] == []


def test_many_at_once_from_a_search_takes_what_it_found_in_its_order(
    searching_client: TestClient, tmp_path: Path
):
    folder = library(tmp_path / "Phone", "red", "green")
    flat("green").save(folder / "Zumi beach.png")
    add(searching_client, folder)
    read_all(searching_client)

    picked = searching_client.post("/batches/pictures", json={"how": "search", "q": "zumi"})
    assert picked.status_code == 200, picked.text
    body = picked.json()
    assert [each["name"] for each in body["pictures"]] == ["Red wall.png", "Zumi beach.png"]
    assert body["words"] == "found by “zumi”"

    ids = ids_by_name(searching_client)
    liked = searching_client.post(
        "/batches/pictures", json={"how": "search", "like": ids["Green wall.png"]}
    ).json()
    assert [each["name"] for each in liked["pictures"]] == ["Zumi beach.png"]


def test_a_search_counts_and_takes_every_picture_it_finds_past_those_shown(
    searching_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(search_api, "MOST", 2)  # a group shows two
    folder = tmp_path / "Phone"
    folder.mkdir()
    for at in range(5):
        flat("green").save(folder / f"Harbour {at}.png")
    for at in range(3):
        flat("red").save(folder / f"Pier {at}.png")  # red: "ZUMI 73" in its words
    add(searching_client, folder)
    read_all(searching_client)

    for words, total in (("harbour", 5), ("zumi", 3)):
        results = found(searching_client, words)
        [group] = results["groups"]
        assert (len(group["pictures"]), group["total"], results["total"]) == (2, total, total)
        picked = searching_client.post("/batches/pictures", json={"how": "search", "q": words})
        assert len(picked.json()["pictures"]) == total


def test_the_first_search_fetches_what_reading_needs(paths: DataPaths, quarantine: Quarantine):
    siglip = FakeSiglip(ready=False)
    best = FakeWords({}, ready=False)
    app = made_app(paths, quarantine, describer=siglip, words=FakeWords({}), best_words=best)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        found(client, "harbour")
        assert (siglip.fetched, best.fetched) == (1, 0)  # words at Fast need nothing

        settings = client.get("/settings").json()
        client.put("/settings", json={**settings, "wordsReader": "best"})
        assert best.fetched == 1  # Best chosen: its model comes


def test_the_words_reader_follows_the_owners_choice(searching_client: TestClient):
    state = searching_client.get("/search/state").json()
    assert state["words"]["chosen"] == "auto"
    assert state["words"]["reader"] == "fast"  # on the processor, with Windows' languages
    assert state["words"]["languages"] == ["en-GB"]

    settings = searching_client.get("/settings").json()
    searching_client.put("/settings", json={**settings, "wordsReader": "best"})

    state = searching_client.get("/search/state").json()
    assert (state["words"]["chosen"], state["words"]["reader"]) == ("best", "best")


def test_changing_the_words_reader_reads_the_words_again(
    paths: DataPaths, quarantine: Quarantine, tmp_path: Path
):
    windows = FakeWords(WORDS)
    best = FakeWords({"red": "ZUMI 73 OPEN DAILY"}, place="processor")
    app = made_app(paths, quarantine, describer=FakeSiglip(), words=windows, best_words=best)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        add(client, library(tmp_path / "Phone", "red", "green"))
        read_all(client)
        assert windows.read_pictures == 2

        settings = client.get("/settings").json()
        client.put("/settings", json={**settings, "wordsReader": "best"})
        searcher(client).wake()
        read_all(client)

        assert best.glanced == 2
        assert best.read_pictures == 1  # only the picture where it found text is read in full
        hit = found(client, "daily")["groups"][0]["pictures"][0]
        assert "".join(piece["text"] for piece in hit["words"]) == "ZUMI 73 OPEN DAILY"


# Keeping the vectors.


def test_the_vectors_are_let_go_of_memory_when_searches_stop(
    searching_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(search, "IDLE", 0.3)
    add(searching_client, library(tmp_path / "Phone", "red"))
    read_all(searching_client)
    vectors = searcher(searching_client).vectors

    found(searching_client, "red")
    assert vectors.held() > 0
    time.sleep(0.8)

    assert vectors.held() == 0
    assert kinds(found(searching_client, "red")) == {"described": ["Red wall.png"]}


def test_a_damaged_search_db_is_started_again(tmp_path: Path):
    path = tmp_path / "search.db"
    path.write_bytes(b"not a database at all, just bytes" * 64)
    vectors = Vectors(path)

    with closing(vectors.connect()) as conn:
        vectors.keep(conn, [(7, 100, 200, vector_of((220, 30, 30)))])
        assert [tuple(row) for row in conn.execute("SELECT picture_id FROM vectors")] == [(7,)]


def test_a_busy_search_db_is_never_taken_for_damaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vectors = Vectors(tmp_path / "search.db")
    with closing(vectors.connect()) as conn:
        vectors.keep(conn, [(7, 100, 200, vector_of((220, 30, 30)))])
    busy = sqlite3.OperationalError("database is locked")
    busy.sqlite_errorcode = sqlite3.SQLITE_BUSY  # pyright: ignore[reportAttributeAccessIssue]

    def locked(self: Vectors) -> sqlite3.Connection:
        raise busy

    with monkeypatch.context() as patched:
        patched.setattr(Vectors, "_open", locked)
        with pytest.raises(sqlite3.OperationalError):
            vectors.connect()

    with closing(vectors.connect()) as conn:  # what was kept is still there
        assert [tuple(row) for row in conn.execute("SELECT picture_id FROM vectors")] == [(7,)]


def test_search_db_made_by_two_at_once_is_made_once(tmp_path: Path):
    vectors = Vectors(tmp_path / "search.db")  # the engine's one, its threads opening it at once
    made: list[str] = []

    def connect() -> None:
        try:
            with closing(vectors.connect()) as conn:
                conn.execute("SELECT COUNT(*) FROM vectors").fetchone()
            made.append("ok")
        except sqlite3.Error as error:
            made.append(str(error))

    workers = [threading.Thread(target=connect) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
    assert made == ["ok"] * 8


def test_reading_waits_a_moment_when_the_database_is_busy_and_goes_on(
    searching_client: TestClient,
    tmp_path: Path,
    siglip: FakeSiglip,
    monkeypatch: pytest.MonkeyPatch,
):
    searching_client.post("/search/pause")
    add(searching_client, library(tmp_path / "Phone", "red", "green"))
    read_all(searching_client)
    assert siglip.pictures == 0
    real = Search._read_some  # pyright: ignore[reportPrivateUsage]
    calls = {"n": 0}

    def busy_once(self: Search) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            error = sqlite3.OperationalError("database is locked")
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY  # pyright: ignore[reportAttributeAccessIssue]
            raise error
        return real(self)

    monkeypatch.setattr(Search, "_read_some", busy_once)
    searching_client.post("/search/resume")
    read_all(searching_client)

    assert siglip.pictures == 2  # read after a moment, not five minutes on


def test_vectors_are_kept_as_16_bit_numbers_and_come_back_whole(tmp_path: Path):
    vectors = Vectors(tmp_path / "search.db")
    one = vector_of((30, 60, 220))
    with closing(vectors.connect()) as conn:
        vectors.keep(conn, [(3, 10, 20, one)])
        blob = conn.execute("SELECT vector FROM vectors").fetchone()[0]
    assert len(blob) == 768 * 2

    [(picture_id, size, modified, score)] = vectors.ranked(one)
    assert (picture_id, size, modified) == (3, 10, 20)
    assert score > 0.99


# Taking turns with the queue.


def test_reading_on_the_card_rests_while_the_queue_makes_a_picture(tmp_path: Path):
    best = FakeWords({}, place="card")
    busy = threading.Event()
    busy.set()
    paths = DataPaths(tmp_path)
    finder = Search(
        paths,
        Previews(paths, lambda: None),
        FakeSiglip(),
        best,
        FakeWords({}),
        ffmpeg=lambda: None,
        reader=lambda _conn: "best",
        busy=busy.is_set,
        now=datetime.now,
    )
    began = time.perf_counter()
    finder._share("best", 0.02)  # pyright: ignore[reportPrivateUsage]
    rested = time.perf_counter() - began
    busy.clear()
    began = time.perf_counter()
    finder._share("best", 0.02)  # pyright: ignore[reportPrivateUsage]

    assert rested >= 0.15  # nine times its turn
    assert time.perf_counter() - began < 0.05


def test_the_card_is_said_busy_only_when_reading_shares_it(
    paths: DataPaths, quarantine: Quarantine
):
    best = FakeWords({}, place="card")
    app = made_app(paths, quarantine, describer=FakeSiglip(), words=FakeWords({}), best_words=best)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        searcher(client)._busy = lambda: True  # pyright: ignore[reportPrivateUsage]
        assert client.get("/search/state").json()["busy"] is False  # Fast reads on the processor

        settings = client.get("/settings").json()
        client.put("/settings", json={**settings, "wordsReader": "best"})
        assert client.get("/search/state").json()["busy"] is True


# What's kept and exported.


def test_the_export_has_the_words_read(
    searching_client: TestClient, tmp_path: Path, paths: DataPaths
):
    add(searching_client, library(tmp_path / "Phone", "red", "green"))
    read_all(searching_client)

    written = export_data(paths, tmp_path / "Export")
    assert written is not None
    with zipfile.ZipFile(written) as archive:
        text = archive.read("words.csv").decode("utf-8")
    lines = text.strip().splitlines()
    assert lines[0] == "path,words,reader,language,readAt"
    assert any("Red wall.png" in line and "ZUMI 73" in line for line in lines[1:])
    assert any("Green wall.png" in line for line in lines[1:])


def test_your_data_says_how_big_search_db_is(searching_client: TestClient, tmp_path: Path):
    add(searching_client, library(tmp_path / "Phone", "red"))
    read_all(searching_client)

    assert searching_client.get("/data").json()["search"] > 0


def test_a_pictures_words_go_with_it_when_its_folder_is_taken_out(
    searching_client: TestClient, tmp_path: Path, paths: DataPaths
):
    folder = add(searching_client, library(tmp_path / "Phone", "red"))
    read_all(searching_client)

    assert searching_client.delete(f"/folders/{folder['id']}").status_code == 204
    with closing(db.connect(paths.database)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM words").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM words_read").fetchone()[0] == 0


def test_reading_never_changes_a_picture(searching_client: TestClient, tmp_path: Path):
    folder = library(tmp_path / "Phone", "red", "yellow")
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in folder.iterdir()}
    add(searching_client, folder)
    read_all(searching_client)
    found(searching_client, "zumi")

    after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in folder.iterdir()}
    assert after == before


def test_vectors_of_pictures_no_longer_in_the_library_are_let_go(
    searching_client: TestClient, tmp_path: Path, paths: DataPaths
):
    folder = library(tmp_path / "Phone", "red", "green")
    add(searching_client, folder)
    read_all(searching_client)
    (folder / "Green wall.png").unlink()
    rescan(searching_client)
    read_all(searching_client)

    with closing(sqlite3.connect(paths.search)) as side:
        assert side.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 1
