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
    # 5. Many at once: recipes (steps kept by name), watch folders (a folder, its recipe and where
    # results go, with what each has taken), and batches, each a picture's job in the queue,
    # which takes them in its own order.
    """
    CREATE TABLE recipes (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,  -- never given again, as batches name it
        name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        steps     TEXT NOT NULL,     -- JSON: the steps in order, each a kind and its choices
        saving    TEXT NOT NULL,     -- JSON: how it saves
        used      INTEGER NOT NULL DEFAULT 0,  -- batches made from it
        used_at   TEXT,              -- the latest
        added_at  TEXT NOT NULL
    ) STRICT;

    CREATE TABLE watch_folders (
        id         INTEGER PRIMARY KEY,
        path       TEXT NOT NULL UNIQUE COLLATE NOCASE,
        recipe_id  INTEGER NOT NULL REFERENCES recipes (id) ON DELETE CASCADE,
        results    TEXT NOT NULL,    -- where its new pictures go
        watching   INTEGER NOT NULL DEFAULT 1 CHECK (watching IN (0, 1)),
        added_at   TEXT NOT NULL,
        since      TEXT NOT NULL,    -- it takes what arrives after this (it was turned on)
        problem    TEXT              -- why it couldn't put its pictures in the queue, lately
    ) STRICT;

    CREATE TABLE watched (           -- what a watch folder took, or found there as it began
        watch_id  INTEGER NOT NULL REFERENCES watch_folders (id) ON DELETE CASCADE,
        path      TEXT NOT NULL COLLATE NOCASE,
        size      INTEGER NOT NULL,
        modified  INTEGER NOT NULL,  -- nanoseconds since 1970
        taken     INTEGER NOT NULL CHECK (taken IN (0, 1)),  -- 0: there before, left alone
        at        TEXT NOT NULL,
        PRIMARY KEY (watch_id, path)
    ) STRICT;

    CREATE TABLE batches (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,     -- what it's called: its recipe's name, or where it's from
        source      TEXT NOT NULL,     -- where its pictures came from: "Holiday"
        shared      TEXT,              -- the folder its pictures share, when they do
        recipe_id   INTEGER REFERENCES recipes (id) ON DELETE SET NULL,
        watch_id    INTEGER REFERENCES watch_folders (id) ON DELETE SET NULL,
        steps       TEXT NOT NULL,     -- JSON: its steps and how it saves
        seen_first  INTEGER NOT NULL DEFAULT 0 CHECK (seen_first IN (0, 1)),
        starts      TEXT NOT NULL CHECK (starts IN ('now', 'tonight', 'after')),
        added_at    TEXT NOT NULL,
        started_at  TEXT,              -- its first picture began
        finished_at TEXT,              -- nothing of it waits any more
        seen_at     TEXT,              -- Home's card for it was seen
        cleared_at  TEXT               -- what didn't work of it was cleared from the Queue
    ) STRICT;

    ALTER TABLE jobs ADD COLUMN batch_id INTEGER REFERENCES batches (id) ON DELETE CASCADE;
    ALTER TABLE jobs ADD COLUMN position INTEGER NOT NULL DEFAULT 0;  -- its place in the queue
    ALTER TABLE jobs ADD COLUMN bytes INTEGER;  -- the picture it's made from, as it was asked
    ALTER TABLE jobs ADD COLUMN made_bytes INTEGER;  -- the picture it saved
    UPDATE jobs SET position = id;
    CREATE INDEX jobs_by_batch ON jobs (batch_id, state, position);
    """,
    # 6. Looking after the library: what Mado sees of each picture to tell one from another, the
    # owner's choices in the review of duplicates and bursts (which to keep, pictures that aren't
    # the same), each setting aside, pictures marked as damaged, and jobs waiting while a
    # picture is open in another app. History learns 'aside', a picture set aside from its
    # group with the one kept beside it; SQLite can't change a CHECK, so its table is made again.
    """
    CREATE TABLE prints (
        picture_id INTEGER PRIMARY KEY REFERENCES pictures (id) ON DELETE CASCADE,
        size       INTEGER NOT NULL,  -- its file as it was looked at
        modified   INTEGER NOT NULL,
        hash       INTEGER,           -- its fingerprint: 64 bits, signed (mado/core/likeness.py)
        fine       BLOB,              -- its finer fingerprint, 256 bits: a copy from a crop
        sharpness  REAL,              -- the Laplacian's variance, once it's in a burst
        digest     TEXT,              -- its bytes' blake2b, once another file shares its size
        at         TEXT NOT NULL
    ) STRICT;

    CREATE TABLE choices (            -- whether the owner keeps a picture of its group
        picture_id INTEGER PRIMARY KEY REFERENCES pictures (id) ON DELETE CASCADE,
        keep       INTEGER NOT NULL CHECK (keep IN (0, 1)),
        size       INTEGER NOT NULL,  -- its file as it was then: once it changes, Mado asks again
        modified   INTEGER NOT NULL,
        at         TEXT NOT NULL
    ) STRICT;

    CREATE TABLE not_same (           -- two pictures the owner said aren't the same
        first      INTEGER NOT NULL REFERENCES pictures (id) ON DELETE CASCADE,
        second     INTEGER NOT NULL REFERENCES pictures (id) ON DELETE CASCADE,
        versions   TEXT NOT NULL,     -- both files as they were then: once one changes, it's asked
        at         TEXT NOT NULL,
        PRIMARY KEY (first, second),
        CHECK (first < second)
    ) STRICT;

    CREATE TABLE reviews (            -- one setting aside of duplicates and bursts
        id         INTEGER PRIMARY KEY,
        at         TEXT NOT NULL,
        duplicates INTEGER NOT NULL,  -- the groups of duplicates whose rest it set aside
        bursts     INTEGER NOT NULL   -- and the bursts
    ) STRICT;

    -- The owner marked it as damaged: it isn't asked about again till its file changes.
    ALTER TABLE pictures ADD COLUMN damaged INTEGER NOT NULL DEFAULT 0 CHECK (damaged IN (0, 1));
    ALTER TABLE jobs ADD COLUMN held_since TEXT;  -- its picture has been open in another app since
    ALTER TABLE jobs ADD COLUMN held_until TEXT;  -- it tries again then
    ALTER TABLE jobs ADD COLUMN held_why TEXT CHECK (held_why IN ('read', 'replace'));

    CREATE TABLE history_6 (
        id          INTEGER PRIMARY KEY,
        at          TEXT NOT NULL,
        kind        TEXT NOT NULL CHECK (kind IN ('made', 'replaced', 'emptied', 'aside')),
        job_id      INTEGER REFERENCES jobs (id) ON DELETE SET NULL,
        name        TEXT NOT NULL,
        made_for    TEXT,
        original    TEXT,              -- 'aside': where it was, which Put back moves it back to
        result      TEXT,
        aside       TEXT,
        aside_at    TEXT,
        cleared_at  TEXT,
        cleared_by  TEXT CHECK (cleared_by IN ('days', 'owner')),
        undone_at   TEXT,              -- 'aside': put back
        bytes       INTEGER,           -- 'emptied': how much went; 'aside': its size
        look        TEXT,
        kept        TEXT,              -- 'aside': the picture of its group that was kept
        review_id   INTEGER REFERENCES reviews (id) ON DELETE SET NULL
    ) STRICT;
    INSERT INTO history_6 (id, at, kind, job_id, name, made_for, original, result, aside,
                           aside_at, cleared_at, cleared_by, undone_at, bytes, look)
        SELECT id, at, kind, job_id, name, made_for, original, result, aside, aside_at,
               cleared_at, cleared_by, undone_at, bytes, look
        FROM history;
    DROP TABLE history;
    ALTER TABLE history_6 RENAME TO history;
    CREATE INDEX history_by_time ON history (at, id);
    CREATE INDEX history_by_review ON history (review_id) WHERE review_id IS NOT NULL;
    """,
    # 7. Editing by clicking: History says what was edited first ("erased a part, cut out the
    # subject"), kept apart from the size and the look; a saved edit is still 'made' or
    # 'replaced', so it stays in its original's family. Its masks are kept in the cache.
    """
    ALTER TABLE history ADD COLUMN edit TEXT;  -- what was edited: "erased a part"
    """,
    # 8. Pictures from anywhere: a picture opened from outside the library (dropped, picked,
    # pasted, opened from File Explorer or the command line) is known by its path, with no
    # library folder, and when it was last opened, so it's forgotten once it hasn't been for a
    # while. A pasted one waits in Mado's data folder till it's saved. SQLite can't let a column
    # be NULL once it's NOT NULL, so the table is made again (the migrations run with foreign keys
    # off, so the tables that refer to it keep their rows, and they're checked before it commits).
    """
    CREATE TABLE pictures_8 (
        id          INTEGER PRIMARY KEY,
        folder_id   INTEGER REFERENCES folders (id) ON DELETE CASCADE,  -- NULL: outside the library
        path        TEXT NOT NULL UNIQUE COLLATE NOCASE,
        dir         TEXT NOT NULL,     -- the folders between its library folder and it; '' outside
        name        TEXT NOT NULL,
        size        INTEGER NOT NULL,
        modified    INTEGER NOT NULL,
        found_at    TEXT NOT NULL,
        seen_at     TEXT NOT NULL,
        gone_at     TEXT,
        read_at     TEXT,
        problem     TEXT,
        raw         INTEGER NOT NULL DEFAULT 0 CHECK (raw IN (0, 1)),
        format      TEXT,
        width       INTEGER,
        height      INTEGER,
        taken_at    TEXT NOT NULL,
        taken_from  TEXT NOT NULL CHECK (taken_from IN ('camera', 'file')),
        camera      TEXT,
        orientation INTEGER,
        located     INTEGER NOT NULL DEFAULT 0 CHECK (located IN (0, 1)),
        damaged     INTEGER NOT NULL DEFAULT 0 CHECK (damaged IN (0, 1)),
        opened_at   TEXT,              -- outside the library: when it was last opened
        pasted      INTEGER NOT NULL DEFAULT 0 CHECK (pasted IN (0, 1))  -- in Mado's data folder
    ) STRICT;
    INSERT INTO pictures_8 (id, folder_id, path, dir, name, size, modified, found_at, seen_at,
                            gone_at, read_at, problem, raw, format, width, height, taken_at,
                            taken_from, camera, orientation, located, damaged)
        SELECT id, folder_id, path, dir, name, size, modified, found_at, seen_at, gone_at,
               read_at, problem, raw, format, width, height, taken_at, taken_from, camera,
               orientation, located, damaged
        FROM pictures;
    DROP TABLE pictures;
    ALTER TABLE pictures_8 RENAME TO pictures;
    CREATE INDEX pictures_by_taken ON pictures (taken_at, id);
    CREATE INDEX pictures_by_folder ON pictures (folder_id, taken_at, id);
    CREATE INDEX pictures_outside ON pictures (opened_at) WHERE folder_id IS NULL;
    """,
)
