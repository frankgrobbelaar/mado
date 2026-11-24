# Engine: guide for coding agents

The engine is everything Mado does except draw the window: the local API the UI calls, the
database, its backups, the tools Mado downloads and the export, and, as Mado grows, reading
pictures, running the AI models and saving what they make. Python 3.14, run with uv. Start with
[../AGENTS.md](../AGENTS.md) and [../CLAUDE.md](../CLAUDE.md).

## Where things go

| What | Where |
| --- | --- |
| Rules about pictures: what a file is, EXIF's values in Mado's words, a HEIF's layout, a camera RAW's turn, crop and preview-or-develop and its reader's errors, Display P3's colour profile, the sizes a picture is made for, its shape, what it is, the model it suits, the recipe of steps and its plan, the tiles, the format, the time, what this PC can do, looks as tables of colours, `.cube` files, the touches' shapes, the fixes (their order, a JPEG's quality from its tables, how dark a picture is, the tone curve, local contrast, the blur model's guard), restoring (which picture needs which, colour put onto a picture's own light, faded colours' levels, the scratch detector's canvases and its mask united, grown and painted over), painting styles (the working size and its canvas, mixing, the classic means, an ONNX graph's weights taken out as inputs), depth (the model's square, nearness and a flat picture, the lens blur in layers, fog, tilt-shift's band) and a 3D photo's path and frames, HDR photos (a gain map's numbers in Adobe's XMP, ISO 21496-1's and Apple's ways, as gains in stops and back; a JPEG's segments and MPF and an Ultra HDR JPEG put together; HEIF files written box by box; what each tool does to a gain map), a batch's steps, nights and room on a drive, fingerprints and sharpness, groups of duplicates and bursts and which to keep, the edits and their parts, mask maths, what paths open as, the monitors' arrangement, a wallpaper's parts and the day's picks, a search as SigLIP reads it and its cut, the words reader's pre- and post-processing | `src/mado/core/`, pure functions only |
| The library: its folders, the scan, the watcher, reading pictures (camera RAW through LibRaw's DLL; an HDR photo's gain map from its headers, and decoded when it's made) and the copies the window shows | `src/mado/library.py`, `scan.py`, `watch.py`, `pictures.py`, `libraw.py`, `hdr.py`, `previews.py` (see [docs/architecture.md](../docs/architecture.md#the-library) and [docs/stack/hdr.md](../docs/stack/hdr.md)) |
| Pictures from anywhere: one opened from outside the library, known by its path and forgotten after a month unopened; a picture pasted from the clipboard, kept in the data folder till it's saved | `src/mado/outside.py`, `pasting.py`, `api/opening.py` (see [docs/architecture.md](../docs/architecture.md#pictures-from-anywhere)) |
| Making a picture right for a screen: sessions on the card, the models' files, a tile at a time, extending edges, making and saving | `src/mado/directml.py`, `ai.py`, `upscale.py`, `extend.py`, `making.py`, `encode.py` (see [docs/stack/upscaling.md](../docs/stack/upscaling.md)) |
| Giving a picture a look: the look's table and the touches laid on it, the owner's looks in the database | `src/mado/looks.py`, `own_looks.py` (see [docs/stack/looks.md](../docs/stack/looks.md)) |
| The quick fixes: noise, blur, JPEG blocks and dark photos, measured on the whole picture and made on any part of it, the models a tile at a time | `src/mado/fixing.py`, `api/fixes.py` (see [docs/stack/fixes.md](../docs/stack/fixes.md)) |
| Restoring old photos: scratches and dust found (kept in the cache) and filled by LaMa a square at a time, DDColor's colours and faded colours' levels worked out once and laid on any part of the picture | `src/mado/restoring.py`, `api/restore.py` (see [docs/stack/restoring.md](../docs/stack/restoring.md)) |
| Painting styles: the painters' one shared session and MicroAST's two halves at the working size, the last few paintings kept for the previews, the owner's styles in the database | `src/mado/painting.py`, `own_styles.py`, `api/styles.py` (see [docs/stack/styles.md](../docs/stack/styles.md)) |
| Depth: a picture's depth read once and kept in the cache; portrait blur, fog and tilt-shift worked out on a copy and joined at full size; 3D photos made into the cache with ffmpeg's H.264 (never OpenH264) and saved | `src/mado/depth.py`, `motion.py`, `api/depth.py`, `api/motion.py` (see [docs/stack/depth.md](../docs/stack/depth.md)) |
| Editing by clicking: picking parts (SAM 2.1), erasing (MI-GAN, LaMa), cutting out (U²-Net small, BiRefNet lite) and blurring behind, the edits made in order and their masks kept | `src/mado/selecting.py`, `erasing.py`, `cutting.py`, `editing.py` (see [docs/stack/editing.md](../docs/stack/editing.md)) |
| The jobs, History and the quarantine | `src/mado/jobs.py`, `history.py`, `quarantine.py` |
| Favourites: the heart, following a picture moved or renamed | `src/mado/favourites.py` |
| The wallpaper studio: the monitors and Windows' wallpaper behind a seam, the parts made and set or saved, the owner's own kept and put back, the daily change | `src/mado/desktop.py`, `wallpaper.py` (see [docs/stack/wallpaper.md](../docs/stack/wallpaper.md)) |
| Many at once: the queue (in the jobs' worker), batches and what they take, See it first, recipes, watch folders | `src/mado/jobs.py`, `batches.py`, `samples.py`, `recipes.py`, `watching.py` (see [docs/stack/queue.md](../docs/stack/queue.md)) |
| This PC: what it has, its check (in a process of its own), its speeds | `src/mado/hardware.py`, `pc_check.py` (see [docs/stack/hardware.md](../docs/stack/hardware.md)) |
| Looking after the library: duplicates and bursts found in the background, the owner's choices, setting the rest aside | `src/mado/duplicates.py` (see [docs/stack/duplicates.md](../docs/stack/duplicates.md)); won't open and space in `api/library.py` |
| Search: the library read in the background (SigLIP for what a picture shows, a reader of words), the vectors in search.db and in memory, the words in FTS5, finding and More like this | `src/mado/siglip.py`, `ocr.py`, `search.py`, `api/search.py` (see [docs/stack/search.md](../docs/stack/search.md)) |
| The AI models Mado ships, with their licences | `src/mado/assets/` (its README says what each is) |
| Reaching the world: files, ffmpeg, the graphics card | modules beside `core/`, one per outside thing, each small and replaceable |
| The API the UI calls | `src/mado/api/<feature>.py`, one `APIRouter` per feature, included in `api/__init__.py` |
| Shared API pieces | `src/mado/api/common.py` (`ApiModel`, `Paths`, `Database`, `Toolbox`) |
| The schema | `src/mado/migrations.py`, append-only |
| What Mado downloads (ffmpeg; LibRaw the first time a camera RAW is read; AI models fetched on first use) | `src/mado/downloads.json`, the list the installer shows; `src/mado/tools.py` fetches and checks it |
| Background care (tonight's backup, the daily clear-out of the quarantine) | `src/mado/care.py` |
| Commands | `src/mado/cli.py` |
| Build tools that run on the engine's Python (the third-party notices) | `tools/`, tested in `tests/` |
| Tests | `tests/test_<module>.py`, and `tests/core/test_<module>.py` for the core; fixtures in `tests/conftest.py` (a quarantine of the test's own, the AI models on the processor, a stand-in PC check); made-up pictures from `tests/drawn.py` (`scene`: a landscape different for every seed, for duplicates and bursts), `tests/heif_files.py`, `tests/hdr_files.py` (HDR photos written by code: Ultra HDR JPEGs with XMP, ISO 21496-1 or both, AVIFs with a `tmap` item, HEICs built box by box around AV1 items with Apple's or ISO's gain map) and `tests/dng_files.py` (DNGs written tag by tag, a Bayer mosaic under a camera's tags, with or without the previews a camera keeps), search's readers from `tests/fake_search.py` (a picture is its colour) unless a test asks for the real ones (`tests/test_search_models.py`: PP-OCRv6 fetched once into pytest's cache), the real LibRaw from the `libraw_folder` fixture (fetched as Mado fetches it, once, into pytest's cache; `raw_client` an engine reading RAW with it, the `client` fixture's RAW reader never fetching), ffmpeg from `tests/fake_ffmpeg.py`, Windows' desktop from `tests/fake_desktop.py`, the fixes' models from `tests/fix_models.py` (stand-ins run through Mado's own sessions and tiles), restoring's detector and DDColor from `tests/restore_models.py` (stand-ins through Mado's own sessions: the detector sure where a pixel stands out from its neighbours, DDColor a sky and grass) and aged prints drawn by `tests/test_restoring.py`, the painting styles' from `tests/style_files.py` (made-up painters and a MicroAST written field by field, found where Mado finds its downloads through `MADO_<DOWNLOAD>_DIR`), the depth model from `tests/depth_models.py` and made-up scenes with known depth from `tests/depth_scenes.py`; the shipped Fast model runs on the processor on tiny pictures; a picture held open with Python's `open()` is open in another app, as Windows sees it |

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
  to deletion. A picture saved as it is (nothing made) is always a new picture. Every change is
  logged so it can be undone.
- An HDR photo's gain map follows every step (`core/gains.py`): a new tool decides what it does
  to it, tests it on the made-up HDR photos in `tests/hdr_files.py`, and says why there.
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
  process of its own. Models that are one graph with different weights (the painters) share one
  session, their weights passed as inputs: never leave them in the graph as overridable defaults,
  which DirectML's fusion bakes in.
- A test never writes to a drive's real quarantine: the `quarantine` fixture keeps it in the test's
  own folder.
- Windows' desktop only through `mado/desktop.py`'s `Desktop`. Only `mado serve` hands the studio
  `WindowsDesktop`; `create_app` otherwise has `NoDesktop`, and the studio's tests hand it
  `tests/fake_desktop.py`. No test sets the owner's wallpaper: a test may read the real desktop,
  never change it. A wallpaper the owner asked to set or save isn't picked up after a restart (set
  days later, it would surprise them): it says it was cut short, and a Save's half-written picture
  is cleared away as the queue's are; the daily change's is made again.
- The `pictures` table holds pictures opened from outside the library too (`folder_id` NULL):
  anything that lists, counts, exports or compares the library's pictures says
  `folder_id IS NOT NULL`. A picture pasted is Mado's own file, in the data folder's `pasted`:
  never written beside or in place of; Save takes a folder of the owner's.
- Mado downloads nothing that isn't in `downloads.json`, and uses a download only when its size and
  SHA-256 match the list.
- Search reads only the library's own pictures (never one from outside it, in a quarantine,
  that won't open or is marked as damaged) and never writes to one: what it reads is kept in the
  database (`words_read`, `words`) and in search.db beside it, which can always be read again and
  so never goes into a backup or the export. Its readers run under the card's one lock like any
  model; SigLIP stays on the processor.
- LibRaw only through `mado/libraw.py`: loaded from the tools folder, never shipped (the notices
  build stops on a bundled LibRaw or ffmpeg), each file opened read-only by a reader of its own,
  nothing written anywhere. A camera RAW is never written over: Save makes a new picture, and the
  engine refuses Replace for one. Its options struct is written only where LibRaw's own setters
  have confirmed its place (`_OPTIONS_AT`, measured per version: moving to a newer LibRaw
  measures it again, docs/stack/libraw.md says how).
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
