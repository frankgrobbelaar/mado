# Mado

Mado (窓, "window") is a personal Windows app for one person's pictures. It upscales them to 4K,
8K or exactly the size a screen or a print wants, makes them look great with filters, fixes and
restores them, edits them with a click, does all of it to many pictures at once, and keeps a
library of the folders they live in, with small AI models that run on the PC. It is the owner's
own tool: one user, one PC, never commercial, no sign-in. The code is shared under the MIT
licence: anyone may fork it, but the repo takes no contributions. It's the sibling of Kura (an
anime library) and Maku (TV series and films), and stands on their foundations.

**Where it stands (2026-11-23):** scoped with the owner and the repo set up on Kura's
foundations: CI, the installer, the updater and the downloads page; the window with its engine and
token, Setup fetching ffmpeg, Settings (light or dark, Start with Windows, updates, nightly backups
and restoring one, the export), and records damaged past use. The look is Graphite, the owner's
pick, with Mado's own mark: every screen is drawn on the Mado Screens canvas, and the app wears
it. Built and tested: the library and a picture's page, the first piece of Mado 1.0 (folders added
in Setup, Home or the Library; every picture read with Pillow, a HEIC's facts by Mado's own reader
and its pixels by ffmpeg, camera RAW listed; the folders watched; thumbnails and screen-sized
views in the cache; the Library by the day pictures were taken, with the folder tree, search and
ticks; a picture's page at Fit, 100% or 400% with its neighbours and the arrow keys); and making
a picture right for a screen, the second piece (the Size tab: the devices, the owner's screens,
prints at 300 dpi, crop around a focus point or extend with LaMa, the model chosen by what the
picture is, before and after at full detail; Real-ESRGAN on ONNX Runtime with DirectML, a tile at
a time, Fast shipped and Best downloaded when asked; saving as a new picture or replacing, the
original in quarantine; History with undo and put back; This PC tested and timed, as Kura does);
and looks, the third (the Looks tab: fourteen looks shown as small copies of the picture and on
the picture itself, strength, six finishing touches drawn by code, hold to see the original, the
owner's own looks from .cube files or kept mixes; and one recipe for both tabs, made by one Save);
and many at once, the fourth (pictures ticked, a folder, a search, or dropped anywhere on the
window or picked on Home, in the library or not; their steps with Change, See it first, when,
saving and what it takes; the Queue in the rail with its badge, nights only, pause, cancel all,
ticked pictures, room on a drive, a drive not connected, carrying on after a stop; recipes and
watch folders; a notification and Home's Needs you and Made today; History's one line a batch);
and looking after the library, the fifth (duplicates and bursts found from the thumbnails in the
background and reviewed on a page of their own, the rest set aside into quarantine under one line
of History; the pictures that won't open, to try again or mark as damaged; the space on the
drives the library uses; a picture open in another app waiting while the queue goes on); and
editing by clicking, the sixth (the Edit tab: Select picks parts with SAM 2.1, then erase them,
cut them out, blur what's behind them or give them a look; Erase's brush; Cut out finds the
subject; looks on just a part; "Cut out the subject" in batches and recipes; each model
downloaded the first time); and pictures from anywhere, the seventh (a picture from outside the
library on a page of its own; paste; File Explorer's "Open in Mado" and Open with; the command
line; and the Library's tags on a group's kept picture); and the wallpaper studio, the eighth
(a place in the rail: the owner's monitors as Windows arranges them, a picture made for each, or
one laid across them all, at exactly each monitor's pixels and set as Windows' own wallpaper or
saved as pictures; favourites, with a heart on a picture's page and its tile and a view of their
own in the Library; the wallpaper changed every day from them if wanted; the owner's own kept and
put back). Next: the rest of Mado 1.0, by [What's next](#whats-next).

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
scripts/        release.mjs (versions, notes, the downloads page), design-snapshot.mjs,
                readme-pictures.mjs (the README's pictures, from the app's own screens)
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
  outlines, `docs/readme/download.svg`, "Coming soon" until the first release, then a line saying
  what the latest version has), seven steps with pictures (the wallpaper studio the fifth, since
  0.7.0), Safe by design, The AI inside, what a PC needs, the siblings. Its pictures
  (`docs/readme/`) are Mado's own screens, taken from its tests with made-up data and pictures
  drawn by code (the boards' scenes), framed in headless Edge as the boards were
  (`node scripts/readme-pictures.mjs`), and taken again when the screens they show change
  (docs/development.md, "Taking the README's pictures again"). Where a step's words and the app
  disagree, the words change to match the app.
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
- Making a picture right for a screen, as built (2026-11-22, Claude's calls while the owner is
  away): the devices are six, as Picture-Size draws them (Phone 1290 × 2796, Tablet 2048 × 2732,
  Laptop 2560 × 1600, Monitor 4K, Ultrawide 3440 × 1440, TV 8K), generic, a screen keeping its
  own way round; prints at 300 dpi turn to the picture's. The owner's screens come from the
  shell and are remembered by size. Fast is Real-ESRGAN's general model (its weak-denoise twin
  when "Clean noise and blocks first" is off), Best is RealESRGAN x4plus for photos (a 67 MB
  download) and its anime 6B model for drawings (shipped); each kind starts on Best where a
  12-megapixel photo takes it two minutes at most on the card, else Fast. Extending edges uses
  LaMa (a 209 MB download), drawn at a scale where it sees the whole picture and joined softly,
  said plainly to suit skies, walls and water. "Keep faces natural" is left out: GFPGAN's licence
  is non-commercial, and a face finder needs real faces to test on, which Mado never uses; 1.2's
  face restoring brings it. JPEG XL waits for a writer Mado can ship. One job at a time, in a
  jobs table the queue builds on.
- Looks, as built (2026-11-22, Claude's calls while the owner is away; docs/stack/looks.md):
  fourteen, the Picture-Looks board's nine and Mado's own Bold colour, Sepia print, Moody blue,
  Cross-processed and Soft pastel ("Vivid" and "Matte", though suggested, are left out as names
  other photo apps' filters use). Every look is a table of colours (a 3D LUT) through Pillow's
  `Color3DLUT`: Mado's made by code at 33 points; a .cube file as the format allows (up to 100 MB,
  about 129 points; bigger than 65 sampled down), 1D too, with its input range; strength mixes a
  look with the colours as they were, and fade goes into the same table. The touches (grain,
  vignette, glow, fade, light leak, dust) are drawn by code, off till turned on (at 20, 35, 30, 30,
  40 and 30, the board's grain and vignette), placed and sized in the picture made by its short side
  and grown from the picture's path, so the preview and the picture saved match. A kept mix is its
  look at its strength made into one table, with its touches, so it never changes under the owner; a
  look's number is never given to another, so a job naming one deleted fails rather than taking
  another's; names are unique in any case and never Mado's, an imported file taking "(2)" and a
  typed name refused with a sentence. Kept packed (16-bit, differences along red, zlib: a 65-point
  table in about 50 KB), in the export as `looks.json` and a .cube file each. One recipe for both
  tabs: the size step, then the look step, either left out (a look alone keeps the picture's
  pixels), made by one Save after the size, so grain never grows; a new picture is named after both
  ("Harbour at dusk (TV 8K, Warm film).jpg"; the Save board's example named only the size), and
  History keeps the look apart from the size. The tab follows its board: no zoom or neighbours there
  (the arrow keys don't change pictures from it), "Hold to see the original" (and the \ key) in
  their place; resting the pointer on a look shows it; the stage shows the picture as Save makes it,
  the Size tab's crop or canvas included, and the Size tab's after carries the look. "Open it" on a
  picture just made shows it as it is, the size and look that made it not kept for it. A look works
  on a picture's colours in its own colour space, its profile kept (wide colours stay wide), 8 bits
  as the Size tab makes it, see-through parts untouched, a grey picture grey unless the look colours
  it. "Only on a part" waits for selection (SAM 2.1), with no control shown; a mask fits as a
  composite of the picture before and after its look. Save stays at the foot of the tools column on
  both tabs. The slider's thumb is the text colour without the board's shadow, which isn't a token.
- Many at once, as built (2026-11-23, Claude's calls while the owner is away; docs/stack/queue.md):
  pictures come ticked in the Library ("Many at once…" leads its ticked bar), from a folder's ⋮ menu
  (inner folders too), beside a search's count, dropped anywhere on the window (Tauri's drag and
  drop, for paths) or picked on Home ("Pick pictures", "Pick a folder", whose folders inside are
  looked through, never a quarantine); camera RAW and pictures that won't open are left out, saying
  why; 10,000 at most, and 50,000 files looked through in what's dropped, what's past either said as
  left out. One picture in the library opens its page; one outside it opens Many at once alone, as a
  picture's page is the library's. A batch's steps are a list (`{"step": "size"…}`, room for later
  kinds), made in Mado's order whatever their order; Change opens the picture page's own choices in
  a card (the devices, screens and prints, the shape, Fast or Best or as this PC suits, clean first;
  the looks as small copies of the batch's first library picture, or by name with none, strength,
  touches, your looks); "Add a step" stays, as the board draws it, disabled once both are in. A size
  step has no point to crop around: each picture's subject is found as it's made. Saving is the Save
  dialog's choice for many: new pictures beside the originals, into a folder by name beside each
  ("Edited", the board's "Holiday › Edited"), or into one folder, JPEG 92 till changed, the owner's
  Saving default first; or the originals replaced, each into quarantine. See it first makes three,
  spread across the batch, by itself 0.8 s after the steps settle, through the jobs' worker before
  the queue (one picture at a time on the card, as everything is, a picture's own Save first); the
  batch keeps them rather than make them again, each by its own picture's file, whatever its place
  in the list, and lets a kept copy go once it's saved. What it takes reckons each picture by its
  pixels (as a photo), this PC's speeds and what See it first found (its time held to a third to
  three times, its space to a tenth to three times, as bytes a pixel vary far more), See it first's
  own counted as kept, and the room on the drive most save to, a 256 MB margin kept. "Now" goes
  ahead of what waits (the picture being made finishes), "After what's in the queue" behind,
  "Tonight" from 23:00 till 07:00 (the picture being made at 07:00 finishes), and Windows doesn't
  sleep while a batch's picture is made. A picture's own Save goes ahead of the queue, even paused.
  Pause stops the picture at its next tile, first in line again; neither a pause nor Mado closing
  counts as a try, only a crash. Cancel all cancels the batches (asked first), not a picture's own
  Save, and a batch the owner cancelled that way isn't told of or shown on Home (one picture
  cancelled, the rest are told). Ticked pictures (those waiting) go next, to the end, or out of the
  queue (as if never put in; a batch left with none goes); Try again puts one at the end. A drive
  without room pauses the queue with one notification, and the queue carries on by itself once the
  first picture waiting there fits; "Make the 11 that fit now" lets those go; "Empty D:'s quarantine
  first…" asks once more; "Wait for room" leaves it to carry on. A drive that filled while a picture
  saved waits for 64 MB more than was free then, and for the picture to fit with its margin, as
  Mado's reckoning was wrong once. A drive not connected waits, one unplugged while its picture is
  made too (back in line, not a try); a picture open in another app waits too (looking after the
  library, below). With nothing waiting, the Queue keeps the latest batch done in the last week
  whose pictures didn't all work, with Try again, till "Clear", as Home's card says "the queue says
  why". When
  nothing of a batch waits, a notification ("Holiday prints is done", "48 pictures made for TV 8K ·
  1 didn't work") leads to Home, whose "Needs you" shows a batch done in the last week (not a watch
  folder's, which come as pictures arrive) till its "Open folder" (the folder its pictures went to,
  when they share one; else "Done"); "Made today" shows the newest six, thumbnails from History for
  pictures outside the library too. Home's board's "Won't open", "Duplicates and bursts" and "Space
  on D:" came with looking after the library (below). History shows a batch as one line in the
  board's words ("Made 47 pictures for the TV overnight", "The watch folder To TV made 6
  pictures", "Replaced 48 pictures with their TV 8K versions") with "Take them away" or "Put the
  originals back" (and back again) once nothing of it waits ("Still being made" till then), each
  picture's line under "Show the 48 pictures"; a batch made overnight is one line, on the day it
  finished. An undo never comes between
  a picture's History line and its moves (one lock holds both). The Queue page shows the batch being
  made, then "Then" for those after it; the rail's badge says how far it's got, else how many wait,
  and the status bar "Graphics card working · Holiday prints 18 of 48". Recipes are named (60
  letters, unique), say how often and when they were used ("tonight" while one waits for it), are
  used on pictures picked or a folder, and edited in a card; one a watch folder runs can't be
  deleted, nor one of the owner's looks a recipe uses (or pictures waiting are made with). Watch
  folders look round every 5 s, through their folders, taking a picture once its size and time have
  held for 5 s and it opens (one that won't for 2 minutes is left alone), never their results folder
  however it's named (real paths compared) nor any picture Mado wrote (History's and the jobs'
  results, by path or as the same file), and never through a link to another folder, so nothing
  loops; a watch folder whose pictures can't go in the queue says why on its row and rests 5 minutes
  before trying again; what's there as one is watched (or turned on again) is left alone, what
  arrived while Mado was closed is taken; new pictures join its batch still waiting, else start one
  behind what waits, saved as new pictures where it says ("Done" inside it at first; never the
  folder itself). "Big batches wait for the night" (Settings › General › Many at once, off at first)
  sends one of more than 20 to tonight. The recipes and watch folders join the export.
- Looking after the library, as built (2026-11-23, Claude's calls while the owner is away;
  docs/stack/duplicates.md): duplicates and bursts are found by the engine on a thread of its own as
  each scan ends, from the thumbnail the scan made, so nothing is decoded twice (not the view the
  size of a screen: the cache holds that only for pictures opened). A 64-bit pHash finds candidates
  in buckets (within 6 bits) and a 256-bit pHash confirms them (within 10), shapes within 1%:
  measured on made-up scenes, copies at 50% and 25%, JPEG 60 to 95, PNG, WebP and sharpened came
  within 4 and 6 bits, a crop of 2% or more each side 14 or more on the finer, other scenes 18 and
  98 at least (a crop under 2% may group: it's practically the same picture). Files sharing a size
  are told by their bytes' blake2b. Bursts are the same camera, folder and size, each within 2 s of
  a neighbour and 12 bits, and keep the sharpest by the Laplacian's variance on a 1024 px grey copy
  of the picture itself (on the thumbnail blurs ranked wrongly, at full size the grain drowned
  them). Never grouped: camera RAW, pictures that won't open, a quarantine, pictures the owner said
  aren't the same (asked again once a file changes), and History's families (no group holds an
  original and what Mado made from it, or two made from one). Duplicates keep the most pixels, then
  the larger file of its format, a name that isn't a copy's, the older file; a burst compares its
  shots each with its copies as one (a sharpened export never outranks its original), and each group
  says which rule decided. The groups are kept in memory and found again after each change. The
  review is a page of its own (`/duplicates`, Home's place lit), drawn from the Queue, History and
  Library boards as none exists: groups newest first, 30 at a time, All, Duplicates or Bursts; a
  click keeps another, a tick keeps more than one (one is always kept), a tile's corner opens it big
  beside the one kept at Fit or 100% (the two moving together), Not the same, Set aside per group,
  and the one primary "Set aside 212, freeing 1.4 GB" (of the kind shown). Setting aside names what
  the review showed (each group's pictures and kept ones; all of a kind, the groups' version, else
  nothing moves), so a picture that joined since is never set aside unseen; keeping writes choices
  only for the pictures shown. Each picture set aside gets its History line (kind `aside`, with the
  one kept) before it moves, under one review line ("Set aside 211 duplicates and bursts, freeing
  1.4 GB", Put them back; each its own Put back, no redo: the review lists them again). Each is
  checked first (its size and time as compared, there, its drive connected, not the kept one's own
  file under another name) and left with a sentence otherwise, as is one open in another app, and a
  whole group when its kept picture isn't there as it was; the library forgets it (`gone_at`) till
  it's put back, when a scan finds it as it was (put back on its own, it's kept); only the 30-day
  clear-out deletes. Won't open: Home's row counts those not marked as damaged; See which opens a
  card of the small things board's cards (Show in folder, Try again, Mark as damaged, which a
  picture's page has too); the mark clears once a scan finds the file changed; a picture another app
  held while it was read is read again a minute on instead, and Try again on one says so. Space: the
  drive with most of the library's pictures (free, the pictures, quarantine, what the queue wants
  there; not connected says so), a line for each other. A picture open in another app (to read, or
  its original to move as it's replaced, which is asked before the picture is made): its job waits,
  tried again every 30 s for 10 minutes and then counted as not working, with the small things
  board's note at the window's foot: Try again now (its ten minutes afresh) and Skip it (not
  working, to try again later). Measured on the owner's PC with 4,950 made-up pictures (60 exact
  copies, 150 saved again, 60 bursts of five, 40 gentle crops planted): finding took 46 s after a
  240 s scan and found the 270 groups planted and nothing else, the sharp shot kept in all 60 bursts
  and the original in all 210 duplicates. The Library board's "burst of 5" and "2 copies" tags on
  the grid came with pictures from anywhere (below).
- Editing by clicking, as built (2026-11-23, Claude's calls while the owner is away;
  docs/stack/editing.md): the Edit tab follows Picture-Edit. Select is SAM 2.1 Hiera-Tiny: the
  picture read once at 1024 × 1024 (the whole of it squeezed, so any size can be picked; on the
  card when it has room), each click its decoder on the processor (49 ms with the outline, never
  waiting for the card); a click starts a part, an Alt-click adds a "not this" point to the part
  it's in (one outside every part says so), the three answers kept smallest first, the surest shown
  unless a bigger one is within 0.1 of it, Bigger, Smaller and the wheel stepping through, Esc
  letting go. Parts are Part 1, Part 2: the board's "The boat" needs recognition, which waits for
  a later piece. The volt dashed outline, the click's ring and "Part 1 · picked with one click",
  "Mado read the picture in 0.3 s; every click after that is instant" and the status bar's "1 part
  picked" are as drawn. With what you picked: Erase it (Fast, MI-GAN; Best, LaMa; the hole grown a
  little and cut out in a square half its size again round it, 512 at least, laid back softly with
  grain like the picture's), Cut it out (on nothing, as PNG or WebP only; a colour, of four
  swatches or any; or the rest blurred; the picture keeps its size), Give it a look (the Looks tab
  with "Only on a part" set to it) and Blur what's behind it (a disc 1.2% of the shorter side, in
  light, the part kept out of the blur, a soft edge). The board's small pictures beside Erase it
  and Cut it out are the picture's thumbnail with the part painted, or alone on the check. Erase's
  brush is 1 to 20% of the shorter side, Alt taking away; Cut out's subject is u2netp at Fast
  (shipped, 4.6 MB, on the processor) or BiRefNet lite at Best. Masks for cut-outs, blurs and looks
  are refined to the picture's edges at full size by a guided filter, worked out on a copy 1024
  across and laid on only along the unsure edge (0.5 to 0.6 s at 12 MP; it halves the error at
  the edge). Undo (↶) and Start again in the header, as drawn, and the \ key to see the original
  (the board's Edit header has no hold button); Save is the Save dialog, quiet till the first
  edit. Each edit is a step of the picture's one recipe, made first, before the size and the look,
  on the picture as the edits before it left it: kept as its clicks, strokes and answers, tied to
  the picture's version (a Save on a changed picture saves nothing; a click on one lets the edits
  go), each mask kept in `cache/edits` by picture and version and picked again from its clicks
  when gone. A saved edit is a `made` or `replaced` line with what was edited in History's new
  `edit` column (migration 7), the new picture named after it first ("Little sail (Erased).jpg",
  "Cut out", "Blurred", "Edited" for more than one kind). A look on a part is feathered over 0.4% of
  the shorter side, placed as the size step places the picture. "Cut out the subject" is a batch's
  step made first (`{"step": "cutout"}`, Fast, Best or as this PC suits, with nothing, a colour or
  the rest blurred behind), a batch or recipe cutting out with nothing behind saving only as PNG or
  WebP. The models come the first time they're needed, from `models-2` (SAM 2.1, 156 MB; MI-GAN,
  28 MB; BiRefNet lite, 224 MB; LaMa from `models-1`), each with its size and progress, offline
  saying Fast cut-outs work meanwhile. A DirectML session keeps its share of the card's memory for
  good (SAM's reader 1.2 GB, MI-GAN 0.6, LaMa 1.0), and going past Windows' budget pages rather
  than fails, so an editing model goes on the card only when DirectX says this process has room for
  it (`hardware.room`, any maker's card); BiRefNet lite commits about 10 GB with its graph fusion
  off, so it runs on the processor on the owner's card (about 10 s). The queue's picture and an
  edit take the card in turn a tile at a time, so an edit waits at most a tile; a click never
  waits (a click made while another is on its way waits its turn, never dropped). Where each
  model runs is in `/pc`, so the tab blames the card only for work on it and says when a picture
  was read on the processor. A look's parts are tied to the picture's version as edits are; a
  batch's edits keep no masks; the previews keep a cut-out's see-through parts; the Looks tab's
  small copies and the small pictures beside Erase it and Cut it out show the picture as edited.
  Mado edits pictures up to 100 megapixels, a bigger one saying so before a part is picked, with
  the way to the Size tab. Measured on made-up scenes: a click picks the
  sun, a sail, a hull or a ball at IoU 0.985 to 0.996, a striped balloon's one stripe first (the
  whole balloon two steps bigger, 0.991); erasing a boat, PSNR in the hole 33.7 dB at Fast (0.43 s)
  and 35.0 at Best (0.99 s).
- Pictures from anywhere, as built (2026-11-23, Claude's calls while the owner is away;
  docs/stack/tauri.md, "Open in Mado" and "Paste"): one picture from outside the library (dropped,
  picked, pasted, opened from File Explorer's "Open in Mado", Open with or `mado.exe <paths…>`)
  opens on a page of its own (`/pictures/{id}`, Home's place lit) with Size, Looks, Edit and Save as
  a library picture's; several, or a folder, open Many at once with them chosen; among other files,
  the one picture opens and a note at the window's foot says what was left out and why. The engine
  knows it by its path, a row of `pictures` with no library folder (migration 8 made the table again
  with `folder_id` able to be NULL, the migrations now running with foreign keys off and checked
  before each commits, and added `opened_at` and `pasted`): never listed, counted, exported or
  looked at for duplicates; one in a library folder is that library picture (one just copied there
  recorded at once, as a scan would); its folder added later, the scan makes it the library's under
  the same number, counted as new, so its jobs stay its own (History goes by path). The page shows
  its folder where the breadcrumb was (a click shows it in File Explorer) with the quiet "Add its
  folder to the library", no neighbours, and no "Mark as damaged" (Won't open lists only the
  library's); as no scan looks after it, asking for its page looks at its file (read again once it
  changed, a Save in its place included; gone, the engine's words say so, or that its drive isn't
  connected), and the page asks again once its Save is done. Not opened for 30 days (the month the
  quarantine and the edits' masks keep), an outside picture is forgotten by the daily care with its
  cache, unless a job waiting names it or a line of History naming it is recent or has something in
  quarantine; opening its page counts as opening it. Save beside it writes in its own folder;
  Replace sends the original to its drive's quarantine, and History puts it back. A picture in a
  quarantine opens to look at only (the tools' place says so, with Open History; the engine refuses
  its Save). Camera RAW from outside shows the library's "not readable yet"; a path not there says
  whether its drive is connected; a long path is reached in Windows' long form when only that
  reaches it; the same picture opened twice is one page. Paste is Ctrl+V anywhere but a text field:
  files copied in File Explorer, read by the shell (CF_HDROP through windows-sys, as the Tauri
  clipboard plugin reads only words and pictures), open as if dropped, asked first as a page sees a
  copied picture file as a picture too; else a picture on the clipboard (the page's paste event,
  PNG) is kept in the data folder's `pasted` as "Pasted 2026-11-23 14.05.png" ("(2)" in the same
  minute), the same bytes again opening the one kept, at most 2^26 pixels (about 67 megapixels: past
  it the window's own clipboard hands a page an empty PNG, measured; it takes 1.2 s at 66), said as
  too big on both sides; else words that are paths (Copy as path, `file:` addresses) open; else
  "Nothing to paste"; a folder with no picture in it says why rather than open an empty Many at
  once. Of Mado's own data folder only a paste opens (as a paste, whatever library holds the
  folder); any other file there is Mado's, not the owner's, and isn't opened. A pasted picture's
  page says "Pasted · not saved yet"; Save is there with nothing chosen (it saves the paste as it
  is, named as pasted, an empty recipe allowed only for a paste) and offers only a new picture, into
  the owner's folder for new pictures when they chose one in Settings, else their Pictures folder
  (Windows' own, wherever it's kept), never beside it or in its place (the engine refuses both); an
  unsaved paste is forgotten like any outside picture, its file deleted (only ever a file in
  `pasted`, a paste whose record went, by a stop or a restore, cleared after its month too), and
  Settings › Your data shows "Pasted" once there is some. "Open in Mado" is a verb under HKCU on
  every extension Mado reads (a test holds the shell's list to the engine's) and on folders,
  `MultiSelectModel` Player: with Windows' default (Document) it's dropped past 15 selected, and
  with either Explorer starts nothing past 100 (measured; past that, the folder's own entry opens
  every picture in it). Explorer starts Mado once per file; the single-instance plugin hands each
  start's paths to the Mado running, which gathers those within 600 ms of the last into one choice
  (measured: 22 ms apart at most to a Mado running, 146 ms from cold; 100 files one choice in 2.3
  s), the last look made on the main thread, where the paths arrive (a start's words become paths
  off the main thread, as a network share not there can take a while to answer); a second start
  finding the first's lock waits up to 2 s for its window (the plugin would otherwise run it as a
  second Mado), and paths arriving before the window's ready wait in the shell till it takes them,
  once the engine is ready, the window coming forward (from the tray too). Send to was measured and
  left out: one start with every path, but Windows refuses past 32,767 letters of them (200 deep
  paths), and it's a second entry. Open with is `OpenWithProgids` (`Mado.Picture`) and
  `Applications\mado.exe\SupportedTypes`, never a type's default value nor UserChoice (Windows reads
  a type's values from the user's keys first, value by value: checked); Tauri's
  `bundle.fileAssociations` isn't used, as its template writes each type's default. Only an
  installed Mado writes them (its uninstaller beside it), at each start and when Settings ›
  General's "Open in Mado in File Explorer" (on till turned off) changes, telling Explorer when
  something changed; taking them away goes by what was written, then each key above left empty, and
  the uninstaller does the same (`MadoForgetExplorer`), not while updating. `mado.exe` takes paths
  as given, quoted or not (a path with spaces typed without quotes put back together, one typed in a
  terminal found where it was typed), `--in-tray` as before. Found on the way: the scan and the
  watcher now never look inside Mado's own data folder (a library folder holding it read the cache
  as pictures), a walk no longer marks gone a picture recorded while it walked (opened then) that's
  still there, and a name Windows can't put in letters no longer stops Mado starting. The Library
  board's tags are built: "burst of 5" on a burst's kept picture and "2 copies" on a duplicate's
  (the group's pictures counted), bottom right in mono on dark glass beside a HEIC or RAW tag, a
  click opening the review at that group (`/duplicates?group=`, the page long enough to hold it,
  marked and scrolled to).
- The wallpaper studio, as built (2026-11-23, Claude's calls while the owner is away;
  docs/stack/wallpaper.md): a place in the rail, "Wallpaper" with a monitor, after the Library,
  rather than a page reached from Home and a picture's page, as it keeps what's about no one picture
  (the monitors, the daily change, putting back) a click away; "Make it a wallpaper" on a picture's
  page (from outside the library and pasted too) opens it with the picture chosen
  (`/wallpaper?picture=`), and while it's open a picture dropped on the window or pasted goes to it,
  through the window's own Opening (`useClaim`), the first of several, a folder said not to be one
  picture. No board covered it, so it's drawn in the picture page's pattern: the monitors on a
  stage, a column with This wallpaper and Every day as tabs, Set as wallpaper the one primary at its
  foot with Save as pictures beside it. The monitors and IDesktopWallpaper are the engine's, by
  ctypes (`mado/desktop.py`, no package), not the shell's: the engine owns the daily change and runs
  in the tray with no window to ask, and a `Desktop` seam lets every test use a fake
  (`tests/fake_desktop.py`); only `mado serve` hands it the real one. Read per-monitor DPI aware:
  each monitor's place and own pixels, scale, turn, main, its own name from DisplayConfig (the
  owner's PC: one, "24G4", 1920 × 1080 at 100%) and its device path, IDesktopWallpaper's name for
  it; asked again every 4 s while the studio's open, so one plugged in or out, resized or turned
  redraws. One for each cuts a part with each monitor's own shape; one across all lays the picture
  over Windows' own arrangement, its desktop pixels (as Windows' display settings and its own span
  place them), a gap of 0 to 200 pixels left at each line where monitors meet. A part is cropped
  around the subject (the biggest part with the shape, up to 4 times nearer, moved by dragging it,
  the arrow keys, + and -, the wheel or the slider, held inside the picture; "Around its subject
  again") or extended (one canvas drawn by LaMa for all of them, so the parts meet), made as the
  Size tab makes a picture (shrunk, pixel art repeated, screenshots smoothed, else the AI with Fast
  or Best), the painted warning past 6 times; the window draws each part from the picture's view as
  the engine cuts it (`geometry.ts`, the engine's `framed`), the engine's plan the truth. Windows
  makes a JPEG wallpaper again at its own quality (`TranscodedWallpaper`, quality 85, read on the
  owner's PC; raising `JPEGImportQuality` would change a setting), at the picture's own size, so
  each part is PNG, 8-bit sRGB, exactly its monitor's pixels, see-through parts on black, made by
  the jobs' worker before the queue's pictures (as See it first's) into `wallpapers\made\<number>`;
  spanned wallpapers are laid to fill first (a span shows one picture), nothing else changed. Save
  as pictures is a Save: each part, or one picture of the whole arrangement (one across all made in
  one piece, what the bezels hide included; one for each on black), PNG, JPEG, WebP or AVIF, into a
  folder the owner picks, "Harbour at dusk (Studio 27 wallpaper).png", each with History's line
  ("for a wallpaper on Studio 27"). A wallpaper being made says how long it has left and Stop stops
  it; one the owner asked to set or save that Mado's closing cut short isn't finished at the next
  start but says so, a Save's half-written picture and its line in History cleared away. Before Mado
  sets one over a wallpaper that isn't its own, it copies each monitor's file into
  `wallpapers\yours` (Windows' `TranscodedWallpaper` when the file's gone and one picture shows on
  every monitor; with one each, Windows' copies come in an order it doesn't say, so Mado doesn't
  guess) and notes how Windows showed it the first time (spanned, a slideshow with its folder,
  interval and shuffle, spotlight); "Put back your own wallpaper" stops the daily change, then puts
  each monitor showing Mado's back to its own file (else the copy; one the owner gave their own
  since is left, and one Windows refuses doesn't stop the rest), starts the slideshow again
  (`SetSlideshow`) unless a monitor shows one the owner chose since, spans again (unless the owner
  chose another fit since) and says where spotlight is turned on (no API does); one monitor alone
  can be put back too. The slideshow and spotlight are said before the first set. Mado's wallpapers
  a monitor shows now and those set in the last 3 days are kept, and those made ahead till their day
  has passed; only Mado's older PNGs go, from its own folder (Settings › Your data shows
  "Wallpapers"). Favourites (migration 9 with the studio's tables: `favourites`, `studio`,
  `studio_pictures`, `wallpapers`, `desktop_yours`, `desktop_before`) are kept by the picture's
  number: a Save in its place keeps it; a move or rename is one picture gone and one found by the
  same scan, and the heart goes to the one found then with the same size and file time, the same
  name first, then the same folder (two files written in the same instant can share both, so one
  there before never counts); one gone 30 days is forgotten; a folder taken out takes its pictures'
  hearts. A picture from outside the library can be a favourite (the heart means the same on every
  page, and the studio works on them), and one is never let go while it is, nor while the studio has
  it. The heart is on a picture's page by its name and on the grid's tiles (on hover, always when
  given); Favourites is the Library's (`?favourites=1`), searched and ordered as the rest, a
  favourite from outside opening on its own page, Many at once taking all of them (`favourites`
  pick); the export has `favourites.json` and `wallpaper.json`. The daily change is off till turned
  on: at 07:00 or the owner's time, as Mado next starts once it's past (Mado open or in the tray,
  Start with Windows beside it), a day's change only at a time after it was turned on or its time
  set (a time set once it's passed first changes the next day; the window sends a time once it
  settles), from the favourites or one library folder (taken out of the library, the change turns
  off and says why), one for each or one across all; each monitor gets a picture its way round (a
  square either way) made less than 6 times bigger, the one not shown for longest first (never shown
  first; ties by the day), none on two monitors while another suits; made 12 hours ahead (19:00 for
  07:00) by the worker, else then, and once more then when making it ahead failed (failing again,
  the day's given up, saying why); a day's never set goes once the day has passed; made again when
  the monitors changed; a favourite gone, moved or on a drive away skipped and counted (the pick
  looks at each file; the studio's counts go by the records); nothing to show said in words (no
  favourites yet, or none that suit), the wallpaper left as it was. A fresh agent reviewed the
  piece; its findings are fixed, test first. The lock screen is left out: Windows lets only packaged
  apps set it. An app that draws its own desktop hides the wallpaper, which the studio's help
  sentence says without naming any. Never set for real while it was built: the first set is the
  owner's (docs/stack/wallpaper.md lists what's untested).
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
  downloaded on first run; see docs/stack/ffmpeg.md; and the AI models fetched when asked),
  `cache\` (each picture's thumbnail and screen-sized view, made again when gone), and `pasted\`
  (pictures pasted from the clipboard, till a month after they were last opened).
- Next to the pictures: `Mado quarantine` at the top of each drive, a folder a day, holding
  replaced originals and pictures taken away for 30 days; Mado deletes only what's in a day's
  folder there, whatever its records say.
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
  inside the installer (WebView2 on a PC without it, ffmpeg, the bigger AI models, from Mado's own
  prerelease `models-1`) goes in one manifest, `engine/src/mado/downloads.json`: what it's for, version, size, licence, source and
  checksum. The installer's first page lists it (`scripts/installer-notes.mjs`), Setup downloads
  Mado's part of it (`engine/src/mado/tools.py`), and Mado downloads nothing that isn't on it.
- Per-user install (no admin) into `%LOCALAPPDATA%\Programs\Mado`, apart from the data.
- The update-signing key is `%USERPROFILE%\.tauri\mado-updater.key` (no password, made
  2026-11-22) and the `TAURI_SIGNING_PRIVATE_KEY` repo secret. Lose it and installed copies can't
  update.
- Not code-signed (Windows SmartScreen warns once on first install); fine for a personal tool.

**The owner's PC**
- GTX 1660 Super 6 GB (Turing), i5-9600K (6 cores), 24 GB RAM, about 1.7 TB free on D: and F:.
  Graphics driver 621.24 (fine as it is; never install drivers). No ffmpeg installed: Mado fetches
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
   a new picture and replacing. Built: the library and a picture's page, making it for a screen
   with saving, looks on the whole picture (a part comes with selecting), many at once with
   recipes, watch folders and the queue, looking after the library (duplicates and bursts,
   the pictures that won't open, space, a picture open in another app, the grid's tags), editing
   by clicking (select, erase and cut out, looks on a part, cutting out in batches and recipes),
   and pictures from anywhere (a picture from outside the library on a page of its own, paste,
   File Explorer's "Open in Mado" and Open with, the command line).
3. 1.1: search by describing a picture and by the words in it, the wallpaper studio (the owner's
   monitors, pixel-exact, changed daily from favourites if wanted), and painting styles. Built:
   the wallpaper studio, with favourites.
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
