"""Shared test setup: every test gets its own empty data folder."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mado import db
from mado.api import create_app
from mado.config import DataPaths

TOKEN = "test-token"


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "Mado")


@pytest.fixture
def client(paths: DataPaths) -> Iterator[TestClient]:
    """A client that talks to the API the way the app does: on 127.0.0.1, with the token."""
    app = create_app(TOKEN, paths)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as test_client:
        yield test_client


@pytest.fixture
def conn(paths: DataPaths) -> Iterator[sqlite3.Connection]:
    """The data folder's database, migrated to the latest schema."""
    with closing(db.connect(paths.database)) as connection:
        db.migrate(connection)
        yield connection
