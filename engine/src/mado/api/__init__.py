"""The local HTTP API the app talks to.

Only the app can use it: the engine listens on 127.0.0.1, and every request must
carry the per-launch token the app passes in MADO_TOKEN. Each feature adds its
routes as an APIRouter in its own module, included below.
"""

import logging
import secrets
import sqlite3
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mado import __version__, db, hardware, watching
from mado.ai import Ai
from mado.api import (
    backups,
    data,
    duplicates,
    editing,
    health,
    history,
    jobs,
    library,
    looks,
    making,
    opening,
    pc,
    pictures,
    queue,
    records,
    scan,
    settings,
    tools,
)
from mado.api import batches as batches_api
from mado.api import recipes as recipes_api
from mado.backups import restore_asked
from mado.batches import Picture
from mado.care import Care
from mado.config import DataPaths
from mado.core.models import BEST_PHOTO
from mado.directml import Sessions
from mado.duplicates import Finder
from mado.editing import Editor
from mado.events import Notify
from mado.hardware import Here
from mado.jobs import Jobs
from mado.making import Maker, Sight
from mado.pc_check import Check, PcCheck, check_in_own_process
from mado.pictures import Command
from mado.previews import Previews
from mado.quarantine import Quarantine
from mado.rescue import Damage, damage
from mado.samples import Samples
from mado.scan import Scanner
from mado.system import own_command
from mado.tools import Tools
from mado.watch import Watcher
from mado.watching import Watch, WatchFolders

# The app's own pages: the installed app, and the Vite dev server in development.
APP_ORIGINS = ["http://tauri.localhost", "http://localhost:1420"]
LOCAL_HOSTS = ["127.0.0.1", "localhost"]

_bearer = HTTPBearer(auto_error=False)

log = logging.getLogger(__name__)


class Unexpected:
    """A fault inside the engine, answered as one in plain words. Starlette's own last resort
    answers outside CORS, so the window couldn't read it and would say the engine didn't answer
    at all."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started = False

        async def sending(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self._app(scope, receive, sending)
        except Exception:
            log.exception("A request to the engine hit a problem")
            if started:  # half answered already: nothing better can be said
                raise
            await JSONResponse({"detail": _UNEXPECTED}, status_code=500)(scope, receive, send)


_UNEXPECTED = (
    "Something went wrong inside Mado, so it couldn't do that. Try again; Mado's log says what "
    "happened."
)


def create_app(
    token: str,
    paths: DataPaths,
    toolbox: Tools | None = None,
    *,
    work: bool = False,
    watch: bool = False,
    notify: Notify = lambda _title, _body, link=None: None,
    ffmpeg: Callable[[], Command | None] | None = None,
    quarantine: Quarantine | None = None,
    here: Callable[[], Here] | None = None,
    check: Check | None = None,
) -> FastAPI:
    """The API, with its parts. Tests pass their own tools, ffmpeg, quarantine (one of their own
    rather than the drive's), where the AI models run (the processor) and PC check. `work` looks
    after Mado in the background while the engine runs (mado/care.py) and checks this PC, and
    `watch` keeps the library current (mado/watch.py): `mado serve` turns both on, and passes
    `notify`, which tells the app what's worth a notification."""
    expected = token.encode()

    def require_token(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> None:
        given = credentials.credentials.encode() if credentials else b""
        if not secrets.compare_digest(given, expected):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Missing or wrong token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def require_records(request: Request) -> None:
        """While Mado's records are damaged, only the way back (and the health check) answers."""
        if request.app.state.damage is not None and not request.url.path.startswith(
            ("/records", "/health")
        ):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Mado's records are damaged, so it can't do that till they're back.",
            )

    @asynccontextmanager
    async def lifespan(running: FastAPI) -> AsyncGenerator[None]:
        restore_asked(paths, _now())  # a backup chosen, before anything opens it
        found = damage(paths)  # records damaged past use: nothing else can start
        running.state.damage = found
        if found is not None:
            log.error("Mado's records are damaged: %s", found.problem)
            notify("Mado's records are damaged", _way_back(found), link="/")
            yield
            return
        with closing(db.connect(paths.database)) as conn:
            db.migrate(conn)
        scanner: Scanner = running.state.scanner
        watcher = Watcher(paths, scanner) if watch else None
        running.state.watcher = watcher
        if watcher is not None:
            watcher.start()  # catches up on what changed while Mado was closed, then watches
        care: Care = running.state.care
        finder: Finder = running.state.finder
        finder.start()  # groups what was looked at before, then looks at what's new
        making_: Jobs = running.state.jobs
        with closing(db.connect(paths.database)) as conn:
            running.state.samples.tidy(conn)  # what an earlier run left in the cache goes
        running.state.editor.tidy()  # the masks of pictures not edited for a month go
        making_.start()  # a job Mado's closing cut short starts again, and batches carry on
        folders = WatchFolders(paths, take, now=_now) if watch else None
        running.state.watch_folders = folders
        if folders is not None:
            folders.start()  # takes what arrived while Mado was closed, then looks every few s
        if work:
            care.start()  # tonight's backup, and the daily clear-out of the quarantine
            running.state.pc.refresh()  # what this PC can do, checked when it needs to be
        yield
        if work:
            care.stop()
        if folders is not None:
            folders.stop()
        making_.stop()  # after the tile it's on
        if watcher is not None:
            watcher.stop()
        scanner.stop()  # after the picture it's on
        finder.stop()

    app = FastAPI(
        title="Mado engine",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.paths = paths
    app.state.damage = None  # Mado's records damaged past use, found as the engine starts
    app.state.rescued = False  # a way back was taken: the app starts the engine again
    app.state.tools = toolbox or Tools(paths)
    # The copies the window shows, made with Mado's ffmpeg for HEIC (tests pass their own).
    app.state.previews = Previews(paths, ffmpeg or (lambda: app.state.tools.path("ffmpeg")))
    # Duplicates and bursts, looked for as each scan ends.
    app.state.finder = Finder(
        paths,
        app.state.previews,
        ffmpeg or (lambda: app.state.tools.path("ffmpeg")),
        now=_now,
    )
    app.state.scanner = Scanner(paths, app.state.previews, ended=app.state.finder.wake)
    app.state.watcher = None  # set while it watches
    app.state.quarantine = quarantine or Quarantine()
    app.state.care = Care(
        paths, app.state.quarantine, now=_now, forget=lambda ids: app.state.previews.forget(ids)
    )

    def where_here() -> Here:
        with closing(db.connect(paths.database)) as conn:
            return hardware.here(conn)

    app.state.sessions = Sessions()  # every AI model's session, kept for the engine's life
    app.state.ai = Ai(app.state.sessions, app.state.tools, here or where_here)
    decoder = ffmpeg or (lambda: app.state.tools.path("ffmpeg"))
    app.state.sight = Sight(decoder)
    # Editing by clicking: parts picked and edits made, kept so the previews and Save agree.
    app.state.editor = Editor(app.state.ai, paths.cache / "edits")
    app.state.jobs = Jobs(
        paths,
        Maker(
            app.state.ai,
            app.state.quarantine,
            decoder,
            now=_now,
            kept=paths.cache / "samples" / "kept",
            editor=app.state.editor,
        ),
        app.state.quarantine,
        now=_now,
        notify=notify,
    )
    # See it first's pictures, made by the jobs' worker before the queue's.
    app.state.samples = Samples(
        paths, app.state.ai, decoder, wake=app.state.jobs.wake, editor=app.state.editor
    )
    app.state.jobs.before_the_queue(app.state.samples)
    app.state.watch_folders = None  # set while it watches

    def take(conn: sqlite3.Connection, folder: Watch, found: list[Picture]) -> None:
        watching.queue_up(conn, app.state.jobs, app.state.ai, folder, found, _now())

    app.state.pc = PcCheck(
        paths,
        check or check_in_own_process(own_command()),
        now=_now,
        busy=app.state.jobs.busy,
        best=lambda: app.state.ai.file(BEST_PHOTO),
    )
    # The middleware added last runs first: CORS answers the webview's preflight
    # checks, then only requests addressed to this PC get through, and a fault inside the
    # engine is answered in words that pass back through CORS, so the window can read them.
    app.add_middleware(Unexpected)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=APP_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Made-In"],  # how long a preview took, which the Size tab shows
    )
    guarded = [Depends(require_token), Depends(require_records)]
    parts = (
        health,
        tools,
        settings,
        library,
        scan,
        pictures,
        opening,
        making,
        editing,
        looks,
        jobs,
        batches_api,
        queue,
        recipes_api,
        duplicates,
        history,
        pc,
        data,
        backups,
        records,
    )
    for part in parts:
        app.include_router(part.router, dependencies=guarded)
    return app


def _now() -> datetime:
    return datetime.now().astimezone()


def _way_back(found: Damage) -> str:
    """What a notification says to do about damaged records."""
    if found.backup is None:
        return "Open Mado to start again with new records."
    made = found.backup.made
    return f"Open Mado to restore the backup from {made.day} {made:%B}, {made:%H:%M}."


def openapi_schema() -> dict[str, Any]:
    """The API's OpenAPI schema. It doesn't depend on the token or the data folder."""
    return create_app(secrets.token_hex(), DataPaths(Path())).openapi()
