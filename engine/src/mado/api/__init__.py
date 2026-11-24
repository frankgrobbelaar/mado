"""The local HTTP API the app talks to.

Only the app can use it: the engine listens on 127.0.0.1, and every request must
carry the per-launch token the app passes in MADO_TOKEN. Each feature adds its
routes as an APIRouter in its own module, included below.
"""

import logging
import secrets
import sqlite3
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, closing, suppress
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mado import __version__, db, favourites, hardware, watching
from mado.ai import Ai
from mado.api import (
    backups,
    data,
    depth,
    duplicates,
    editing,
    health,
    history,
    jobs,
    library,
    looks,
    making,
    motion,
    opening,
    pc,
    pictures,
    queue,
    records,
    scan,
    settings,
    styles,
    tools,
)
from mado.api import batches as batches_api
from mado.api import recipes as recipes_api
from mado.api import search as search_api
from mado.api import wallpaper as wallpaper_api
from mado.backups import restore_asked
from mado.batches import Picture
from mado.care import Care
from mado.config import DataPaths
from mado.core.files import kind_of
from mado.core.hardware import Place
from mado.core.models import BEST_PHOTO
from mado.core.search import Reader as SearchReader
from mado.core.search import reader_for
from mado.depth import Depths
from mado.desktop import Desktop, NoDesktop
from mado.directml import Sessions
from mado.duplicates import Finder
from mado.editing import Editor
from mado.events import Notify
from mado.hardware import Here
from mado.jobs import Jobs
from mado.libraw import Reader
from mado.making import Maker, Sight
from mado.making import Picture as Picture_
from mado.motion import Motions
from mado.ocr import PPOCR, Best, Fast
from mado.pc_check import Check, PcCheck, check_in_own_process
from mado.pictures import Command
from mado.previews import Previews
from mado.quarantine import Quarantine
from mado.rescue import Damage, damage
from mado.samples import Samples
from mado.scan import RAW_NOTES, Scanner, stopped_on
from mado.search import BestWords, Describer, FastWords, Search, chosen
from mado.siglip import SIGLIP, Siglip
from mado.system import own_command
from mado.tools import Tools
from mado.wallpaper import Studio
from mado.watch import Watcher
from mado.watching import Watch, WatchFolders

# The app's own pages: the installed app, and the Vite dev server in development.
APP_ORIGINS = ["http://tauri.localhost", "http://localhost:1420"]
LIBRAW = "libraw"  # camera RAW's reader, in downloads.json
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
    desktop: Desktop | None = None,
    reader: Reader | None = None,
    describer: Describer | None = None,
    words: FastWords | None = None,
    best_words: BestWords | None = None,
) -> FastAPI:
    """The API, with its parts. Tests pass their own tools, ffmpeg, quarantine (one of their own
    rather than the drive's), where the AI models run (the processor), PC check, desktop (a
    fake: only `mado serve` hands the studio Windows' own, so no test touches the owner's
    wallpaper) and RAW reader (LibRaw where they read camera RAW, else one that never fetches).
    `work` looks after Mado in the background while the engine runs (mado/care.py, the daily
    wallpaper) and checks this PC, and `watch` keeps the library current (mado/watch.py): `mado
    serve` turns both on, and passes `notify`, which tells the app what's worth a notification.
    Tests pass their own SigLIP (`describer`) and readers of words (`words`, Windows' own;
    `best_words`, PP-OCRv6), so the library is read for search only where they ask it to be."""
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
        reader_: Reader = running.state.reader
        with closing(db.connect(paths.database)) as conn:
            db.migrate(conn)
            stopped_on(conn, reader_, now=_now())  # RAWs an earlier engine stopped on, first
        scanner: Scanner = running.state.scanner
        watcher = Watcher(paths, scanner) if watch else None
        running.state.watcher = watcher
        if watcher is not None:
            watcher.start()  # catches up on what changed while Mado was closed, then watches
        care: Care = running.state.care
        finder: Finder = running.state.finder
        finder.start()  # groups what was looked at before, then looks at what's new
        searching: Search = running.state.search
        searching.start()  # reads what's new for search, once its models are here
        making_: Jobs = running.state.jobs
        studio: Studio = running.state.wallpaper
        with closing(db.connect(paths.database)) as conn:
            running.state.samples.tidy(conn)  # what an earlier run left in the cache goes
            studio.recover(conn)  # a wallpaper a stop cut short is made again
        running.state.editor.tidy()  # the masks of pictures not edited for a month go
        running.state.depths.tidy()  # and the depth of pictures not used for a month
        running.state.motions.tidy()  # 3D photos an earlier run made and nobody saved
        running.state.previews.tidy()  # a HEIC's gain map a stop left on its way to ffmpeg
        making_.start()  # a job Mado's closing cut short starts again, and batches carry on
        folders = WatchFolders(paths, take, now=_now, reader=reader_) if watch else None
        running.state.watch_folders = folders
        if folders is not None:
            folders.start()  # takes what arrived while Mado was closed, then looks every few s
        if work:
            care.start()  # tonight's backup, and the daily clear-out of the quarantine
            studio.start()  # the daily wallpaper, and Mado's own wallpapers tidied
            running.state.pc.refresh()  # what this PC can do, checked when it needs to be
        yield
        if work:
            care.stop()
            studio.stop()
        if folders is not None:
            folders.stop()
        making_.stop()  # after the tile it's on
        running.state.motions.stop()  # between frames
        if watcher is not None:
            watcher.stop()
        scanner.stop()  # after the picture it's on
        finder.stop()
        searching.stop()  # after the picture it's on
        reader_.forget_notes()  # what it was reading didn't stop it

    app = FastAPI(
        title="Mado engine",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.paths = paths
    app.state.damage = None  # Mado's records damaged past use, found as the engine starts
    app.state.rescued = False  # a way back was taken: the app starts the engine again
    app.state.tools = toolbox or Tools(paths)

    def libraw_folder() -> Path | None:
        try:
            return app.state.tools.folder(LIBRAW)
        except KeyError:  # a list without it
            return None

    def libraw(action: str) -> Callable[[], None]:
        def act() -> None:
            with suppress(KeyError):
                getattr(app.state.tools, action)(LIBRAW)

        return act

    def fetch_libraw() -> None:  # asked for by itself: not again after a download refused
        with suppress(KeyError):
            app.state.tools.start(LIBRAW, by_itself=True)

    # Camera RAW's reader: LibRaw, fetched the first time a RAW is read or opened, each RAW it
    # reads noted while it does.
    app.state.reader = reader or Reader(
        libraw_folder, fetch_libraw, libraw("broken"), notes=paths.root / RAW_NOTES
    )

    def arrived(tool: str) -> None:
        if tool == LIBRAW:  # the RAWs listed while they waited for it are read now
            app.state.scanner.request()
        # Search reads with a model as soon as it's here; a picture it couldn't read before
        # (a HEIC before ffmpeg, a RAW before its reader) is tried again.
        app.state.search.wake(again=tool not in (SIGLIP, PPOCR))

    app.state.tools.arrived = arrived
    # The copies the window shows, made with Mado's ffmpeg for HEIC (tests pass their own).
    app.state.previews = Previews(
        paths, ffmpeg or (lambda: app.state.tools.path("ffmpeg")), app.state.reader
    )
    # Duplicates and bursts, looked for as each scan ends.
    app.state.finder = Finder(
        paths,
        app.state.previews,
        ffmpeg or (lambda: app.state.tools.path("ffmpeg")),
        now=_now,
    )

    def scan_ended() -> None:
        """A scan ended: favourites follow pictures it found moved or renamed, and what it read
        is looked at for duplicates."""
        try:
            with closing(db.connect(paths.database)) as conn:
                favourites.follow(conn)
        except sqlite3.Error:
            log.exception("Mado couldn't look for favourites that moved")
        app.state.finder.wake()
        app.state.search.wake(again=True)  # what couldn't be read is tried once more

    app.state.scanner = Scanner(paths, app.state.previews, ended=scan_ended)
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
    app.state.sight = Sight(decoder, app.state.reader)
    # Editing by clicking: parts picked and edits made, kept so the previews and Save agree.
    app.state.editor = Editor(app.state.ai, paths.cache / "edits")
    # Depth: each picture's read once and kept, for portrait blur, fog, tilt-shift and 3D photos.
    app.state.depths = Depths(app.state.ai, app.state.editor, paths.cache / "depth")

    # 3D photos: made into the cache, played in the page, saved when the owner says.
    def picture_image(source: Path, version_: str) -> Image.Image:
        return app.state.sight.picture(
            Picture_(source, kind_of(source.name) or "picture", None, None), version_
        )

    def motion_ffmpeg() -> list[str] | None:
        found = (ffmpeg or (lambda: app.state.tools.path("ffmpeg")))()
        if found is None:
            return None
        return [str(found)] if isinstance(found, Path) else [str(each) for each in found]

    app.state.motions = Motions(
        paths.cache / "motion",
        app.state.ai,
        app.state.depths,
        app.state.editor,
        image=picture_image,
        ffmpeg=motion_ffmpeg,
    )
    app.state.jobs = Jobs(
        paths,
        Maker(
            app.state.ai,
            app.state.quarantine,
            decoder,
            now=_now,
            kept=paths.cache / "samples" / "kept",
            editor=app.state.editor,
            reader=app.state.reader,
            depths=app.state.depths,
            scratch=paths.cache / "hdr",
        ),
        app.state.quarantine,
        now=_now,
        notify=notify,
    )
    # See it first's pictures, made by the jobs' worker before the queue's.
    app.state.samples = Samples(
        paths,
        app.state.ai,
        decoder,
        wake=app.state.jobs.wake,
        editor=app.state.editor,
        reader=app.state.reader,
        depths=app.state.depths,
    )
    # The wallpaper studio: its wallpapers made by the jobs' worker after See it first's.
    app.state.wallpaper = Studio(
        paths.wallpapers,
        desktop or NoDesktop(),
        app.state.ai,
        app.state.sight,
        app.state.quarantine,
        database=paths.database,
        wake=app.state.jobs.wake,
        now=_now,
    )

    def first(stop: Callable[[], bool]) -> bool:
        return app.state.samples(stop) or app.state.wallpaper(stop)

    app.state.jobs.before_the_queue(first)
    app.state.watch_folders = None  # set while it watches

    def take(conn: sqlite3.Connection, folder: Watch, found: list[Picture]) -> None:
        watching.queue_up(conn, app.state.jobs, app.state.ai, folder, found, _now())

    # Search: the library read in the background for what each picture shows (SigLIP) and the
    # words in it (Best, PP-OCRv6, on the card when it has room; Fast, Windows' own reader).
    def best_place() -> Place:
        return app.state.ai.edit_place(PPOCR, real_best.detector())

    real_best = Best(app.state.sessions, app.state.tools, best_place)

    def words_reader(conn: sqlite3.Connection) -> SearchReader:
        place = app.state.ai.where().place
        return reader_for(chosen(conn), place, app.state.search.fast.ready())

    app.state.search = Search(
        paths,
        app.state.previews,
        describer or Siglip(app.state.sessions, app.state.tools),
        best_words or real_best,
        words or Fast(),
        ffmpeg=decoder,
        reader=words_reader,
        busy=app.state.jobs.busy,
        now=_now,
    )
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
        # how long a preview took, which the Size tab shows; and what the scratch detector found
        expose_headers=["X-Made-In", "X-Found", "X-Place", "X-Waited"],
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
        depth,
        motion,
        looks,
        styles,
        jobs,
        batches_api,
        queue,
        recipes_api,
        duplicates,
        search_api,
        wallpaper_api,
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
