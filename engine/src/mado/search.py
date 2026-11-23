"""Search: the library read in the background, by SigLIP for what each picture shows and by an OCR
reader for the words in it, and what a search finds (docs/stack/search.md).

- Reading, as duplicates are looked for (mado/duplicates.py): a thread of its own reads each
  library picture once the scan has read it, and again once its file changes, a picture at a
  time: SigLIP from the thumbnail the scan made (so nothing is decoded twice); the words at Best
  only where the detector finds text in that thumbnail, then from the picture itself, at Fast by
  Windows' own reader. It never reads a picture from outside the library, one in a quarantine,
  one that won't open or is marked as damaged, nor one on a drive that isn't connected (whose
  pictures keep what was read of them). It can be paused, says how far it has got, and takes
  turns with the queue and edits at the graphics card's one lock (mado/directml.py), a picture's
  work at a time; while the queue makes a picture, it rests between its turns on the card, so
  the queue keeps nearly all of it.
- Keeping: the words in the database (`words_read`, and FTS5's `words`); each picture's vector,
  768 numbers kept as 16-bit floats, in search.db beside it, made again by reading when it's
  lost or damaged (it never goes into a backup or the export).
- Finding: the vectors are loaded into memory (32-bit) when a search comes, kept up to date with
  what reading adds, and let go after IDLE with none; a search is ranked by SigLIP's own score
  and cut where it isn't what was described (mado/core/search.py).
"""

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Collection, Iterable, Sequence
from contextlib import closing, suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado import db
from mado.config import DataPaths
from mado.core.files import kind_of
from mado.core.hardware import Place
from mado.core.naming import QUARANTINE
from mado.core.search import (
    DIMENSIONS,
    Choice,
    Ranked,
    Reader,
    described,
    index_terms,
    nearest,
)
from mado.directml import ModelError
from mado.ocr import SIDE, Read
from mado.pictures import (
    Command,
    InUseError,
    NeedsFfmpegError,
    NeedsReaderError,
    PictureGoneError,
    UnreadableError,
    decode,
)
from mado.previews import Previews, Source

log = logging.getLogger(__name__)

type Vector = npt.NDArray[np.float32]

IDLE = 600.0  # seconds without a search before the vectors are let go of memory
_REST = 300.0  # seconds the thread rests with nothing to read; a scan ending wakes it
_CHUNK = 16  # pictures read between looks at what's waiting
_PAUSED = "search_paused"  # the settings row that keeps a pause across restarts
_SCHEMA = 1  # search.db's own version: another one is read again from the start
_FAST_SIDE = 1280  # Windows' reader reads a picture this big, at twice its size
_LOAD = 4096  # rows of search.db brought into memory at a time
# While the queue makes a picture, reading rests this many times as long as its turn on the card
# took, so the queue keeps nearly all of it.
_SHARE = 9.0
# What reading looks at: the library's own pictures, read, that open, not marked as damaged.
LISTED = (
    "p.gone_at IS NULL AND p.read_at IS NOT NULL AND p.problem IS NULL AND p.damaged = 0"
    " AND NOT (p.raw = 1 AND p.width IS NULL) AND p.folder_id IS NOT NULL"
)
# What its progress counts: those, and the pictures the scan hasn't read yet, as they're to come.
COUNTED = (
    "p.gone_at IS NULL AND p.problem IS NULL AND p.damaged = 0 AND p.folder_id IS NOT NULL"
    " AND NOT (p.raw = 1 AND p.width IS NULL AND p.read_at IS NOT NULL)"
)
type Failing = Literal["pictures", "words"]  # SigLIP, or the reader of words


class Describer(Protocol):
    """What reads a picture, or a search, into its vector: SigLIP (mado/siglip.py)."""

    def ready(self) -> bool: ...

    def fetch(self) -> None: ...

    def picture(self, image: Image.Image, *, threads: int | None = ...) -> Vector: ...

    def search(self, words: str) -> Vector: ...


class BestWords(Protocol):
    """The words reader at Best: PP-OCRv6 (mado/ocr.py)."""

    def ready(self) -> bool: ...

    def fetch(self) -> None: ...

    def place(self) -> Place: ...

    def glance(self, thumbnail: Image.Image) -> bool: ...

    def read(self, picture: Image.Image) -> Read: ...


class FastWords(Protocol):
    """The words reader at Fast: Windows' own (mado/ocr.py)."""

    def languages(self) -> list[str]: ...

    def ready(self) -> bool: ...

    def read(self, picture: Image.Image) -> Read: ...


@dataclass(frozen=True)
class Progress:
    """How far reading has got: pictures read as they are now, of those there are to read (the
    library's pictures that open, on drives connected, or read before), and what it's doing."""

    read: int
    of: int
    reading: bool  # reading now
    paused: bool  # the owner paused it
    busy: bool  # the queue has the graphics card: reading takes its turns more slowly
    failed: int = 0  # pictures that couldn't be read now: tried again after the next scan
    problem: tuple[Failing, str] | None = None  # a reader that couldn't run, and what it said


@dataclass
class _Index:
    """The vectors in memory: a row each, with its picture and the file it was read from."""

    ids: npt.NDArray[np.int64] = field(default_factory=lambda: np.zeros(0, np.int64))
    sizes: npt.NDArray[np.int64] = field(default_factory=lambda: np.zeros(0, np.int64))
    modified: npt.NDArray[np.int64] = field(default_factory=lambda: np.zeros(0, np.int64))
    matrix: npt.NDArray[np.float32] = field(
        default_factory=lambda: np.zeros((0, DIMENSIONS), np.float32)
    )
    seq: int = 0  # the last change of search.db it holds
    rows: dict[int, int] = field(default_factory=dict[int, int])
    count: int = 0  # rows in use; the matrix has room for more


class Vectors:
    """What SigLIP read each picture into, in search.db beside the database, and the copy in
    memory a search ranks."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()  # the copy in memory
        self._index: _Index | None = None
        self._used = 0.0  # when a search last asked for it (monotonic)
        self._timer: threading.Timer | None = None
        self._started_again = False  # search.db was made again: memory's copy is of the old one
        # A connection opened at a time: two making search.db at once trip over each other's locks
        # before it's in WAL, and SQLite gives one of them up as busy at once.
        self._opening = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        """search.db, made as it should be: one damaged, or of another version, is deleted and
        started afresh (it's Mado's own, and reading makes it again)."""
        with self._opening:
            return self._connected()

    def _connected(self) -> sqlite3.Connection:
        try:
            return self._open()
        except sqlite3.DatabaseError as error:
            if _busy(error):  # another connection has it for a moment: not damage
                raise
            # Its words, not the error itself: a log that keeps it would keep the file open.
            log.warning("search.db can't be used (%s), so Mado reads the library again", str(error))
            for each in (self._path, *self._path.parent.glob(f"{self._path.name}-*")):
                with suppress(OSError):
                    each.unlink()
            self._started_again = True
            return self._open()

    def _open(self) -> sqlite3.Connection:
        conn = db.connect(self._path)
        try:
            version: int = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, _SCHEMA):
                raise sqlite3.DatabaseError(f"its version is {version}, not {_SCHEMA}")
            if version == 0:  # made here, the write lock taken first: two making it wait
                conn.executescript(
                    f"""BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS vectors (
                        picture_id INTEGER PRIMARY KEY,
                        size       INTEGER NOT NULL,  -- the picture's file as it was read
                        modified   INTEGER NOT NULL,
                        seq        INTEGER NOT NULL,  -- when, in order: what memory's copy holds
                        vector     BLOB NOT NULL      -- 768 numbers, 16-bit floats
                    ) STRICT;
                    CREATE INDEX IF NOT EXISTS vectors_by_seq ON vectors (seq);
                    PRAGMA user_version = {_SCHEMA};
                    COMMIT;"""
                )
            conn.execute("SELECT 1 FROM vectors LIMIT 1").fetchone()
        except BaseException:
            conn.close()
            raise
        return conn

    def keep(
        self,
        conn: sqlite3.Connection,
        kept: Iterable[tuple[int, int, int, npt.NDArray[np.float32]]],
    ) -> None:
        """Pictures' vectors (each picture's number, its file's size and time, its vector)."""
        rows = list(kept)
        if not rows:
            return
        # Numbered on from the last under the write lock, so two keeping at once (reading, and
        # More like this reading a picture there and then) never take the same number, which
        # the copy in memory would miss one of.
        conn.execute("BEGIN IMMEDIATE")
        try:
            seq: int = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM vectors").fetchone()[0]
            conn.executemany(
                """INSERT INTO vectors (picture_id, size, modified, seq, vector)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (picture_id) DO UPDATE SET size = excluded.size,
                       modified = excluded.modified, seq = excluded.seq,
                       vector = excluded.vector""",
                [
                    (picture_id, size, modified, seq + at, vector.astype("<f2").tobytes())
                    for at, (picture_id, size, modified, vector) in enumerate(rows, start=1)
                ],
            )
        except BaseException:
            conn.rollback()
            raise
        conn.commit()

    def forget(self, conn: sqlite3.Connection, keep: Collection[int]) -> int:
        """Lets go of the vectors of pictures no longer in the library: those not in `keep`."""
        held = [row[0] for row in conn.execute("SELECT picture_id FROM vectors")]
        gone = [(each,) for each in held if each not in keep]
        with conn:
            conn.executemany("DELETE FROM vectors WHERE picture_id = ?", gone)
        return len(gone)

    def ranked(self, search: npt.NDArray[np.float32]) -> list[tuple[int, int, int, float]]:
        """The pictures SigLIP scores as what a search describes, best first: each picture's
        number, the file it was read from (size and time) and its score."""
        index = self._current()
        found = described(index.matrix[: index.count], search)
        return self._rows(index, found)

    def like(self, picture_id: int) -> list[tuple[int, int, int, float]] | None:
        """The pictures most like one, by their vectors, nearest first, with how alike they are;
        None when that picture has no vector yet."""
        index = self._current()
        row = index.rows.get(picture_id)
        if row is None:
            return None
        return self._rows(index, nearest(index.matrix[: index.count], row))

    def vector_of(self, picture_id: int) -> tuple[int, int] | None:
        """The file (size and time) a picture's vector was read from, if it has one."""
        index = self._current()
        row = index.rows.get(picture_id)
        return None if row is None else (int(index.sizes[row]), int(index.modified[row]))

    def held(self) -> int:
        """Bytes the copy in memory holds now (0 when it's let go)."""
        with self._lock:
            return 0 if self._index is None else int(self._index.matrix.nbytes)

    def let_go(self) -> None:
        """Lets go of the copy in memory (it's loaded again by the next search)."""
        with self._lock:
            self._index = None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _rows(self, index: _Index, found: Ranked) -> list[tuple[int, int, int, float]]:
        return [
            (int(index.ids[row]), int(index.sizes[row]), int(index.modified[row]), score)
            for row, score in zip(found.rows, found.scores, strict=True)
        ]

    def _current(self) -> _Index:
        """The copy in memory, brought up to date with search.db (loaded whole the first time),
        and let go again after IDLE without a search."""
        with self._lock:
            with closing(self.connect()) as conn:
                if self._started_again:
                    self._started_again = False
                    self._index = None
                index = self._index or _Index()
                fresh: int = conn.execute(
                    "SELECT COUNT(*) FROM vectors WHERE seq > ?", (index.seq,)
                ).fetchone()[0]
                if fresh:
                    _room(index, index.count + fresh)
                    found = conn.execute(
                        "SELECT picture_id, size, modified, seq, vector FROM vectors"
                        " WHERE seq > ? ORDER BY seq",
                        (index.seq,),
                    )
                    while chunk := found.fetchmany(_LOAD):
                        _add(index, chunk)
            self._index = index
            self._used = time.monotonic()
            self._later()
            return index

    def _later(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(IDLE, self._idle)
        self._timer.daemon = True
        self._timer.start()

    def _idle(self) -> None:
        with self._lock:
            if time.monotonic() - self._used >= IDLE - 1:
                self._index = None
                self._timer = None


def _room(index: _Index, need: int) -> None:
    """Room in the copy in memory for `need` rows: made once for a whole load, and a quarter more
    at a time as reading adds a few, so the vectors aren't copied over and over."""
    if need <= len(index.matrix):
        return
    rows = max(need, len(index.matrix) + len(index.matrix) // 4, 1024)
    index.matrix = _grown(index.matrix, rows, (DIMENSIONS,), np.float32)
    index.ids = _grown(index.ids, rows, (), np.int64)
    index.sizes = _grown(index.sizes, rows, (), np.int64)
    index.modified = _grown(index.modified, rows, (), np.int64)


def _add(index: _Index, rows: list[sqlite3.Row]) -> None:
    """Rows of search.db into the copy in memory: a picture read again takes its row's place, a
    new one a row at the end."""
    _room(index, index.count + len(rows))
    blob = b"".join(row["vector"] for row in rows)
    vectors = np.frombuffer(blob, "<f2").reshape(len(rows), DIMENSIONS).astype(np.float32)
    for at, row in enumerate(rows):
        place = index.rows.get(row["picture_id"])
        if place is None:
            place = index.count
            index.rows[row["picture_id"]] = place
            index.count += 1
        index.matrix[place] = vectors[at]
        index.ids[place] = row["picture_id"]
        index.sizes[place] = row["size"]
        index.modified[place] = row["modified"]
        index.seq = max(index.seq, int(row["seq"]))


def _grown[T: np.generic](
    array: npt.NDArray[T], rows: int, shape: tuple[int, ...], kind: type[T]
) -> npt.NDArray[T]:
    bigger = np.zeros((rows, *shape), kind)
    bigger[: len(array)] = array
    return bigger


class Search:
    """Reads the library for search in the background, and finds what's searched for."""

    def __init__(
        self,
        paths: DataPaths,
        previews: Previews,
        siglip: Describer,
        best: BestWords,
        fast: FastWords,
        *,
        ffmpeg: Callable[[], Command | None],
        reader: Callable[[sqlite3.Connection], Reader],
        busy: Callable[[], bool] = lambda: False,
        now: Callable[[], datetime],
    ) -> None:
        """`reader` says which words reader is in use (the owner's choice, or as this PC suits);
        `busy` whether the queue is making a picture."""
        self.vectors = Vectors(paths.search)
        self._paths = paths
        self._previews = previews
        self.siglip = siglip
        self.best = best
        self.fast = fast
        self._ffmpeg = ffmpeg
        self._reader = reader
        self._busy = busy
        self._now = now
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._asked = 0
        self._thread: threading.Thread | None = None
        self._reading = False
        self._skipped: set[tuple[int, int, int]] = set()  # pictures that couldn't be read now
        self._problems: dict[Failing, str] = {}  # readers that couldn't run, and what they said

    def start(self) -> None:
        self._stopping.clear()
        self.wake()
        self._thread = threading.Thread(target=self._loop, name="search", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.vectors.let_go()

    def wake(self, *, again: bool = False) -> None:
        """Reads what's new now: a scan ended, a model came, the owner changed something.
        `again` tries the pictures that couldn't be read before, and a reader that couldn't run
        (a scan ended, ffmpeg or the RAW reader came, the owner's Try again)."""
        with self._lock:
            self._asked += 1
            self._idle.clear()
            if again:
                self._skipped.clear()
                self._problems.clear()
        self._wake.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Till nothing's left to read now (tests). True when so."""
        return self._idle.wait(timeout)

    def reader_now(self, conn: sqlite3.Connection) -> Reader:
        """The words reader in use: the owner's choice, or as this PC suits."""
        return self._reader(conn)

    # Pausing.

    def paused(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (_PAUSED,)).fetchone()
        return row is not None and row["value"] == "true"

    def pause(self, conn: sqlite3.Connection, paused: bool) -> None:
        """Pauses reading after the picture it's on, or goes on; kept across restarts."""
        with conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (_PAUSED, "true" if paused else "false"),
            )
        self.wake(again=not paused)  # going on tries again what couldn't be read

    # How far it's got.

    def progress(self, conn: sqlite3.Connection) -> Progress:
        """How far reading has got, counted a library folder at a time: a picture is read once
        every reader there is now has read it (SigLIP, and the words reader in use); one the
        scan hasn't read yet is still to come; one on a drive that isn't connected counts only
        once it's read, as it can't be till it's back."""
        reader = self._reader(conn)
        describing, wording = self.siglip.ready(), self._words_ready(reader)
        away = away_folders(conn)
        with self._lock:
            skipped = [list(each) for each in self._skipped]
            problem = next(iter(self._problems.items()), None)
        read = of = 0
        with self._attached(conn):
            for row in conn.execute(
                f"""SELECT p.folder_id, COUNT(*) AS pictures,
                           SUM(listed AND v.picture_id IS NOT NULL) AS described,
                           SUM(listed AND w.picture_id IS NOT NULL) AS worded,
                           SUM(listed AND v.picture_id IS NOT NULL
                               AND w.picture_id IS NOT NULL) AS both
                    FROM (SELECT p.*, p.read_at IS NOT NULL AS listed FROM pictures AS p
                          WHERE {COUNTED}) AS p
                    LEFT JOIN seen.vectors AS v
                      ON v.picture_id = p.id AND v.size = p.size AND v.modified = p.modified
                    LEFT JOIN words_read AS w
                      ON w.picture_id = p.id AND w.size = p.size AND w.modified = p.modified
                         AND w.reader = ?
                    GROUP BY p.folder_id""",  # noqa: S608 - a fixed fragment
                (reader,),
            ):
                if describing and wording:
                    done = row["both"]
                elif describing:
                    done = row["described"]
                elif wording:
                    done = row["worded"]
                else:  # nothing reads now: what was read before
                    done = row["described"]
                read += done
                of += done if row["folder_id"] in away else row["pictures"]
            failed: int = conn.execute(
                f"""SELECT COUNT(*) FROM pictures AS p
                    WHERE {LISTED} AND p.folder_id NOT IN (SELECT value FROM json_each(?))
                      AND EXISTS (
                          SELECT 1 FROM json_each(?) AS s
                          WHERE s.value ->> 0 = p.id AND s.value ->> 1 = p.size
                            AND s.value ->> 2 = p.modified)""",  # noqa: S608 - fixed
                (json.dumps(sorted(away)), json.dumps(skipped)),
            ).fetchone()[0]
        with self._lock:
            reading = self._reading
        # Reading shares the card only for the words at Best, when they're read there.
        shares = wording and reader == "best" and self.best.place() == "card"
        busy = shares and self._busy()
        return Progress(read, of, reading, self.paused(conn), busy, failed, problem)

    # Finding.

    def described_as(self, words: str) -> list[tuple[int, int, int, float]]:
        """The pictures that look like what `words` describe, best first, with SigLIP's score:
        each picture's number and the file it was read from. Raises ModelError while SigLIP
        isn't downloaded."""
        return self.vectors.ranked(self.siglip.search(words))

    def worded(self, conn: sqlite3.Connection, query: str) -> list[int]:
        """The pictures whose words (read as their files are now) match an FTS5 query of the
        words index, the best matches first: every one, as Many at once takes them all."""
        return [
            row["id"]
            for row in conn.execute(
                f"""SELECT p.id FROM words AS w
                    JOIN words_read AS r ON r.picture_id = w.rowid
                    JOIN pictures AS p ON p.id = r.picture_id
                    WHERE words MATCH ? AND r.size = p.size AND r.modified = p.modified
                      AND {LISTED}
                    ORDER BY bm25(words), p.taken_at DESC""",  # noqa: S608 - fixed
                (query,),
            )
        ]

    def texts(self, conn: sqlite3.Connection, ids: Sequence[int]) -> dict[int, str]:
        """The words read in some pictures, as they were read (those a search shows)."""
        return {
            row["rowid"]: row["text"]
            for row in conn.execute(
                "SELECT rowid, text FROM words WHERE rowid IN (SELECT value FROM json_each(?))",
                (json.dumps(list(ids)),),
            )
        }

    def like(self, conn: sqlite3.Connection, picture_id: int) -> list[tuple[int, int, int, float]]:
        """The pictures most like one, nearest first: read now, when it hasn't been yet and SigLIP
        is there, if it's one reading reads (the library's, opening, not marked as damaged, not
        in a quarantine). Raises ModelError while SigLIP isn't downloaded, or it can't be read."""
        row = conn.execute(
            f"SELECT p.* FROM pictures AS p WHERE p.id = ? AND {LISTED}",  # noqa: S608 - fixed
            (picture_id,),
        ).fetchone()
        if row is None or _in_a_quarantine(row["path"]):
            raise ModelError("Search doesn't read that picture: it isn't one of your library's.")
        if self.vectors.vector_of(picture_id) != (row["size"], row["modified"]):
            image = self._thumbnail(row)
            if image is None:
                raise ModelError("Mado couldn't read that picture for search.")
            vector = self.siglip.picture(image)  # on reading's session: SigLIP held once
            with closing(self.vectors.connect()) as side:
                self.vectors.keep(side, [(picture_id, row["size"], row["modified"], vector)])
        return self.vectors.like(picture_id) or []

    # Reading.

    def _words_ready(self, reader: Reader) -> bool:
        return self.best.ready() if reader == "best" else self.fast.ready()

    def _loop(self) -> None:
        while not self._stopping.is_set():
            with self._lock:
                seen = self._asked
            worked = False
            try:
                worked = self._read_some()
            except sqlite3.OperationalError as error:
                if _busy(error):  # a database busy for a moment: again shortly, not in minutes
                    log.info("Reading for search waits for the database: %s", error)
                    self._stopping.wait(1.0)
                    worked = True
                else:
                    log.exception("Reading the library for search hit a problem")
            except Exception:  # reading must outlive any one problem
                log.exception("Reading the library for search hit a problem")
            with self._lock:
                if self._asked == seen and not worked:
                    self._idle.set()
                if not worked:  # between chunks it's still reading, as the window polls
                    self._reading = False
            if worked:
                continue
            self._wake.wait(_REST)
            self._wake.clear()

    def _read_some(self) -> bool:
        """Reads the next few pictures not read as they are now. False when there were none, or
        reading is paused."""
        with closing(db.connect(self._paths.database)) as conn:
            if self.paused(conn):
                return False
            reader = self._reader(conn)
            with self._lock:
                failing = set(self._problems)
            describing = self.siglip.ready() and "pictures" not in failing
            wording = self._words_ready(reader) and "words" not in failing
            if not (describing or wording):
                return False
            todo = self._waiting(conn, reader, describing, wording)
            if not todo:
                self._tidy(conn)
                return False
            with self._lock:
                self._reading = True
            with closing(self.vectors.connect()) as side:
                for row in todo:
                    if self._stopping.is_set() or self.paused(conn):
                        return True
                    if not self._read_one(conn, side, row, reader, describing, wording):
                        return True  # a reader that can't run: the other reads on
        return True

    def _waiting(
        self, conn: sqlite3.Connection, reader: Reader, describing: bool, wording: bool
    ) -> list[sqlite3.Row]:
        """The next pictures to read, newest file first: on drives connected, not left as
        unreadable now (as their files are), missing what a reader there is now would read."""
        missing = (
            "(v.picture_id IS NULL OR w.picture_id IS NULL)"
            if describing and wording
            else "v.picture_id IS NULL"
            if describing
            else "w.picture_id IS NULL"
        )
        away = sorted(away_folders(conn))
        with self._lock:
            skipped = [list(each) for each in self._skipped]
        with self._attached(conn):
            rows = conn.execute(
                f"""SELECT p.*, v.picture_id IS NULL AS to_describe,
                           w.picture_id IS NULL AS to_word
                    FROM pictures AS p
                    LEFT JOIN seen.vectors AS v
                      ON v.picture_id = p.id AND v.size = p.size AND v.modified = p.modified
                    LEFT JOIN words_read AS w
                      ON w.picture_id = p.id AND w.size = p.size AND w.modified = p.modified
                         AND w.reader = ?
                    WHERE {LISTED} AND {missing}
                      AND p.folder_id NOT IN (SELECT value FROM json_each(?))
                      AND NOT EXISTS (
                          SELECT 1 FROM json_each(?) AS s
                          WHERE s.value ->> 0 = p.id AND s.value ->> 1 = p.size
                            AND s.value ->> 2 = p.modified)
                    ORDER BY p.modified DESC, p.id LIMIT ?""",  # noqa: S608 - fixed fragments
                (reader, json.dumps(away), json.dumps(skipped), _CHUNK),
            ).fetchall()
        wanted: list[sqlite3.Row] = []
        for row in rows:
            if _in_a_quarantine(row["path"]):  # never read, nor looked at again
                self._skip(row)
            else:
                wanted.append(row)
        if rows and not wanted:  # all of them set aside: the next ones
            return self._waiting(conn, reader, describing, wording)
        return wanted

    def _read_one(
        self,
        conn: sqlite3.Connection,
        side: sqlite3.Connection,
        row: sqlite3.Row,
        reader: Reader,
        describing: bool,
        wording: bool,
    ) -> bool:
        """Reads one picture: its vector from its thumbnail, its words; either kept as soon as
        it's read. One that can't be read now is left till something changes, or the next scan.
        False when a reader couldn't run: it's said, and rests till Try again or the next scan,
        rather than try every picture; the other reads on."""
        thumbnail = self._thumbnail(row)
        if thumbnail is None:
            self._skip(row)
            return True
        try:
            if describing and row["to_describe"]:
                try:
                    vector = self.siglip.picture(thumbnail)
                except ModelError as error:
                    self._failing("pictures", row, error)
                    return False
                self.vectors.keep(side, [(row["id"], row["size"], row["modified"], vector)])
            if wording and row["to_word"]:
                began = time.perf_counter()
                try:
                    read = self._words(row, thumbnail, reader)
                except ModelError as error:
                    self._failing("words", row, error)
                    return False
                took = time.perf_counter() - began
                if read is None:
                    self._skip(row)
                    return True
                _keep_words(conn, row, reader, read, self._now())
                self._share(reader, took)
        except sqlite3.Error:
            raise
        except Exception:  # whatever it was, one picture never stops reading
            log.exception("Reading %s for search hit a problem", row["path"])
            self._skip(row)
        return True

    def _failing(self, reader: Failing, row: sqlite3.Row, error: ModelError) -> None:
        log.warning(
            "Mado's reader of %s couldn't read %s for search: %s", reader, row["path"], error
        )
        with self._lock:
            self._problems[reader] = str(error)

    def _words(self, row: sqlite3.Row, thumbnail: Image.Image, reader: Reader) -> Read | None:
        """The words in a picture: at Best only once the detector finds text in its thumbnail;
        None when the picture itself can't be read now."""
        if reader == "best" and not self.best.glance(thumbnail):
            return Read("", 0)
        side = SIDE if reader == "best" else _FAST_SIDE
        try:
            picture = decode(
                Path(row["path"]),
                kind_of(row["name"]) or "picture",
                longest=side,
                ffmpeg=self._ffmpeg(),
                reader=self._previews.reader,
            )
        except (PictureGoneError, NeedsFfmpegError, NeedsReaderError, InUseError) as error:
            log.info("Mado couldn't read the words in %s now: %s", row["path"], error)
            return None
        except (UnreadableError, OSError) as error:
            log.info("Mado couldn't read the words in %s: %s", row["path"], error)
            return None
        return self.best.read(picture) if reader == "best" else self.fast.read(picture)

    def _share(self, reader: Reader, took: float) -> None:
        """While the queue makes a picture, rests after a turn on the card, leaving it the
        queue's nearly all the time."""
        if reader == "best" and self.best.place() == "card" and self._busy():
            self._stopping.wait(min(took * _SHARE, 5.0))

    def _thumbnail(self, row: sqlite3.Row) -> Image.Image | None:
        """A picture's thumbnail, made now if the cache lost it; None when it can't be made."""
        source = Source.of(row)
        try:
            path = self._previews.kept_thumbnail(source) or self._previews.thumbnail(source)
            with Image.open(path) as opened:
                opened.load()
                return opened.copy()
        except (
            PictureGoneError,
            UnreadableError,
            NeedsFfmpegError,
            NeedsReaderError,
            OSError,
            ValueError,
        ) as error:
            log.info("Mado couldn't read %s for search now: %s", row["path"], error)
            return None

    def _skip(self, row: sqlite3.Row) -> None:
        with self._lock:
            self._skipped.add((row["id"], row["size"], row["modified"]))

    def _tidy(self, conn: sqlite3.Connection) -> None:
        """Lets go of the vectors of pictures no longer in the library, once reading is done."""
        kept = {row[0] for row in conn.execute("SELECT id FROM pictures WHERE gone_at IS NULL")}
        with closing(self.vectors.connect()) as side:
            self.vectors.forget(side, kept)

    def _attached(self, conn: sqlite3.Connection) -> _Attached:
        return _Attached(conn, self.vectors)


class _Attached:
    """search.db attached to a connection to the database as `seen`, for the length of a
    `with`."""

    def __init__(self, conn: sqlite3.Connection, vectors: Vectors) -> None:
        self._conn = conn
        self._vectors = vectors

    def __enter__(self) -> None:
        with closing(self._vectors.connect()):  # made as it should be, first
            pass
        self._conn.execute("ATTACH DATABASE ? AS seen", (str(self._vectors_path()),))

    def __exit__(self, *_exc: object) -> None:
        self._conn.execute("DETACH DATABASE seen")

    def _vectors_path(self) -> Path:
        return self._vectors._path  # pyright: ignore[reportPrivateUsage]


def _keep_words(
    conn: sqlite3.Connection, row: sqlite3.Row, reader: Reader, read: Read, now: datetime
) -> None:
    """The words read in a picture, as its file was then, in place of what was read before."""
    with conn:
        conn.execute("DELETE FROM words WHERE rowid = ?", (row["id"],))
        if read.text:
            conn.execute(
                "INSERT INTO words (rowid, text, terms) VALUES (?, ?, ?)",
                (row["id"], read.text, index_terms(read.text)),
            )
        conn.execute(
            """INSERT INTO words_read (picture_id, size, modified, reader, language, lines, at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (picture_id) DO UPDATE SET size = excluded.size,
                   modified = excluded.modified, reader = excluded.reader,
                   language = excluded.language, lines = excluded.lines, at = excluded.at""",
            (
                row["id"],
                row["size"],
                row["modified"],
                reader,
                read.language,
                read.lines,
                now.isoformat(timespec="seconds"),
            ),
        )


def _busy(error: sqlite3.Error) -> bool:
    """Whether SQLite said a database is busy or locked for now, which waiting mends."""
    code = getattr(error, "sqlite_errorcode", None)
    if isinstance(code, int):
        return (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    return "locked" in str(error)


def chosen(conn: sqlite3.Connection) -> Choice:
    """The owner's choice of words reader (Settings › General › Search): as this PC suits till
    they choose."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'words_reader'").fetchone()
    try:
        value: object = json.loads(row["value"]) if row else "auto"
    except ValueError:
        return "auto"
    if value == "fast":
        return "fast"
    if value == "best":
        return "best"
    return "auto"


def away_folders(conn: sqlite3.Connection) -> set[int]:
    """The library folders whose drive isn't connected (or that aren't there now)."""
    return {
        row["id"]
        for row in conn.execute("SELECT id, path FROM folders")
        if not Path(row["path"]).is_dir()
    }


def _in_a_quarantine(path: str) -> bool:
    folded = QUARANTINE.casefold()
    return any(part.casefold() == folded for part in PureWindowsPath(path).parts)
