# The quick fixes (noise, blur, JPEG blocks, dark photos)

The Fix tab takes out what's wrong with a picture: noise, blur from a shaking camera or a moving
subject, JPEG blocks, and darkness. Each fix is turned on with its one setting and compared
before and after, the line between them dragged, fitted or at 100% and 400%. The fixes are a step
of the picture's one recipe, made after the edits and before the picture grows, by the same Save.
No board drew the tab, so it's built in the Edit tab's patterns: a card of rows, each a fix, and
the Size tab's before-and-after stage.

| Part | Where |
| --- | --- |
| The fix step, its words, the models it needs and the order they're made in; a JPEG's quality from its tables; how dark a picture is, the tone curve, debanding, local contrast; the blur model's guard; what's suggested | `mado/core/fixes.py` |
| What the dark photo fix takes from the whole picture, and the fixes made on any part of it | `mado/fixing.py` |
| Each model's file and kept session, a tile at a time, on the card where it has room | `mado/ai.py` (`fixer`, `fix_file`, `fix_place`, `fix_starts_on`) |
| The fix step in a recipe, its plan, its previews and Save; the part kept cut out and fixed before the size | `mado/core/recipe.py`, `mado/making.py`, `mado/api/making.py`, `mado/api/fixes.py` |
| History's words (`fix`, migration 11), a batch's Fix step | `mado/history.py`, `mado/core/batch.py`, `mado/batches.py` |
| The Fix tab and its stage; the Fix step's card for many at once | `app/src/features/picture/fix-tab.tsx`, `fix-stage.tsx`, `fixes.ts`; `app/src/features/batch/step-dialogs.tsx` |

## The models

| Model | For | File | Licence | Comes | Runs |
| --- | --- | --- | --- | --- | --- |
| SCUNet, real-noise PSNR (`scunet`) | Noise; the noise a dark photo's brightening brings out; JPEG blocks at Fast | 73 MB | Apache-2.0 (KAIR's helper layers MIT) | downloaded the first time a fix needs it (`models-1`) | the card |
| FBCNN, colour (`fbcnn`) | JPEG blocks at Best, as hard as asked | 288 MB | Apache-2.0 (KAIR's helper layers MIT) | downloaded the first time Best is asked for (`models-1`) | the card |
| NAFNet, GoPro width 32 (`nafnet`) | Blur from a shaking camera or a moving subject | 69 MB | MIT (its file carries BasicSR's Apache-2.0 notice) | downloaded the first time the blur fix is asked for (`models-3`) | the card |

Each was exported to ONNX from its authors' official weights and checked against their code by the
models agent (2026-11-22 and 23), and published in Mado's own prereleases
[`models-1`](https://github.com/frankgrobbelaar/mado/releases/tag/models-1) and
[`models-3`](https://github.com/frankgrobbelaar/mado/releases/tag/models-3), each in
`downloads.json` with its size and SHA-256 and its licence files beside it. All three run in full
precision (fp32): their fp16 copies are half the download but 1.6 to 1.85 times slower on a GTX 16
card, and fail to load on the processor at ONNX Runtime's highest optimisation. Dark photos need no
model of their own: the low-light models' code is on Mado's list, but every one was trained on
data sets for research only, and the classic fix matched knowing the true exposure on made-up
scenes.

## The order, and nothing cleaned twice

Inside the fix step, in this order (`core/fixes.stages`); a fix at 0% does nothing, and the dark
photo fix nothing to a picture that isn't dark (under a stop, `LEAST_STOPS`):

1. **JPEG blocks** at Best (FBCNN): the saving made them last, so they come out first.
2. **Brightening** a dark photo: in linear light, by the gain its brightest 0.5% measures (to just
   under white, 1 to 16 times, never the average), then the extended Reinhard tone curve.
3. **Noise** (SCUNet): one pass, as strong as the strongest fix asking for it: the noise fix's own
   strength; a dark photo's denoise, as much as brightening brought noise out (half at one stop,
   all of it from two); JPEG blocks at Fast (twice their strength, so a JPEG saved at 50 or under
   is cleaned in full). SCUNet never runs twice.
4. **Blur** (NAFNet), after the noise is out: sharpening noise only makes more of it.
5. **Local contrast** (CLAHE), after the denoise, as a slider: it lowers PSNR and SSIM against the
   truth, so it's off till asked.

Then the size step. A picture the fixes cleaned isn't cleaned again as it grows (`core/fixes.cleans`):
Fast goes to Real-ESRGAN's weak-denoise twin, as "Clean noise and blocks first" off does, and the
Size tab (and a batch's Size card, when its Fix step cleans) says so in that switch's place.
Cleaned means the noise fix or JPEG blocks above 0%, as much taken out as the owner asked (Fast
taking more would undo it), or a photo two stops dark or more (`CLEAN_STOPS`), whose denoise ran in
full. Under two stops a dark photo's denoise takes out only the noise brightening brought, so Fast
cleans what was there before, as it would in any picture. Best (x4plus, or anime 6B) always cleans
as it grows, and finds little left to clean. The blur fix cleans nothing, so Fast still cleans
after it.

How dark a picture is decides what the dark photo fix makes, so the plan is made for it: on the
picture's page from the measure the previews share, and in a job once the picture is read and its
edits made (`making.make`'s `replan`). A picture that isn't dark isn't brightened, named
"Brightened" or left to Fast's weak-denoise twin, and a Save of nothing but fixes that change
nothing in it says so ("It isn't dark, so there was nothing to fix."): the Fix tab, or the job's
line in a batch, where nothing is saved.

Save makes the fixes on the part of the picture the size keeps (its crop, or its canvas extended by
LaMa, whose new edges then match the picture fixed), in whole pixels, before the model makes it
bigger: less to fix, and noise and blocks out before it grows. The part is fixed with 96 px of the
picture round it (`fixing.MARGIN`), then cut back, so its edges see what's beside them, as a
preview of a part does.

## Each fix

**Noise.** SCUNet's answer, kept as strongly as asked (`strength` blends it with the picture as it
was). 100% at first: it measured best on made-up noise at every level (below).

**Blur.** NAFNet in 384 px tiles overlapping by 32, always with the guard, never on a whole picture:
trained on photos that never had a flat area, it returns -275 to 690 on a flat grey square (the
authors' own code), and whole-picture or unguarded runs came out worse than doing nothing. The
guard holds each pixel's change to its input's local contrast (light's range over 31 × 31 px, plus
2/255), a separable running max and min in numpy (`core/fixes.local_range`). And on some tiles it
breaks down outright, its answer colours anywhere (3 tiles in 100 of the made-up scenes' blurred
pictures, and one of a sharp one: a road's flat tarmac beside its straight lines, say; the same on
the card and the processor): a mend moved a tile by 0.02 on average at most, a breakdown by 0.38
or more, so a tile moved by 0.05 or more (`BROKEN`) comes back as it was (`core/fixes.guarded`),
and its neighbours' mends meet it through the tiles' overlap. It mends a shaking camera and a
moving subject; a picture out of focus only comes a little crisper (a slight blur, about 3 dB),
as no sharpening brings back detail that's gone, nor to a picture too small, and the tab says
so.

**JPEG blocks.** Fast is SCUNet (one model for noise too), Best is FBCNN; "as this PC has it" is Best
once FBCNN is downloaded, else Fast, so a fix needs one download, not two. The strength is FBCNN's
own quality setting (`qf_override`: 0.7 takes the picture for a JPEG saved at 30), started at the
picture's own quality from its tables (82% for a JPEG saved at 18), 60% when it can't be read; at
Fast, SCUNet's answer blended at twice the strength. A screenshot starts on Best, which keeps
letters crisp. A batch's Fix step (and so a recipe's, and a watch folder's) has no strength to set:
each JPEG's blocks come out as hard as it was squeezed, read from its tables as the plan is made
(`core/fixes.for_picture`), and a picture that isn't a JPEG (PNG, WebP, HEIC, a camera RAW) is left
as it is, as it has none. One strength for all told FBCNN every picture was a JPEG saved at 40,
smoothing a camera's JPEG saved at 95, and every PNG.

**Dark photos.** The gain and the tone curve's white are measured on a small copy of the whole
picture (1024 px, made straight from it, its see-through parts left out), so a part made alone
brightens as the whole does; only this fix measures. A picture wanting less than a stop isn't
dark (a well-lit picture with nothing white in it measures about 0.6): the fix leaves it as it is,
brightening, denoise and local contrast alike, and the tab says so. Brightened four times or more, an 8-bit file's own steps would show as bands (a level
becomes 16), and the denoise keeps them, as it takes a clean step for an edge: so first, where
the picture is flat to within a level or two (its light's range over 15 px), each pixel is moved
toward the mean of the 17 px square round it, all the way where it's one level flat, not at all
where it spans two levels or more; edges and texture keep every level, and a grey picture stays
grey (`core/fixes.debanded`, each band of rows read with the 15 rows round it). Local contrast's
tables come from the same small copy, brightened, and each pixel is blended between the four tile
centres round it by its place in the whole picture.

## What Mado suggests

Only what it can measure cheaply and reliably (`GET /pictures/{id}/fixes`):

- **JPEG blocks**, from a JPEG's own quantisation tables (read from its header, nothing decoded):
  the standard tables' quality nearest them. Suggested at quality 60 or under.
- **A dark photo**, from its brightest 0.5% on the same small copy: suggested from 1.5 stops dark. A
  night scene with lights isn't suggested, as its lights are bright already; a picture made dark on
  purpose, with nothing bright in it, would be.

Noise and blur aren't suggested: a texture (grass, foliage, fabric) reads as noise to any cheap
measure, and a sharpness measure can't tell a shaken photo from one out of focus, which NAFNet
only sharpens a little. The tab says when it found nothing it can measure, and that noise and shake are for
trying and comparing.

## A fix on a part

Left out. The four flaws are the camera's or the file's and lie over the whole picture, and a part
fixed alone leaves a seam where cleaned grain meets the rest's. The one local case, a moving
subject, the guarded blur fix mends without harming the sharp rest (below). And the Fix tab's stage
drags to compare and to move round, where a click to pick a part would fight it.

## Where each runs, tiles and memory

On the card where the PC runs the models, through Mado's kept sessions (`mado/directml.py`): every
fix model's session is made and run under the one lock, kept for the engine's life, its batch,
height and width pinned at 384. As a session is never let go, each goes on the card only while the
card has room for what it keeps there (`ai.HELD`, measured below, as the editing models), and on
the processor otherwise: SCUNet, FBCNN and NAFNet together hold 3 GB, and with the upscaler and the
editing models past a 6 GB card's budget, DirectX pages, and everything on the card slows tenfold.
The plan says where they run (`fixPlace`), and the Fix tab says when a full card sends them to the
processor, and that restarting Mado frees it; a pace is learned where its model ran. One size for all three: NAFNet needs 384 at least to see a shake,
and SCUNet and FBCNN run about as fast for each megapixel at 256, 384 and 512 (below), 384 keeping
the seams' overlap small. On a PC whose card can't run the models, the processor, 12 to 21 times
slower (below), and the tab says the time there. A preview takes the card a tile at a time, so the queue's
picture and a preview take turns, and a preview that waits says the queue has the card.

## Previews

A part at full detail (100%, 400%) is made as Save makes it: the picture round it, 96 px each way,
fixed as the whole picture measures, then cut back. A newer preview of the picture (a slider moved,
the part dragged) stops the one before at its next tile (`api/making.Newest`): the window has let
it go, and on the processor a part takes SCUNet a minute.

All of it fitted (the Fix, Size and Looks stages, and the Looks tab's small copies) shows only a
dark photo's brightening and local contrast, made on the copy shown as Save makes them, with no
model and so nothing to download first: noise, blur and blocks are too small to judge on a copy
that size, and their models over a stage-sized copy would take seconds on the card and minutes on
the processor. The Fix stage, fitted with only those on, says they show at 100%.

## Measured on the owner's PC

GTX 1660 Super 6 GB, i5-9600K, onnxruntime-directml 1.24.4, 2026-11-23, through Mado's own code
(`mado.fixing.fixed`), each model in a process of its own after three quiet readings of the card.
The made-up pictures are drawn by code (the models agent's scenes), never a photo.

Seconds for a picture fixed, the session already made (its first run makes it and compiles it for
384 px: about 2 s more), and what each holds of the card's memory for the engine's life:

| Fix | 1080p, card | 12 MP, card | 1080p, processor | 12 MP, processor | The card's memory |
| --- | --- | --- | --- | --- | --- |
| Noise (SCUNet) | 3.9 | 23 | 79 | 498 | 1.3 GB |
| JPEG blocks, Fast (SCUNet) | 3.9 | 23 | as noise | as noise | 1.3 GB |
| JPEG blocks, Best (FBCNN) | 2.6 | 16 | 43 | 283 | 1.3 GB |
| Blur (NAFNet) | 1.2 | 7.2 | 16 | 89 | 0.4 GB |
| Dark photo (brightening, then SCUNet) | 4.4 | 26 | 80 | about 500 | 1.3 GB |
| Dark photo, with local contrast | 5.0 | 29 | | | 1.3 GB |

A tile on the card, by its size (milliseconds, and for each megapixel of tiles; the card's memory
its session keeps):

| Model | 256 px | 384 px | 512 px |
| --- | --- | --- | --- |
| SCUNet | 98 ms, 1.49 s, 0.45 GB | 210 ms, 1.42 s, 1.27 GB | 366 ms, 1.39 s, 1.32 GB |
| FBCNN | 63 ms, 0.95 s, 0.92 GB | 141 ms, 0.95 s, 1.31 GB | 247 ms, 0.94 s, 1.31 GB |
| NAFNet | | 55 ms, 0.38 s, 0.37 GB | 92 ms, 0.35 s, 0.64 GB |

The gain on six made-up scenes (960 × 640: a lighthouse, a boat, a flower field, a road, a balloon,
a snowy mountain), PSNR and SSIM against the clean picture, before and after:

| Damage | Before | After |
| --- | --- | --- |
| Noise, σ 10 | 28.3 dB, 0.615 | 40.7 dB, 0.995 |
| Noise, σ 25 | 20.6 dB, 0.237 | 39.1 dB, 0.994 |
| Noise, σ 50 | 15.2 dB, 0.097 | 36.4 dB, 0.991 |
| JPEG quality 10, Best / Fast | 30.2 dB, 0.969 | 33.8 dB, 0.991 / 31.6 dB, 0.982 |
| JPEG quality 30, Best / Fast | 34.8 dB, 0.984 | 39.8 dB, 0.996 / 37.8 dB, 0.995 |
| JPEG quality 50, Best / Fast | 36.4 dB, 0.989 | 40.9 dB, 0.997 / 38.9 dB, 0.996 |
| JPEG quality 70, 90 (Best) | 37.7, 40.3 dB | 42.2, 44.1 dB |
| A screenshot's letters, JPEG 20, Best / Fast | 27.2 dB, 0.954 | 30.6 dB, 0.992 / 29.1 dB, 0.989 |
| A straight shake (15 px) | 29.0 dB, 0.949 | 32.7 dB, 0.979 |
| A hand's shake (a 25 px path) | 26.3 dB, 0.928 | 26.3 dB, 0.933 |
| A moving subject (a ball streaked 21 px) | 35.3 dB, 0.987 | 38.3 dB, 0.991 |
| Out of focus (a 5 px disc) | 29.1 dB, 0.946 | 32.3 dB, 0.970 |
| Darkened 4 times (two stops, a small sensor's noise) | 9.9 dB, 0.779 | 36.1 dB, 0.995 |
| Darkened 16 times (four stops) | 6.0 dB, 0.429 | 37.0 dB, 0.995 |
| Darkened 4 and 16 times, local contrast 50% | | 32.6 and 28.5 dB, 0.990 and 0.989 |

The noise fix at 50% and 75% gained less at every level (σ 10: +5.2 and +8.4 dB against +10.2 at
100%; σ 25: +5.8 and +10.6 against +16.2; σ 50: +6.0 and +11.4 against +19.1, on 640 × 480
copies of four of the scenes), so it starts at 100%. A JPEG
saved at 70 or 90 still gains, but its blocks hardly show (37.7 and 40.3 dB before), so Mado
suggests the fix only at 60 or under. Fast's SCUNet gains about half what Best's FBCNN does, and
takes longer: Fast is there for a PC that has SCUNet for noise and not FBCNN. The hand's shake was
too long a path to mend; a slight blur out of focus comes about 3 dB crisper, which a stronger one
wouldn't. The moving subject's ball went from 24.6 to 28.0 dB while the sharp rest of the picture
changed by 0.17 levels on average (5 at most for 99 pixels in 100; 47.8 to 46.3 dB against the
truth): mending the whole picture leaves its sharp parts as they were, so a fix on a part isn't
needed for it. Before the breakdown guard, the road's moving subject and out-of-focus picture
came out at 20.8 and 19.2 dB, from 34.7 and 29.7. Banding: a smooth dark gradient in 8 bits
brightened 16 times came out with no jump of more than one level from one pixel to the next,
with the debanding or without it (SCUNet smooths the steps too), and the debanding brought it
1.6 dB closer to the truth (53.0 against 51.4 dB; 186 levels against 182, the truth's 198).
Before-and-after crops of each are in the measuring folder, not the repo, as they're the made-up
scenes' pictures.

What Mado suggests, on made-up pictures: a JPEG's quality from its tables was exact for every one
of 152 (eight scenes at qualities 5 to 95, both chroma layouts) and for tables each value moved by
up to 10%, as a camera's own might be; darkness was right in all 74 cases (14 scenes at normal
exposure and one to four stops under, one stop under counted either way, four night scenes with
lights), the stops it measured 0.22 off on average.

## Gotchas

- A whole-picture NAFNet session takes 4.4 GB of the card and made later tile sessions ten times
  slower: Mado never makes one.
- NAFNet breaks down on some tiles whatever runs it (a flat place beside straight lines): its
  answer is clipped to 0 to 1 in the export, so nothing is out of range to see, but it moves the
  tile by 0.38 or more on average, and the guard leaves such a tile as it was.
- FBCNN's second input, `qf_override`, is `[batch, 1]`: pinning `batch` pins it too.
- SCUNet wants sides of a multiple of 64, FBCNN 8, NAFNet 16: every tile is 384, and a picture
  smaller than a tile is padded by mirroring (`upscale._tile_result`).
- The tests run stand-ins for the three models through Mado's own sessions and tiles
  (`tests/fix_models.py`): the real ones are downloads CI never has.

## Upgrading

A newer SCUNet, FBCNN or NAFNet export, or a newer ONNX Runtime, is measured on the same made-up
pictures (the gains above) and timed before it's taken; a new export goes in a new `models-N`
release, with its `downloads.json` entry, the notices, this page and the README's "The AI inside"
in the same commit.
