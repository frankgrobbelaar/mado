import json
import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import httpx2
import pytest
from typer.testing import CliRunner

from mado import __version__, db
from mado.cli import app, stop_when_stdin_closes
from mado.config import DataPaths
from tests.conftest import TOKEN

runner = CliRunner()


def test_version_prints_the_engine_version():
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_serve_needs_the_token_from_the_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MADO_TOKEN", raising=False)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 2
    assert "MADO_TOKEN is not set" in result.stderr


def _engine() -> list[str]:
    """The engine from source, or the bundled build when MADO_ENGINE_EXE names it."""
    if bundled := os.environ.get("MADO_ENGINE_EXE"):
        return [str(Path(bundled).resolve())]
    return [sys.executable, "-m", "mado"]


def test_serve_announces_its_port_and_stops_when_the_app_goes_away(tmp_path: Path):
    """The handshake the app's shell relies on (see app/src-tauri/src/engine.rs). CI runs this
    against the bundled engine too, naming it in MADO_ENGINE_EXE."""
    home = tmp_path / "Mado"
    env = {**os.environ, "MADO_TOKEN": TOKEN, "MADO_DATA_DIR": str(home)}
    command = [*_engine(), "serve", "--watch-stdin"]
    with subprocess.Popen(
        command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as engine:
        assert engine.stdin is not None
        assert engine.stdout is not None
        ready = json.loads(engine.stdout.readline())
        assert ready["event"] == "ready"

        response = httpx2.get(
            f"http://127.0.0.1:{ready['port']}/health",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=30,
        )
        assert response.status_code == 200

        engine.stdin.close()
        assert engine.wait(timeout=30) == 0

    assert (home / "logs" / "engine.log").is_file()  # it logs in its data folder


def test_the_app_going_stops_the_engine(monkeypatch: pytest.MonkeyPatch):
    class Stdin:
        def fileno(self) -> int:
            return 0

    class Server:
        should_exit = False

    def closed(_fd: int, _size: int) -> bytes:
        return b""  # the app's end of the pipe closed

    monkeypatch.setattr("mado.cli.sys.stdin", Stdin())
    monkeypatch.setattr("mado.cli.os.read", closed)
    server = Server()

    stop_when_stdin_closes(server)  # type: ignore[arg-type]

    assert server.should_exit


def test_an_engine_with_damaged_records_stays_up_to_offer_the_way_back(tmp_path: Path):
    """Its records damaged past opening: it starts anyway, answering only what the way back
    needs, and ends when the app goes away."""
    home = tmp_path / "Mado"
    home.mkdir()
    (home / "mado.db").write_bytes(b"not a database at all" * 200)
    env = {**os.environ, "MADO_TOKEN": TOKEN, "MADO_DATA_DIR": str(home)}
    command = [*_engine(), "serve", "--watch-stdin"]
    with subprocess.Popen(
        command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as engine:
        assert engine.stdin is not None
        assert engine.stdout is not None
        ready = json.loads(engine.stdout.readline())
        found = httpx2.get(
            f"http://127.0.0.1:{ready['port']}/records",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=30,
        ).json()

        engine.stdin.close()
        assert engine.wait(timeout=30) == 0

    assert found == {
        "problem": "file is not a database",
        "badRead": False,
        "backup": None,
        "made": None,
    }


def test_an_engine_that_cant_start_says_so_and_ends_cleanly(tmp_path: Path):
    """Its records from a newer Mado: it announced its port, then couldn't start."""
    home = tmp_path / "Mado"
    home.mkdir()
    with closing(db.connect(home / "mado.db")) as conn:
        conn.execute("PRAGMA user_version = 999")
    env = {**os.environ, "MADO_TOKEN": TOKEN, "MADO_DATA_DIR": str(home)}
    command = [*_engine(), "serve", "--watch-stdin"]
    with subprocess.Popen(
        command,
        env=env,
        stdin=subprocess.PIPE,  # held open, as the app holds it, while the engine ends
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as engine:
        assert engine.stdout is not None
        assert engine.stderr is not None
        engine.stdout.read()
        said = engine.stderr.read()
        code = engine.wait(timeout=60)

    assert code == 3  # uvicorn's for a start that failed: an ending, not a crash
    assert "Fatal Python error" not in said


def test_export_says_when_there_is_nothing_yet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("MADO_DATA_DIR", str(tmp_path / "Mado"))

    result = runner.invoke(app, ["export", str(tmp_path / "exports")])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Mado has no data yet, so there is nothing to export."


def test_export_says_where_it_saved_the_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("MADO_DATA_DIR", str(tmp_path / "Mado"))
    with closing(db.connect(DataPaths.default().database)) as conn:
        db.migrate(conn)

    result = runner.invoke(app, ["export", str(tmp_path / "exports")])

    assert result.exit_code == 0
    assert result.stdout.startswith(f"Saved Mado's data to {tmp_path / 'exports'}")


def test_openapi_writes_the_contract(tmp_path: Path):
    result = runner.invoke(app, ["openapi", str(tmp_path / "openapi.json")])

    assert result.exit_code == 0
    written = json.loads((tmp_path / "openapi.json").read_text(encoding="utf-8"))
    assert written["info"]["title"] == "Mado engine"
