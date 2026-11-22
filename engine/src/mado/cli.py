"""Mado's command line. The app runs `mado serve`; the uninstaller runs `mado export`."""

import json
import logging
import os
import socket
import sys
import threading
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from mado import __version__, events
from mado.api import create_app, openapi_schema
from mado.config import DataPaths
from mado.export import export_data
from mado.pc_check import probe
from mado.system import end_programs_with_engine

app = typer.Typer(help="Mado's engine.", no_args_is_help=True, add_completion=False)


@app.command()
def version() -> None:
    """Print the engine's version."""
    typer.echo(__version__)


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port on 127.0.0.1; 0 picks a free one.")] = 0,
    watch_stdin: Annotated[
        bool, typer.Option(help="Stop when stdin closes. The app holds it open while it runs.")
    ] = False,
) -> None:
    """Run the local API for the Mado app.

    Prints one JSON line, {"event": "ready", "port": N}, once it accepts connections.
    """
    token = os.environ.get("MADO_TOKEN")
    if not token:
        typer.echo(
            "MADO_TOKEN is not set. The Mado app sets it when it starts the engine.", err=True
        )
        raise typer.Exit(2)
    paths = DataPaths.default()
    _log_to_file(paths)
    end_programs_with_engine()  # no program it starts outlives it, however it ends

    sock = socket.socket()
    sock.bind(("127.0.0.1", port))
    sock.listen()  # early requests wait in the queue until the server is up
    # While it runs, the engine looks after Mado in the background (tonight's backup) and keeps
    # the library current.
    app = create_app(token, paths, work=True, watch=True, notify=events.notify)
    # A stop waits this long for open answers to end, then ends them, so Mado's care stops
    # cleanly before the app's patience runs out.
    config = uvicorn.Config(app, log_config=None, access_log=False, timeout_graceful_shutdown=2)
    server = uvicorn.Server(config)
    if watch_stdin:
        stop = threading.Thread(target=stop_when_stdin_closes, args=(server,), daemon=True)
        stop.start()
    typer.echo(json.dumps({"event": "ready", "port": sock.getsockname()[1]}))
    try:
        server.run(sockets=[sock])  # one that can't start (its records damaged) ends with 3
    except SystemExit as ending:
        code = ending.code if isinstance(ending.code, int) else 1
    else:
        code = 0
    # Its work stopped and its records closed, it ends without Python's teardown: letting
    # DirectML's sessions go can crash on the way out (mado/directml.py).
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


@app.command(name="check-model", hidden=True)
def check_model(
    timing: Annotated[bool, typer.Option("--time", help="Time each model too.")] = False,
    heavy_tile: Annotated[int, typer.Option(help="The tile the heavy models take here.")] = 256,
    best: Annotated[Path | None, typer.Option(help="The Best photo model, once fetched.")] = None,
) -> None:
    """Whether the AI models run on this PC's graphics card, and how fast: one JSON line. The
    PC check runs this in a process of its own, so a graphics driver that fails takes only it."""
    found = probe(timing=timing, heavy_tile=heavy_tile, best=best)
    typer.echo(json.dumps({"runs": found.runs, "problem": found.problem, "speeds": found.speeds}))
    sys.stdout.flush()
    os._exit(0)  # no teardown: letting DirectML's sessions go can crash on the way out


@app.command()
def export(folder: Annotated[Path, typer.Argument(help="Folder to write the zip into.")]) -> None:
    """Export everything Mado knows to one zip in FOLDER."""
    try:
        archive = export_data(DataPaths.default(), folder)
    except Exception as error:
        typer.echo(f"The export failed: {error}", err=True)
        raise typer.Exit(1) from error
    if archive is None:
        typer.echo("Mado has no data yet, so there is nothing to export.")
    else:
        typer.echo(f"Saved Mado's data to {archive}")


@app.command()
def openapi(path: Annotated[Path, typer.Argument(help="Where to write the schema.")]) -> None:
    """Write the API's OpenAPI schema: the contract the app's engine types follow."""
    path.write_text(json.dumps(openapi_schema(), indent=2) + "\n", encoding="utf-8", newline="\n")


def stop_when_stdin_closes(server: uvicorn.Server) -> None:
    """Stops the engine once the app exits and its end of the pipe closes. Read straight from
    the pipe, with no buffer between: Python can't end cleanly while a thread holds one."""
    stdin = sys.stdin.fileno()
    while os.read(stdin, 4096):
        pass
    server.should_exit = True


def _log_to_file(paths: DataPaths) -> None:
    """The engine's log, a file a day in the data folder's logs, the last 30 days kept."""
    paths.logs.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        paths.logs / "engine.log", when="midnight", backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
