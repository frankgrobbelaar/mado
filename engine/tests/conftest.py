"""Shared test setup: every test gets its own empty data folder."""

import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mado import db
from mado.api import create_app
from mado.config import DataPaths
from mado.scan import Scanner

TOKEN = "test-token"
# ffmpeg as the tests have it: a stand-in that draws a made-up picture (tests/fake_ffmpeg.py).
FFMPEG = [sys.executable, str(Path(__file__).parent / "fake_ffmpeg.py")]


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "Mado")


@pytest.fixture
def app(paths: DataPaths) -> FastAPI:
    return create_app(TOKEN, paths, ffmpeg=lambda: FFMPEG)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client that talks to the API the way the app does: on 127.0.0.1, with the token."""
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as test_client:
        yield test_client


@pytest.fixture
def conn(paths: DataPaths) -> Iterator[sqlite3.Connection]:
    """The data folder's database, migrated to the latest schema."""
    with closing(db.connect(paths.database)) as connection:
        db.migrate(connection)
        yield connection


def add(client: TestClient, folder: Path) -> dict[str, Any]:
    """Adds a folder to the library through the API, and waits for the scan that reads it."""
    response = client.post("/folders", json={"path": str(folder)})
    assert response.status_code == 201, response.text
    app: Any = client.app
    scanner: Scanner = app.state.scanner
    scanner.wait(timeout=30)
    return response.json()
