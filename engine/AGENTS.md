# Engine: guide for coding agents

The engine is everything Mado does except draw the window: the local API the UI calls, the
database, its backups, the tools Mado downloads and the export, and, as Mado grows, reading
pictures, running the AI models and saving what they make. Python 3.14, run with uv. Start with
[../AGENTS.md](../AGENTS.md) and [../CLAUDE.md](../CLAUDE.md).

## Where things go

| What | Where |
| --- | --- |
| Rules about pictures: what a file is, EXIF's values in Mado's words, a HEIF's layout, the sizes a picture is made for, its shape, what it is, the model it suits, the recipe of steps and its plan, the tiles, the format, the time, what this PC can do, looks as tables of colours, `.cube` files, the touches' shapes, a batch's steps, nights and room on a drive, fingerprints and sharpness, groups of duplicates and bursts and which to keep, the edits and their parts, mask maths | `src/mado/core/`, pure functions only |
| The library: its folders, the scan, the watcher, reading pictures and the copies the window shows | `src/mado/library.py`, `scan.py`, `watch.py`, `pictures.py`, `previews.py` (see [docs/architecture.md](../docs/architecture.md#the-library)) |
| Making a picture right for a screen: sessions on the card, the models' files, a tile at a time, extending edges, making and saving | `src/mado/directml.py`, `ai.py`, `upscale.py`, `extend.py`, `making.py`, `encode.py` (see [docs/stack/upscaling.md](../docs/stack/upscaling.md)) |
| Giving a picture a look: the look's table and the touches laid on it, the owner's looks in the database | `src/mado/looks.py`, `own_looks.py` (see [docs/stack/looks.md](../docs/stack/looks.md)) |
| Editing by clicking: picking parts (SAM 2.1), erasing (MI-GAN, LaMa), cutting out (U²-Net small, BiRefNet lite) and blurring behind, the edits made in order and their masks kept | `src/mado/selecting.py`, `erasing.py`, `cutting.py`, `editing.py` (see [docs/stack/editing.md](../docs/stack/editing.md)) |
| The jobs, History and the quarantine | `src/mado/jobs.py`, `history.py`, `quarantine.py` |
| Many at once: the queue (in the jobs' worker), batches and what they take, See it first, recipes, watch folders | `src/mado/jobs.py`, `batches.py`, `samples.py`, `recipes.py`, `watching.py` (see [docs/stack/queue.md](../docs/stack/queue.md)) |
| This PC: what it has, its check (in a process of its own), its speeds | `src/mado/hardware.py`, `pc_check.py` (see [docs/stack/hardware.md](../docs/stack/hardware.md)) |
| Looking after the library: duplicates and bursts found in the background, the owner's choices, setting the rest aside | `src/mado/duplicates.py` (see [docs/stack/duplicates.md](../docs/stack/duplicates.md)); won't open and space in `api/library.py` |
| The AI models Mado ships, with their licences | `src/mado/assets/` (its README says what each is) |
| Reaching the world: files, ffmpeg, the graphics card | modules beside `core/`, one per outside thing, each small and replaceable |
| The API the UI calls | `src/mado/api/<feature>.py`, one `APIRouter` per feature, included in `api/__init__.py` |
| Shared API pieces | `src/mado/api/common.py` (`ApiModel`, `Paths`, `Database`, `Toolbox`) |
| The schema | `src/mado/migrations.py`, append-only |
| What Mado downloads (ffmpeg, AI models fetched on first use) | `src/mado/downloads.json`, the list the installer shows; `src/mado/tools.py` fetches and checks it |
| Background care (tonight's backup, the daily clear-out of the quarantine) | `src/mado/care.py` |
| Commands | `src/mado/cli.py` |
| Build tools that run on the engine's Python (the third-party notices) | `tools/`, tested in `tests/` |
| Tests | `tests/test_<module>.py`, and `tests/core/test_<module>.py` for the core; fixtures in `tests/conftest.py` (a quarantine of the test's own, the AI models on the processor, a stand-in PC check); made-up pictures from `tests/drawn.py` (`scene`: a landscape different for every seed, for duplicates and bursts) and `tests/heif_files.py`, ffmpeg from `tests/fake_ffmpeg.py`; the shipped Fast model runs on the processor on tiny pictures; a picture held open with Python's `open()` is open in another app, as Windows sees it |

## Building a feature

1. **Core first, test first.** Write the pure function with tests built from real examples in
   `docs/design/` (made-up pictures only: sizes like 4032 x 3024, names like `IMG_2041.HEIC`).
2. **Wrap it in I/O.** Read what the core needs, call it, store the result. Keep that code thin.
3. **Expose it.** An `ApiModel` response and a route; test through the `client` fixture.
4. **Update the contract.** `uv run mado openapi openapi.json`, then mirror the types in
   `app/src/lib/engine.tsx`, in the same commit.
5. **Schema change?** Append a migration (never edit a shipped one), test it, and add the new data
   to `export.py`.

## Rules

- `core/` imports nothing that does I/O: no `sqlite3`, `subprocess`, `httpx2`, file reads or
  writes, and nothing from `api/`. It takes values and returns values.
- A picture changes only as the owner chose: a result is saved as a new picture beside its original
  unless the owner chose to replace it, and a replaced original goes to quarantine, never straight
  to deletion. Every change is logged so it can be undone.
- Never print to stdout while serving: the shell reads the one ready line and the events after it
  (`mado/events.py`). Log with `logging`.
- Pyright strict passes without ignores. Data inside the engine is frozen dataclasses; Pydantic
  models live only at the API edge.
- Errors carry a sentence a person can act on, and say what Mado already did.
- Long jobs (a batch, a big upscale) report their stage, percentage and time left, can pause, and
  pick up where they stopped after a restart or a crash.
- Mado runs on other people's PCs too: work on the graphics card uses what this PC has, never one
  card by name, and a heavier AI model comes as a choice beside a lighter one, never in its place.
- DirectML's rules (`mado/directml.py`): every card session made and run under its one lock (a
  processor session is made and run without it, and a session made already is handed out without
  it, so a click picked on the processor never waits for the queue), kept for the engine's life
  (letting one go can crash another), its sizes pinned, never a quiet fall back to the processor.
  A session keeps what it took of the card's memory, so an editing model goes on the card only
  when `hardware.room()` says it fits. Work that makes and drops sessions (the PC check) runs in a
  process of its own.
- A test never writes to a drive's real quarantine: the `quarantine` fixture keeps it in the test's
  own folder.
- Mado downloads nothing that isn't in `downloads.json`, and uses a download only when its size and
  SHA-256 match the list.
- Every new package must survive PyInstaller: after adding one, build the engine and run the
  handshake test against the bundle (see [docs/stack/pyinstaller.md](../docs/stack/pyinstaller.md)).
- Add a dependency only for a clear need, at its latest stable version (`uv add`), with a licence
  on the allowed list in `tools/third_party_notices.py`, and give it a page or a section in
  `docs/stack/`. An AI model, too, starts at its newest release that runs well enough on the
  owner's PC, and moves up as newer ones measure as well (see "Updating dependencies" in
  [docs/development.md](../docs/development.md)).

## Commands

```powershell
uv sync                                   # set up or update the environment
uv run pytest                             # tests (add -k <words> to pick some)
uv run ruff format; uv run ruff check --fix; uv run pyright
uv run mado serve --port 8765             # run alone (set MADO_TOKEN and MADO_DATA_DIR first)
uv run mado openapi openapi.json          # rewrite the API contract after changing the API
uv run pyinstaller mado-engine.spec --noconfirm   # build the bundled engine
$env:MADO_ENGINE_EXE = "dist/mado-engine/mado-engine.exe"; uv run pytest tests/test_cli.py -k announces
```

## Done means

Ruff, Pyright and pytest are green; new behaviour has tests; `openapi.json` and the UI's types
match; the export includes any new data; docs are updated. Guides:
[python.md](../docs/stack/python.md), [fastapi.md](../docs/stack/fastapi.md),
[sqlite.md](../docs/stack/sqlite.md), [testing.md](../docs/stack/testing.md).
