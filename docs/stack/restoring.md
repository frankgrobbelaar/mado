# Restoring old photos (scratches and dust, colour, faded colours)

Restoring mends a scanned old print: the scratches, creases and dust Mado finds, shown as a mask
the owner checks with the brush before anything is filled, then filled from what's round them; a
black-and-white or sepia print coloured; a colour photo's faded colours brought back. It sits at
the top of the Fix tab, before the fixes, and is a step of the picture's one recipe, made after the
edits and before the fixes, on the picture at its own size, by the same Save. Faces are left as
they are: no face model on Mado's list may ship (below). No board draws it: it's the Fix tab's
own rows, and the mask is the Edit tab's brush on the Fix tab's stage.

| Part | Where |
| --- | --- |
| The restore step and its words; which picture needs which; colour put onto a picture's own light; faded colours' levels; the detector's canvases, uniting and growing its masks, the owner's strokes over them | `mado/core/restore.py` |
| Finding scratches (kept in `cache/edits`), filling them with LaMa a square at a time, DDColor's colours, the levels; laying colour and faded colours on any part of the picture | `mado/restoring.py` |
| Each model's file and kept session, its place | `mado/ai.py` (`scratch_finder`, `colourer`, `restore_file`, `restore_place`) |
| The restore step in a recipe, its plan, previews and Save; the mask's endpoint | `mado/core/recipe.py`, `mado/making.py`, `mado/editing.py`, `mado/api/making.py`, `mado/api/restore.py` |
| History's words (`restore`, migration 14), a batch's Restore step | `mado/history.py`, `mado/core/batch.py`, `mado/batches.py` |
| The Fix tab's restoring rows, the mask's stage; the Restore step's card for many at once | `app/src/features/picture/restore-section.tsx`, `scratch-stage.tsx`, `restore.ts`; `app/src/features/batch/step-dialogs.tsx` |

## The models

| Model | For | File | Licence | Comes | Runs |
| --- | --- | --- | --- | --- | --- |
| Microsoft's old-photo scratch detector, half precision (`oldphoto-scratch-detector`) | Finding scratches, creases and dust | 75 MB | MIT | downloaded the first time scratches are asked for (`models-3`) | the card while it has room for it (it keeps 2.7 GB there), else the processor |
| LaMa (`lama`) | Filling them | 209 MB | Apache-2.0 | already Mado's (the Size tab's extending, Erase at Best) | where the PC runs the models |
| DDColor tiny (`ddcolor-tiny`) | Colouring a black-and-white or toned print | 270 MB | Apache-2.0 | downloaded the first time colouring is asked for (`models-1`) | the card while it has room for it (2.4 GB), else the processor |

The detector is the scratch half of Bringing Old Photos Back to Life, exported by the models agent
(2026-11-23) and published in half precision only: 75 MB against 150, though half precision runs
about 1.5 times slower on a GTX 16 card (the models report, note 3). It runs once a picture
(0.6 s on the card at 12 MP), so the smaller download stands; a full-precision file would need
publishing first. Half-precision files fail to load on the processor at ONNX Runtime's highest
optimisation in 1.24.4 (the layer-norm fusion bug Kura met with Whisper), so there its session is
made a level lower (`Sessions.get(..., half=True)`: `ORT_ENABLE_EXTENDED`). DDColor tiny is the
authors' ConvNeXt-tiny weights in full precision, its file in `models-1` with its licence. Both are
in `downloads.json` with their sizes and SHA-256, and the installer's first page lists them.

**Faces.** GFPGAN's face restorer and CodeFormer were the candidates; GFPGAN leans on parts whose
licences forbid commercial use and CodeFormer's own licence (S-Lab's) is non-commercial, so neither
can ship in an MIT app that anyone may fork. Faces are left as the scratches, colour and fixes leave
them, and the README's "The AI inside" says so.

## Which picture needs which

A black-and-white picture or a toned print (sepia, a cyanotype) is offered colouring; a colour
photo is offered its faded colours back (`core/restore.colours_of`, on a 256 px copy of the picture
as its edits leave it, through `GET /pictures/{id}/fixes`). Its colours in Lab are smoothed over a
5 × 5 square first (a scanner's colour noise out), then:

- **Black and white**: the faintest colour, its 99th percentile of chroma under 2.3 (Lab's units).
- **A toned print**: one tint all over, the colour its light doesn't explain (chroma's spread
  within each of 16 bins of lightness) under 1.3; sepia when that tint's hue is 20° to 110°.
- **A colour photo**: anything else.

Measured on 1,440 made-up pictures (30 scenes drawn by code, two of each, as drawn, grey, toned four
ways (sepia, a lighter sepia, selenium, cyanotype) and faded two ways, at two sizes with three
levels of a scanner's colour noise): black and white was right 180 times in 180; toned 684 in 720
(30 taken for colour: a sepia moon over the sea, a night city; 6 for grey); colour 499 in 540 (41
taken for toned: faded pictures of few colours, a page of words, a chessboard, a chart).
Sepia was named sepia 348 times in 360. A wrong call only starts the Colour row the other way and
moves "Suggested" off it: the owner can switch. Fading isn't suggested: a colour photo's saturation
and cast are the scene's own as often as age's, and nothing cheap tells them apart, so the tab says
to try it and compare.

## Scratches and dust

**Finding them** (`core/restore.canvas_for`, `found_mask`; report-3 note 6). The picture as its
edits leave it is made grey with its short side 768 (the mask's size, Lanczos), then made smaller
to a short side of 256, as the authors run it, and of 512, where it's surer of thin lines
(bilinear, as their PyTorch code does), and laid on fixed canvases of 256 × 512 and 512 × 1024
(a portrait picture turned onto them, a panorama fitted by its long side, the rest mirrored), so
one session a size serves every shape. Each answer is cut back, made the mask's size, kept where
the detector is 40% sure or more, the two united, then grown round by 3 px. The mask is kept in
the cache with the edits' masks (`cache/edits/<picture>/<version>/scratches-<edits>.png`, gone
after a month unused), never beside the picture.

**The mask first.** The detector finds the light scratches well and misses dark ones, and can take
a line that belongs in the picture for a scratch (a road's dashed line, a boat's rigging), so
nothing is filled till the owner has seen what it found: turning on "Scratches and dust" shows the
mask over the picture in the accent, the owner paints over what it missed and holds Alt to take
away what isn't a scratch, as Edit's brush does (a finer brush: 1% of the shorter side at first),
then "Fill them in". The strokes are drawn at the mask's size after what was found, in order
(`core/restore.marked`), and tied to the picture's version (colour and faded colours aren't: they
go by the picture as it is). Save waits on every tab till the mask has been checked; leaving the
Fix tab counts as done checking, so the other tabs show the picture as Save makes it. Strokes stop
at 512, as the engine takes them, and the stage says so.

**Filling them** with LaMa (MI-GAN can't fill thin lines: report-3 note 6), on a copy with its
short side 768 at most (`FILL_SHORT`): its 512 squares step 448, each pixel of the mask filled by
the square whose middle is nearest, so a square never fills a scratch from its own edge. The fill
is laid back at the picture's own size through the mask made smooth, a band of rows at a time, and
given the print's own grain (as an extended edge is), so it doesn't read as a smooth patch; the
picture is never touched outside the mask. Measured on eight made-up 12 MP prints with the
detector's own masks (PSNR against the undamaged picture, inside the damage and over the whole):

| Filled at | Inside the damage | Whole picture | Time (card) |
| --- | --- | --- | --- |
| As scratched | 7.5 dB | 27.3 dB | |
| Short side 768 (Mado's) | 26.3 dB | 40.7 dB | 2.9 s |
| Short side 1536 | 26.2 dB | 40.5 dB | 11.6 s |
| The picture's own size (3024) | 25.7 dB | 39.9 dB | 29.6 s |

As good at 768 as larger, and two and a half to six and a half times as quick: thin scratches lose
nothing at that size, and LaMa fills a wide crease better seeing more round it.

**A mask over most of the picture.** Past half the picture (`MOST_MASK`), Mado won't fill it (it
would invent most of the picture: "The mask covers 62% of the picture: Mado fills scratches and
dust, not most of a picture"), and Save waits; from a quarter (`MUCH`), the tab says that's a lot
to invent. Nothing found says so, and that whatever the owner paints is filled.

**Dust** comes with the scratches: the detector finds dust specks as reliably as light scratches
(below), so there's no second finder. A classic speck finder (a pixel 30 levels off its 5 × 5
median, in small blobs only) found 96% of the dust at 98% precision on the made-up prints, but on
made-up scenes full of small marks that belong in them, aged as prints with no dust at all (a night
city's lights, a page of words, fireworks, stars, a calendar, rain, sand: 32 pictures), it marked
0.8% of the picture on average and up to 2.8% (a page's letters, a city's lights), where a print's
dust covers 0.1 to 0.2%: it would fill the lights and the dots of the letters. Whatever the detector
misses, the brush adds. The detector itself took a shower's streaks for scratches (17% of the
picture) and a starry sky's stars and a calendar's lines for dust and scratches (4 to 5%), and
marked under 0.1% of a page of words: one more reason the mask comes first.

What the detector found on the eight prints (each made up and aged by code: sepia or faded colour,
lifted blacks, a vignette, grain, a soft lens; then scratched, creased and dusted, the truth kept
apart), within 3 px at the mask's size:

| | Found |
| --- | --- |
| Light scratches | 100% (all eight) |
| Dark scratches | 88% of their pixels; one dark scratch in a dark forest missed entirely (0 of 2,337 px), one on a landscape 74% found |
| Dust | 91% |
| The mask on real damage | 60% of it within 3 px of a scratch or speck: the rest is its coarse cells and the 3 px grown round them |
| On the same prints undamaged | 1.1% of the picture marked on average (0 to 3.1%: a boat's rigging, flower stems, a road's dashed line) |

## Colour

DDColor tiny sees the picture squeezed to a 512 × 512 square, as its lightness alone (Lab's L made
grey RGB, as its authors feed it), and guesses Lab's a and b there (`ai.colourer`). Those are made
the size of whatever part is shown and put onto that part's own lightness (OpenCV's Lab, D65, as
DDColor was trained), so every detail is the original's and only the colour is guessed
(`core/restore.coloured`). The strength mixes the guess with the picture's own colour: a grey
picture's none, a sepia print's brown. A grey picture's colour profile (one for grey) is dropped
once it's coloured, as the colours are sRGB's. The guess is from what photos usually look like, so
the tab says a coat's colour is a guess; a picture in colour already can be coloured too, and the
tab says its own colours give way to new ones.

## Faded colours

By classic means, with no model (`core/restore.levels_of`, `faded_back`): each colour's darkest and
brightest half percent, measured on a 1,024 px copy of the picture (see-through parts left out),
taken as its black and white. Stretching all three by the same levels lifts the fade but keeps the
cast; each by its own takes the cast out but goes too far on a picture that's warm by nature; so
Mado goes 75% of the way from the three's together toward each colour's own (`_OWN`). The strength
mixes it with the picture as it was. On 60 faded made-up pictures (ΔE against the picture before it
was faded):

| | ΔE | The cast (b*; unfaded −3.0) |
| --- | --- | --- |
| Faded | 23.4 | 5.5 |
| Each colour's own levels, 50% of the way | 19.5 | 3.5 |
| 75% (Mado's) | 19.5 | −0.2 |
| 100% | 20.4 | −3.9 |

75% gains as much as halfway and takes the cast out; all the way overshoots. A barely faded
picture gains little (16.1 before, 16.5 after) and an unfaded one changes (ΔE 14.1), so it's
offered, never suggested, with its strength and the before-and-after to judge by. A black-and-white
picture or a print has no colours to bring back, and the tab says so.

## Together, in the recipe

The restore step comes after the edits and before the fixes
(`{"version": …, "scratches": {"strokes": […]} | null, "colour": {"strength": …} | null,
"faded": {"strength": …} | null}`): the scratches filled first, so DDColor never sees one and its
colours don't run along them; then colour or faded colours; then the fixes' noise and JPEG blocks if
wanted, as the brief's chain has it, and the rest of the recipe. It's made on the picture at its own
size (a scratch is a few pixels wide: a crop or a new size would move it off its mask). The strokes
are tied to the picture's version; a picture changed since they were painted lets them go, finds
its scratches again and shows the mask to check again, saying why; a Save in the original's own
place, which carries the restoring in it, lets it go quietly, as edits are.

What's worked out once is kept (`Restorer`): what the detector found (memory and the cache), the
picture with its scratches filled for the owner's latest strokes, DDColor's colours and the levels.
Colour and faded colours are then laid on whatever is shown, from what's kept: a stage's fitted
copy, a part at 100% and 400% (only round the part, with the fixes' margin), the Looks tab's small
copies and the styles', or the whole picture a band of rows at a time for Save, so a strength moved
never waits for a model. The one exception is a picture the Size tab extends: LaMa draws its new
edges from the picture as restoring leaves it, so they're drawn again for a new strength. The
results are kept apart for scratches off and for scratches on with nothing painted, as they're two
different pictures. A new picture is named
"Coloured" when that's all it was, else "Restored" ("Harbour at dusk (Restored, TV 8K).jpg"), and
History's `restore` column (migration 14) says "filled its scratches and dust and coloured it",
in the brackets with the edits and fixes. An HDR photo's gain map follows (docs/stack/hdr.md):
filled where its scratches were, from the same mask, and one channel when its colour is brought
in or back.

## Many at once

A batch's Restore step colours each picture that's black and white or a toned print and brings back
each colour photo's faded colours, each as it needs (`{"step": "restore", "colour": …, "faded":
…}`, both on at first); a picture with nothing for it to do (a colour photo when only colouring is
on) is a line saying why. **It never fills scratches**: the mask is each picture's own, the
detector misses dark scratches and takes lines that belong in a picture for scratches, and filling
what's found without a look would paint over roads, rigging and stems on some pictures while
leaving dark scratches on others. So scratches are filled one picture at a time, on its Fix tab,
where the owner checks the mask; the step's card says so, and a recipe with scratches in it is
refused with that sentence.

## Where each runs, and memory

Through Mado's kept sessions (`mado/directml.py`), under the one lock, each kept for the engine's
life, the detector's two canvases pinned through free-dimension overrides (DDColor's square is
fixed in its export).
Each goes on the card only while it has room for what it keeps there (`ai.HELD`): measured each in
its own process, the detector keeps 2.7 GB (its 512 × 1024 canvas), DDColor 2.4 GB and LaMa 1.0 GB;
all three in one process kept 3.3 GB, as DirectML shares its working memory. With the card full of
the models used since Mado started, they run on the processor, and the Fix tab says so. A preview
takes the card a model at a time, so the queue's picture and a preview take turns, and a preview
that waits says the queue has the card.

## The small things

- A model to download first: each card says what it does and its size; the stage waits for it, and
  faded colours need no download, so they work meanwhile, offline too.
- The card busy with the queue: finding the scratches says it waits for the graphics card, as a
  preview does.
- A huge scan: past 100 megapixels, the Size tab makes a smaller copy first, as the edits ask.
- Nothing found: said, and the brush still paints what Mado fills; with nothing painted either,
  there's nothing to fill, and the plan and Save go on without the scratches (nothing to save, or
  only the colour), so History never says scratches were filled.
- A mask over most of the picture: not filled, Save waits, the tab says how to take some away.
- A picture already in colour asked to be coloured: allowed, with the line that its own colours give
  way to the guess.
- A sepia print: offered colouring, the strength mixing the guess with its brown; no faded colours
  to bring back.
- See-through parts: kept as they are, through the fill and the colour.
- A picture changed while its mask waited: the strokes go, the scratches are found again on it as it
  is, and the mask is shown to check again, with the reason.

## Measured on the owner's PC

GTX 1660 Super 6 GB, i5-9600K, onnxruntime-directml 1.24.4, 2026-11-24, through Mado's own code
(`mado.restoring`), each step in a process of its own (report-3 note 5) after a quiet card and
processor, on a made-up 12.2 MP print (4032 × 3024) drawn and aged by code. Seconds once the session
is made (its first run makes it: about a second or two more), and what the model keeps on the card:

| Step | 12 MP, card | 12 MP, processor | The card's memory |
| --- | --- | --- | --- |
| Finding scratches and dust (the detector, both canvases) | 0.58 | 8.8 | 2.7 GB |
| Filling them (LaMa at 768; this print's mask covers 5%) | 2.9 | 14.7 | 1.0 GB |
| Colouring: DDColor at its square | 0.48 | 1.4 | 2.4 GB |
| Colouring: laid on the whole picture | 4.1 | 4.2 | |
| Faded colours: the levels, then laid on the whole picture | 1.2 | 1.2 | |
| All of it: scratches found and filled, then coloured, as Save makes it | 10.5 | 28 | 3.3 GB together |

Laying colour on is the processor's work either way (Lab and back, 12 million pixels); the
stages' copies take a fraction of a second.

## Gotchas

- The detector's file is half precision: on the processor it loads only a level under the highest
  optimisation, and on a GTX 16 card it's about 1.5 times slower than a full-precision file would
  be.
- The detector's answer is coarse (its authors run it at a short side of 256): the 512 canvas and
  the 3 px growth cover what its cells miss, and the mask is shown before anything is filled.
- DDColor is trained on photos: on drawings and made-up scenes it guesses too, often wrongly, which
  is why the tab says a colour is a guess.
- The tests run stand-ins for the detector and DDColor through Mado's own sessions
  (`tests/restore_models.py`): the real ones are downloads CI never has.

## Upgrading

A newer detector or DDColor export, or a newer ONNX Runtime, is measured on the same made-up prints
(the tables above) and timed before it's taken; a new export goes in a new `models-N` release with
its `downloads.json` entry, the notices, this page and the README's "The AI inside" in the same
commit. A face model comes only when one may ship under Mado's licence.
