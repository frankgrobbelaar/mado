"""Settings > Your data: where Mado keeps it and how big each part is, and the export."""

import sqlite3
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from mado.config import DataPaths


def test_each_part_of_the_data_folder_is_measured(
    client: TestClient, paths: DataPaths, conn: sqlite3.Connection
):
    parts = (
        ("cache", 500),
        ("logs", 200),
        ("backups", 100),
        ("tools", 50),
        ("pasted", 30),
        ("wallpapers", 70),
    )
    for folder, size in parts:
        (paths.root / folder).mkdir(parents=True, exist_ok=True)
        (paths.root / folder / "a file").write_bytes(bytes(size))
    (paths.tools / "ffmpeg").mkdir()
    (paths.tools / "ffmpeg" / "ffmpeg.exe").write_bytes(bytes(25))  # a folder's files count

    found = client.get("/data").json()

    assert found == {
        "folder": str(paths.root),
        "database": found["database"],
        "cache": 500,
        "logs": 200,
        "backups": 100,
        "tools": 75,
        "pasted": 30,
        "wallpapers": 70,
    }
    assert found["database"] > 0


def test_parts_not_made_yet_measure_nothing(client: TestClient):
    found = client.get("/data").json()

    assert (found["cache"], found["logs"], found["backups"], found["tools"]) == (0, 0, 0, 0)
    assert found["pasted"] == 0
    assert found["wallpapers"] == 0


def test_the_export_is_written_where_the_owner_asks(
    client: TestClient, conn: sqlite3.Connection, tmp_path: Path
):
    answer = client.post("/export", json={"folder": str(tmp_path / "Backups")}).json()

    path = Path(answer["path"])
    assert path.parent == tmp_path / "Backups"
    assert answer["size"] == path.stat().st_size
    assert "mado.db" in zipfile.ZipFile(path).namelist()


def test_an_export_that_cant_be_written_says_why(
    client: TestClient, conn: sqlite3.Connection, tmp_path: Path
):
    (tmp_path / "a file").write_bytes(b"not a folder")

    answer = client.post("/export", json={"folder": str(tmp_path / "a file")})

    assert answer.status_code == 422
    assert answer.json()["detail"].startswith("Mado couldn't write the export there")
