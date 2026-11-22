"""Preferences chosen during setup."""

import json
import sqlite3

from fastapi.testclient import TestClient


def test_a_new_mado_is_not_set_up_yet(client: TestClient):
    assert client.get("/settings").json() == {"setUp": False}


def test_choices_are_kept(client: TestClient, conn: sqlite3.Connection):
    saved = client.put("/settings", json={"setUp": True})

    assert saved.status_code == 200
    assert saved.json() == {"setUp": True}
    assert client.get("/settings").json() == {"setUp": True}
    stored = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    assert json.loads(stored["set_up"]) is True  # what the export carries


def test_a_choice_mado_doesnt_offer_is_refused(client: TestClient):
    response = client.put("/settings", json={"setUp": "maybe"})

    assert response.status_code == 422


def test_a_stored_value_this_mado_doesnt_know_falls_back_to_the_default(
    client: TestClient, conn: sqlite3.Connection
):
    with conn:
        conn.execute("INSERT INTO settings VALUES ('set_up', ?)", (json.dumps("halfway"),))

    assert client.get("/settings").json() == {"setUp": False}
