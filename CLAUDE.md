# Mado

Mado (窓, "window") is a personal Windows app for one person's pictures. It upscales them to 4K,
8K or exactly the size a screen or a print wants, makes them look great with filters, fixes and
restores them, edits them with a click, does all of it to many pictures at once, and keeps a
library of the folders they live in, with small AI models that run on the PC. It is the owner's
own tool: one user, one PC, never commercial, no sign-in. The code is shared under the MIT
licence: anyone may fork it, but the repo takes no contributions. It's the sibling of Kura (an
anime library) and Maku (TV series and films), and stands on their foundations.

**Where it stands (2026-11-24):** scoped with the owner and the repo set up on Kura's
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
put back); and camera RAW, the ninth (LibRaw's own Windows build downloaded the first time a RAW is
read and used through its DLL: a RAW's facts without developing it, the grid's thumbnail from its
camera's preview, its page and every tool on it developed into Display P3, saving only as a new
picture, RAWs among duplicates and bursts but never with their JPEGs); and search, the tenth of
them and the second of 1.1 (the library read in the background by SigLIP for what each picture
shows and by a reader of words, PP-OCRv6 at Best or Windows' own at Fast; the Library's search box
finding by what a picture shows, the words in it and its name, in groups, Many at once from them;
More like this on a picture's page); and the quick fixes, the eleventh and the first of 1.2 (the
Fix tab: noise, blur from a shaking camera or a moving subject, JPEG blocks and dark photos, each
with its one setting and compared before and after, the brightening over the whole picture and
every fix at full detail; suggested only where Mado can measure the need; made before a picture
grows, never cleaned twice; a step for batches and recipes, each JPEG's blocks as hard as it was
squeezed; SCUNet, FBCNN and NAFNet downloaded the first time each is needed, on the card while it
has room); and painting styles, the twelfth and the third of 1.1 (a group of their own on the
Looks tab: After Van Gogh, After Hokusai, After Monet and After Seurat from networks Mado trained
on public-domain paintings, any picture as the style through MicroAST and kept as one of the
owner's styles, and pencil, coloured pencil, oil paint and cartoon drawn by code; each with its
strength, the networks' in the picture's own colours if asked, on a part as a look is, painted at
a working size and made the picture's size; a step for batches and recipes; each model downloaded
the first time); and depth, the thirteenth and the second of 1.2 (the Depth tab: Depth Anything V2
Small reading how far away each part of a picture is, downloaded the first time; portrait blur in
focus at the subject or where it's clicked, fog and tilt-shift's band dragged on the picture, a
step for batches and recipes; and 3D photos, a short looping video of the picture with the view
moving through it, made with Windows' own encoder or the graphics card's, played on the page
before it's saved); and restoring old photos, the fourteenth and the third of 1.2 (at the top of the
Fix tab: scratches and dust found by Microsoft's old-photo detector and shown as a mask checked with
the brush before LaMa fills them; a black-and-white or sepia print coloured by DDColor tiny, or a
colour photo's faded colours brought back, each with a strength; faces left as they are; a step for
batches and recipes that colours each picture as it needs and leaves scratches to its page; each
model downloaded the first time); and HDR photos with saving as it is, the fifteenth, part of 1.0's
promise to keep phones' HDR (gain maps read from Ultra HDR and ISO 21496-1 JPEGs, Apple's and ISO's
HEICs and AVIFs, from their headers as the scan reads them; an "HDR" tag on the tile and the page;
the page in HDR where Windows has HDR on; the gain map kept through every tool and written again in
JPEG and AVIF; and Save with nothing made, always a new picture, a batch or a recipe just Save too).
Next: the rest of 1.2, by [What's next](#whats-next).

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
  what the latest version has), eight steps with pictures (the quick fixes the fourth, the wallpaper
  studio the sixth), Safe by design, The AI inside, what a PC needs, the siblings. Its pictures
  (`docs/readme/`) are Mado's own screens, taken from its tests with made-up data and pictures drawn
  by code (the boards' scenes), framed in headless Edge as the boards were (`node
  scripts/readme-pictures.mjs`), and taken again when the screens they show change
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
  and FBCNN (Apache-2.0) to fix; CLIP (MIT; SigLIP took its place, as search was built),
  RapidOCR (Apache-2.0), YuNet (MIT) and SFace (Apache-2.0) for the library; Florence-2 (MIT) for
  captions. Out, as non-commercial or AGPL: CodeFormer, BRIA's background removers, Ultralytics'
  YOLO, InsightFace's face models,
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
  looked through, never a quarantine); pictures that won't open are left out, saying why (camera
  RAW too while its reader comes, asked again once it's here); 10,000 at most, and 50,000 files
  looked through in what's dropped, what's past either said as
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
  them). Never grouped: a camera RAW with a picture that isn't one (RAWs joined with their reader,
  below), pictures that won't open, a quarantine, pictures the owner said aren't the same (asked
  again once a file changes), and History's families (no group holds an
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
  its Save). Camera RAW from outside is read as the library's is; a path not there says whether
  its drive is connected; a long path is reached in Windows' long form when only that reaches it;
  the same picture opened twice is one page. Paste is Ctrl+V anywhere but a text field: files
  copied in File Explorer, read by the shell (CF_HDROP through windows-sys, as the Tauri clipboard
  plugin reads only words and pictures), open as if dropped, asked first as a page sees a copied
  picture file as a picture too; else a picture on the clipboard (the page's paste event,
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
- Camera RAW, as built (2026-11-23, Claude's calls while the owner is away; docs/stack/libraw.md):
  LibRaw 0.22.3's own Windows build (`LibRaw-0.22.3-Win64.zip`, 3.5 MB, from libraw.org; LGPL-2.1
  or CDDL-1.0), listed in `downloads.json` with its licence files kept beside it (ffmpeg's now too,
  `notices`), never shipped: THIRD-PARTY-NOTICES names what Mado downloads apart from what ships,
  and a bundle holding LibRaw's or ffmpeg's files stops the build. It's fetched by itself the first
  time a RAW is read or opened (a scan reading one, its page, a file dropped, a watch folder), again
  a minute after a try that failed (never by itself after one that didn't match the list), Try
  again at once; a scan finding RAWs that wait, as 0.7.0 listed them, asks too, as does opening
  one; Settings › About says whether it's there. Of the zip it keeps only `libraw.dll` and the
  licence files, and the installed engine never takes a development copy (`MADO_LIBRAW_DIR`).
  Its DLL through ctypes, not its programs, measured: facts in 0.5 ms against `raw-identify`'s 26
  ms a process; the programs take paths in the old code page (a folder named in Japanese wouldn't
  open) and those taking a camera's preview out write it beside the RAW; developing is the same
  code, 10 to 25% quicker without a process. LibRaw reads inside the engine, a file to a reader of
  its own, read-only, nothing written; a fault ctypes catches makes the RAW one that won't open,
  and every read notes its RAW in a file of its own named for the engine's run (`reading-raw`), so
  one that stopped the engine is marked won't open as the next starts, before anything reads it,
  never stopping it again (a power cut mid-read marks one too: Try again reads it). A RAW's facts
  come without developing it (its size as shown, cropped and turned; the camera's clock; the
  camera; its turn; a place). The grid's
  thumbnail and a burst's sharpness come from the camera's preview when it's big enough and the
  picture's shape, else from developing at half size; the view and full size are always developed
  (the brief asked for the preview there too, but the stage of the Size and Looks tabs is drawn from
  the view, and the camera's preview is its own rendering: the page would show what Save doesn't
  make). Developing: the camera's white balance, LibRaw's AHD and brightening, the RAW's own crop
  (`raw_inset_crops[0]`: a DNG's default crop, a maker's) cut after developing and its turn, at 8
  bits, the pipeline's depth, into Display P3 rather than sRGB (a camera's colours go past sRGB and
  Mado keeps a picture's own colours through every tool to the picture saved; P3 is what wide
  screens and phones show, and 8 bits band far less over it than over Adobe RGB or ProPhoto), with
  Mado's own Display P3 profile written by code (`core/icc.py`). Half size and the camera's white
  balance have no C call: they're written into LibRaw's options struct at the place measured for
  0.22.3 (`_OPTIONS_AT`), only after LibRaw's own setters confirm it. Every tool works on a RAW
  (Size, Looks, Edit, Many at once, recipes, watch folders, the studio, favourites); Save is always
  a new picture (JPEG at first, as a photo), Save and Many at once saying why Replace isn't
  offered, the engine and the job refusing it; a picture made from a RAW carries its date, camera,
  exposure and lens (its place when kept), written from LibRaw's facts. While the reader comes, a
  RAW is listed as it is (`waiting`): its tile and page say how the reader's coming (offline and a
  checksum failure in the download's words, Try again), its page reads it the moment it's there, a
  batch leaves RAWs out saying why and asks again once it's there, a watch folder waits with them
  (never given up on), Home counts them, and once it's there a scan reads them. A RAW that won't
  develop (half copied: tags and preview there, pixels not) joins Won't open when its page asks; one
  LibRaw doesn't know, or can't unpack (a JPEG XL DNG: this build has no DNG SDK), says so in its
  own words. Duplicates and bursts take RAWs now, as their thumbnails come from the reader and RAWs
  are the biggest files to keep twice, but only among RAWs: a camera's RAW and its JPEG of one
  moment, or a JPEG made from a RAW, are never taken for copies, and the review offers nothing for
  such a pair. The Library shows RAW and JPEG as two tiles side by side, the RAW wearing its tag:
  each file stays a picture of its own, as File Explorer shows it, so ticks, Many at once,
  favourites and History mean the same for each, and nothing is hidden behind another. Pick
  pictures offers RAW (a test holds its list to the engine's) and Home's drop zone lists it. Tested
  only through DNG written by code (`tests/dng_files.py`), never a real photo; the other RAW
  formats are LibRaw's to read. A fresh agent reviewed the whole piece and its twelve findings are
  fixed, test first: RAWs 0.7.0 listed fetch the reader; a linear DNG's crop follows the size
  developed; a RAW another app writes to is in use, not damaged; a packing this build can't unpack
  says so; memory short now passes, never kept as won't open; the job refuses Replace before See it
  first's shortcut; every read is noted; a refused download isn't fetched over and over; a
  camera's broken preview is developed instead. Measured on the owner's PC: a 24-megapixel RAW's
  facts in 0.7 ms, its thumbnail from the camera's preview in 68 ms (352 ms developed), its view in
  0.43 s and full size in 3.1 s; at 100 megapixels 0.18 s, 1.6 s and 13 s; a scan of 1,000 RAWs as
  quick as of the same scenes as JPEGs (50 ms each).
- Search, as built (2026-11-23, Claude's calls while the owner is away; docs/stack/search.md): the
  Library's search box finds pictures by what they show, by the words in them and by their names,
  all from the same words, and a picture's page has "More like this". SigLIP base (Apache-2.0,
  Google's, as Xenova's int8 ONNX conversion; 208 MB from `models-3`) takes CLIP's place from the
  scoping's shortlist: on the round-three scenes it found every scene from a plain description and
  98% from a paraphrase, where CLIP ViT-B/32 found 91% and 83%, at a third of CLIP's size; SigLIP 2,
  which reads other languages, waits (378 MB as int8). It reads each library picture from the scan's
  thumbnail (nothing decoded twice) into 768 numbers, on the processor, on two of its six cores
  (0.15 s a picture, 0.07 s on all six; on a GTX 16 card int8 is no quicker and its session would
  keep 1.1 GB of the card for good); a search is read the same way at once, lower case, no
  punctuation, padded with `</s>` to exactly 64 tokens (its text tower reads the last place;
  tokenizer.json, read with Hugging Face's `tokenizers`, doesn't canonicalise), and ranked by
  SigLIP's own score, the sigmoid of the vectors' product times its learned 117.3 less 12.93, cut at
  0.01, so a search for what isn't there finds nothing (ten searches for what isn't in the made-up
  library found nothing among its 1,997 pictures). The words: Best is PP-OCRv6 small (RapidOCR's
  ONNX conversion of PaddleOCR's detector and recogniser, Apache-2.0; 31 MB from `models-3`), the
  angle classifier off, through Mado's own NumPy port of RapidOCR's pre- and post-processing
  (`core/ocr.py`, its licence beside it and in the notices; no OpenCV; pyclipper, MIT with Clipper's
  BSL-1.0, grows the lines; shapely, whose wheels carry LGPL GEOS, isn't used), given blue, green
  and red as the models were trained: it looks first at the thumbnail (21 ms on the card) and reads
  in full only where it finds text (the detector on a 1280 square, each line cut out straight, 48 px
  high, on the card a line at a time at 320, 960 or 2560 across), on the card when DirectX says this
  process has room for its 910 MB and the queue's heaviest model beside it (`ai.HELD`), else the
  processor: 1.1% character errors and 99.5% of words on the 47 round-three text pictures, 0.33 s
  each on the card, 2.1 s on the processor, as RapidOCR's own pipeline read them. On the thumbnail,
  a "line" thicker than a quarter of its shorter side is a plain sky the detector took for text (it
  took most drawn skies for text there, in either order of colours), and a line of fewer than two
  letters or digits isn't kept. Fast is Windows' own reader (Windows.Media.Ocr through pywinrt's
  `winrt-*`, MIT), the picture read at twice its size, nothing downloaded: 93.6% of words in 0.17 s,
  only in Windows' OCR languages. As this PC suits, Best where the AI runs on a graphics card, Fast
  on the processor alone, Best where Windows has no OCR language; Settings › General › Search
  changes it, and the words are read again in the background. The detector's first look, on the
  thumbnail, halves the time on a library of photos: the made-up library's 1,997 pictures read in
  8.5 minutes looking first (196 read in full, 123 found with words) against 16.6 reading every one
  in full (124 with words); before a line as thick as a quarter of the thumbnail counted as a plain
  sky, it passed 1,798 of them on and the read took 20 minutes. Reading is a thread of its own, as
  duplicates are looked for: newest file first, again once a picture changes (by its size and time),
  never a picture from outside the library, in a quarantine, that won't open or is marked as
  damaged, a RAW waiting for its reader, nor one on a drive that isn't connected (whose readings
  stay: found, its tile saying "Away"); paused and going on (kept across restarts); saying how far
  it has got ("Read 2,340 of 18,200 so far: search covers those", in the Library's results, Home's
  Your library while it reads and Settings); taking turns at the card's one lock with the queue and
  edits, a run at a time, resting nine times its turn on the card while the queue makes a picture
  (twelve made-up photos made for a 4K monitor at Fast took 3.64 s each with reading paused and
  3.61 s while the library was read at Best on the card). A reader that can't run says so, with Try
  again, and rests till then or the next scan, the other reading on; a picture that can't be read
  now is counted apart and tried again after the next scan. The words are kept in the database
  (migration 10: `words_read`, and FTS5's `words` with the text as read and its terms, folded, each
  Chinese and Japanese letter apart; in backups, and in the export as `words.csv`), the vectors
  beside it in search.db, 16-bit, never backed up or exported (207 MB at 100,000 pictures, made
  again by reading when lost), loaded into memory as 32-bit when a search comes and let go after ten
  minutes without one (307 MB at 100,000 pictures, loaded in 0.85 s; a search then takes 19 ms, More
  like this 17 ms). The results, as no board draws them, are groups in the Library grid's pattern (a
  heading with its count over the tiles): With the words (every word starting a word read, capitals
  and the accents of Latin, Greek and Cyrillic letters folded away, a Chinese or Japanese word its
  letters in a row anywhere in a line, the matched words bold under the tile; the first 500 shown,
  with how many more), Looks like (the closest first), In the name (the list's order), each picture
  once, in the first group that holds it; the date-order button gives way while searching; a picture
  opened from them goes along them (its neighbours are the results'), Many at once takes them, and
  favourites are searched alike. The models come the first time the library is searched, with their
  size and progress, and till then names (and words, at Fast) still find. A search in another
  language (another writing, or another language's little words with no English one beside them)
  isn't described and says so in a line; a search in a writing the words reader can't read says so,
  with the way to Best, as does Windows with no OCR language at all. More like this is the nearest
  vectors (their product 0.6 at least, 60 at most), a picture not read yet read there and then (only
  one that reading reads). A fresh agent's review found eighteen things, all fixed test first: words
  folded and kept as the words index needs them (Greek's accents, Chinese and Japanese inside a
  line), a reader that can't run said with Try again while the other reads on, pictures that
  couldn't be read counted and tried again after the next scan, the progress counting pictures the
  scan hasn't read and not freezing between turns, More like this only for the library's pictures
  and the folder tree leaving it, vectors numbered under the write lock, texts fetched only for
  what's shown, see-through pictures read on white, Windows' reader falling back to a language it
  has, the models given blue, green and red; measuring then found search.db, busy for a moment,
  taken for damaged, fixed too. Measured on the owner's PC: the made-up library read in 8.5 minutes
  at Best on the card (0.26 s a picture), 12.9 at Fast; on the round-three scenes a description put
  its kind first every time and a paraphrase 98.3% of the time (all in the first ten), the cut
  letting in 13 scenes of other kinds over 900; searching 100,000 vectors takes 19 ms once they're
  loaded.
- The quick fixes, as built (2026-11-23, Claude's calls while the owner is away;
  docs/stack/fixes.md): a tab of their own, "Fix", after Size, Looks and Edit, rather than a place
  in one of them: Size is about what a picture is made for and Edit about parts picked, while the
  four fixes are about the whole picture's flaws, each with its own setting, its model to download
  and Mado's suggestion, and they want the Size tab's before-and-after stage at Fit as at 100% and
  400%; on their own tab each tab stays simple. No board drew it, so it's the Edit tab's patterns: a
  card of rows, each a fix with its switch, its one setting once on, and "Suggested" where Mado
  measured the need. Noise is SCUNet (strength blends its answer, 100% at first: it measured best at
  every level); blur is NAFNet in 384 px tiles overlapping by 32, always held by the guard (each
  pixel's change kept within its input's light range over 31 px, plus 2/255), never a whole picture,
  a tile it breaks down on (colours anywhere, 3 tiles in 100 of the made-up blurred scenes: flat
  tarmac beside a road's straight lines) left as it was, saying it mends a shaking camera or a
  moving subject and only sharpens a picture out of focus a little; JPEG blocks are SCUNet at Fast
  and FBCNN at Best ("as this PC has it" is Best once FBCNN is downloaded, else Fast, whose model
  also takes noise out, so a fix needs one download), the strength FBCNN's own quality setting,
  started at the JPEG's own quality from its tables (82% for one saved at 18; 60% when unknown), a
  screenshot starting on Best, which keeps letters crisp; a dark photo by classic means: the gain
  from its brightest 0.5% to just under white (1 to 16 times, never the average, so a night with
  lights stays a night), the extended Reinhard curve, then SCUNet as much as brightening brought
  noise out (all of it from two stops), CLAHE a slider after it (off at first: it lowers PSNR and
  SSIM against the truth); a picture under a stop dark isn't (a well-lit one with nothing white in
  it measures about 0.6), and the fix leaves it as it is. Brightened four times or more, an 8-bit
  file's own steps are smoothed first where it's flat to within a level or two, as the denoise keeps
  a clean step as an edge: no jump of more than a level came through either way (SCUNet smooths the
  steps too), and the debanding brought a smooth dark gradient 1.6 dB closer to the truth. The fixes
  are the recipe's step after the edits (`fix`, each null or its setting), made on the part the size
  keeps (its crop, or its canvas extended, LaMa's edges fixed with the rest, with 96 px of the
  picture round it, then cut back) before it grows, in this order: JPEG blocks at Best, brightening,
  noise (one SCUNet pass at the strongest strength any fix asks: noise, a dark photo's denoise, JPEG
  blocks at Fast), blur, local contrast; a fix at 0% does nothing. Nothing is cleaned twice: a
  picture the fixes cleaned (the noise fix or JPEG blocks above 0%, or a photo two stops dark or
  more, whose denoise ran in full; under that it takes out only what brightening brought) goes to
  Fast's weak-denoise twin, and the Size tab (and a batch's Size card) says "The Fix tab takes noise
  and blocks out first" where its switch was; Best cleans as it grows and finds little left. What
  the dark photo fix takes from the whole picture (the gain, the white, local contrast's tables) is
  measured once on a 1024 px copy of it as its edits leave it (see-through parts left out), and the
  plan is made for it (in a job, again once the picture is read), so a picture that isn't dark isn't
  brightened, named "Brightened" or left unclean, and a Save of only fixes that change nothing says
  so ("It isn't dark, so there was nothing to fix."), saving nothing. A part previewed at 100% is
  made with 96 px round it, as Save makes it, and a newer preview stops the one before at its next
  tile; all of a picture fitted (the stages, the Looks tab's small copies) shows only a dark photo's
  brightening and local contrast, with no model to download first, as noise, blur and blocks are too
  small to judge there and their models would take seconds to minutes over it, and the Fix stage
  says they show at 100%. Mado suggests only what it measures cheaply and reliably: JPEG blocks from
  a JPEG's tables (quality 60 or under) and a dark photo from its brightest 0.5% (1.5 stops or
  more); measured on made-up pictures, the quality was exact for all 152 JPEGs (tables moved by up
  to 10% too) and darkness right in all 74 cases (two to four stops under suggested, normal pictures
  and night scenes with lights not); noise and blur aren't suggested, as a texture reads as noise
  and sharpness can't tell shake from focus. Nothing measured to fix says so, and that noise and
  shake are for trying. The small things: each model downloaded the first time with its size and
  progress (offline, the fixes whose models are here work); the card busy with the queue ("Waiting
  for the graphics card: Phone wallpapers lets it go after the tile it's on", a preview a tile at a
  time); the card too full of the models used since Mado started (each fix model goes on it only
  while it has room, as the editing models; else the processor, and the tab says restarting Mado
  frees it); a huge picture fixed a tile at a time, saying the time first from 40 megapixels; grey
  pictures stay grey (made in colour, made grey again), see-through parts stay as they are, a
  phone's wide colours are kept with their profile (Display P3 has sRGB's curve), and a camera RAW
  is fixed as Mado develops it with its JPEG blocks off ("a camera RAW has no JPEG blocks"). A fix
  on a part is left out: the flaws lie over the whole picture and a part fixed alone leaves a seam
  where cleaned grain meets the rest's; the one local case, a moving subject, the guarded blur fix
  mends while the sharp rest changes by 0.17 levels on average (the ball 24.6 to 28.0 dB); and the
  stage drags to compare, where a click to pick would fight it. Fix is a batch's step after a
  cut-out and before the size (`{"step": "fix", ...}`), its card the tab's own rows, with no JPEG
  strength to set: each JPEG's blocks come out as hard as it was squeezed, read from its tables, and
  a picture that isn't a JPEG is left as it is (one strength for all smoothed camera JPEGs and PNGs
  alike); its words "Noise at 80%, JPEG blocks as each JPEG was saved, Best"; a recipe or watch
  folder runs it as any step, and a picture with nothing for it to fix is a line saying why. History
  has a `fix` column (migration 11), "took out noise and JPEG blocks, brightened it and mended the
  blur", beside the edits in brackets; a new picture is named "Cleaned" (noise or blocks),
  "Sharpened", "Brightened" or "Fixed" for more than one kind, after the edits and before the size
  ("Harbour at dusk (Brightened, TV 8K).jpg"); Save's header, jobs and See it first carry the words,
  and a job's stage "Fixing it", its share of the bar only in a job with fixes. The three models
  come from `models-1` (SCUNet 73 MB, FBCNN 288 MB) and `models-3` (NAFNet 69 MB), each in
  downloads.json with its licence files, in full precision (fp16 is slower on a GTX 16 card and
  fails on the processor at the highest optimisation), on the card in 384 tiles, sessions kept:
  SCUNet holds 1.3 GB of the card, FBCNN 1.3, NAFNet 0.4 (at 512 the same speed a megapixel, at 256
  SCUNet 0.8 GB less for 15% more time). Measured on the owner's PC through Mado's own code: a
  12-megapixel photo's noise in 23 s on the card and 8.3 min on the processor, JPEG blocks at Best
  16 s and 4.7 min, blur 7.2 s and 1.5 min, a dark photo 26 s on the card; a 1080p one in 1.2 to 5 s
  on the card, 16 to 80 s on the processor. Gains on made-up pictures (PSNR): noise σ 10, 25 and 50
  from 28.3, 20.6 and 15.2 dB to 40.7, 39.1 and 36.4; JPEG quality 10, 30 and 50 at Best from 30.2,
  34.8 and 36.4 to 33.8, 39.8 and 40.9 (Fast about half the gain); a straight shake 29.0 to 32.7, a
  moving subject 35.3 to 38.3, a slight blur out of focus 29.1 to 32.3, a hand's long shake not at
  all (26.3); darkened 4 and 16 times from 9.9 and 6.0 to 36.1 and 37.0. Found on the way: the Queue
  said a picture being cut out was at its save step, and Many at once called every model it waited
  for "Best for photos", offering Fast for it.
- Painting styles, as built (2026-11-24, Claude's calls while the owner is away;
  docs/stack/styles.md): a group of their own on the Looks tab, after the looks, as no board drew
  them: a small copy of the picture in each (None, Mado's painters, the classic means, the owner's
  own styles, a picture's style not kept yet) and "A picture of yours…" last; resting the pointer on
  one shows it on the picture, as the looks do. A style is a step of its own (`paint`, after the
  size and before the look), not one of the looks: a look grades the colours and a style repaints
  the picture, so a look can still warm or cool what's painted, the touches go on top of both, and
  picking one never clears the other. Of the six networks Mado trained (models-3, 6.9 MB each, MIT,
  the network's design PyTorch examples' under BSD-3-Clause), four earn their place, judged in Mado
  on made-up pictures at full strength, at 60% and in their own colours: After Van Gogh and After
  Hokusai, the strongest, each reading at once as its painting; After Monet, soft dabs, the least
  distinctive alone and the best painted photo in the picture's own colours; After Seurat, pale
  pastel dots, pretty in daylight. Klimt's Birch Forest is left out (everything becomes the same
  rust-and-moss tapestry, skies and seas leaf litter, and neither strength nor the picture's colours
  rescue it), and so is Turner's Fighting Temeraire (a warm amber haze over canvas grain, which the
  looks already do, with grain). Strength mixes the painting with the picture as it was, 100% at
  first; "Keep the picture's colours", offered for the networks (a classic means' colours are its
  own), takes the painting's lightness with the picture's own colour and reads well, above all
  where a painting's palette fights a picture (Van Gogh's has no red; Monet's skies go olive,
  Seurat's nights pale). A style is painted whole, never in tiles, at a working size: a 1392 square
  canvas (1600 × 1200's pixels, a multiple of 4), the picture's long side 1392 and the rest
  mirrored out, so one size compiles once and the strokes are the same size against any picture,
  on the stage and in the picture saved (the small copies, thumbnails where no stroke shows, are
  painted on the processor on a 464 canvas, 0.4 s each, so going through the styles never takes
  the card's memory for a style not chosen); then it's made the picture's size, or
  the Size tab's, by plain Lanczos, chosen on 100% crops (docs/stack/styles/) over the upscaler,
  which drew streaks and cracks into the dabs and smeared Seurat's dots in 23 s on the processor,
  and over the picture's fine detail put back, which looked the same or printed the photo through
  the paint; made more than five times bigger than it's painted, a picture says its strokes go soft
  and that a smaller size keeps them crisp. The four painters share one session, as each session
  keeps 2.2 GB of the card for good: made from the first painter's file with its 62 weights taken
  out of the graph as inputs (Mado's own reader and writer of the file, `core/onnx_graph.py`, no
  `onnx` package), each painter's own passed in; weights left in the graph as overridable defaults
  gave wrong pictures, DirectML's fused node baking in the first painter's. A picture as the style
  is MicroAST (MIT, 2 MB from models-3), taken from this picture, one picked from the library, or
  one dropped or pasted while its card is open, and kept from picture to picture as the style
  chosen is: its first half reads a copy 512 pixels long on the processor into 512 numbers (44 ms),
  kept in the recipe as base64 (2 KB); its second paints at the same canvas with its own strength
  at full, Mado mixing after; a picture under 96 pixels across, or nearly one colour with nearly no
  texture, says why it can't give a style, and the card says plainly the style comes from a
  picture's colours and textures, never what it shows. "Keep as a style" keeps its numbers and a
  copy 160 pixels at most to know it by, never the picture (migration 12, the `styles` table; in the
  export as `styles.json` and `styles/`), names unique and never Mado's, a number never given
  again, so a recipe naming one deleted fails rather than painting with another, and none deleted
  while a recipe or the queue needs it. Pencil sketch (a colour dodge; its setting the darkness),
  coloured pencil (a pale wash under the lines), oil paint (a soft Kuwahara worked out where its
  squares are 6 px, brush strokes in relief; the brush) and cartoon (after Winnemöller: Kuwahara
  smoothing, soft tone steps, colour kept and a little fuller, a difference of Gaussians inked; the
  colours) are NumPy and Pillow only, every reach a hundredth of the picture made's short side:
  2 to 15 ms a small copy, 0.07 to 0.40 s the stage's preview (oil's finest brush 0.84 s), 0.4 to
  1.4 s at 12 MP. On the card when this process has room for what each keeps (2.3 GB the painters,
  1.25 GB MicroAST, 512 MB spare), else the processor with denormals as nought; one lock, sessions
  kept, the canvas pinned, full precision (fp16 is slower on GTX 16 cards). Measured on the owner's
  PC through Mado's own code: a painter at the working size 0.34 s on the card and 2.5 s on the
  processor; the whole painting step of a 12 MP Save 0.63 s and 2.9 s, of 8K 1.1 s and 3.3 s;
  MicroAST 0.22 s and 1.6 s; the painters' session holds 2.2 GB of the card, MicroAST's 1.2 GB. The
  small things: each model downloaded the first time with its size and progress (its tile tagged
  with the size, a card under the styles, the stage saying the style shows once it's here, Save
  waiting; offline, the classic means work); the card busy with the queue ("Waiting for the
  graphics card: Holiday prints lets it go after the tile it's on"); a huge picture (the soft
  strokes said); a style picture too small or too plain (a sentence why); a grey picture (painted
  in the style's colours, which the tab says, unless its own are kept, then grey again); see-through
  parts kept (what they hide carried in from what shows first, so no dark fringe is painted); a
  look, a style and touches at once (the stage says "After Monet · 80% · Warm film · 60% · grain");
  and a style on a part (the Looks tab's "Only on a part" goes for its style as for its look, the
  rest as it was). A batch's step (`{"step": "paint", ...}`, after the size, before the look), its
  card the tab's choices (Mado's and the owner's styles as pills, strength, each picture's own
  colours, a classic one's setting); a picture's own style goes on a batch once it's kept. Save and
  History say it with the look ("with After Hokusai at 80% and Warm film at 60%"), a new picture is
  named after it ("Harbour at dusk (TV 8K, After Hokusai, Warm film).jpg"), and a job's stage is
  "Painting it". A fresh agent's review found eighteen things, the real ones fixed test first: the
  Queue called a picture being painted "Save"; small copies of a see-through picture lost their
  see-through parts; a long panorama was refused as too small to give a style; the small copies
  took the card's memory (2.2 GB, and 1.2 GB more with a kept style) before any style was
  chosen; every visit to the Looks tab measured the whole picture for the grey hint, now asked
  only with a style chosen; a batch's estimate asked DirectX for room once a picture; a picture's
  style was read from what its see-through parts hide; a name past 200 letters broke its style;
  damaged numbers were said as a style gone; "on a part" came after the colours; a job of only a
  style at 0% said "no look"; See it first's guess didn't know where a style paints, and the
  processor's times were the trainer's; unused plumbing went; and the words say "AI model", not
  "network". Found on the way: a picture read as the style kept the first one's name in "Keep as
  a style". Left as they are: oil paint at 100% lays its strokes from the part's own corner (the
  same look, not the same pixels as the picture saved), and the Recipes card shows a style's id
  till the engine's words come, as it does a look's.
- Depth, as built (2026-11-24, Claude's calls while the owner is away; docs/stack/depth.md): a tab
  of its own, "Depth", after Fix, rather than touches in Looks: its tools need the depth model and
  the card, portrait blur takes a click on the picture and tilt-shift a band dragged on it where
  the Looks stage's clicks pick a part, and the Looks tab's small copies would each need the depth
  read. No board drew it, so it's the Fix tab's patterns, "Blur and fog" and "3D photo" above.
  Depth Anything V2 Small (Apache-2.0; its bigger sizes are non-commercial) reads the whole picture
  squeezed to one 518 square: as good as keeping its shape on made-up scenes whose depth is known
  (rank correlation 0.994 to 0.996), twice as quick, one session for every shape. Its numbers are
  made 0 (the farthest) to 1 (the nearest) by the picture's own 2nd and 98th percentiles and kept in
  `cache/depth` by the picture's version and edits; a flat picture (little spread for its size and
  no jumps: a scan, a screenshot; pixel art too) is said, the tools still working. Portrait blur is
  in focus at the subject (u2netp at Fast, BiRefNet lite at Best, as Cut out finds it, made firm
  from 30% to 70% so a crisp edge stays crisp, a part of it not as near as the subject, a sun, left
  out) or where clicked; the blur grows with the nearness's distance from the focus's, as a lens's
  circle grows with the difference of inverse distances, to 3% of the shorter side at f/1.4 (f/1.4
  to f/16, f/2.8 first), made in up to twelve layers on a 1024 copy, one exactly at the focus, what's
  behind a nearer layer carried in from its own colours, small bright places boosted to bloom into
  discs, then joined at full size a band at a time. Edit's "Blur what's behind it" stays apart (an
  even blur behind a part, no model, for a flat backdrop or a drawing), and the tab says how they
  differ. Fog keeps exp(-3.2 x density x far²) of each point, the rest the picture's own haze (its
  farthest twentieth made paler) or Mist, Warm or Cool. Tilt-shift goes by place, not depth: by depth
  the band is a focus distance, portrait blur's job, and by place read as a miniature on made-up
  rows of houses and the field; blur to 2% of the shorter side at the farther of its top and foot,
  colours 12% richer, so it works without the model. The three are the recipe's `depth` step after
  the size and before a painting style and the look (a lens and the air come before a painter paints
  what they saw), made at the size made; a new picture is named "(Portrait blur)", "(Fog)",
  "(Tilt-shift)" or "(Depth)"; History has a `depth` column (migration 13), "portrait blur
  at f/2.8, fog and tilt-shift"; a batch's Depth step has each picture in focus at its own subject
  and the band at the same fractions. 3D photos push in, sway or circle for 3, 5 or 8 s at 30 frames
  a second, looping: the subject stays put, nearer things move one way and farther ones the other
  (3.5% of the shorter side at full amount), the whole a little bigger; each frame is found backwards
  on a 3-pixel grid, and where the view stretches the picture or a point never settles, a layer
  behind shows, filled three times the view's reach into near things from what's farther (Fast
  stretches it in; Best draws over that with LaMa, a 384 square at a time). In what the view
  uncovered on a made-up scene whose truth is known, Fast scored 21.9 and 20.9 dB, Best 20.7 and
  21.2, the picture only stretched 16.5 and 17.9 (filled only as far as the view reached, Best came
  out purple, 15.3). The video is H.264 in MP4 through Mado's ffmpeg, Windows' own encoder
  (`h264_mf`) first, then NVENC, AMF and Quick Sync, never OpenH264 (its patent licence covers only
  Cisco's builds); 1080p, or 4K when the picture has the pixels; an animated WebP where no encoder
  works. It's made into `cache/motion`, played on the stage and saved only when asked, beside the
  picture or into a folder ("(3D photo).mp4"), History's line "into a 3D photo, swaying for 5 s". A
  batch doesn't make them: its saving, See it first and History work on pictures, and each wants
  looking at. Measured on the owner's PC at 12 MP: depth read in 0.14 s on the card (0.4 GB held)
  and 0.52 s on the processor; portrait blur 4.0 s at f/2.8 and 4.6 at f/1.4, fog 2.0, tilt-shift
  3.9, all three 7.3; a 5-second 3D photo at 1080p in 54 s (1.9 MB) at Fast and 61 s at Best (LaMa
  holding 1.0 GB more), at 4K in 3.7 minutes (23 MB), as an animated WebP 1280 across in 42 s (1.5
  MB). Found on the way: a cut-out mask's soft fringe blurred the subject's own edge and haloed it,
  and the layer behind took the near thing's colours. A fresh agent's review found the depth step
  making a batch's edits again on the picture already edited, the window's security policy
  refusing to play the video (no `media-src`), tilt-shift's band taken as fractions of a crop,
  ffmpeg's end (Windows' `EINVAL`, its words never read, a stopped one left running), 3D photos
  in a wide-colour picture's colours with no tags, a 3D photo let go by looking at another tab,
  and the focus and band with no keyboard handle; all mended, each with its test.
- Restoring old photos, as built (2026-11-24, Claude's calls while the owner is away;
  docs/stack/restoring.md): at the top of the Fix tab, "Restore an old photo", not a tab of its own:
  scratches, colour and fading are the whole picture's flaws, as the fixes are, the brief's chain
  runs on into the fixes' noise and JPEG blocks, they want the same before-and-after stage at Fit,
  100% and 400%, and a sixth tab would crowd the column. Two rows in the fixes' patterns: "Scratches
  and dust" and "Colour" ("Colour it" or "Bring its colours back", a strength). Scratches are found
  by Microsoft's old-photo detector (MIT, half precision, 75 MB, `models-3`) as report-3 note 6
  says: grey at short sides 256 and 512 on fixed canvases of 256 x 512 and 512 x 1024 (a portrait
  turned onto them), 40% sure and up, united and grown round by 3 px at a mask 768 short, kept in
  `cache/edits` by the picture's version and edits; the mask is shown on the stage in the accent
  before anything is filled, the owner painting over what it missed and holding Alt to take away
  what isn't a scratch (Edit's brush, 1% of the shorter side at first), then "Fill them in"; leaving
  the tab counts as checked. On eight made-up 12 MP aged prints it found 100% of the light
  scratches, 88% of the dark ones' pixels (one dark scratch in a dark forest missed whole) and 91%
  of the dust; 60% of its mask lay within 3 px of real damage, and on the same prints undamaged it
  marked 1.1% (a road's dashed line, rigging, stems). Dust comes with it: a classic speck finder
  found 96% at 98% precision on the prints but marked up to 2.8% of made-up night cities, pages of
  words and fireworks (a print's dust is 0.1 to 0.2%), so there's no second finder. LaMa fills on a
  copy 768 short (as good inside the damage as at 1536 or full size, 26.3 dB against 7.5 scratched,
  and 2.6 and 6.7 times as quick), its 512 squares stepping 448, each hole pixel filled by the square
  whose middle is nearest, laid back at full size through the smoothed mask with the print's grain;
  a mask over half the picture isn't filled (Save waits), from a quarter the tab says it's a lot to
  invent. Colour is DDColor tiny (Apache-2.0, 270 MB, `models-1`) on the picture squeezed to 512 as
  its lightness, its a and b made the size of what's shown and put onto that part's own lightness
  (OpenCV's Lab), so detail stays the original's; the strength mixes with the picture's own colour
  (a sepia print's brown), a grey picture's profile goes once it's coloured, and the tab says a
  coat's colour is a guess. Faded colours come back by classic means: each channel's 0.5th and
  99.5th percentiles on a 1024 copy, taken 75% of the way from the three's together toward each
  channel's own (on 60 faded made-up pictures ΔE 23.4 to 19.5 with the cast gone; all the way
  overshoots, 20.4), mixed at its strength. Which picture needs which, from a 256 copy with its
  colours smoothed 5 x 5: black and white under 2.3 of chroma at its 99th percentile, a toned print
  under 1.3 of colour its light doesn't explain (sepia by its hue), else colour; on 1,440 made-up
  pictures grey was right 180 of 180, toned 684 of 720 and colour 499 of 540, and a wrong call only
  starts the row the other way. Colouring is suggested for grey and toned pictures, fading never (a
  photo's own saturation and cast can't be told from age's). Restoring is the recipe's `restore`
  step after the edits and before the fixes, on the picture at its own size (a scratch is a few
  pixels: a crop or new size would move it off its mask): scratches first, so DDColor never sees
  one. The picture filled, DDColor's colours and the levels are worked out once and kept, so the
  stages, the Looks tab's and the styles' small copies and a part at 100% lay colour on what's shown.
  The strokes are tied to the picture's version: a picture changed since lets them go, finds the
  scratches again and shows the mask, saying why; Mado's own Save in its place lets restoring go
  quietly, as edits do. A new picture is named "Coloured" (colour alone) or "Restored", and History
  has a `restore` column (migration 14), "filled its scratches and dust and coloured it", in the
  brackets after the edits. A batch's Restore step (and a recipe's, a watch folder's) colours each
  black-and-white or toned picture and brings back each colour photo's faded colours, each as it
  needs, both on at first; it never fills scratches, as the mask is each picture's own and filling
  what's found unseen would paint over a road's lines on one picture and leave dark scratches on
  another, so the step's card says scratches are filled on each picture's page, and a recipe with
  them is refused with that sentence. Faces are left as they are: GFPGAN leans on parts for
  non-commercial use and CodeFormer's licence is non-commercial, and the README says so. The small
  things: each model downloaded the first time with its size and progress (faded colours need none,
  so they work offline); the card busy with the queue, said while finding waits; a scan past 100
  megapixels made smaller first on the Size tab; nothing found, said, the brush still filling what's
  painted; a picture in colour asked to be coloured, its own colours said to give way; a sepia
  print, its brown mixed in and no faded colours to bring back; see-through parts kept. Each model
  keeps its session on the card while it has room (`ai.HELD`: the detector 2.7 GB, DDColor 2.4, both
  measured in their own processes; all three with LaMa kept 3.3 GB in one), else the processor; the
  detector's half-precision file loads a level under the highest optimisation there. Measured on the
  owner's PC at 12 MP: finding 0.58 s on the card and 8.8 on the processor, filling (LaMa, a mask
  over 5%) 2.9 and 14.7, DDColor 0.48 and 1.4, its colour laid on the whole picture 4.1 s, faded
  colours 1.2 s; all of it, filled and coloured, 10.5 s on the card and 28 on the processor. Save
  waits on every tab till the mask has been checked, a mask covering nothing fills nothing (the
  plan, Save and History go on without the scratches), and a part at 100% has colour laid only
  round it. Found on the way: Save's header didn't name restoring. A fresh agent's review found
  colour alone tied to the picture's version (a Save failing with words about scratches, a picture
  saved in its place coloured again), what was worked out for a picture unfilled used for it
  filled, a job's edits made twice when it restored, the plan saying restoring ran on the
  processor when only a model it didn't use would, a speck's mask rounded to nothing, Save
  working while the mask was still being checked, a part at 100% laying colour on the whole
  picture, the small copies taking strokes painted before a change, no limit on strokes in the
  window, and DDColor fetched for a colour at 0%; all mended, each with its test.
- HDR photos and saving as it is, as built (2026-11-24, Claude's calls while the owner is away;
  docs/stack/hdr.md): the gain maps phones write now are read: Ultra HDR JPEGs (Android's: Adobe's
  `hdrgm` XMP and, from Android 15, ISO 21496-1's numbers too), JPEGs with ISO's alone, HEICs with
  Apple's auxiliary gain map (its headroom in its XMP or the MakerNote) or ISO's `tmap` item, and
  AVIFs with a `tmap` item. Whether a picture carries one is read from its headers as the scan reads
  it (a JPEG's first 64 KB and its gain map's first segments, a HEIF's `meta` box) and kept as
  `pictures.hdr` (migration 15: none, one Mado reads, one it can't; pictures read before it are
  looked at once by the next scan, by their headers alone). "HDR" shows on the tile and in the
  page's facts as "RAW" does, the facts' tooltip saying how far it goes. A gain map of a version
  Mado doesn't know (hdrgm's other than 1.0, ISO's other than 0) or with numbers that make no sense
  leaves the picture as it is, without its HDR, said under its name. The gain map is decoded only
  when the picture is made or its view is: as gains in stops, turned as the picture's EXIF (or a
  HEIC's `irot` and `imir`) turns it, kept at its share of the picture (a quarter stays a quarter, a
  full-size one full), 4096 pixels on its longer side at most (a huge photo's is smooth); a HEIF's
  item written out alone as a HEIF of its own, an AVIF's decoded by Pillow in memory, a HEIC's
  (HEVC) by ffmpeg from a file in `cache/hdr`, deleted straight after. A base that's the HDR
  rendition makes its ordinary rendition by dividing by its gains, as ISO and libavif have it. The
  page is in HDR where Windows has HDR on, simply: an HDR photo's view (and a HEIC's full size) is
  an Ultra HDR JPEG, which WebView2's Chromium draws in HDR on an HDR screen and as its ordinary
  picture elsewhere; at 100% a JPEG or an AVIF is itself; thumbnails and what the tabs show while a
  tool is chosen stay ordinary, and Mado never touches Windows' HDR. Through every tool
  (`core/gains.py`, each tested on made-up HDR photos), the AI models working on the picture alone:
  the size crops it, extends it (the edge's gain carried on) and resizes it plainly, as it's smooth;
  an erase fills it from round the part (the wall's gain, not the lamp's), a cut-out on a colour has
  none behind it (a flat colour is the same on any screen), a blurred backdrop or Blur what's behind
  it blurs it the same way, and a cut-out on nothing saves as PNG or WebP, which can't hold one; a
  look grades the ordinary picture and keeps the gain map, so the HDR rendition is the graded
  picture brightened where it was, a colour gain map made one channel first so its colours don't
  bring back what the look took out (a black and white look stays black and white); a painter's or a
  picture's style, oil paint and cartoon keep it (a lamp painted still glows), while a pencil
  sketch, paper and lines, fades it with its strength, none left at 100% on the whole picture; the
  fixes keep it as it is (brightening's curve keeps the highlights below white, and the gain map
  opens them up again); restoring fills it where scratches and dust were filled, as an erase does (a
  white scratch on a photographed print would glow on again), and keeps it, one channel, as a look
  does, when a picture's colour is brought in or back; portrait blur, fog and tilt-shift make it
  again from both renditions given the same tool in linear light at the gain map's size, so fog
  thins the gain with distance and a lamp blurred into a disc glows as a disc; a 3D photo is an
  ordinary video (sRGB, HD colour tags) and the Depth tab says an HDR photo's extra brightness isn't
  kept in it, as the wallpaper studio says of Windows' wallpaper, which is an ordinary picture, the
  studio otherwise as it was; a batch, a recipe and a watch folder keep it the same, their Saving
  with "An HDR photo's HDR (its gain map)"; duplicates and bursts compare the ordinary picture, as
  before. A gain map left flat isn't written. Saved, it's written in JPEG as Android writes Ultra
  HDR, so phones, browsers and Windows read it whichever way they look (the picture with hdrgm's XMP
  and directory, ISO's version and an MPF; then the gain map at quality 90 with its own XMP and ISO
  numbers), and in AVIF by Mado's own boxes round the AV1 items of two AVIFs Pillow encodes (a
  hidden gain map item, a `tmap` item with ISO's numbers, `altr`, the `tmap` brand), as Pillow can't
  write one; its least and most gains made afresh, gamma 1, the headroom and offsets as the photo
  had them. PNG and WebP can't hold one, and the save dialog says so before Save under "Its HDR (the
  gain map)", a new line of "Keep from the original", on by default. Checked with second readers:
  Pillow's MPO reader sees two pictures, the MPF's offsets right; libavif reads the AVIF and refuses
  a `tmap` cut short, so the tests read every AVIF they write; and Chromium, in the shooting
  script's Edge, drew XMP and ISO, XMP alone, ISO alone and the AVIF alike, an HDR base's half at
  192 where 191.6 was worked out (which found that an HDR base divides). Saving as it is: Save is
  there with nothing chosen, quiet till a tool asks for something, and the Size tab says "Save keeps
  it as it is, in the format you pick", rather than an "As it is" size: one more choice among sizes
  that all make something would muddle the Size tab, and Save is already where saving happens. A
  recipe with no step at all is saved as it is (steps that change nothing are still said as changing
  nothing): at its own size, in the format and quality chosen (a JPEG starting at the quality it was
  saved at), keeping what's ticked; a RAW developed at full size, an HDR photo with its gain map, a
  HEIC as a JPEG (no HEVC encoder Mado may ship). It's always a new picture: the dialog doesn't
  offer Replace and says why, the API refuses it (409), and a batch that's just Save turns Replace
  to a new picture and says so. In the format it's already in, it's a fresh copy ("(2)"), said in
  the dialog, rather than refused: a copy without its location, or at another quality, is a reason
  to save one. A RAW waiting for Mado's RAW reader says it can be saved as it is once the reader is
  here, and a batch leaves it out till then. A batch, a recipe or a watch folder can be just Save,
  changing many pictures' format at once (See it first says there's nothing to see first: each copy
  is the picture itself); History says "Saved Harbour as JPEG", a batch "Saved 240 pictures as
  JPEG". Measured on the owner's PC: a picture's facts read in 0.7 ms with a gain map and 0.4
  without, so a scan of 1,000 made-up JPEGs took the same either way (55.3 and 52.1 s without, 57.7
  and 52.0 with), its time the thumbnails'; the gain map decoded in 7 ms at 12 MP and 23 at 48; its
  extra time through the tools at 12 MP (48 MP) 9 to 23 ms for a size (18 to 33), 21 to 81 ms for an
  edit (81 to 322), 3 ms for a look or a pencil sketch (9), none for the fixes, and for the depth
  tools, each worked out twice, 0.53 s for fog, 2.0 s for portrait blur and 3.0 s for tilt-shift
  (0.71, 2.3 and 3.2); writing it 12 ms more as JPEG (44) and 63 as AVIF. Saved as it is: a 12 MP
  JPEG in 0.37 to 0.44 s, an HDR one with its gain map in 0.45 to 0.48, a 24 MP RAW developed in 3.8
  to 3.9 s, and a batch of 1,000 PNGs (1600 × 1200) as JPEG in 145 s. Every gain map was tested only
  through files made by code (Ultra HDR JPEGs of each kind, AVIFs with `tmap`, HEICs built box by
  box round AV1 items with Apple's or ISO's gain map; a HEVC gain map only through ffmpeg's
  stand-in, as no HEVC encoder may make one). Found on the way: Chromium's drawing showed that an
  HDR base's ordinary rendition divides by its gains (Mado had multiplied); the Fix tab took the
  picture's as-it-is plan for its own and the Size tab could show it for a moment; the Edit and Size
  tabs said to erase or pick a size first beside a Save that saves the picture as it is (the
  README's Edit picture taken again); and Pillow opens an Ultra HDR JPEG as a plain JPEG (it sees
  hdrgm's XMP), so the tests call its MPO reader by hand. A fresh agent's review found a gain map's
  decoder raising what wasn't caught (Pillow's AVIF reader a RuntimeError, a frame header claiming
  billions of pixels), so a damaged one stopped the view and Save; every picture's page decoding it
  whole for its as-is plan, now made at a glance from its thumbnail and the size the library read;
  See it first's three kept after the HDR choice changed; a HEIC's HEVC gain map taken whatever
  shape ffmpeg gave; "Always save this way" keeping "new" from a save that could be nothing else (as
  it is, or a camera RAW); Home's card for a batch that was just Save reading "Made , as new
  pictures"; a just-Save recipe's card speaking of replacing; the page's tag lagging a picture that
  lost its gain map; the view trying a broken gain map on every request; the scan's catch-up reading
  pictures from outside the library, a commit each; the Depth tab's big-picture note reading the
  as-is plan; a gain map with no numbers said as not there, and the XMP directory not tried where
  the MPF was wrong; the AVIF claiming AV1's baseline profile; `cache/hdr` not emptied at start; and
  dead code: all mended, each with its test. Left as it is: the facts' tooltip shows on hover only,
  as Mado's other titles (paths, folders) do.
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
  downloaded on first run, see docs/stack/ffmpeg.md; LibRaw, the first time a camera RAW is read,
  see docs/stack/libraw.md; and the AI models fetched when asked; each with its licence files),
  `cache\` (each picture's thumbnail and screen-sized view, made again when gone; the depth Mado
  read of a picture, kept by its version as the edits' masks are; 3D photos made and not saved,
  cleared as the engine starts; a HEIC's gain map on its way to ffmpeg, for a moment, in
  `cache\hdr`), and `pasted\`
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
  inside the installer (WebView2 on a PC without it, ffmpeg, LibRaw, the bigger AI models, from
  Mado's own prereleases `models-1`, `models-2` and `models-3`) goes in one manifest,
  `engine/src/mado/downloads.json`: what it's for, version, size, licence, source and checksum.
  The installer's first page lists it (`scripts/installer-notes.mjs`), Setup downloads ffmpeg,
  the rest come the first time they're needed (`engine/src/mado/tools.py`), and Mado downloads
  nothing that isn't on it.
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
   pictures from anywhere (a picture from outside the library on a page of its own, paste,
   File Explorer's "Open in Mado" and Open with, the command line), camera RAW (read by
   LibRaw, downloaded the first time a RAW is read; every tool on it; RAWs among duplicates and
   bursts), and HDR photos with saving as it is (gain maps read, shown in HDR, kept through every
   tool and written again in JPEG and AVIF; Save with nothing made, a batch or a recipe just
   Save).
3. 1.1: search by describing a picture and by the words in it, the wallpaper studio (the owner's
   monitors, pixel-exact, changed daily from favourites if wanted), and painting styles. Built:
   the wallpaper studio, with favourites, search (by describing a picture, by the words in it,
   and More like this), and painting styles (four painters, any picture as the style, pencil, oil
   paint and cartoon by classic means, a step for batches and recipes): done.
4. 1.2: restoring old photos (scratches, faces, colour) and the quick fixes (noise, blur, JPEG
   blocks, dark photos), portrait blur and 3D photos. Built: the quick fixes (the Fix tab, a step
   for batches and recipes), portrait blur and 3D photos (the Depth tab, with fog and tilt-shift, a
   step for batches and recipes), and restoring old photos (scratches and dust shown as a mask and
   filled, colour, faded colours, at the top of the Fix tab; faces left as they are, as no face
   model may ship).
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
