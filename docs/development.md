# Development

How to set up a Windows PC for Mado, run it, check it and keep it current.

## Set up once

| Tool | Why | Get it |
| --- | --- | --- |
| Visual Studio Build Tools 2022, "Desktop development with C++" | Rust's linker and the Windows SDK | `winget install Microsoft.VisualStudio.2022.BuildTools` |
| Rust (stable) | The shell | [rustup.rs](https://rustup.rs), then `rustup component add clippy rustfmt` |
| Node.js LTS | The UI's tooling | `winget install OpenJS.NodeJS.LTS` |
| pnpm 12 | UI packages | `npm install -g pnpm@latest` |
| uv | Python and the engine's packages | `winget install astral-sh.uv` (uv installs Python 3.14 itself) |
| GitHub CLI, signed in | Pushing, releases and watching CI | `winget install GitHub.cli`, then `gh auth login` |

Then, from the repo:

```powershell
cd engine; uv sync          # Python 3.14, the engine and its dev tools
cd ../app; pnpm install     # the UI, Tauri's CLI and Biome
```

WebView2, which draws the window, is part of Windows 11.

## Run Mado

```powershell
cd app; pnpm tauri dev
```

This starts Vite (the UI with hot reload), builds and opens the shell, and the shell starts the
engine from source with `uv run`. Engine data goes to `engine/.dev-data`, never to the real
`%LOCALAPPDATA%\Mado`. Rust and Python changes need a restart; UI changes appear as you save.

To work on the engine alone:

```powershell
cd engine
$env:MADO_TOKEN = "dev"; $env:MADO_DATA_DIR = ".dev-data"
uv run mado serve --port 8765        # then call http://127.0.0.1:8765/health with "Authorization: Bearer dev"
uv run mado --help                   # every command
```

## Check your work

CI runs exactly these; run them before every push.

```powershell
cd engine; uv run ruff format --check; uv run ruff check; uv run pyright; uv run pytest
cd app; pnpm check; pnpm build
cd app/src-tauri; cargo fmt --check; cargo clippy --all-targets -- -D warnings; cargo test
cd app; pnpm build:engine; pnpm build:notices
```

`pnpm check` runs Biome, the TypeScript compiler and Vitest. The last line builds the engine as
the installer bundles it and checks every bundled part's licence (it needs `pnpm build` first);
CI then also starts the bundled engine once (`tests/test_cli.py` with `MADO_ENGINE_EXE` set). To fix formatting:
`uv run ruff format` and `uv run ruff check --fix` in `engine/`, `pnpm fix` in `app/`, `cargo fmt` in
`app/src-tauri/`.

## Common changes

**A new API endpoint.** Add a router module in `engine/src/mado/api/` (see `health.py`) and include
it in `api/__init__.py`. Test it in `engine/tests/`. Run `uv run mado openapi openapi.json`, then add
the matching type and hook to `app/src/lib/engine.tsx`. Commit both sides together.

**A schema change.** Append a migration to `engine/src/mado/migrations.py`; never edit one that has
shipped. Add a test, and include the new data in `export.py`.

**A new screen.** Build it in `app/src/features/<area>/` to its board in [design/](design/), using
the tokens and existing components. Add the route in `app/src/app.tsx`. Give it its empty, loading
and error states.

**A new tool or library.** Use its latest stable version and add a page (or a section) in
[stack/](stack/) saying how Mado uses it.

## Updating dependencies

Mado stays on the latest versions of everything it uses, packages and AI models alike, wherever
possible (the owner, 2026-10-15). There is no Dependabot (it would open branches), so update on
`main`, ideally every couple of weeks, and look for a newer release whenever you add or touch
something:

```powershell
uv self update; cd engine; uv lock --upgrade; uv sync    # Python packages
cd ../app; pnpm update --latest                          # npm packages
cd src-tauri; rustup update; cargo update                # Rust and crates
```

Raise the minimum versions in `pyproject.toml`, `package.json` and `Cargo.toml` to match, run every
check, skim the changelogs of anything that jumped a major version, and update the versions table in
[docs/README.md](README.md). Pinned GitHub Actions are updated the same way: look up each action's
latest release and change the SHA and the version comment. pnpm refuses packages younger than a day
(a supply-chain safeguard); if the newest release is that fresh, take the one before it.

### AI models and downloads

The programs Mado downloads, and the AI models its tools will use, are pinned (a release or
commit, a size and a SHA-256), so a file never changes under Mado, and so they never update by
themselves. At each update, look for the newest release of each:

| What | Pinned in | Where releases come from |
| --- | --- | --- |
| ffmpeg (an LGPL build) | `engine/src/mado/downloads.json` | the source it names (BtbN's FFmpeg-Builds) |

WebView2 is Microsoft's and keeps itself current. Each AI model joins the table as its tool is
built. A newer model or build is measured before it's taken: its speed on the owner's PC, and its
quality on the same pictures its stack page measured it with. Take it when it's at least as good
and fits the time the owner accepted; then update its pin (version, addresses, sizes, SHA-256), its
licence in the notices (`engine/tools/third_party_notices.py`), its page in [stack/](stack/), the
versions table in [README.md](README.md), "The AI inside" in the [project's README](../README.md),
and the changelog. When the newest doesn't fit, the one in use stays, and its stack page says what
was tried and why, so the next update doesn't measure it again for nothing.

Other people's PCs count too: a newer model never raises what a PC needs ("What your PC needs" on
the downloads page and in the README). One that wants more memory or a stronger card than the one
it replaces comes as a choice beside the lighter one, as Best beside Fast.

## Troubleshooting

**"Are you sure you have RC.EXE in your $PATH" when building the shell.** Rust finds the Windows
SDK's resource compiler through the registry, and on some PCs that entry points at the wrong
folder. Set the user variable `RC` to rc.exe, then open a new terminal:

```powershell
[Environment]::SetEnvironmentVariable('RC', 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\rc.exe', 'User')
```

**The window says "Mado's engine isn't running".** "Copy details" (when shown) has the engine's last error lines.
In development, run `uv sync` in `engine/`; the engine's own log is `engine/.dev-data/logs/engine.log`.

**Port 1420 is busy.** A previous `pnpm tauri dev` left Vite running; close it or end the `node`
process using that port.
