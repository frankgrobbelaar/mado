"""The local HTTP API the app talks to.

Only the app can use it: the engine listens on 127.0.0.1, and every request must
carry the per-launch token the app passes in MADO_TOKEN. Each feature adds its
routes as an APIRouter in its own module, included below.
"""

import logging
import secrets
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mado import __version__, db
from mado.api import backups, data, health, library, pictures, records, scan, settings, tools
from mado.backups import restore_asked
from mado.care import Care
from mado.config import DataPaths
from mado.events import Notify
from mado.pictures import Command
from mado.previews import Previews
from mado.rescue import Damage, damage
from mado.scan import Scanner
from mado.tools import Tools
from mado.watch import Watcher

# The app's own pages: the installed app, and the Vite dev server in development.
APP_ORIGINS = ["http://tauri.localhost", "http://localhost:1420"]
LOCAL_HOSTS = ["127.0.0.1", "localhost"]

_bearer = HTTPBearer(auto_error=False)

log = logging.getLogger(__name__)


def create_app(
    token: str,
    paths: DataPaths,
    toolbox: Tools | None = None,
    *,
    work: bool = False,
    watch: bool = False,
    notify: Notify = lambda _title, _body, link=None: None,
    ffmpeg: Callable[[], Command | None] | None = None,
) -> FastAPI:
    """The API, with its parts. Tests pass their own tools and ffmpeg. `work` looks after Mado
    in the background while the engine runs (mado/care.py), and `watch` keeps the library
    current (mado/watch.py): `mado serve` turns both on, and passes `notify`, which tells the app
    what's worth a notification."""
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
        if work:
            care.start()  # tonight's backup
        yield
        if work:
            care.stop()
        if watcher is not None:
            watcher.stop()
        scanner.stop()  # after the picture it's on

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
    app.state.scanner = Scanner(paths, app.state.previews)
    app.state.watcher = None  # set while it watches
    app.state.care = Care(paths, now=_now)
    # The middleware added last runs first: CORS answers the webview's preflight
    # checks, then only requests addressed to this PC get through.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=APP_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    guarded = [Depends(require_token), Depends(require_records)]
    for part in (health, tools, settings, library, scan, pictures, data, backups, records):
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
