# Mado

Mado (窓, "window") is a personal Windows app for one person's pictures. It upscales them to 4K,
8K or exactly the size a screen or a print wants, makes them look great with filters, fixes and
restores them, edits them with a click, does all of it to many pictures at once, and keeps a
library of the folders they live in, with small AI models that run on the PC. It is the owner's
own tool: one user, one PC, never commercial, no sign-in. The code is shared under the MIT
licence: anyone may fork it, but the repo takes no contributions. It's the sibling of Kura (an
anime library) and Maku (TV series and films), and stands on their foundations.

**Where it stands (2026-11-22):** scoped with the owner and the repo set up on Kura's
foundations: CI, the installer, the updater and the downloads page; the window with its engine and
token, Setup fetching ffmpeg, Settings (light or dark, Start with Windows, updates, nightly backups
and restoring one, the export), and records damaged past use. The look is Graphite, the owner's
pick, with Mado's own mark: every screen is drawn on the Mado Screens canvas, and the app wears
it. Built and tested: the library and a picture's page, the first piece of Mado 1.0 (folders added
in Setup, Home or the Library; every picture read with Pillow, a HEIC's facts by Mado's own reader
and its pixels by ffmpeg, camera RAW listed; the folders watched; thumbnails and screen-sized
views in the cache; the Library by the day pictures were taken, with the folder tree, search and
ticks; a picture's page at Fit, 100% or 400% with its neighbours and the arrow keys, its tools
column a placeholder). Next: making a picture right for a screen, with the upscaler and saving,
by [What's next](#whats-next).

## Ground rules

- **One branch.** Work on `main` in `C:\GitHub\mado`. No feature branches, worktrees or PRs unless
  the owner asks. Commit and push to `main` once every check passes. If another session is working
  at the same time, stage only your own files (never `git add -A`).
- **Never change the look unasked.** Mado's look is Graphite, the owner's pick: its colours,
  type, shapes and motion live in [app/src/styles/tokens.css](app/src/styles/tokens.css) and change
  only with the owner.
- **Nothing changes until the owner reviews it.** A tool's result is a new picture beside the
  original unless the owner chooses to replace it; a replaced original or a duplicate goes to
  quarantine (30 days), never straight to deletion. Renames, moves and deletions are proposed
  first, applied only when approved, logged, and undoable. Pictures are never touched by
  uninstalling.
- **Mado is personal.** No email address, no company name (no employer, no organisation behind
  Mado) and no personal details beyond the owner's name (LICENSE, commit author), anywhere in the
  project: files, test data, commit messages, publisher, accounts, signing. The publisher name is
  "Mado". Commits carry only the owner's GitHub no-reply address (the clone's `user.email`), and
  Claude's co-author line has no address.
- **Only ship what Mado may share.** Mado is MIT. A dependency's or model's licence must be on the
  allowed list in [engine/tools/third_party_notices.py](engine/tools/third_party_notices.py) (the
  installer build stops otherwise); code adapted from elsewhere keeps its notice (shadcn/ui:
  `app/src/components/ui/LICENSE-shadcn.txt`). No photos, artwork or other media in the repo or the
  installer: test and example pictures are drawn by code. Pictures of Mado that go public (the
  README's, the design boards and their snapshots in `docs/design/`) show made-up pictures only,
  never a real photo, artwork or person.
- **Every change you'd notice goes in CHANGELOG.md**, in the same commit, under "Unreleased"
  (see [docs/releasing.md](docs/releasing.md)). Versions are semantic, and every release must be
  newer than the last so installed copies see it as an update.
- **Latest versions.** Use the newest stable release of every package, tool and AI model, and keep
  them current wherever possible (see "Updating dependencies" in
  [docs/development.md](docs/development.md)). A model or a downloaded tool moves up once the newer
  one measures at least as good and fast enough on the owner's PC, and never raises what a PC
  needs: a heavier one comes as a choice beside the lighter one, as Best beside Fast.
- **Fix what you find.** A real fault found while working is fixed in the same piece of work, test
  first. Ask only about what is genuinely the owner's call: scope, money, anything irreversible or
  public.
- **Scoping means talking.** When the owner asks "is it possible…" or is scoping, answer in the
  conversation: no code, scripts or long checks.
- **Simple beats clever.** The bar is Revolut or Linear: few elements, one clear primary action,
  plain language, motion that explains. Code follows the same bar: small modules, obvious names.

## Layout

```
AGENTS.md       the guide for coding agents; each area below has its own AGENTS.md
CHANGELOG.md    every change you'd notice, by version
LICENSE         MIT
app/            the desktop app
  src/            React UI (TypeScript): components/, features/, lib/, styles/
  src-tauri/      Tauri shell (Rust): window, engine process, updates, installer config
engine/         the engine (Python): src/mado/, tests/, tools/ (build tools), mado-engine.spec,
                openapi.json
docs/           how it all works; docs/design/ holds the screens
scripts/        release.mjs (versions, notes, the downloads page), design-snapshot.mjs
.github/        CI and release workflows
```

## Commands

Run the app (Vite, the Rust shell, and the engine from source):

```powershell
cd app; pnpm tauri dev
```

Check everything CI checks (each line from the repo root):

```powershell
cd engine; uv run ruff format --check; uv run ruff check; uv run pyright; uv run pytest
cd app; pnpm check; pnpm build
cd app/src-tauri; cargo fmt --check; cargo clippy --all-targets -- -D warnings; cargo test
node --test "scripts/*.test.mjs"
cd app; pnpm build:engine; pnpm build:notices
```

Fix formatting: `uv run ruff format` (engine), `pnpm fix` (app), `cargo fmt` (shell).
Build the installer locally: `cd app; pnpm build:installer` (needs the signing key, see
[docs/releasing.md](docs/releasing.md)). Release: on GitHub, Actions › Release › Run workflow on
`main` (patch, minor, major or an exact version); from a PC,
`node scripts/release.mjs patch|minor|major` (commits and tags), then
`git push --atomic origin main v1.2.3`. A release reaches every installed copy, so releasing is
the owner's call.

## How it fits together

- **Shell** (`app/src-tauri`, Tauri 2, Rust): the window with its own title bar, one instance only.
  It starts the engine with a fresh token, tells the UI where it is, stops it on exit, and installs
  updates. Keep it thin.
- **UI** (`app/src`, React 19, Tailwind 4): talks to the engine over HTTP on 127.0.0.1 with the
  token. Server data goes through TanStack Query; screens live in `features/`.
- **Engine** (`engine/`, Python 3.14): everything else. A FastAPI app (`mado serve`) and a CLI
  (`mado export`, …), bundled by PyInstaller as a folder with its own Python. Picture logic goes in
  `mado/core` as pure functions with no I/O; the code around it does files, network and database.
- **Data**: one SQLite file, `%LOCALAPPDATA%\Mado\mado.db`, upgraded by append-only migrations in
  `mado/migrations.py`. Development uses `engine/.dev-data` instead, never the real folder.
- **Contracts**: the engine's API is snapshotted in `engine/openapi.json` (a test fails when it
  drifts); the UI's types in `app/src/lib/engine.tsx` mirror it by hand. Change both together.

Details: [docs/architecture.md](docs/architecture.md).

## Decisions

Everything decided so far. Don't ask again; change only with the owner.

**The product** (scoped with the owner on 2026-11-22)
- The first idea: "upscale to 4k, 8k etc images"; then, with Kura's stack, "super cool features"
  using small AI models "like we have for the other projects".
- Pictures made for every device's screen (the owner: "all types of devicew", then "I meant the
  images should be catered for sizing, quality etc for all device sizes"): the sizes cover phones,
  tablets, laptops and monitors (1080p, 1440p, 4K, ultrawide, two screens side by side) and TVs
  (4K, 8K), each with the shape it wants (cropped around the subject, or its edges extended), its
  exact pixels, and a format and quality that suit it. The owner's own screens are remembered, and
  the list of devices is kept current. Mado itself is a Windows app on Kura's stack (the owner:
  "No mac or phones", "Windows").
- Mado reads pictures from anywhere: phones (HEIC, JPEG, WebP), cameras (JPEG and RAW), scanners,
  screenshots and pictures saved from the web. Camera RAW needs a reader Mado can't ship (LibRaw
  is LGPL), so it's downloaded on first use and listed in the installer, as ffmpeg is; recent
  phones' HDR photos and wide colours are kept, not flattened.
- Both a tool and a library (the owner: "both, but we will haev folders/directories for the
  lbirarties"): libraries are folders the owner adds, as in Kura, and any picture can go through
  the tools without being in one: dropped on the window, pasted, right-clicked in File Explorer,
  or put in a watch folder.
- The upscaler, done properly: sizes by purpose (any device's screen, 4K, 8K, a wallpaper for the
  owner's screens, a print size) rather than "4x"; the right model for the picture (photos, anime and drawings, pixel
  art kept blocky-sharp with no AI, screenshots by a gentler method that doesn't invent letters),
  guessed and changeable; faces redrawn in the same pass, kept subtle; noise and JPEG blocks out
  before it grows; overlapping tiles so 8K and 16K fit a 6 GB card; a before-and-after slider
  with deep zoom; and honest about limits (2x to 4x looks real, 8K from a thumbnail looks
  painted).
- Filters (the owner: "I would love also to include various filters to make images look really
  cool"): looks previewed on the picture itself as they're scrolled (film, cinematic, black and
  white, golden hour, night neon, duotone and more), under Mado's own names, never film brands;
  finishing touches (strength, grain, vignette, glow, fade, light leaks and dust drawn by code);
  the owner's own looks (.cube files imported, any mix saved); a look on the subject, the
  background or any part clicked; fog and tilt-shift from a depth map; painting styles after
  public-domain painters (Van Gogh, Hokusai, Monet), trained for Mado so the licence is Mado's, or
  any picture as the style; sketch, oil paint and cartoon by classic means. No anime look: the
  models that do it are non-commercial.
- Saving (the owner: "we must consider when saving to overwrise or cretae new images"): asked at
  each save, with the owner's default in Settings. "New picture" (the default) goes beside the
  original ("Beach (4K).jpg") or into a folder the owner chooses, keeping the date taken, camera
  details and colour profile; the location can be stripped. "Replace the original" sends the
  original to quarantine for 30 days, and History puts it back. The format stays unless another is
  chosen (JPEG, PNG, WebP, AVIF, JPEG XL); a name that's taken gets "(2)".
- Many at once (the owner: "like batch items, we shold be able to do many at once"): pictures
  picked by ticks in the library, a whole folder, a search, a pile dropped on the window, or many
  selected in File Explorer; any tool on all of them; seen first on a few, then Kura's queue (now
  or overnight, the time and space worked out first, pause, cancel all); recipes, a saved chain of
  steps ("4K, then Warm film at 60%, then JPEG into Edited") run on any batch or on every new
  picture in a watch folder. Saving asks the same: new pictures or replace the originals.
- The README is a tour, as Kura's and Maku's are (the owner, 2026-11-22: "build the README really
  nice as we have for the others"): the mark, a volt "Download for Windows" button (IBM Plex Sans
  outlines, `docs/readme/download.svg`, "Coming soon" until the first release), six steps with
  pictures, Safe by design, The AI inside, what a PC needs, the siblings. Its pictures
  (`docs/readme/`) are the Mado Screens boards, drawn by code, framed in headless Edge and said to
  be the design; they're retaken from the app as its screens are built.
- Everything happens on the PC: nothing is uploaded, AI included. Mado works on pictures already
  on the PC and never searches for, downloads or shares pictures.
- The AI models are small, on the allowed licences, measured on the owner's PC before one is
  chosen, and each comes with a Fast and a Best where a PC's card matters. The shortlist from the
  scoping: Real-ESRGAN's family (BSD-3-Clause; Kura already ships one) and SwinIR (Apache-2.0) to
  upscale; GFPGAN for faces (its licence to check first); SAM 2.1 (Apache-2.0) to select; MI-GAN
  (MIT) and LaMa (Apache-2.0) to erase; BiRefNet (MIT) and U²-Net (Apache-2.0) to cut out; Depth
  Anything V2 Small (Apache-2.0; its bigger sizes are non-commercial) for depth; DDColor
  (Apache-2.0) and Microsoft's old-photo model (MIT) to restore; SCUNet (Apache-2.0), NAFNet (MIT)
  and FBCNN (Apache-2.0) to fix; CLIP (MIT), RapidOCR (Apache-2.0), YuNet (MIT) and SFace
  (Apache-2.0) for the library; Florence-2 (MIT) for captions. Out, as non-commercial or AGPL:
  CodeFormer, BRIA's background removers, Ultralytics' YOLO, InsightFace's face models,
  4x-UltraSharp, AnimeGAN and White-box Cartoonization. Generative models (pictures from words,
  filling big gaps with new things) are out: too big for a 6 GB card, and their licences aren't on
  the list.
- The name (the owner, 2026-11-22: "Go with Mado"), the pick of six (Mado, Akari, Kagami, Iro,
  Sumi, Gaku): Kura the storehouse, Maku the curtain, Tansu the chest of drawers, Mado the window
  you see your pictures through. The only namesake found was an obscure "MadoPhoto" listing.

**Design**
- **Graphite**, the owner's pick of three on the
  [Mado Looks](https://claude.ai/artifact/3te6hjNWp42cxk5EXcsDXv) canvas (2026-11-22: "Go with the
  graphite look"; snapshots in `docs/design/looks*`), with its menu as drawn: the slim icon rail on
  the side ("Keep the menu on the side as graphite has it", after a moment's liking for Gallery's
  top bar). A mid-grey bench #2A2B2E, panels #333438, lines #46474D, text #F0F0F1 and #B4B5BA, one
  volt accent #C9F24D (#172000 on it), IBM Plex Sans and IBM Plex Mono, dense panels and a status
  bar; neutral greys around the pictures, because colour in the window changes how a photo's
  colours look. The two looks not chosen, Darkroom and Gallery, stay on the canvas.
- Light and dark (the owner: "Is there an option to switch between light and dark?"): as Windows
  is, or chosen in Settings › General ("Light or dark": Same as Windows, the default, Light or
  Dark), as in Kura. Graphite's light is Aluminium: a bench of #D3D4D7 and a deeper volt, #4C7500.
- The mark (the owner: "You can create the logo"): a round window (Japanese architecture's
  marumado, a round window onto a garden) lit in volt, with a graphite hill seen through it, on a
  graphite tile: `app/src-tauri/icons/mado.svg`, the app's icons, `components/mado-logo.tsx`, the
  downloads page and the README. It keeps its colours in light and dark. Not four panes: a window
  of four squares is too near Microsoft's Windows logo.
- Every screen is drawn on the [Mado Screens](https://claude.ai/artifact/TJcDDQ5XmVTNPMvRdE3Jfb)
  canvas (2026-11-22; snapshots in `docs/design/screens*`), the source of truth to build to: 20
  boards in Graphite, Home, the Library, A picture · Size and Settings › General again in
  Aluminium, and a Tokens board with every colour role in both (Aluminium: window #D3D4D7, panels
  #E4E5E8, text #1A1B1E, the accent #4C7500 with white on it). Settings sits at the rail's foot.
- Graphite is in the app (2026-11-22, the owner: "build Graphite into the app"): its tokens and
  Aluminium's in `tokens.css`, IBM Plex Sans and Mono bundled, the rail down the side with the
  mark, a slim title bar, the status bar, and Setup, Home and Settings restyled; the downloads
  page wears it too. docs/design.md has the token table.
- Kura's rules carry over: motion that explains (120 ms hover and press, 200 ms toggles, 320 ms
  panels, one curve `cubic-bezier(.2,.8,.2,1)`, none when Windows' animation effects are off),
  status by shape first, light and dark designed together (as Windows is, or chosen in Settings ›
  General), everything reachable from the keyboard, and only the page scrolls.

**Architecture**
- Kura's: a Tauri 2 shell, React + Tailwind + shadcn/ui (restyled to the tokens) UI, and a Python
  engine sidecar built with PyInstaller as a folder (fast start; ships its own Python). A local API
  with a per-launch token, plus a CLI. SQLite for data.
- The AI runs on ONNX Runtime with DirectML, as Kura's does: the PC's high-performance card, never
  quietly falling back to the processor where the card should run it, and the processor where the
  PC has no card. ONNX Runtime and the models arrive with the tools that use them.
- A pure core behind small interfaces, as in Kura.

**Data**
- `%LOCALAPPDATA%\Mado`: mado.db, nightly backups (keep 7), logs (30 days), `tools\` (ffmpeg,
  downloaded on first run; see docs/stack/ffmpeg.md), and `cache\` (each picture's thumbnail and
  screen-sized view, made again when gone).
- Export: one zip (the database, settings, the library's folders, every picture with what Mado
  read of it as CSV, and a manifest), growing with the schema.
- Records damaged past use: as the engine starts, Mado says so and offers the newest backup that
  opens (with none, new records, as on its first day), keeping the damaged file beside them as it
  is, never deleting it.
- Uninstall: offer the export first, keep the data folder unless the owner ticks "Delete the
  application data", never touch pictures.

**Tooling** (2026-11-22, all latest stable, as Kura and Maku have them)
- Python 3.14 (uv-managed), uv, Ruff, Pyright (strict), pytest, FastAPI, Typer, PyInstaller.
- Node LTS, pnpm 12, Vite 8, React 19, TypeScript 7, Tailwind 4, Vitest 5, Biome 2 (lint and
  format; it skips Markdown and the lockfile).
- Rust stable (edition 2024), Tauri 2.12 with the single-instance, updater, dialog, opener,
  notification and autostart plugins, and its tray icon.
- No Dependabot: it opens branches. Dependencies are updated on `main` with the routine in
  [docs/development.md](docs/development.md).

**Delivery**
- GitHub repo `frankgrobbelaar/mado`, public under the MIT licence (the owner, 2026-11-22: "public
  but not contributions, only forking"): anyone may fork; issues, projects, wiki and discussions
  are off; only collaborators can open pull requests; secret scanning with push protection is on;
  the workflow token is read-only. The app's identifier is `io.github.frankgrobbelaar.mado`. CI on
  every push to `main` (Windows runners).
- Semantic versions and a changelog: patch for fixes, minor for features, major for a change to
  act on. `scripts/release.mjs` picks the version, moves CHANGELOG.md's "Unreleased" entries under
  it, commits and tags; it and the release workflow refuse a version that isn't newer than the
  last.
- The owner releases from GitHub's site (Actions › Release › Run workflow): on `main` it checks CI
  passed, runs `release.mjs`, builds and checks the installer, then pushes the release commit and
  tag together and publishes the release with its notes, `latest.json` (which installed copies
  check daily, no login needed) and `THIRD-PARTY-NOTICES.txt`, and refreshes the downloads page.
- Downloads page: https://frankgrobbelaar.github.io/mado/, the repo's website on GitHub Pages,
  every version newest first with its notes, installer, size and SHA-256.
- `THIRD-PARTY-NOTICES.txt` lists everything that ships, with its licence, and goes next to Mado
  with `LICENSE.txt`; `engine/tools/third_party_notices.py` writes it from what was actually
  bundled and stops the build on a licence that isn't allowed.
- **Every download is listed in the installer.** No one installs anything by hand. What isn't
  inside the installer (WebView2 on a PC without it, ffmpeg, later the bigger models) goes in one
  manifest, `engine/src/mado/downloads.json`: what it's for, version, size, licence, source and
  checksum. The installer's first page lists it (`scripts/installer-notes.mjs`), Setup downloads
  Mado's part of it (`engine/src/mado/tools.py`), and Mado downloads nothing that isn't on it.
- Per-user install (no admin) into `%LOCALAPPDATA%\Programs\Mado`, apart from the data.
- The update-signing key is `%USERPROFILE%\.tauri\mado-updater.key` (no password, made
  2026-11-22) and the `TAURI_SIGNING_PRIVATE_KEY` repo secret. Lose it and installed copies can't
  update.
- Not code-signed (Windows SmartScreen warns once on first install); fine for a personal tool.

**The owner's PC**
- GTX 1660 Super 6 GB (Turing), i5-9600K (6 cores), 24 GB RAM, about 1.7 TB free on D: and F:.
  Graphics driver 617.42 (fine as it is; never install drivers). No ffmpeg installed: Mado fetches
  its own. GitHub CLI signed in as frankgrobbelaar.
- Its Windows SDK registry entry points at the wrong folder, so the user variable `RC` names
  rc.exe for Rust builds (see docs/development.md, "Troubleshooting").

## What's next

1. The look: Graphite (picked), the mark (made), every screen on the Mado Screens canvas (drawn),
   and Graphite in the app (built): done.
2. Mado 1.0: libraries from folders (every picture read, a grid by date or by folder, the folders
   watched, duplicates and bursts found); the upscaler done properly, with sizes for every device's
   screen; looks, finishing touches and the owner's own, on the whole picture or a part; click to
   select, then erase or cut out; many at once, with recipes and the queue; and the choice between
   a new picture and replacing.
3. 1.1: search by describing a picture and by the words in it, the wallpaper studio (the owner's
   monitors, pixel-exact, changed daily from favourites if wanted), and painting styles.
4. 1.2: restoring old photos (scratches, faces, colour) and the quick fixes (noise, blur, JPEG
   blocks, dark photos), portrait blur and 3D photos.
5. Later: people (faces grouped, on the PC only), renaming by date taken, shrinking the library
   (AVIF or JPEG XL, originals to quarantine), and captions.

The owner, 2026-11-22, going AFK: "you can develop, review & test mado ... release all when you
want, it does not have to be a v1.0.0 release when you are done ... I saw you had some other 1.1
and 1.2 stuff, build that as well." So Claude builds 2 to 4 in that order, a piece at a time, each
reviewed and tested before it's committed, and releases minors (0.1.0, 0.2.0, …) as pieces land:
the library and a picture's page first, then making it for a screen with the upscaler and saving,
then looks, many at once with recipes, duplicates and bursts, select, erase and cut out, then 1.1's
and 1.2's tools. The AI models are exported or fetched, checked and timed on the owner's PC before
any is taken (docs/stack/ pages say how).

Build each screen to its board in [docs/design/](docs/design/), with its empty, error and recovery
states.

## Guides and docs

- **Area guides.** [AGENTS.md](AGENTS.md) is the entry for any coding agent, and each area has its
  own: [engine/AGENTS.md](engine/AGENTS.md), [app/AGENTS.md](app/AGENTS.md) (the UI),
  [app/src-tauri/AGENTS.md](app/src-tauri/AGENTS.md) (the shell) and [docs/AGENTS.md](docs/AGENTS.md).
  Read the guide for an area before changing it: it says what belongs there, the patterns to copy,
  and what "done" means.
- **Docs.** [docs/README.md](docs/README.md) is the map: architecture, development, conventions,
  design, releasing, and one page per tool in [docs/stack/](docs/stack/). Read the stack page before
  changing how a tool is used, and update docs in the same commit as the code they describe.
