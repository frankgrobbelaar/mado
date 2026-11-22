# SQLite (Mado's database)

Everything Mado knows lives in one [SQLite](https://sqlite.org) file, `mado.db`, in the data folder.
There is no database server: Python's built-in `sqlite3` module opens the file directly. One file is
easy to back up, export, move to another drive, and open with any SQLite tool.

## Files

| File | What it holds |
| --- | --- |
| `mado/db.py` | `connect()`, `migrate()`, `schema_version()` |
| `mado/migrations.py` | The schema, as an append-only list of SQL scripts |
| `mado/export.py` | The export zip, which includes a consistent copy of the database |

## Connecting

`db.connect(path)` opens the database the way Mado always uses it:

- `journal_mode = WAL`: readers keep working while a write happens, and a crash can't corrupt the
  file.
- `foreign_keys = ON`: relationships are enforced.
- `busy_timeout = 5000`: a writer waits up to five seconds for another instead of failing.
- Rows come back as `sqlite3.Row` (by name: `row["key"]`).

The API opens one connection per request (the `Database` dependency) and closes it afterwards.
Connections may move between threads but are never shared by two at once.

Write in transactions: `with conn: conn.execute(...)` commits on success and rolls back on error.
Always pass values as parameters (`?`), never with f-strings.

## Migrations

The schema version is SQLite's `PRAGMA user_version`. `migrations.py` holds `MIGRATIONS`, a tuple of
SQL scripts: script 1 takes a new database to version 1, script 2 to version 2, and so on.
`migrate()` runs the missing ones in order, each inside its own transaction, so a failure leaves the
database exactly as it was. A database newer than the running Mado is refused with a clear message
rather than touched.

To change the schema, append a script; never edit one that has shipped in a release. Use `STRICT`
tables, give every table a primary key, and add the new data to the export.

## The tables

| Table | Since | Holds |
| --- | --- | --- |
| `settings` | 1 | The owner's choices (so far whether Setup is done), and what the engine notes for itself (how the last restore went), one JSON value per key |
| `folders` | 2 | The library's folders: each one's path (unique, in any case), when it was added, and when a scan last looked all through it |
| `pictures` | 2 | Every picture found in them: its path, the folders between its library folder and it (`dir`, as "2026/Trip"), its name, size and file time; when it was found, last seen and found gone; and what reading it found: format, size as shown, when it was taken (local time, and whether by the camera's clock or the file's), camera, orientation, whether it carries a location, or why it won't open. Camera RAW is kept as `raw`, read as it's found |
| `scans` | 2 | Each scan: when it started and finished, how it went (`running`, `done`, `failed`), its stage (`finding`, `reading`, `done`), why it stopped, and the pictures it found new and gone |

Each of Mado's tools adds its tables as it's built.

### How the library uses them

- A picture is in the grid once it's read (`read_at`), camera RAW and pictures that won't open
  included; one still to read waits. Pictures found gone (`gone_at`) stay in the records, so one
  on a drive that comes back is the same picture again.
- The grid pages by `(taken_at, id)` (`pictures_by_taken`, and `pictures_by_folder` for a folder),
  so its pages stay put however many pictures there are.
- A folder's pictures and those of the folders inside it are those whose `dir` is its own, or
  starts with it and a "/".
- A file whose size or time changes is read again, its facts and its copies made anew.

## Backups and export

- Consistent copies use SQLite's backup API (`source.backup(copy)`), never a file copy of a database
  in use. The export does this, and so do the nightly backups (`backups/mado 2026-10-11 0300.db`,
  the last 7 kept), each checked with `PRAGMA integrity_check` before it's kept. Backups made by
  hand, before a restore and from an export are named so (`mado 2026-10-11 1015 by hand.db`) and
  kept 7 of each kind; two made in one minute are `(2)` apart, and none is renamed over another.
- Restoring a backup opens it read-only (`file:…?mode=ro`, so one that went is never made anew,
  empty), checks it, backs up the live records (kept even when they don't check out: they're what
  there was, and the backup being restored is never pruned), then copies it into `mado.db` the
  same way, as the engine starts and before anything else opens the database, and migrates it if
  an older Mado made it.
- As the engine starts, `mado/rescue.py` checks the records (`PRAGMA quick_check`): damaged ones
  (SQLite's `SQLITE_CORRUPT` or `SQLITE_NOTADB`, a disk that can't read them,
  `SQLITE_IOERR_READ` or `_SHORT_READ`, or a check that doesn't come back `ok`) can't be backed up
  with the backup API, so restoring over them renames them aside instead, `-wal` first, so a new
  `mado.db` never meets an old write-ahead log. For a read error the app offers Try again first
  (the drive may have been away a moment). Another program holding the file isn't damage
  (`SQLITE_BUSY`): the engine fails to start, saying why.
- The exported `mado.db` is switched to `journal_mode = DELETE`, so it is one self-contained file.

## Looking inside

```powershell
cd engine; uv run python -c "import sqlite3; print(sqlite3.connect('.dev-data/mado.db').execute('select * from settings').fetchall())"
```

Or open `mado.db` in any SQLite browser while Mado isn't writing.
