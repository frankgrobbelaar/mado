"""Preferences chosen during setup and in Settings: Saving's among them."""

import json
import sqlite3

from fastapi.testclient import TestClient

DEFAULTS = {
    "setUp": False,
    "saveFirst": "new",
    "newPictures": "beside",
    "newFolder": None,
    "keepLocation": False,
    "bigBatchesAtNight": False,
}


def test_a_new_mado_is_not_set_up_yet_and_saves_new_pictures_beside_their_originals(
    client: TestClient,
):
    assert client.get("/settings").json() == DEFAULTS


def test_choices_are_kept(client: TestClient, conn: sqlite3.Connection):
    chosen = {
        **DEFAULTS,
        "setUp": True,
        "saveFirst": "replace",
        "newPictures": "folder",
        "newFolder": "D:\\Pictures\\Edited",
    }
    saved = client.put("/settings", json=chosen)

    assert saved.status_code == 200
    assert saved.json() == chosen
    assert client.get("/settings").json() == chosen
    stored = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    assert json.loads(stored["set_up"]) is True  # what the export carries
    assert json.loads(stored["save_first"]) == "replace"


def test_a_choice_mado_doesnt_offer_is_refused(client: TestClient):
    assert client.put("/settings", json={"setUp": "maybe"}).status_code == 422
    assert client.put("/settings", json={"saveFirst": "overwrite"}).status_code == 422


def test_a_stored_value_this_mado_doesnt_know_falls_back_to_the_default(
    client: TestClient, conn: sqlite3.Connection
):
    with conn:
        conn.execute("INSERT INTO settings VALUES ('set_up', ?)", (json.dumps("halfway"),))

    assert client.get("/settings").json() == DEFAULTS
