"""Making a 3D photo (docs/stack/depth.md; the rules are mado/core/motion.py): a short video of a
picture with the view moving gently through it by its depth, looping.

The picture is made the video's size; its depth (kept, as the depth tools' is) made to follow its
edges; what the moving view can uncover behind near things filled into a layer behind it, by
stretching what's beside it from farther away (Fast) or by LaMa (Best); then each frame is found
backwards from the view's path, the picture itself where it shows and the layer behind where the
view uncovered something, on a few threads at once, and handed to Mado's ffmpeg as it's made. The
video is H.264 in MP4 from the first of the encoders that work here (Windows' own first, then the
graphics card's; never OpenH264), or an animated WebP. It's made into the cache, shown playing in
the page, and saved only when the owner says, as a new file beside the picture or into a folder,
with its line in History.
"""

import logging
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado import history
from mado.ai import Ai
from mado.core.depth import placed
from mado.core.edits import Edit
from mado.core.masks import Mask, box
from mado.core.motion import (
    ENCODERS,
    FPS,
    Moving,
    behind,
    check_command,
    encode_command,
    margin,
    moving_words,
    own_share,
    path,
    pivot_of,
    sample,
    shown,
    sources,
    to_fill,
    video_size,
    webp_size,
)
from mado.core.naming import new_name
from mado.depth import Depths, edges_of, subject_at
from mado.directml import ModelError
from mado.editing import EditingError, Editor
from mado.encode import in_srgb
from mado.erasing import erased
from mado.jobs import PARTIAL
from mado.quarantine import MoveError, move
from mado.upscale import StoppedError, bled

log = logging.getLogger(__name__)

type Pixels = npt.NDArray[np.uint8]
type Floats = npt.NDArray[np.float32]
type State = Literal["waiting", "making", "done", "failed"]

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CHECKING = 20  # seconds an encoder's check may take
_THREADS = 4  # frames made at once
_COARSE = 3  # where each frame's pixels came from is found on a grid this many pixels apart
_CELL = 384  # what's uncovered is drawn by LaMa in squares about this big
_KEPT = 4  # 3D photos kept in the cache, the newest


class MotionError(Exception):
    """A 3D photo that couldn't be made or saved, with a sentence saying why."""


class Encoders:
    """The first of the H.264 encoders that works with Mado's ffmpeg on this PC (Windows' own
    first, then the graphics cards'), found once for each ffmpeg."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._found: dict[str, str] = {}

    def first(self, ffmpeg: Sequence[str]) -> str | None:
        """The encoder found, kept for the engine's life; with none, they're tried again next
        time (a driver can come back)."""
        name = "\0".join(ffmpeg)
        with self._lock:
            if name in self._found:
                return self._found[name]
        found = next((each for each in ENCODERS if _works(ffmpeg, each)), None)
        if found is not None:
            with self._lock:
                self._found[name] = found
        return found


def _works(ffmpeg: Sequence[str], encoder: str) -> bool:
    try:
        done = subprocess.run(  # noqa: S603 - Mado's own ffmpeg, fixed arguments, no shell
            check_command(ffmpeg, encoder),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_CHECKING,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return False
    return done.returncode == 0


@dataclass(frozen=True)
class Asked:
    """A 3D photo asked for: of which picture (its file and its version, its id in the library,
    or None), made how, and how it's coming on."""

    id: str
    picture_id: int
    source: Path
    version: str
    moving: Moving
    state: State = "waiting"
    progress: float = 0.0
    seconds: float | None = None  # what making it took, once it's made
    width: int = 0
    height: int = 0
    bytes: int = 0
    encoder: str | None = None  # the encoder that made an MP4
    problem: str | None = None
    file: Path | None = None


@dataclass(frozen=True)
class Saved:
    path: Path
    history_id: int


class Motions:
    """The 3D photos asked for, made one at a time on a thread of their own into the cache
    (`cache/motion`), the newest few kept; saved when the owner says."""

    def __init__(
        self,
        folder: Path,
        ai: Ai,
        depths: Depths,
        editor: Editor,
        *,
        image: Callable[[Path, str], Image.Image],
        ffmpeg: Callable[[], Sequence[str] | None],
    ) -> None:
        """`image` decodes a picture at full size from its path and version; `ffmpeg` is Mado's
        own, once it's downloaded (None till then)."""
        self._folder = folder
        self._ai = ai
        self._depths = depths
        self._editor = editor
        self._image = image
        self._ffmpeg = ffmpeg
        self._encoders = Encoders()
        self._lock = threading.Lock()
        self._asked: dict[str, Asked] = {}
        self._order: list[str] = []
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._dropped: set[str] = set()
        self._edits: dict[str, tuple[Edit, ...]] = {}
        self._saving = threading.Lock()  # one 3D photo saved at a time

    def ffmpeg_ready(self) -> bool:
        """Whether Mado's ffmpeg is here, which an MP4 needs."""
        return self._ffmpeg() is not None

    def encoder(self) -> str | None:
        """The H.264 encoder Mado makes videos with here, or None (no ffmpeg yet, or none works)."""
        ffmpeg = self._ffmpeg()
        return self._encoders.first(ffmpeg) if ffmpeg is not None else None

    def ask(
        self, picture_id: int, source: Path, version_: str, moving: Moving, edits: tuple[Edit, ...]
    ) -> Asked:
        """Asks for a 3D photo of a picture as its edits leave it; the one asked for before it
        that isn't made yet is let go."""
        asked = Asked(secrets.token_hex(6), picture_id, source, version_, moving)
        with self._lock:
            for each in list(self._order):
                if self._asked[each].state in ("waiting", "making"):
                    self._dropped.add(each)
            self._asked[asked.id] = asked
            self._edits[asked.id] = edits
            self._order.append(asked.id)
            self._tidy()
            self._start()
        self._wake.set()
        return asked

    def get(self, asked_id: str) -> Asked | None:
        with self._lock:
            return self._asked.get(asked_id)

    def drop(self, asked_id: str) -> None:
        """Lets go of a 3D photo: stopped between frames if it's being made, its file gone."""
        with self._lock:
            found = self._asked.pop(asked_id, None)
            if asked_id in self._order:
                self._order.remove(asked_id)
            self._dropped.add(asked_id)
            self._edits.pop(asked_id, None)
        if found is not None and found.file is not None:
            with suppress(OSError):
                found.file.unlink(missing_ok=True)

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def tidy(self) -> None:
        """As the engine starts: 3D photos an earlier run made and nobody saved go."""
        if self._folder.is_dir():
            shutil.rmtree(self._folder, ignore_errors=True)

    def save(
        self,
        asked_id: str,
        folder: Path,
        stem: str,
        *,
        conn: sqlite3.Connection,
        now: datetime,
    ) -> Saved:
        """Saves a 3D photo made: a new file named after the picture ("Harbour at dusk (3D
        photo).mp4", "(2)" when it's taken) in `folder`, written beside first, then moved in, its
        line in History written before it moves. Raises MotionError."""
        found = self.get(asked_id)
        if found is None or found.state != "done" or found.file is None:
            raise MotionError("That 3D photo isn't made any more: make it again, then save it.")
        if not folder.is_dir():
            raise MotionError(
                f"{folder} isn't there any more: its drive may be unplugged, or it was moved. "
                "Choose a folder for it."
            )
        extension = found.file.suffix
        partial = folder / f"{asked_id}{extension}{PARTIAL}"  # its own, however many saves
        with self._saving:
            try:
                shutil.copyfile(found.file, partial)
            except OSError as error:
                partial.unlink(missing_ok=True)
                raise MotionError(_unsaved(folder, error)) from None
            with history.MOVES:
                target = folder / new_name(
                    stem, "3D photo", extension, lambda each: (folder / each).exists()
                )
                entry = history.made(
                    conn,
                    now=now,
                    job_id=None,
                    name=found.source.name,
                    made_for=None,
                    original=found.source,
                    result=target,
                    depth=moving_words(found.moving),
                )
                for _ in range(50):
                    try:
                        move(partial, target)
                        return Saved(target, entry)
                    except MoveError:
                        if not target.exists():
                            break
                        target = folder / new_name(
                            stem, "3D photo", extension, lambda each: (folder / each).exists()
                        )
                        history.renamed(conn, entry, target)
                partial.unlink(missing_ok=True)
                history.forget(conn, entry)
                raise MotionError(f"Mado couldn't save it in {folder}.")

    # Making them, one at a time.

    def _start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="motion", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while not self._stopping.is_set():
            chosen: Asked | None = None
            with self._lock:
                for each in reversed(self._order):
                    if self._asked[each].state == "waiting" and each not in self._dropped:
                        chosen = self._asked[each]
                        break
                if chosen is not None:
                    self._update(replace(chosen, state="making"))
            if chosen is None:
                self._wake.wait(5)
                self._wake.clear()
                continue
            self._make(chosen)

    def _make(self, asked: Asked) -> None:
        began = time.monotonic()

        def stop() -> bool:
            with self._lock:
                return self._stopping.is_set() or asked.id in self._dropped

        def report(done: float) -> None:
            with self._lock:
                current = self._asked.get(asked.id)
                if current is not None:
                    self._update(replace(current, progress=min(max(done, 0.0), 1.0)))

        try:
            made = self._made(asked, stop, report)
        except StoppedError:
            made = replace(asked, state="failed", problem="It was stopped before it was made.")
        except MotionError as error:
            made = replace(asked, state="failed", problem=str(error))
        except Exception:  # the thread must outlive any one 3D photo
            log.exception("Mado couldn't make a 3D photo of %s", asked.source.name)
            made = replace(
                asked,
                state="failed",
                problem="Something went wrong inside Mado making it; its log says what.",
            )
        with self._lock:
            self._edits.pop(asked.id, None)
            if asked.id in self._asked:
                self._update(replace(made, seconds=round(time.monotonic() - began, 1)))
                return
        if made.file is not None:  # let go as it was made
            with suppress(OSError):
                made.file.unlink(missing_ok=True)

    def _made(
        self, asked: Asked, stop: Callable[[], bool], report: Callable[[float], None]
    ) -> Asked:
        moving = asked.moving
        ffmpeg = self._ffmpeg()
        encoder = None
        if moving.format == "mp4":
            if ffmpeg is None:
                raise MotionError(
                    "Making a video needs ffmpeg, which Mado downloads: download it in Settings, "
                    "then make it again."
                )
            encoder = self._encoders.first(ffmpeg)
            if encoder is None:
                raise MotionError(
                    "This PC has no H.264 encoder Mado may use (Windows' own, or an NVIDIA, AMD "
                    "or Intel card's), so it can't make an MP4: make it as an animated WebP."
                )
        try:
            picture = self._image(asked.source, asked.version)
        except Exception as error:  # what decoding raises, each with its sentence
            raise MotionError(str(error)) from None
        with self._lock:
            edits = self._edits.get(asked.id, ())
        key = f"{str(asked.source).casefold()}|{asked.version}"
        try:
            state = self._editor.state(picture, key, edits) if edits else picture
            reading = self._depths.read(picture, key, edits, edited=state)
            subject, _place = self._editor.subject(picture, key, edits, "fast", edited=state)
        except (ModelError, EditingError) as error:  # each with its sentence
            raise MotionError(str(error)) from None
        size = (
            video_size(state.width, state.height, moving.size)
            if moving.format == "mp4"
            else webp_size(state.width, state.height)
        )
        report(0.02)
        profile = picture.info.get("icc_profile")
        try:
            fill = self._ai.eraser("best")[0] if moving.fill == "best" else None
            maker = Frames(
                state,
                reading.near,
                subject,
                moving,
                size,
                fill,
                profile=profile if isinstance(profile, bytes) else None,
            )
        except (ModelError, EditingError) as error:
            raise MotionError(str(error)) from None
        report(0.1)
        self._folder.mkdir(parents=True, exist_ok=True)
        out = self._folder / f"{asked.id}.{moving.format}"
        made = maker.frames(stop, lambda done: report(0.1 + 0.85 * done))
        if moving.format == "mp4":
            assert ffmpeg is not None  # noqa: S101 - checked above
            assert encoder is not None  # noqa: S101
            encoded(made, ffmpeg, encoder, size, out)
        else:
            _webp(made, out)
        if stop():
            out.unlink(missing_ok=True)
            raise StoppedError
        return replace(
            asked,
            state="done",
            progress=1.0,
            width=size[0],
            height=size[1],
            bytes=out.stat().st_size,
            encoder=encoder,
            file=out,
        )

    def _update(self, asked: Asked) -> None:
        self._asked[asked.id] = asked

    def _tidy(self) -> None:
        """The newest few kept; older ones' files go (under the lock)."""
        while len(self._order) > _KEPT:
            old = self._order.pop(0)
            found = self._asked.pop(old, None)
            self._dropped.add(old)
            if found is not None and found.file is not None:
                with suppress(OSError):
                    found.file.unlink(missing_ok=True)


class Frames:
    """A 3D photo's frames: the picture made the video's size, its depth following its edges,
    what the view can uncover filled into a layer behind it, and each frame found backwards from
    the view's path."""

    def __init__(
        self,
        picture: Image.Image,
        near: Floats,
        subject: Mask,
        moving: Moving,
        size: tuple[int, int],
        fill: Callable[[Pixels, npt.NDArray[np.bool_]], Pixels] | None,
        *,
        profile: bytes | None = None,
    ) -> None:
        """`profile`: the picture's colour profile (its own, unless said; an edited copy can
        lose it). A video has none, so its frames are made in sRGB."""
        width, height = size
        own = picture.info.get("icc_profile")
        rgb = in_srgb(
            _on_black(picture),
            profile if profile is not None else own if isinstance(own, bytes) else None,
        )
        self.size = size
        self.pixels: Pixels = np.asarray(
            rgb.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
        )
        whole = (0.0, 0.0, float(picture.width), float(picture.height))
        self.near = edges_of(placed(near, whole, picture.size, size), self.pixels)
        small_subject = (
            np.asarray(Image.fromarray(subject, "L").resize(size, Image.Resampling.BILINEAR))
            if subject.any()
            else None
        )
        self.pivot = pivot_of(self.near, subject_at(self.near, small_subject))
        self.views = path(moving, min(size))
        self.scale = margin(self.views, size, self.pivot)
        reach = 2 + int(
            np.ceil(
                max(
                    max(abs(v.across), abs(v.down)) + abs(v.push) * max(size) / 2
                    for v in self.views
                )
                * max(self.pivot, 1 - self.pivot)
            )
        )
        _uncovers, self.back_near = behind(self.near, reach)
        self.back = self._filled(to_fill(self.near, reach), fill)
        ys, xs = np.mgrid[0:height:_COARSE, 0:width:_COARSE].astype(np.float32)
        self._grid = (xs, ys)
        self._coarse = (xs.shape[1], xs.shape[0])

    def frames(self, stop: Callable[[], bool], report: Callable[[float], None]) -> Iterator[Pixels]:
        """Each frame, in order, made a few at a time."""
        count = len(self.views)
        with ThreadPoolExecutor(max_workers=_THREADS) as pool:
            ahead = [pool.submit(self.frame, at) for at in range(min(_THREADS * 2, count))]
            for at in range(count):
                if stop():
                    for each in ahead:
                        each.cancel()
                    raise StoppedError
                made = ahead.pop(0).result()
                upcoming = at + len(ahead) + 1
                if upcoming < count:
                    ahead.append(pool.submit(self.frame, upcoming))
                report((at + 1) / count)
                yield made

    def frame(self, at: int) -> Pixels:
        """One frame: the picture itself where it shows, the layer behind where the view
        uncovered what near things hid (looked up only there)."""
        view = self.views[at]
        fx, fy, missed = sources(self.near, view, self.pivot, self.scale, self._grid, self.size)
        keep = _grown(shown(own_share(fx, fy, self.scale, _COARSE), missed), self.size)
        made = sample(self.pixels, _grown(fx, self.size), _grown(fy, self.size))
        behind_here = keep < 0.999
        if behind_here.any():
            bx, by, _missed = sources(
                self.back_near, view, self.pivot, self.scale, self._grid, self.size
            )
            back = sample(
                self.back, _grown(bx, self.size)[behind_here], _grown(by, self.size)[behind_here]
            )
            mix = keep[behind_here][..., None]
            made[behind_here] = mix * made[behind_here] + (1.0 - mix) * back
        made += 0.5
        return np.clip(made, 0, 255, out=made).astype(np.uint8)

    def _filled(
        self,
        hole: npt.NDArray[np.bool_],
        fill: Callable[[Pixels, npt.NDArray[np.bool_]], Pixels] | None,
    ) -> Pixels:
        """The layer behind: the picture with what the view can uncover filled from farther
        away: stretched from what's beside it (Fast), or drawn by LaMa a square at a time over
        that (Best), so a square never takes the near thing's colours from the next."""
        if not hole.any():
            return self.pixels.copy()
        stretched = bled(self.pixels, np.where(hole, 0, 255).astype(np.uint8))
        # Smoothed where it was carried in, as stretching would: the halving's steps go.
        soft = box(box(stretched.astype(np.float32), 3), 3)
        made = np.where(hole[..., None], np.clip(soft + 0.5, 0, 255), stretched).astype(np.uint8)
        if fill is None:
            return made
        height, width = hole.shape
        for top in range(0, height, _CELL):
            for left in range(0, width, _CELL):
                part = np.zeros_like(hole)
                part[top : top + _CELL, left : left + _CELL] = hole[
                    top : top + _CELL, left : left + _CELL
                ]
                if part.any():
                    made, _smeared = erased(made, (part * 255).astype(np.uint8), fill)
        return made


def _grown(values: Floats, size: tuple[int, int]) -> Floats:
    """A grid found `_COARSE` pixels apart made the frame's size, smoothly."""
    grown = Image.fromarray(np.ascontiguousarray(values, np.float32), "F").resize(
        size, Image.Resampling.BILINEAR
    )
    return np.asarray(grown, np.float32)


def _on_black(picture: Image.Image) -> Image.Image:
    """A picture's colours, see-through parts on black: a video has none."""
    if "A" in picture.getbands() or "transparency" in picture.info:
        rgba = picture.convert("RGBA")
        ground = Image.new("RGB", rgba.size, (0, 0, 0))
        ground.paste(rgba, mask=rgba.getchannel("A"))
        return ground
    return picture.convert("RGB")


def encoded(
    frames: Iterator[Pixels],
    ffmpeg: Sequence[str],
    encoder: str,
    size: tuple[int, int],
    out: Path,
) -> None:
    """The frames handed to ffmpeg as they're made, written as an MP4; what it says read as it
    says it, so it never waits on Mado. Whatever goes wrong, ffmpeg is stopped and no part of the
    file is left. Raises MotionError, StoppedError, and what making the frames raises."""
    try:
        process = subprocess.Popen(  # noqa: S603 - Mado's own ffmpeg, a path, no shell
            encode_command(ffmpeg, encoder, size[0], size[1], str(out)),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=_NO_WINDOW,
        )
    except OSError as error:
        raise MotionError(f"ffmpeg couldn't start: {error.strerror or error}.") from None
    stdin, stderr = process.stdin, process.stderr
    assert stdin is not None  # noqa: S101 - asked for
    assert stderr is not None  # noqa: S101
    said: list[bytes] = []
    reader = threading.Thread(target=lambda: said.extend(stderr), daemon=True)
    reader.start()

    def last_said() -> str:
        reader.join(timeout=5)
        text = b"".join(said).decode("utf-8", "replace").strip()
        return text.splitlines()[-1] if text else ""

    finished = False
    try:
        try:
            for frame in frames:
                stdin.write(frame.tobytes())
            stdin.close()
        except OSError:  # it stopped taking frames: a broken pipe, or EINVAL on Windows
            with suppress(subprocess.SubprocessError):
                process.wait(timeout=10)
            raise MotionError(
                f"ffmpeg stopped making the video: {last_said() or 'it gave no reason'}."
            ) from None
        if process.wait() != 0 or not out.is_file():
            reason = last_said() or f"it stopped with {process.returncode}"
            raise MotionError(f"ffmpeg couldn't make the video: {reason}.")
        finished = True
    finally:
        if not finished:
            if process.poll() is None:
                process.kill()
            with suppress(subprocess.SubprocessError):
                process.wait(timeout=10)
            with suppress(OSError):
                stdin.close()
            out.unlink(missing_ok=True)
        reader.join(timeout=5)


def _webp(frames: Iterator[Pixels], out: Path) -> None:
    """The frames as an animated WebP, looping."""
    images = [Image.fromarray(frame) for frame in frames]
    images[0].save(
        out,
        format="WEBP",
        save_all=True,
        append_images=images[1:],
        duration=round(1000 / FPS),
        loop=0,
        quality=82,
        method=4,
    )


def _unsaved(folder: Path, error: OSError) -> str:
    if error.errno == 28:  # ENOSPC
        return f"There isn't enough space in {folder} for it. Free some, then try again."
    return f"Mado couldn't save it in {folder}: {error.strerror or error}."
