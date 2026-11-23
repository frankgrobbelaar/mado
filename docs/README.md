# Mado docs

Short pages, one subject each. Start with the architecture, then the page for what you're touching.
Coding agents start at [AGENTS.md](../AGENTS.md); each area (`engine/`, `app/`, `app/src-tauri/`,
`docs/`) has its own `AGENTS.md` with the direction for working there.

| Page | What it covers |
| --- | --- |
| [architecture.md](architecture.md) | The three parts (shell, UI, engine), how they talk, where data lives |
| [development.md](development.md) | Setting up this PC, running Mado, checks, updating dependencies |
| [conventions.md](conventions.md) | How we write code: Python, TypeScript, Rust, tests, commits |
| [design.md](design.md) | UI and UX rules, Mado's look and its tokens, patterns |
| [releasing.md](releasing.md) | Versions, the installer, updates, third-party notices, the signing key |
| [design/](design/) | Every screen from the design canvases, as pages you can open |
| [readme/](readme/) | The README's pictures: the designed screens, every picture in them drawn by code |

## The stack

Every tool Mado uses, its version on 2026-11-22, and the page that explains how Mado uses it.

| Tool | Version | Job | Page |
| --- | --- | --- | --- |
| Tauri | 2.12 | Desktop shell, window, installer, updater | [tauri.md](stack/tauri.md) |
| Rust | stable 1.99, edition 2024 | The shell's language | [tauri.md](stack/tauri.md) |
| windows-registry, windows-sys | 0.100, 0.61 | File Explorer's "Open in Mado" and Open with under HKCU; the files copied in File Explorer; a second start finding the first | [tauri.md](stack/tauri.md) |
| React | 19.3 | UI components | [react.md](stack/react.md) |
| TypeScript | 7.0 | Typed UI code (the native compiler) | [react.md](stack/react.md) |
| Vite | 8.3 | Dev server and bundler for the UI | [react.md](stack/react.md) |
| React Router | 8.5 | Navigation between sections | [react.md](stack/react.md) |
| TanStack Query | 5.108 | Fetching and caching engine data | [react.md](stack/react.md) |
| Biome | 2.6 | Lint and format for the UI | [react.md](stack/react.md) |
| Tailwind CSS | 4.3 | Styling, fed by the design tokens | [tailwind.md](stack/tailwind.md) |
| shadcn/ui, Radix | shadcn 4.21, radix-ui 1.8 | Accessible component starting points | [tailwind.md](stack/tailwind.md) |
| Lucide | 1.77 | Icons | [tailwind.md](stack/tailwind.md) |
| Fontsource | 5.3 | IBM Plex Sans and IBM Plex Mono, bundled for offline use | [tailwind.md](stack/tailwind.md) |
| Python | 3.14 | The engine's language | [python.md](stack/python.md) |
| uv | 0.13 | Python, packages, lockfile, running tools | [python.md](stack/python.md) |
| Ruff, Pyright | 0.17, 1.1.414 | Python lint, format and strict types | [python.md](stack/python.md) |
| FastAPI, Uvicorn, Pydantic | 0.165, 0.54, 2.14 | The engine's local API | [fastapi.md](stack/fastapi.md) |
| Typer | 0.29 | The engine's command line | [fastapi.md](stack/fastapi.md) |
| SQLite | bundled with Python | Mado's one database file | [sqlite.md](stack/sqlite.md) |
| Pillow | 13.0 | Reading pictures: their facts and EXIF, and the copies the window shows | [pillow.md](stack/pillow.md) |
| Looks | Pillow's Color3DLUT, Mado's own code | Looks as tables of colours (Mado's, `.cube` files, mixes kept), finishing touches drawn by code | [looks.md](stack/looks.md) |
| watchdog | 7.1 | Noticing new, changed and removed pictures in the library's folders | [watchdog.md](stack/watchdog.md) |
| ffmpeg | 9.0.2 (downloaded on first run) | Decoding a phone's HEIC; more formats for Mado's tools to come | [ffmpeg.md](stack/ffmpeg.md) |
| ONNX Runtime (DirectML) | 1.24.4 | Running the AI models on the graphics card, or the processor | [upscaling.md](stack/upscaling.md) |
| NumPy | 2.5 | The pictures' pixels as the models take them | [upscaling.md](stack/upscaling.md) |
| Real-ESRGAN models | general x4v3 and its twin, x4plus anime 6B (shipped); x4plus (downloaded) | Making pictures bigger, Fast and Best | [upscaling.md](stack/upscaling.md) |
| LaMa | big-lama, reshaped for DirectML (downloaded) | Extending a picture's edges; erasing at Best | [upscaling.md](stack/upscaling.md), [editing.md](stack/editing.md) |
| Editing models | SAM 2.1 tiny, MI-GAN v2 pipeline, BiRefNet lite (downloaded); U²-Net small (shipped) | Picking parts with a click, erasing, cutting out | [editing.md](stack/editing.md) |
| This PC | | What the graphics card can do, tested and timed | [hardware.md](stack/hardware.md) |
| The queue | Mado's own code | Many at once: batches made one at a time, nights, room on a drive, See it first, recipes and watch folders | [queue.md](stack/queue.md) |
| Duplicates and bursts | Mado's own code, on NumPy and Pillow | Fingerprints from the thumbnails, groups, which to keep, setting the rest aside | [duplicates.md](stack/duplicates.md) |
| Windows' desktop | IDesktopWallpaper, the display APIs and DisplayConfig, by ctypes | The wallpaper studio: the monitors, Windows' own wallpaper set, the owner's own put back, every day's change | [wallpaper.md](stack/wallpaper.md) |
| PyInstaller | 6.22 | Bundles the engine with its own Python | [pyinstaller.md](stack/pyinstaller.md) |
| Vitest, Testing Library, pytest | 5.1, 16.3, 9.2 | Tests | [testing.md](stack/testing.md) |
| GitHub Actions | | CI and releases | [github-actions.md](stack/github-actions.md) |
| NSIS | via Tauri | The Windows installer | [tauri.md](stack/tauri.md#installer) |

Tools still to come (the models for selecting, erasing, depth and the library) get a page, or a
section, when they're first used.
