"""The database schema, as an append-only list of migrations.

Migration N upgrades the database from version N-1 to N; the version lives in
SQLite's `PRAGMA user_version`. Never edit a migration once it has shipped in a
release: add a new one at the end instead.
"""

from typing import Final

MIGRATIONS: Final[tuple[str, ...]] = (
    # 1. Settings: Mado's preferences, and what the engine notes for itself (how the last
    # restore went), one JSON value per key.
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL  -- JSON
    ) STRICT;
    """,
    # 2. The library: the folders the owner added, every picture found in them with what Mado
    # read of it, and the scans that keep it current.
    """
    CREATE TABLE folders (
        id        INTEGER PRIMARY KEY,
        path      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        added_at  TEXT NOT NULL,
        walked_at TEXT  -- when a scan last looked all through it; NULL until one has
    ) STRICT;

    CREATE TABLE pictures (
        id          INTEGER PRIMARY KEY,
        folder_id   INTEGER NOT NULL REFERENCES folders (id) ON DELETE CASCADE,
        path        TEXT NOT NULL UNIQUE COLLATE NOCASE,
        dir         TEXT NOT NULL,     -- the folders between its library folder and it: "2026/Trip"
        name        TEXT NOT NULL,     -- the file's name
        size        INTEGER NOT NULL,  -- bytes
        modified    INTEGER NOT NULL,  -- nanoseconds since 1970, as Windows reports it
        found_at    TEXT NOT NULL,
        seen_at     TEXT NOT NULL,     -- the last scan that found it
        gone_at     TEXT,              -- a later scan didn't find it
        read_at     TEXT,              -- when Mado read it; NULL while it's still to read
        problem     TEXT,              -- why it won't open, in words
        raw         INTEGER NOT NULL DEFAULT 0 CHECK (raw IN (0, 1)),  -- camera RAW: not read yet
        format      TEXT,              -- "JPEG", "HEIC"…; a RAW file's own ("CR3")
        width       INTEGER,           -- as it's shown, turned the way its orientation says
        height      INTEGER,
        taken_at    TEXT NOT NULL,     -- local time, by the camera's clock, else the file's time
        taken_from  TEXT NOT NULL CHECK (taken_from IN ('camera', 'file')),
        camera      TEXT,
        orientation INTEGER,           -- EXIF's 1 to 8
        located     INTEGER NOT NULL DEFAULT 0 CHECK (located IN (0, 1))  -- it carries a place
    ) STRICT;
    CREATE INDEX pictures_by_taken ON pictures (taken_at, id);
    CREATE INDEX pictures_by_folder ON pictures (folder_id, taken_at, id);

    CREATE TABLE scans (
        id          INTEGER PRIMARY KEY,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        state       TEXT NOT NULL CHECK (state IN ('running', 'done', 'failed')),
        stage       TEXT NOT NULL CHECK (stage IN ('finding', 'reading', 'done')),
        problem     TEXT,
        added       INTEGER,  -- pictures it found that weren't there before
        gone        INTEGER   -- pictures it found gone
    ) STRICT;
    """,
    # 3. Making pictures: the jobs that make one (the queue of many builds on it), and History,
    # what Mado did that can be undone or put back, with what waits in quarantine.
    """
    CREATE TABLE jobs (
        id          INTEGER PRIMARY KEY,
        kind        TEXT NOT NULL CHECK (kind IN ('make')),
        picture_id  INTEGER REFERENCES pictures (id) ON DELETE SET NULL,
        source      TEXT NOT NULL,     -- the picture's file, when it was asked for
        recipe      TEXT NOT NULL,     -- JSON: what to make and how to save it
        state       TEXT NOT NULL
                    CHECK (state IN ('queued', 'running', 'done', 'failed', 'cancelled')),
        stage       TEXT,              -- reading, shaping, making, saving
        progress    REAL NOT NULL DEFAULT 0,  -- 0 to 1
        attempts    INTEGER NOT NULL DEFAULT 0,  -- started, counting a start Mado cut short
        queued_at   TEXT NOT NULL,
        started_at  TEXT,
        finished_at TEXT,
        result      TEXT,              -- the picture saved, or the file it's written to till then
        problem     TEXT               -- why it didn't work, in words
    ) STRICT;
    CREATE INDEX jobs_by_state ON jobs (state, id);

    CREATE TABLE history (
        id          INTEGER PRIMARY KEY,
        at          TEXT NOT NULL,     -- local time, with its offset
        kind        TEXT NOT NULL CHECK (kind IN ('made', 'replaced', 'emptied')),
        job_id      INTEGER REFERENCES jobs (id) ON DELETE SET NULL,
        name        TEXT NOT NULL,     -- the original's file name; for 'emptied', the drive
        made_for    TEXT,              -- what the picture was made for: "TV 8K"
        original    TEXT,              -- where the original is ('made') or was ('replaced')
        result      TEXT,              -- the picture Mado made, where it was put
        aside       TEXT,              -- what waits in quarantine for it now, if anything
        aside_at    TEXT,              -- since when: the clear-out's days count from it
        cleared_at  TEXT,              -- what was aside went for good then
        cleared_by  TEXT CHECK (cleared_by IN ('days', 'owner')),  -- the clear-out, or emptied
        undone_at   TEXT,              -- taken away ('made') or put back ('replaced')
        bytes       INTEGER            -- 'emptied': how much went
    ) STRICT;
    CREATE INDEX history_by_time ON history (at, id);
    """,
    # 4. Looks: the owner's own, a .cube file imported or a mix kept from the Looks tab, each a
    # table of colours packed small (mado/core/grids.py); and the look a picture was made with,
    # for History.
    """
    CREATE TABLE looks (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,  -- never given again, as jobs name it
        name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        kind      TEXT NOT NULL CHECK (kind IN ('cube', 'mix')),
        points    INTEGER NOT NULL CHECK (points BETWEEN 2 AND 65),  -- the table's points a side
        grid      BLOB NOT NULL,     -- the table: 16-bit steps along red, zlib-packed
        touches   TEXT,              -- JSON: a kept mix's finishing touches
        source    TEXT NOT NULL,     -- the .cube file's name, or the look mixed: "Warm film at 60%"
        added_at  TEXT NOT NULL
    ) STRICT;

    ALTER TABLE history ADD COLUMN look TEXT;  -- what it was made with: "Warm film at 60%"
    """,
)
