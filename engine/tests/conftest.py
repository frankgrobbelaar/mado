"""Shared test setup: every test gets its own empty data folder, its own quarantine (never a
drive's), and AI models on the processor (no graphics card in CI)."""

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
from mado.hardware import Here
from mado.jobs import Jobs
from mado.pc_check import Probe
from mado.quarantine import Quarantine
from mado.scan import Scanner

TOKEN = "test-token"
# ffmpeg as the tests have it: a stand-in that draws a made-up picture (tests/fake_ffmpeg.py).
FFMPEG = [sys.executable, str(Path(__file__).parent / "fake_ffmpeg.py")]


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "Mado")


@pytest.fixture
def quarantine(tmp_path: Path) -> Quarantine:
    """A quarantine of the test's own: one folder for every drive's, in its temporary folder."""
    return Quarantine(lambda _picture: tmp_path / "Mado quarantine")


ON_PROCESSOR = Here("processor", None, {})


def fake_check(_timing: bool, _heavy_tile: int, _best: Path | None) -> Probe:
    """The PC check, standing in for the graphics card: the models run, quickly."""
    return Probe(True, None, {"realesr-general-x4v3@card": 0.5})


@pytest.fixture
def app(paths: DataPaths, quarantine: Quarantine) -> FastAPI:
    return create_app(
        TOKEN,
        paths,
        ffmpeg=lambda: FFMPEG,
        quarantine=quarantine,
        here=lambda: ON_PROCESSOR,
        check=fake_check,
    )


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


def made(client: TestClient, job: dict[str, Any], timeout: float = 120) -> dict[str, Any]:
    """Waits for a job to be over, and says how it went."""
    app: Any = client.app
    jobs: Jobs = app.state.jobs
    assert jobs.wait(timeout), "the job didn't finish in time"
    response = client.get(f"/jobs/{job['id']}")
    assert response.status_code == 200, response.text
    return response.json()


def add(client: TestClient, folder: Path) -> dict[str, Any]:
    """Adds a folder to the library through the API, and waits for the scan that reads it."""
    response = client.post("/folders", json={"path": str(folder)})
    assert response.status_code == 201, response.text
    app: Any = client.app
    scanner: Scanner = app.state.scanner
    scanner.wait(timeout=30)
    return response.json()
