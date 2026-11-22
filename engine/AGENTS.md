# Engine: guide for coding agents

The engine is everything Mado does except draw the window: the local API the UI calls, the
database, its backups, the tools Mado downloads and the export, and, as Mado grows, reading
pictures, running the AI models and saving what they make. Python 3.14, run with uv. Start with
[../AGENTS.md](../AGENTS.md) and [../CLAUDE.md](../CLAUDE.md).

## Where things go

| What | Where |
| --- | --- |
| Rules about pictures: the size a purpose needs, the model a picture suits, plans, checks, estimates | `src/mado/core/`, pure functions only (it starts with the first such rule) |
| Reaching the world: files, ffmpeg, the graphics card | modules beside `core/`, one per outside thing, each small and replaceable |
| The API the UI calls | `src/mado/api/<feature>.py`, one `APIRouter` per feature, included in `api/__init__.py` |
| Shared API pieces | `src/mado/api/common.py` (`ApiModel`, `Paths`, `Database`, `Toolbox`) |
| The schema | `src/mado/migrations.py`, append-only |
| What Mado downloads (ffmpeg, AI models fetched on first use) | `src/mado/downloads.json`, the list the installer shows; `src/mado/tools.py` fetches and checks it |
| Background care (tonight's backup) | `src/mado/care.py` |
| Commands | `src/mado/cli.py` |
| Build tools that run on the engine's Python (the third-party notices) | `tools/`, tested in `tests/` |
| Tests | `tests/test_<module>.py`, and `tests/core/test_<module>.py` for the core; fixtures in `tests/conftest.py` |

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
