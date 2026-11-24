# Architecture

Mado is three programs that work as one: a thin **shell** that owns the window, a **UI** inside it,
and an **engine** that does the real work. Everything runs on this PC; the only network traffic is
fetching what the installer lists (ffmpeg; LibRaw the first time a camera RAW is read; the bigger
AI models when first asked for, search's the first time the library is searched) and checking for
updates.

```mermaid
flowchart LR
    subgraph shell["mado.exe · Tauri shell (Rust)"]
        ui["UI · React in WebView2"]
    end
    engine["mado-engine.exe · Python<br/>local API and CLI"]
    data[("%LOCALAPPDATA%\Mado<br/>mado.db · backups · logs · tools")]
    pictures[["Picture folders"]]
    releases[("GitHub releases")]

    shell -- "starts with a token, stops on exit" --> engine
    ui -- "HTTP on 127.0.0.1 + token" --> engine
    engine --> data
    engine -. "reads and watches; saves what the owner makes" .-> pictures
    shell -- "latest.json, signed installer" --> releases
```

| Part | Where | Does |
| --- | --- | --- |
| Shell | `app/src-tauri` | The window and its title bar, one instance at a time, the engine's lifetime, updates, the tray; the paths Windows hands Mado, the files copied in File Explorer, and File Explorer's "Open in Mado" |
| UI | `app/src` | Every screen. Reads and changes things only through the engine's API |
| Engine | `engine/src/mado` | The library (its folders, the scan, the watcher, the copies the window shows, duplicates and bursts, favourites, search: the library read for what each picture shows and the words in it), editing pictures by clicking, fixing them (noise, blur, JPEG blocks, dark photos), making them right for a screen (the AI models on the graphics card), giving them depth (portrait blur, fog, tilt-shift) and a look, and saving them, 3D photos (a video of a picture moving by its depth), many at once in the queue with recipes and watch folders, the wallpaper studio (the monitors and Windows' wallpaper, every day if wanted), History and the quarantine, this PC's check, Setup's downloads, settings, backups, the export, the database |

The shell stays small on purpose: logic that isn't about the window or the process belongs in the
engine, where it is easy to test.

## Start, run, stop

1. The shell starts `mado serve --watch-stdin` with a fresh random token in `MADO_TOKEN`
   (in development: `uv run mado …` from `engine/`; installed: the bundled `mado-engine.exe`).
2. The engine listens on `127.0.0.1` on a free port and prints one line:
   `{"event": "ready", "port": 51234}`.
3. The shell sends the UI an `engine-status` event with the address and token.
4. The UI calls the API with `Authorization: Bearer <token>`.
5. On exit the shell closes the engine's stdin and the engine shuts down (the shell ends it after
   3 seconds if it hasn't). If Mado crashes, Windows closes the pipe anyway, so the engine never
   outlives the window. The engine puts itself in a Windows job that ends every program it starts
   (ffmpeg) when it ends, however it ends.
6. With "Start with Windows" on (Settings › General), Windows starts Mado at sign-in in the tray.
   With "Keep Mado running when you close the window" on (beside it), closing the window keeps
   Mado there, so its work and the nightly backup carry on; Quit Mado in the tray's menu ends it.
   Off, closing the window quits Mado. After the ready line the engine may print
   `{"event": "notify", "title": …, "body": …, "link": …}` lines, which the shell shows as Windows
   notifications while the window is away, and passes to the window while it's open (the `notice`
   event), where they show as a note at its foot.

If the engine is silent for a minute before its ready line, exits first, or stops on its own later,
the status becomes `failed` with the engine's last error lines, and the UI says so with "Try again"
and "Copy details". While the window is away (Mado waiting in the tray), a Windows notification
says so once, and the shell tries again by itself after 30 seconds, a minute, 5 minutes, then every
15. Both sides of this handshake are tested: `engine/tests/test_cli.py` and
`app/src-tauri/src/engine.rs`.

## The library

The owner adds folders; the engine reads every picture in them and keeps watching. Nothing in
the folders changes: the library only looks.

```mermaid
flowchart LR
    folders[["Library folders"]] -- "walk (finding)" --> records[("pictures table")]
    records -- "read each new or changed one (reading)" --> pillow["Pillow; ffmpeg for HEIC; LibRaw for camera RAW"]
    pillow -- "facts" --> records
    pillow -- "thumbnails" --> cache[("data folder's cache")]
    watcher["watchdog"] -. "a picture came, changed or went" .-> scan["the next scan"]
```

| Part | File | Does |
| --- | --- | --- |
| Folders | `mado/library.py` | Adding a folder (one inside a library folder is refused; one holding library folders takes them in), taking one out, and walking one to record every picture with its size, time and place |
| Reading | `mado/pictures.py` | A picture's facts (format, size as shown, when it was taken, camera, orientation, a location) from its header and EXIF, and its pixels, turned upright (see [stack/pillow.md](stack/pillow.md)) |
| Camera RAW | `mado/libraw.py`, `mado/core/raw.py`, `mado/core/icc.py` | LibRaw's DLL through ctypes, downloaded the first time a RAW is read: a RAW's facts without developing it, the preview its camera kept for a small copy, anything bigger developed with the camera's white balance into Display P3, cropped and turned as the RAW says; till the reader is there, a RAW is listed as it is and read once it comes (see [stack/libraw.md](stack/libraw.md)) |
| The scan | `mado/scan.py` | One at a time, on its own thread: finding (walking every folder: new, changed and gone pictures), then reading what's new or changed, newest file first, making each thumbnail on the way. Everything is saved as it goes, so a scan Mado's closing stops loses nothing |
| The watcher | `mado/watch.py` | A scan as Mado starts, and one a few seconds after a picture comes, changes or goes (see [stack/watchdog.md](stack/watchdog.md)) |
| Copies | `mado/previews.py` | A thumbnail (512 px), a view the size of a screen (2560 px) and a full-size copy for a format the window can't show, made once and kept in the cache |
| Rules | `mado/core/` | What a file is by its name, how folders sit together, EXIF's values in Mado's words, a HEIF's layout: pure functions |

A picture's copies come to the window through the API like everything else, with the token: the
UI fetches each and shows it as an object URL (`usePictureImage` in `app/src/lib/engine.tsx`),
thumbnails only as they come near the view, so the grid holds many thousands.

## Looking after the library

Duplicates and bursts are found in the background, from the thumbnails the scan made, and
reviewed on a page of their own; Home's Needs you also lists the pictures that won't open, and
its Space card the room on the drives the library uses. docs/stack/duplicates.md has the
fingerprints, the thresholds and what was measured.

```mermaid
flowchart LR
    scan["a scan ends"] -- wakes --> finder["the finder (mado/duplicates.py)"]
    finder -- "fingerprints from each thumbnail; digests; sharpness" --> prints[("prints")]
    prints --> groups["groups (mado/core/duplicates.py)"]
    groups -- "/duplicates" --> review["the review"]
    review -- "/duplicates/aside" --> aside["each picture checked, then into its drive's quarantine"]
    aside --> history[("History: a line each, one line a review")]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/likeness.py`, `mado/core/duplicates.py` | Pure: fingerprints, sharpness, close fingerprints in buckets; the groups, what's never grouped, which to keep |
| The finder | `mado/duplicates.py` | Looking at each picture once it's read and again once it changes, on a thread of its own; the groups kept in memory; the owner's choices and "not the same"; setting the rest aside, each picture checked first |
| Won't open | `mado/api/library.py`, `mado/api/pictures.py` | The pictures that won't open, but those marked as damaged; marking one (`pictures.damaged`, cleared once its file changes) |
| Space | `mado/api/library.py` | Each drive the library's folders are on: free, the pictures, quarantine, what the queue wants there |
| In use | `mado/jobs.py` | A picture open in another app waits and is tried again by itself (docs/stack/queue.md) |

## Search

The library is read in the background for search, as duplicates are looked for: SigLIP reads
what each picture shows from its thumbnail into 768 numbers, and a reader of words (PP-OCRv6 at
Best, Windows' own at Fast) reads the words in it, the detector looking first. The Library's
search box finds by the words, by what was described and by name, all at once; a picture's page
finds the pictures most like it. docs/stack/search.md has the models, the cut and what was
measured.

```mermaid
flowchart LR
    scan["a scan ends"] -- wakes --> reading["reading (mado/search.py)"]
    reading -- "the thumbnail: SigLIP (processor)" --> vectors[("search.db: a vector each")]
    reading -- "the detector first, then the words (card or processor; or Windows')" --> words[("words: FTS5")]
    box["the Library's search box"] -- "/search" --> finding["words, described, name"]
    vectors --> finding
    words --> finding
    page["a picture's page"] -- "/search/like/{id}" --> nearest["More like this"]
    vectors --> nearest
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/search.py`, `mado/core/ocr.py` | Pure: a search as SigLIP reads it, its score and cut, nearest vectors, a search's language and writing, word queries and the words marked; PP-OCRv6's canvas, lines, cuts and decoding |
| The models | `mado/siglip.py`, `mado/ocr.py` | SigLIP on the processor; PP-OCRv6 on the card when it has room (`hardware.room`), else the processor; Windows' own reader through pywinrt |
| Reading and finding | `mado/search.py` | The thread that reads, a picture at a time, paused or not, taking turns at the card's lock; the vectors in search.db and in memory (loaded when a search comes, let go after ten quiet minutes); the words in the database |
| The API | `mado/api/search.py` | `/search`, `/search/like/{id}`, `/search/state`, pausing; a picture's neighbours (`api/pictures.py`) and Many at once (`api/batches.py`) from what a search found |
| The UI | `features/library/search-results.tsx`, `features/settings/search-panel.tsx` | The results in groups with the notes above them; Settings › General › Search |

## Making a picture right for a screen

The Size tab asks the engine for a plan as the owner chooses (a size, the shape, the point to crop
around, what the picture is, Fast or Best), shows previews of the part being looked at, and on
Save starts a job. Nothing changes until then: the job writes a new picture beside the original,
or puts it in the original's place with the original set aside in quarantine, and History says
so. docs/stack/upscaling.md has the models, the tiles and DirectML's rules; docs/stack/hardware.md
the PC check.

```mermaid
flowchart LR
    tab["Size tab"] -- "plan, previews" --> plan["mado/core: size, shape, kind, model, time"]
    tab -- "Save" --> job["a job (mado/jobs.py)"]
    job --> read["read it whole (Pillow, ffmpeg for HEIC)"]
    read --> shape["crop, or extend with LaMa"]
    shape --> model["the model a tile at a time (ONNX Runtime, DirectML)"]
    model --> save["save beside, check, put in place"]
    save --> history[("history, quarantine")]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/` (`sizes`, `framing`, `kind`, `models`, `recipe`, `tiles`, `quality`, `estimate`, `hardware`, `naming`, `outpaint`) | Pure: the sizes, the shape and its words, what a picture is, the model it suits, the plan, the tiles, the format, the time, what this PC can do, names |
| Sessions | `mado/directml.py`, `mado/ai.py` | ONNX Runtime sessions on the card (or the processor where the card can't), made once per model and tile size, kept, run under one lock; each model's file, shipped or downloaded |
| Making | `mado/upscale.py`, `mado/extend.py`, `mado/making.py`, `mado/encode.py` | The model a tile at a time, laid into the size made; the edges drawn by LaMa; reading, making and saving with what's kept of the original |
| Jobs | `mado/jobs.py` | One job at a time on its own thread, with stage, progress, the time left and Cancel (up to saving); a job cut short started again once, or finished or taken back by its History line when it was saving |
| History | `mado/history.py`, `mado/quarantine.py` | What Mado made, a week at a time, its undo and redo (a picture's changes newest first); the quarantine on each drive, the daily clear-out after 30 days (`mado/care.py`, a drive not connected waiting for it), emptying a drive by hand |
| This PC | `mado/hardware.py`, `mado/pc_check.py` | What Windows says the PC has; the check in a process of its own (`mado check-model`), timing each model; the speeds learned from each picture made |

## Giving a picture a look

The Looks tab shows every look as a small copy of the picture and the one picked on the picture
itself, with its strength and finishing touches; what the Edit, Size and Looks tabs set together
is one recipe (`mado/core/recipe.py`: the edits, the fixes, the size step, the painting style,
then the look step, any left out), made by one Save: edited, fixed, cropped or extended, made
bigger, painted in its style, given its look and touches at that size (only on a part, when the
look says so), then saved.
Every look is a table of colours (a 3D LUT) run through Pillow's `Color3DLUT`; the owner's own
(a `.cube` file imported, or a mix kept) are kept in the database. docs/stack/looks.md has how
looks are made, what `.cube` files may be, and the times.

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/` (`grids`, `looks`, `cube`, `touches`, `recipe`) | Pure: a table of colours and keeping it small, Mado's looks made by code, reading a `.cube` file, the touches' shapes, the recipe of steps and its plan |
| Laying it on | `mado/looks.py` | A look's one table, then the touches where they fall on the picture made, see-through parts and grey pictures kept as they are |
| Your looks | `mado/own_looks.py` | Importing, keeping, renaming and deleting the owner's looks, and finding any look by its id |

## Painting a picture in a style

The Looks tab's painting styles are a group of their own beside the looks: Mado's four painters,
the classic means drawn by code, and the owner's own styles (a picture's style kept); any picture
can be the style. A style is the recipe's step after the size and before the look (`paint`): Save
paints the picture made at a working size of about 1600 × 1200, whole, never in tiles, makes it
the size made by plain resampling, mixes it with the picture at its strength (in the picture's
own colours when asked), and then gives it its look and touches. The stage shows it the same
way, so its strokes look as they will in the picture saved; the small copies are painted on the
processor on a smaller canvas, so going through the styles never takes the card's memory. docs/stack/styles.md
has the networks, the working size, the choices and what was measured.

```mermaid
flowchart LR
    tab["Looks tab: painting styles"] -- "/pictures/{id}/styles/{style}" --> small["a small copy in each style"]
    tab -- "/pictures/{id}/style" --> reader["MicroAST reads a picture's style (processor)"]
    tab -- "/plan, /preview with the recipe's paint" --> painter["mado/painting.py: at the working size, the last few kept"]
    painter -- "one session for the painters; MicroAST's own" --> models["ONNX Runtime, DirectML"]
    tab -- "Save" --> job["a job: edits, fixes, size, depth, paint, look, saved"]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/painting.py`, `mado/core/onnx_graph.py` | Pure: the styles and the painting step and its words, the working size and the square canvas a picture is mirrored out to, mixing at a strength and in the picture's own colours, the classic means (pencil, coloured pencil, oil paint, cartoon), whether a picture can give a style; an ONNX graph read and written again with the painters' weights taken out as inputs |
| Painting | `mado/painting.py` | The painters' one session (made from the first painter's file, each painter's own weights read once) and MicroAST's two halves, each on the card when it has room for what it keeps, else the processor; a picture's style read on the processor; the last few paintings at the working size kept for the previews |
| Your styles | `mado/own_styles.py` | Keeping, renaming and deleting the owner's styles (a picture's 512 numbers and a small copy of it, never the picture), and finding any style by its id |
| Making | `mado/making.py` | The paint step of a Save: painted at the working size, made the picture's size, mixed, on a part when it says so, its see-through parts and a grey picture's greyness kept |
| The API | `mado/api/styles.py`, `mado/api/making.py` | The styles, their small copies, reading and keeping a picture's style; the recipe's paint step in plans, previews and Save |

## Editing by clicking

The Edit tab picks parts of a picture with clicks and does things with them: erases them, cuts
them out, blurs what's behind them, or gives them a look (the Looks tab's "Only on a part"); a
brush erases what clicking can't pick, and Cut out finds the subject without a click. The edits
are the recipe's first step, made before the size and the look by the same Save, at the
picture's full size; nothing changes till then. docs/stack/editing.md has the models, the masks,
the card's memory and what was measured.

```mermaid
flowchart LR
    click["a click on the stage"] -- "/pictures/{id}/select" --> pick["SAM 2.1: read once (card), pick (processor)"]
    pick -- "parts and their outline" --> tab["Edit tab"]
    tab -- "/pictures/{id}/edit" --> editor["mado/editing.py: each edit in order, at full size"]
    editor -- "masks, by version" --> cache[("cache/edits")]
    tab -- "/preview, /plan with the recipe's edits" --> editor
    tab -- "Save" --> job["a job: edits, size, look, saved"]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/edits.py`, `mado/core/masks.py` | Pure: parts, strokes and edits as the recipe keeps them, their words, which answer goes first; masks together and apart, strokes drawn, edges grown and feathered, the guided filter, outlines, smears |
| Picking | `mado/selecting.py` | The picture as SAM reads it, each part's three answers smallest first, masks at the picture's size, the outline on a copy 1024 across |
| Erasing | `mado/erasing.py` | The hole cut out in a square, filled by MI-GAN or LaMa, laid back softly with grain; a fill that smeared |
| Cutting out | `mado/cutting.py` | Masks refined to the picture's edges a band of rows at a time; on nothing, a colour or the rest blurred; the lens blur behind a part |
| Edits | `mado/editing.py` | The edits made in order under the picture's one lock, each kept (a batch's, nothing); masks in the cache, made again from their clicks when gone or not fitting; a look's part; the Looks tab's small copy |
| Models | `mado/ai.py`, `mado/directml.py`, `mado/hardware.py` | Each model's file and where it runs: on the card when it has room (DirectX's own budget, `hardware.room`), else the processor |
| The API | `mado/api/editing.py`, `mado/api/edits.py`, `mado/api/making.py` | Picking, making edits; the recipe's edit step in plans, previews and Save |

## Fixing a picture

The Fix tab takes noise, blur from a shaking camera or a moving subject, JPEG blocks and darkness
out of a picture, each fix turned on with its one setting and compared before and after, fitted
or at full detail. The fixes are the recipe's step after the edits: Save makes them on the part
of the picture its size keeps, before it grows, so noise and blocks come out first and the
upscaler doesn't clean again. docs/stack/fixes.md has the models, the order, the guard, what's
suggested and what was measured.

```mermaid
flowchart LR
    tab["Fix tab"] -- "/pictures/{id}/fixes" --> found["a JPEG's quality, how dark it is"]
    tab -- "/plan, /preview with the recipe's fix" --> fix["mado/fixing.py: blocks, brighten, noise, blur, contrast"]
    fix -- "a tile at a time" --> models["FBCNN, SCUNet, NAFNet (ONNX Runtime, DirectML)"]
    tab -- "Save" --> job["a job: edits, shape, fixes, size, depth, paint, look, saved"]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/fixes.py` | Pure: the fix step and its words, the models it needs and the order they're made in (SCUNet once at most), a JPEG's quality from its tables, how dark a picture is, the tone curve, debanding, local contrast (CLAHE) by the whole picture's tables, the blur model's guard, what's suggested; what the fixes make of a picture as it measures (a picture that isn't dark isn't brightened, a batch's JPEG blocks by each JPEG's own quality) and whether they leave it clean for the upscaler |
| Fixing | `mado/fixing.py` | What the dark photo fix takes from the whole picture (measured once on a small copy), and the fixes made on any part of it, the models a tile at a time through `upscale.through_model` (their answers the tile's own size), brightening and contrast a band of rows at a time; all of a picture fitted, the brightening and contrast alone |
| Models | `mado/ai.py` | Each fix model's file (a download) and its kept session, a 384 tile at a time, on the card while it has room for it: FBCNN told how hard, NAFNet's answer held by the guard, either kept as strongly as asked |
| The API | `mado/api/fixes.py`, `mado/api/making.py` | The fix step's choices; what's suggested (`/pictures/{id}/fixes`); the recipe's fix step in plans (made for how dark the picture measures), previews (fitted, the brightening on the copy shown; a part, every fix on the picture round it, stopped when a newer one comes) and Save |

## Depth

The Depth tab reads how far away each part of a picture is, once, with Depth Anything V2 Small,
and makes three tools of it: portrait blur (a lens's depth of field, from a point in focus),
fog (haze thickening with distance) and tilt-shift (a band in focus, blur growing up and down from
it). They're the recipe's step after the size and before the look, made at the size made. A 3D
photo is a video of the picture with the view moving gently through it by its depth, made into
the cache, played on the page, and saved only when the owner says. docs/stack/depth.md has the
model, the lens blur, the choices made and what was measured.

```mermaid
flowchart LR
    tab["Depth tab"] -- "/pictures/{id}/depth" --> read["Depth Anything V2 Small at 518 square (card or processor)"]
    read -- "nearness, by version" --> cache[("cache/depth")]
    tab -- "/plan, /preview with the recipe's depth" --> tools["mado/depth.py: fog, the lens in layers, tilt-shift"]
    tab -- "Save" --> job["a job: edits, fixes, size, depth, paint, look, saved"]
    tab -- "/pictures/{id}/motion" --> motion["mado/motion.py: frames by depth, the layer behind filled"]
    motion -- "frames" --> ffmpeg["ffmpeg: H.264 (Windows' own first) or an animated WebP"]
    ffmpeg --> video[("cache/motion, then saved beside it or into a folder")]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/depth.py`, `mado/core/motion.py` | Pure: the depth step and its words; the model's square, nearness and a flat picture; placing it on what's made; the lens blur in layers, its highlights, its join at full size; fog; tilt-shift's band; a 3D photo's path, finding each frame backwards, what it uncovers, its size and the encoders' commands |
| Reading depth | `mado/depth.py` | The model's reading of a picture as its edits leave it, kept in memory and in `cache/depth` by picture and version; the tools worked out on a copy and joined at full size a band of rows at a time, the subject's edges from Cut out's model |
| 3D photos | `mado/motion.py` | The video's frames on a few threads, the layer behind filled (stretched, or LaMa), ffmpeg's H.264 encoder found once, an animated WebP; made into `cache/motion` one at a time, saved with History's line |
| Models | `mado/ai.py` | The depth model's session, its size pinned, on the card while it has room for it |
| The API | `mado/api/depth.py`, `mado/api/motion.py`, `mado/api/making.py` | The depth step's choices; what the tab reads; the recipe's depth step in plans, previews (fitted, or a part at full detail joined to the whole's) and Save; 3D photos made, played and saved |

## Many at once

Pictures ticked in the Library, a folder, what a search found, or files and folders dropped on
the window or picked (in the library or not) become a batch: its steps (the size, then the look,
as the picture page's tabs choose them), how it saves, and when it starts. See it first makes
three of them in full, unsaved; then each picture is a job in the queue, made one at a time by
the same worker as a picture's own Save. docs/stack/queue.md has the order, nights, room on a
drive, See it first, recipes and watch folders.

```mermaid
flowchart LR
    pick["ticks, a folder, a search, a drop"] -- "/batches/pictures" --> batch["Many at once"]
    batch -- "/batches/samples" --> first["See it first: three made, unsaved"]
    batch -- "/batches" --> queue[("jobs, a picture each")]
    watch["a watch folder's new pictures"] --> queue
    queue --> worker["the jobs' worker, one at a time"]
    first --> worker
    worker --> saved["saved: new pictures, or originals to quarantine"]
    saved --> history[("History: one line a batch")]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/batch.py` | Pure: nights, See it first's pictures, reckoning a batch by them, room on a drive, steps in Mado's order and their words |
| The queue | `mado/jobs.py` | The worker: a picture's own Save first, then batches by their place; pausing, cancelling, ticked pictures next, last or out, trying again; room on a drive; the PC kept awake; a batch done told once |
| Batches | `mado/batches.py`, `mado/samples.py` | The pictures a batch is made of, what it takes, putting it in the queue; See it first |
| Recipes and watch folders | `mado/recipes.py`, `mado/watching.py` | Steps kept by name; folders whose new pictures, once copied, are made to a recipe, never their own results nor anything Mado wrote |

The window's drag and drop is Tauri's (`lib/drop.ts`), which gives the files' paths; Home's Pick
pictures uses the shell's `pick_pictures` (`src-tauri/src/dialogs.rs`).

## Pictures from anywhere

A picture doesn't have to be in the library. Dropped on the window, picked, pasted with Ctrl+V,
or handed over by Windows (File Explorer's "Open in Mado", Open with, the command line), one
picture opens on a page of its own with Size, Looks, Edit and Save; several, or a folder, open
Many at once with them chosen; what isn't a picture Mado reads is said in a note, beside the one
picture that opened or in its place.

```mermaid
flowchart LR
    explorer["Open in Mado, Open with, mado.exe paths"] -- "a start each; the single-instance plugin hands its paths over" --> gather["shell: gathered into one choice (opened.rs)"]
    gather -- "opened event; take_opened" --> ui["UI (Opening)"]
    drop["dropped, picked"] --> ui
    paste["Ctrl+V"] -- "files copied: clipboard_files" --> ui
    ui -- "/open" --> engine["engine: what the paths open as"]
    ui -- "a picture on the clipboard: /pasted" --> engine
    engine -- "one picture" --> page["its page: the library's, or one from outside it"]
    engine -- "several, or a folder" --> many["Many at once"]
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/opening.py` | Pure: one picture opens its page, several or a folder Many at once; the words for what's left out; a pasted picture's name |
| Outside pictures | `mado/outside.py` | A picture known by its path, in the `pictures` table with no library folder: never listed, counted, exported or compared for duplicates; one in a library folder is the library's; its folder added later, it becomes the library's under its number; looked at as it is now whenever its page asks (no scan looks after it). Of Mado's own folder, only a paste opens. Forgotten after 30 days unopened, with its cache, unless the queue or History still needs it |
| Pasting | `mado/pasting.py` | A picture from the clipboard kept as PNG in the data folder's `pasted` till it's saved (as it is, or made to a recipe), 2^26 pixels at most, all the window's clipboard hands over; the same bytes again open the one kept |
| The API | `mado/api/opening.py` | `/open`, `/pasted`; Save refused beside or in place of a pasted picture, and on one in a quarantine (`api/making.py`) |
| The shell | `src-tauri/src/opened.rs`, `clipboard.rs`, `open_in_mado.rs` | Paths from the command line and second starts, gathered and kept till the window takes them; the files copied in File Explorer; "Open in Mado" and Open with under HKCU |
| The UI | `components/shell/opening.tsx`, `features/batch/open.ts`, `features/picture/outside.tsx` | Drops, pastes and what Windows hands over, with their notes; the page's header for a picture from outside, pasted, or in a quarantine |

docs/stack/tauri.md ("Open in Mado", "Paste") has the registry's keys and what was measured.

## The wallpaper studio

The owner's monitors as Windows arranges them, a picture made for each (or one laid across them
all) at exactly each monitor's pixels, set as Windows' own wallpaper or saved as pictures; the
wallpaper changed every day from the favourites if wanted; the owner's own kept and put back.
The engine reaches Windows itself (the monitors and IDesktopWallpaper, by ctypes), as it owns the
daily change and runs in the tray with no window to ask. docs/stack/wallpaper.md has what Windows
does to a wallpaper file and what was chosen from it.

```mermaid
flowchart LR
    studio["the studio (UI)"] -- "/wallpaper: monitors, choices, parts" --> engine["mado/wallpaper.py"]
    engine -- "monitors, set, put back" --> desktop["mado/desktop.py: IDesktopWallpaper, display APIs"]
    studio -- "/wallpaper/set, /save" --> engine
    engine -- "a wallpaper waiting" --> worker["the jobs' worker, before the queue"]
    worker -- "each part, PNG at its monitor's pixels" --> made[("data folder: wallpapers")]
    daily["the daily change (its own thread)"] --> engine
    made --> desktop
```

| Part | File | Does |
| --- | --- | --- |
| The rules | `mado/core/wallpaper.py` | Pure: the arrangement and its word, the gap for the bezels, where a part is cut (crop, zoom, extend), laying one across, which pictures suit a monitor, the day's picks |
| Windows | `mado/desktop.py` | The monitors (per-monitor DPI aware, their names from DisplayConfig) and each one's wallpaper; setting it, how wallpapers are laid, the slideshow and spotlight; `Desktop`, the seam the tests fill with a fake, `NoDesktop` where there's none |
| The studio | `mado/wallpaper.py` | Its choices; each part planned and made (by the jobs' worker); set, saved as pictures, or kept for its day; the owner's own kept and put back; the daily change; Mado's own wallpapers tidied |
| Favourites | `mado/favourites.py` | The heart; following a picture moved or renamed; forgetting one long gone |
| The API | `mado/api/wallpaper.py`, `mado/api/pictures.py` | `/wallpaper` and its changes; `PUT /pictures/{id}/favourite` |
| The UI | `features/wallpaper/`, `components/heart.tsx`, `components/shell/claim.tsx` | The studio (the monitors drawn, the column's tabs, picking, saving, every day), the heart, and a page taking what's dropped or pasted for itself |

## Contracts

| Between | How | Kept honest by |
| --- | --- | --- |
| Shell and engine | `serve` arguments, `MADO_TOKEN`, the ready line, stdin | Tests on both sides |
| Shell and UI | Commands `engine_status`, `restart_engine`, `prepare_update`, `install_update`, `screens`, the dialogs (`pick_folder`, `pick_pictures`, …), `take_opened`, `clipboard_files`, `open_in_explorer`, `set_open_in_explorer`; events `engine-status`, `opened` and Tauri's drag and drop | Types mirrored in `app/src/lib/engine.tsx`, `updates.ts`, `screens.ts`, `dialogs.ts`, `drop.ts`, `opened.ts` and `startup.ts` |
| UI and engine | JSON over HTTP, camelCase | `engine/openapi.json` snapshot + test; types in `app/src/lib/engine.tsx` |

Change a contract on both sides in the same commit.

## The engine's API

| Route | For |
| --- | --- |
| `GET /health` | Is the engine up, its version, the data folder, the schema version (0 while the records are damaged) |
| `GET /settings`, `PUT /settings` | The owner's choices: whether Setup is done, Saving, whether a watch folder's big batch waits for the night, and search's reader of words |
| `GET /tools`, `POST /tools/{id}/download` | What Mado downloads (ffmpeg, LibRaw, the AI models fetched when asked), each one's state, and fetching it |
| `GET /backups`, `POST /backups`, `POST /backups/import`, `POST /backups/{name}/restore` | The backups, one made by hand, importing an export, restoring one as the engine starts again |
| `GET /data`, `POST /export` | What the data folder holds, by part (pictures pasted and Mado's wallpapers too), and the export zip |
| `GET /folders`, `POST /folders`, `DELETE /folders/{id}` | The library's folders, each with its counts and the folders inside it as a tree; adding one (which a scan then reads, and the watcher watches); taking one out (its pictures stay where they are) |
| `GET /library` | The library in numbers, for Home: pictures, folders, size, what's still to read, camera RAW (and how many wait for Mado's RAW reader), what won't open (and how many of those are marked as damaged), each folder's share, the favourites |
| `GET /library/wont-open`, `POST /pictures/{id}/damaged` | The pictures that won't open, each with why, those marked as damaged left out; marking one as damaged |
| `GET /space` | The drives the library is on, the one with the most of it first: free, the pictures, quarantine, what the queue wants there |
| `GET /duplicates` | The groups of duplicates and bursts, a page at a time (`kind`, `offset`, `limit`; `reach`, a group the page must hold), each with its pictures, the ones kept, and whether it can be set aside now; how far looking has got; what setting every group aside would set aside and free; the latest review, when it was put back whole |
| `PUT /duplicates/{key}/keep`, `POST /duplicates/{key}/not-same`, `POST /duplicates/aside` | Which of a group to keep, of its pictures as shown; a group not the same; setting aside the rest of groups as the review showed them (each one's pictures and kept ones), or of every group of a kind as long as none changed since (`version`, else 409), and what was left as it was and why |
| `GET /scan` | How the latest scan went, or is going: its stage, what it found and read, time left, folders not connected, what came and went |
| `GET /pictures` | A page of pictures by the day they were taken (`folder`, `dir`, `q`, `order`, `after`, `limit`; `favourites`, only the favourites, from outside the library too), with each day on it counted whole, a group's kept picture tagged ("burst of 5", "2 copies"), each picture's heart, and whether it's a camera RAW (`waiting` while Mado's RAW reader comes) |
| `GET /pictures/{id}`, `GET /pictures/{id}/neighbours` | One picture in full (from outside the library too: where it lives, pasted, in a quarantine; looked at as its file is now, 404 with why once it went; asking counts as opening it); the pictures either side of it in the list it was opened from (a search's results, or More like this, in their order), none for one from outside |
| `GET /search` | What the Library's search box finds (`q`, in a folder, `dir`, or the favourites): the pictures whose words match (the words, the matched ones marked), those that look like what was described (SigLIP's score past its cut, best first), and those with every word in their name, each picture once, those on a drive away marked; whether the search reads as English, a writing the words reader can't read; how far reading has got and what it waits for. The first search fetches what reading needs |
| `GET /search/like/{id}` | The library's pictures most like one, nearest first (it read there and then when it hasn't been) |
| `GET /search/state`, `POST /search/pause`, `POST /search/resume` | How far reading the library for search has got (read, of, reading, paused, the queue on the card, pictures that couldn't be read now, a reader that couldn't run), SigLIP's download and the words reader (the owner's choice, the one in use, its download, Windows' languages, where Best runs); pausing it, and going on, which tries again what couldn't be read |
| `POST /open` | Paths dropped, picked, pasted or handed over by Windows: one picture as Mado knows it, with what else came and was left out; several, or a folder, as Many at once takes them; 404 or 422, with why, when none of it is a picture |
| `POST /pasted` | A picture from the clipboard (PNG), kept in the data folder and said as a picture outside the library; the same picture again is the one kept; 413 past 2^26 pixels (about 67 megapixels) |
| `GET /pictures/{id}/thumbnail`, `/view`, `/full` | Its copies (WebP, or the picture itself at full size where the window shows its format), kept by the window (their addresses carry the picture's version); a camera RAW's thumbnail from its camera's preview, its view and full size developed, and one that won't develop marked as one that won't open |
| `POST /pictures/{id}/read` | Reads one picture again now (one that wouldn't open may have been mended; a camera RAW waiting for its reader, once it's here) |
| `PUT /pictures/{id}/favourite` | Gives a picture a heart, or takes it back |
| `GET /sizes`, `POST /screens` | The sizes a picture can be made for (the devices, the owner's screens, prints); remembering this PC's screens as the window sees them |
| `POST /pictures/{id}/select` | Parts picked with clicks on the picture as its edits so far left it: a click starts a part, an Alt-click takes from the part it's in; each part's name ("Part 1"), its answer and the outline round them all; how long reading the picture took and how long it waited for the card (409 while SAM isn't downloaded, or the picture changed) |
| `POST /pictures/{id}/edit` | Makes the edits (the last one new) so the previews show them: how long it took, where it ran, and whether an erase came out smooth where the picture has detail |
| `POST /pictures/{id}/plan` | How a picture would be made to a recipe (its edits, its fixes, its size step, its depth tools, its painting style and its look step, any of them none, the style and the look on the whole picture or parts): its shape and the words for it, what it is, the model (not cleaning again what the fixes cleaned), its look (the style named with it), edits, fixes and depth tools, about how long here (the fixes' and the depth tools' shares apart, and where the depth model runs), where its style is painted and whether it's made so much bigger than it's painted that its strokes go soft, the format (PNG or WebP for a cut-out with nothing behind it), colours and size, and the downloads it waits for |
| `POST /pictures/{id}/depth` | How near each part of the picture is, as its edits leave it, read once (the depth model while it isn't downloaded, said and nothing read): whether it's flat, its subject's middle, where the model runs and how long reading took |
| `GET /pictures/{id}/motion`, `POST /pictures/{id}/motion` | What a picture's 3D photo can be made with here (ffmpeg, the H.264 encoder that works, the sizes the picture has the pixels for); making one into the cache, the one before it let go |
| `GET /motion/{id}`, `GET /motion/{id}/video`, `POST /motion/{id}/save`, `DELETE /motion/{id}` | How a 3D photo is coming on; the video (MP4, or an animated WebP); saving it beside the picture or into a folder, with History's line; letting it go |
| `GET /pictures/{id}/fixes` | What the Fix tab suggests: a JPEG's own quality from its tables, how many stops dark it is, and whether it's grey, has see-through parts or wide colours, kept as they are |
| `POST /pictures/{id}/preview` | The picture made, all of it fitted (from its screen-sized view, as JPEG) or a part at full detail (as WebP), before (stretched) or after (made, with its look and touches), with its colour profile and how long it took |
| `POST /pictures/{id}/saving` | The name a picture made would be saved as ("Harbour at dusk (TV 8K, Warm film).jpg"), whether that's taken, and about how big it comes out |
| `POST /pictures/{id}/make` | Makes it to its recipe and saves it as chosen, as a job |
| `GET /looks` | Mado's looks and the owner's own, each with a version its small copies' addresses carry |
| `GET /pictures/{id}/looks/{look}` | A small copy of the picture in a look, from its thumbnail (WebP, kept by the window) |
| `POST /pictures/{id}/looks/{look}` | The same, of the picture as its edits leave it, once the Edit tab has made some (409 once the picture changed) |
| `POST /looks/import`, `POST /looks` | Importing a `.cube` file as a look; keeping the mix on the Looks tab (a look, its strength and its touches) as one |
| `PUT /looks/{id}`, `DELETE /looks/{id}` | Renaming one of the owner's looks; deleting one (pictures made with it stay as they are; not while a recipe uses it, or pictures waiting in the queue are made with it) |
| `GET /styles` | Mado's painting styles (the painters, each with its download, and the classic means, each with its one setting) and the owner's own; the download that reads a picture's style |
| `GET /pictures/{id}/styles/{style}` | A small copy of the picture in a style at its full strength, from its thumbnail (WebP, kept by the window; 409 while its model isn't downloaded) |
| `POST /pictures/{id}/styles/{style}` | The same, of the picture as its edits leave it, or in a picture's own style not kept (`picture`, its numbers in the body) |
| `POST /pictures/{id}/style` | A picture's style, read by MicroAST from its colours and textures: its 512 numbers, what it's called and its version (422, with why, for a picture too small or too plain to give one; 409 while MicroAST isn't downloaded) |
| `GET /styles/{id}/thumbnail` | The small copy of the picture one of the owner's styles came from |
| `POST /styles`, `PUT /styles/{id}`, `DELETE /styles/{id}` | Keeping a picture's style as one of the owner's (its numbers and a small copy of the picture, never the picture); renaming one; deleting one (pictures painted with it stay as they are; not while a recipe uses it, or pictures waiting in the queue are painted with it) |
| `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel` | Pictures' own Saves (a picture's, or those under way; the queue's are `/queue`'s): stage, progress, time left, what they saved, why they didn't work; Cancel |
| `GET /jobs/held`, `POST /jobs/{id}/try-now`, `POST /jobs/{id}/skip` | The pictures waiting while they're open in another app, the queue's and Saves'; trying one again now; skipping one |
| `POST /batches/pictures` | The pictures a batch would be made of: ticked (`ids`), a folder's (`folder`, `dir`), what a search found (`q`), the favourites (with `q`, those it found among them), or the pictures in files and folders dropped or picked (`paths`), with those left out and why (`waiting`: a camera RAW left out only while Mado's RAW reader comes); a batch with camera RAW saves new pictures only (409 for Replace) |
| `POST /batches/takes` | What a batch would take: about how long, how much space and what's free where it's saved, by this PC's speeds and what See it first found; its steps in words, where its pictures go, a name they'd take, and the downloads it waits for |
| `POST /batches/samples`, `GET /batches/samples/{id}`, `DELETE /batches/samples/{id}`, `GET /batches/samples/{id}/{index}/{side}` | See it first: three pictures made in full, not saved (`round` asks for three others); how they're coming on; letting them go; each one before and after (WebP) or as made |
| `POST /batches`, `GET /batches/done`, `POST /batches/{id}/seen` | Putting a batch in the queue (now, after what's in it, or tonight), See it first's pictures kept; the batches done that Home tells of; Home's card for one seen |
| `GET /queue`, `GET /queue/now` | The queue as its page shows it (the batch being made and its pictures, the batches after it, a drive without room and how much more it needs; with nothing waiting, the latest batch whose pictures didn't all work, `finished`); the queue in a word, for the rail's badge and the status bar |
| `POST /queue/pause`, `/resume`, `/cancel`, `/fit`, `/next`, `/last`, `/remove`, `/clear`, `POST /queue/{job}/retry` | Pause and resume; cancel all; make what fits on a drive without room; ticked pictures next, to the end, or out of the queue; what didn't work of the batches done cleared from the Queue; a picture that didn't work tried again |
| `GET /recipes`, `POST /recipes`, `PUT /recipes/{id}`, `DELETE /recipes/{id}` | The owner's recipes, each with its steps in words and how often and when it was used; keeping, changing and deleting one (not while a watch folder runs it) |
| `GET /watch-folders`, `POST /watch-folders`, `PUT /watch-folders/{id}`, `DELETE /watch-folders/{id}` | The watch folders: each one's recipe, where its new pictures go, on or off, connected, when it last took pictures, and why its pictures couldn't go in the queue lately; adding (what's there already left alone), changing, turning off and on, and stopping watching one |
| `GET /history`, `POST /history/{id}/undo`, `POST /history/{id}/redo`, `POST /history/clear` | History a week of days at a time (`before`, `q`), with the batches its lines were made in; taking a new picture away or putting a replaced original back, newest first; putting a picture taken away back, or replacing an original again; clearing History |
| `POST /history/batches/{id}/undo`, `/redo`, `GET /history/today`, `GET /history/{id}/thumbnail` | A whole batch taken away or its originals put back, and done again, once nothing of it waits (409 till then); what was made today, for Home; a thumbnail of a picture a line made, in the library or not |
| `POST /history/reviews/{id}/undo` | Every picture a review of duplicates and bursts set aside put back, each where it was |
| `GET /quarantine`, `POST /quarantine/empty` | What waits in quarantine on each drive; emptying one now |
| `GET /pc`, `POST /pc/test` | This PC: its card, processor and memory, where the models run (and each editing model now), each kind at each quality with its time, what each starts on; testing it again |
| `GET /wallpaper`, `PUT /wallpaper` | The studio: the monitors as Windows arranges them, the pictures chosen and where they're cut, each part as it'll be made, the latest set or saved, the owner's own and the daily change; one for each or one across all, and the gap |
| `PUT /wallpaper/pictures`, `DELETE /wallpaper/pictures` | A monitor's picture (or the one across all), its shape, where it's cut, Fast or Best; letting it go |
| `POST /wallpaper/set`, `POST /wallpaper/save`, `POST /wallpaper/cancel` | The parts made and set as Windows' wallpaper (the owner's own kept first), or saved as pictures into a folder picked; the one being made stopped |
| `POST /wallpaper/put-back`, `PUT /wallpaper/daily` | The owner's own wallpaper back, every monitor or one; the daily change's choices |
| `GET /wallpaper/monitors/{key}/wallpaper` | What Windows shows on a monitor now, small (WebP) |
| `GET /records`, `POST /records/restore`, `POST /records/new` | Records damaged past use, and the two ways back |

## Data

- **The data folder**, `%LOCALAPPDATA%\Mado`: `mado.db` (everything Mado knows), `search.db`
  (what SigLIP read each picture into, for search: read again when it's lost, never in a backup or
  the export), `logs/`
  (`engine.log`, kept 30 days), `tools/` (ffmpeg, LibRaw once a camera RAW is read, and the AI
  models fetched when asked, each with its licence files), `pasted/` (pictures pasted from the
  clipboard, till a month after last opened), `wallpapers/` (the wallpapers Mado made, those
  showing and the last 3 days', and its copy of the owner's own), `cache/` (the pictures'
  thumbnails and views, the last few full-size copies, each edit's mask in `cache/edits` and each
  picture's depth in `cache/depth`, by picture and version, let go after a month unused: anything
  in it can go, a mask made again from its clicks and depth read again; and the last few 3D photos
  made in `cache/motion`, cleared as the engine starts), and `backups/` (the last 7 nights, each checked as it's made, and apart from them the
  last 7 made by hand, before a restore and from an export; none is ever written over).
  `mado/care.py` makes tonight's backup from 03:00 (or the first chance after). A backup chosen in
  Settings is restored as the engine starts again, before anything opens the database, once it
  checks out; what Mado knew till then is backed up first, and kept even when it doesn't check out.
  Development uses `engine/.dev-data`, so it never touches the real folder.
- **The database** is SQLite, upgraded in place by migrations (see [stack/sqlite.md](stack/sqlite.md)).
  A database written by a newer Mado is refused, not damaged. Records damaged past use (a disk
  fault, a power cut mid-write: `mado/rescue.py`) are found as the engine starts, before anything
  else opens them; the engine then answers only `/records` and `/health`, and the app's window
  shows the way back in place of every page: the newest backup that opens, restored over them, or,
  with none, new records as on Mado's first day (when the disk couldn't read them, Try again comes
  first). Either way the damaged file is set aside as it is, never deleted, and the app starts the
  engine again.
- **The quarantine**, `Mado quarantine` at the top of each drive, a folder a day: a replaced
  original, or a picture taken away, waits there 30 days (`mado/quarantine.py`), then the daily
  clear-out deletes it. Setting one aside is a rename on its own drive. Mado deletes only what's
  in a day's folder of a quarantine, whatever its records say, and the library's scan never looks
  into one.
- **Export**: one zip, readable without Mado, written to a folder the owner picks in Settings (or
  with `mado export`): the database, its settings, the library's folders (`folders.json`), every
  picture with what Mado read of it (`pictures.csv`, marked as damaged when it is), the words read
  in each for search (`words.csv`), History (`history.csv`, with what each picture was made for and with, what was edited, what the fixes and the depth tools did, each picture set aside, the one kept and its review), the owner's looks (`looks.json`, and each as a `.cube` file in `looks/`), their painting styles (`styles.json`, each style's numbers, and the small copy it's known by in `styles/`), their recipes (`recipes.json`) and watch folders (`watch-folders.json`), what they decided of duplicates and bursts (`duplicates.json`: pictures not the same, which they keep, each setting aside), their favourites (`favourites.json`) and the wallpaper studio (`wallpaper.json`), and a manifest. It grows with the
  schema. Settings imports one too: the database it holds
  is restored like a backup as the engine starts again, and what Mado knew till then is backed up
  first. An export from a newer Mado waits for an update.

## Safety on a shared PC

- The engine listens only on `127.0.0.1`, on a port chosen at random.
- Every request needs the launch's token; anything else gets 401.
- Only the app's own pages may call it (CORS), and only when addressed to this PC (Host check).
  A fault inside the engine is answered in plain words inside CORS (`api.Unexpected`), so the
  window can say so, rather than that the engine didn't answer; the details go to its log.
- The window's content security policy allows the app itself, Tauri's IPC and the local engine.
- The window may call only the core APIs, its title bar buttons and Mado's own commands
  (`app/src-tauri/capabilities/default.json`).
- An update runs only if its signature matches the public key built into Mado.

## On an installed PC

| What | Where |
| --- | --- |
| Program | `%LOCALAPPDATA%\Programs\Mado` (`mado.exe`, `engine\`, `uninstall.exe`) |
| Data | `%LOCALAPPDATA%\Mado` |
| WebView2 cache | `%LOCALAPPDATA%\io.github.frankgrobbelaar.mado` |
| "Open in Mado" and Open with | `HKCU\Software\Classes`: `SystemFileAssociations\<type>\shell\Mado.Open`, `Directory\shell\Mado.Open`, `Applications\mado.exe`, `Mado.Picture`, and the value `Mado.Picture` under each type's `OpenWithProgids` |
| Uninstaller's export | `Documents\Mado export <date>.zip` |
