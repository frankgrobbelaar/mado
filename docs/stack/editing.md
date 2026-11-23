# Editing by clicking (selecting, erasing, cutting out)

The Edit tab picks parts of a picture with clicks, then erases them, cuts them out, blurs what's
behind them or gives them a look; a brush erases what a click can't pick, and Cut out finds the
subject without a click. The edits are the first step of the picture's one recipe, made again at
full size by Save with the size and the look. The screens are Picture-Edit, Picture-Looks' "Only
on a part" and Recipes' "Cut-outs for cards" on the [Mado Screens canvas](../design/screens.html).

| Part | Where |
| --- | --- |
| Parts, strokes and edits as the recipe keeps them; their words; which answer goes first | `mado/core/edits.py` |
| Masks: together and apart, strokes drawn, grown and feathered, the guided filter, outlines, how much detail a place has | `mado/core/masks.py` |
| Picking: the picture as SAM reads it, each part's answers, masks at the picture's size, the outline | `mado/selecting.py` |
| Erasing: the hole in a square, filled, laid back with grain; a fill that smeared | `mado/erasing.py` |
| Cutting out: masks refined to the picture's edges; on nothing, a colour, the rest blurred; the lens blur | `mado/cutting.py` |
| The edits made in order and kept, their masks in the cache; a look's part | `mado/editing.py` |
| Where each model runs, its sessions | `mado/ai.py`, `mado/directml.py`, `mado/hardware.py` (`room`) |
| The API | `mado/api/editing.py`, `mado/api/edits.py`, `mado/api/making.py` |
| The Edit tab, its stage, the picking hook; "Only on a part" | `app/src/features/picture/edit-tab.tsx`, `edit-stage.tsx`, `editing.ts`, `looks-tab.tsx` |
| Cut out the subject as a batch's step | `mado/core/batch.py`, `app/src/features/batch/` |

## The models

| Model | For | File | Licence | Comes | Runs |
| --- | --- | --- | --- | --- | --- |
| SAM 2.1 Hiera-Tiny (`sam2.1-hiera-tiny`) | Picking a part with a click | 156 MB (two parts, each with its weights) | Apache-2.0 | downloaded the first time a part is picked | reading on the card when it has room, picking on the processor |
| MI-GAN v2 pipeline (`mi-gan`) | Erasing at Fast | 28 MB | MIT | downloaded the first time Erase is asked for | the card when it has room |
| LaMa (`lama`) | Erasing at Best (and extending edges) | 209 MB | Apache-2.0 | downloaded the first time either is asked for (`models-1`) | the card |
| U²-Net small (`u2netp`) | Cutting out at Fast | 4.6 MB | Apache-2.0, ONNX conversion MIT | inside Mado | the processor |
| BiRefNet lite (`birefnet-lite`) | Cutting out at Best | 224 MB | MIT | downloaded the first time Best is asked for | the processor, unless the card has 10.5 GB of room |

Each is its authors' own ONNX file or a published conversion of their weights, byte for byte,
from Mado's own release [`models-2`](https://github.com/frankgrobbelaar/mado/releases/tag/models-2)
(LaMa from `models-1`), each in `downloads.json` with its size and SHA-256 and its licences
beside it. SAM's two parts are saved as `vision_encoder.onnx` and
`prompt_encoder_mask_decoder.onnx`, each with its `.onnx_data`, the names their graphs look for.
u2netp ships: at 4.6 MB it costs the installer little, and cutting out at Fast then works offline
and in a recipe or a watch folder from the first run. How they were chosen and checked:
the models agent's report (2026-11-22) and the measurements below.

## Picking a part

SAM reads the picture once, the whole of it squeezed to 1024 × 1024 however big it is (so a
picture of any size can be picked), and keeps what it read for the picture as its edits left it.
Each click is then its decoder alone, on the processor, where it never waits for the card: a
click starts a part, an Alt-click inside a part adds a "not this" point to it, and the decoder
answers each part with three masks at 256 × 256. They're kept smallest first. Mado shows the one
SAM is surest of, unless a bigger one is nearly as sure (within 0.1), as one click most often
means the whole thing; Bigger, Smaller and the mouse wheel step through the rest. The outline
the window draws (volt, dashed) is worked out on a copy 1024 across by marching squares, so a
click never waits for a big picture. Parts are called Part 1, Part 2: Mado recognises nothing.

The decoder's points can't be padded to a fixed count (label -10 changed its answers by up to 31
in its numbers), so it keeps free sizes; on the processor that costs nothing.

## Masks at full size

A model's mask is at its own size (SAM's 256 square spans 16 of a 12-megapixel picture's pixels
a cell), so its edge is a few pixels off. Cut-outs, blurs and looks refine it to the picture's
own edges with a guided filter (He, Sun and Tang): its coefficients worked out on a copy 1024
across (a closed-form 3 × 3 inverse, 32-bit running sums), then laid on the picture itself a band
of rows at a time and only along the mask's unsure edge, where it isn't nearly 0 or 1. Erasing
doesn't need it: the hole is grown 0.3% of the shorter side (3 pixels at least) to take the
thing's fringe too. A look's part is feathered over 0.4% of the shorter side, at the picture's
size, then placed as the size step places the picture (cropped, or on its extended canvas, where
what's at the picture's edge carries on), so the preview and the picture saved agree.

## Erasing

The hole is cut out in a square: half its longer side again on every side, 512 pixels at least
(so a small hole is drawn at the picture's own detail), mirrored to a square where the picture is
narrower. It's made 512 square, filled by MI-GAN (its own pipeline, `uint8` in and out, 255 to
keep) or LaMa (0 to 1 in, 0 to 255 out), made its size again and laid back only where the hole
was, fading in over 2 pixels, with grain like the picture's (`extend.grain`). Nothing else is
touched. A fill whose fine detail, told on a copy a quarter the size where a photo's grain
averages away, is under 30% of what's round it, in a place busy enough for it to show, has
smeared: the tab offers Best.

## Cutting out and blurring

The subject comes from u2netp (320 square) or BiRefNet lite (1024 square, its numbers through a
sigmoid), stretched to 0 to 1 as rembg does, then refined. What's cut out sits on nothing (its
see-through parts the mask's, the picture kept whole underneath; saved as PNG or WebP only, and
the plan, the Save dialog and a batch's saving say so), on a colour, or on the rest of the
picture blurred (a haze 2% of the shorter side). It keeps the picture's size. "Blur what's behind
it" blurs everything outside the part with a disc 1.2% of the shorter side across, as a lens
does, in light (the numbers to the power 2.2) so bright places bloom, the part left out of the
blur so its colour never bleeds round it (each pixel the mean of what's outside the part near
it), on a copy 1024 across, then joined over 0.4% of the shorter side.

## The card's memory

A DirectML session keeps what it took of the card's own memory for as long as it lives, and
Mado never lets one go (mado/directml.py). Measured on the owner's 6 GB card, held after a run:

| Session | Held |
| --- | --- |
| SAM 2.1's reader at 1024 | 1.19 GB |
| SAM 2.1's picker | 0.09 GB |
| MI-GAN at 512 | 0.56 GB |
| LaMa at 512 | 1.0 GB |
| u2netp at 320 | 0.27 GB |
| Real-ESRGAN general, 512 tiles | 0.2 GB |
| RealESRGAN x4plus, 256 tiles | 1.22 GB |
| x4plus anime 6B, 256 tiles | 1.09 GB |
| BiRefNet lite, graph fusion off | 10 GB committed (the card filled, the rest paged out) |

Going past the budget Windows gives a process doesn't fail, it pages: a 6B tile went from 0.16 s
to 1.2 s. So an editing model goes on the card only when it fits: `hardware.room()` asks DirectX
(DXGI's `QueryVideoMemoryInfo` on the high-performance card, any maker) for the budget less what
this process holds, and Mado makes the session there only with the model's measured share and
512 MB to spare (`ai.HELD`); where DirectX can't say, it takes the card to have 4 GB, enough for
SAM and MI-GAN but never BiRefNet. Otherwise the model runs on the processor. Once made on the
card it stays there. `/pc` says where each runs now (`Ai.editing_places`), so the tab says so: the
read note ("Mado read the picture in 2.1 s on the processor"), Best's cut-out ("Best runs on the
processor on this PC"), and the card's note only for work on the card. u2netp runs on the
processor anyway (0.3 s) and SAM's picker too, which keeps clicks off the card. BiRefNet lite
takes far more than the card has unless the card is big, so on the owner's PC it runs on the
processor.

## Sharing the card with the queue

The queue's picture takes the card a tile at a time, under `directml.LOCK`; an edit's work on the
card (SAM's read, an erase) takes it between two tiles, so it waits at most one tile, never a
whole picture. A click is the decoder on the processor and never waits at all: a session made
already is handed out without the lock, one on the processor is made and run without it, and
SAM's reader is made only when a picture is read, never on a click. While an edit on the card
takes longer than a moment with the queue working, the stage says so ("Waiting for the graphics
card: Holiday prints lets it go after the tile it's on"). A click made while another is on its way
(the first, while the picture is read) is made in turn when that one's back, never dropped.

## Kept for Save

An edit is a step of the recipe: the parts as their clicks (fractions of the picture) and the answer
shown, a brush's strokes as their points, each edit made on the picture as the edits before it left
it, all tied to the picture's version. The engine keeps the last few pictures as edits left them (60
megapixels at most) and what SAM read of each, in memory, and each edit's mask in
`cache/edits/<picture>/<version>/` as a PNG, so Save, made later by the queue or after a restart,
makes the same mask without picking again; a mask that's gone, or doesn't fit the picture as it's
read now, is picked again from its clicks. A batch's pictures, each made once, keep nothing: no mask
in the cache and nothing in memory. Masks of pictures not edited for a month go as the engine
starts. Parts picked for a look are tied to the picture's version as edits are (the window sends it,
and the engine ties them to the picture as it is when it doesn't). A Save whose picture changed
since its edits were made fails with a sentence and saves nothing; a click or an edit on one is
refused (409), and the tab lets its edits go, quietly when the change was Mado's own Save in the
original's place, asked for since the edits began. A picture's edits are made under its one lock
(one of 64, by the picture), so two threads making its chain never wait for each other's.

The previews keep a cut-out's see-through parts: at full detail before and after, and on an
extended canvas, as Save does. The Looks tab's small copies show the picture as its edits leave
it (`POST /pictures/{id}/looks/{look}`, from one small copy kept for all the looks), and so do the
small pictures beside Erase it and Cut it out, cropped to fill as the board draws them. Where a
picture is see-through itself, a cut-out onto a colour shows the colour through it.

## Limits

Mado edits pictures up to 100 megapixels (`editing.MOST_PIXELS`); a bigger one says so on the
Edit tab and in "Only on a part" before a part is picked, and offers the Size tab to make a smaller
copy. SAM only ever sees the copy squeezed to 1024, and every step past the squeeze works on the
part's own region (a mask's sigmoid, growing and feathering it, refining its edge), so time and
memory follow the picture's size only where they must: at 100 megapixels the engine peaked at
3.4 GB. A preview of a part at full detail works out a cut-out's see-through parts only round the
part (over a whole 12-megapixel picture that took 1.2 s a look).

## Measured on the owner's PC

GTX 1660 Super 6 GB, i5-9600K, onnxruntime-directml 1.24.4, 2026-11-23, the card and the
processor otherwise idle (checked before each run); made-up scenes drawn by code at 4032 × 3024
(the little sail of the Edit board, a red ball on grass, a striped balloon), with their shapes'
own masks as the truth. Times are the median after a first run.

| | Card | Processor |
| --- | --- | --- |
| SAM reading a 12-megapixel picture (squeezing it to 1024, then the encoder) | 0.28 s (the encoder 0.16 s) | 2.1 s (the encoder) |
| A click: the decoder and the outline | | 49 ms |
| The first click through the editor, reading included | 0.36 s | |
| Making SAM's sessions, once an engine's life | 1.3 s | |
| Erasing the boat (685 × 544 pixels of a 12-megapixel picture) | Fast 0.43 s, Best 0.99 s | |
| Cutting out a 12-megapixel picture's subject | | Fast 0.25 to 0.32 s, Best 9.9 to 10.8 s |
| Refining a mask at 12 megapixels | | 0.5 to 0.6 s (SAM's), 0.6 to 0.8 s (U²-Net's) |

| Picture | Picking, the first time | Cutting out a part | Erasing it | Most memory |
| --- | --- | --- | --- | --- |
| 12 megapixels | 1.5 s | 0.09 s | 0.94 s | 1.0 GB |
| 48 megapixels | 1.6 s | 0.26 s | 1.45 s | 2.0 GB |
| 100 megapixels | 1.6 s | 0.54 s | 2.5 s | 3.4 GB |

(The first pick includes making SAM's sessions; the first erase, MI-GAN's.)

How well a click picks, IoU against the shapes drawn (Mado's first answer; the best of three):

| Part | First | Best of three |
| --- | --- | --- |
| The sun | 0.996 | 0.996 |
| The bigger sail | 0.988 | 0.988 |
| The hull | 0.985 | 0.985 |
| A red ball on grass | 0.996 | 0.996 |
| A striped balloon | 0.159 (one stripe) | 0.991 (two steps bigger) |

On the balloon SAM is surest of one stripe (0.97) and least sure of the whole (0.19); neither its
scores nor how stable each answer is tells the whole balloon from the wrong big answers on other
scenes, so Mado shows the surest and Bigger reaches the rest.

Refining the edge at full size: the mean difference from the truth within 8 pixels of the edge,
for SAM's answers 0.04 to 0.08 made the picture's size smoothly (0.18 to 0.21 by its nearest
cell), 0.025 to 0.047 refined, the IoU of the shapes 1.0; for U²-Net 0.27 to 0.29 down to 0.15 to
0.18 (IoU 0.99 up to 1.0); for BiRefNet 0.08 down to 0.03 to 0.04 (IoU 0.974 to 0.996 up to 0.977
to 1.0, its balloon taking the basket too). Worked out on a copy 512 across it was quicker but no
better than SAM's own mask, so it stays at 1024.

Erasing, PSNR in the hole against the same scene drawn without the boat: Fast 33.7 dB, Best
35.0 dB (10 dB before); everything 40 pixels or more from the hole exactly as it was.

The queue's picture with edits beside it: Fast making a 12-megapixel photo 7680 × 5760 took
13.2 s alone and 14.8 s (12% longer) while 7 reads, 21 clicks and 7 erases were made beside it, a
quarter of a second apart. A read waited at most 137 ms for the card (a tile), an erase didn't
wait, and a click never does (71 ms all in, the processor shared).

## Gotchas

- SAM's ONNX takes `input_boxes` of shape `[1, 0, 4]` for no box, and labels 1 and 0; don't pad
  the points.
- MI-GAN's pipeline takes any size, but each size compiles anew on DirectML: Mado feeds it 512
  squares only, its sizes pinned.
- BiRefNet lite fails on a 6 GB card with DirectML's graph fusion on (out of memory); off, it
  commits about 10 GB. Its session is made with `ep.dml.disable_graph_fusion` only on the card.
- A session made on the processor runs without `directml.LOCK`; one on the card always takes it.
- The stand-ins in `engine/tests/edit_models.py` play SAM (the patch of like colour round a click)
  and the fill; CI never has the downloads. u2netp is real in the tests.

## Upgrading

A newer SAM, MI-GAN, BiRefNet or U²-Net is measured on the same made-up scenes (IoU, PSNR in the
hole, times, the memory it keeps) before it's taken, goes in a new `models-N` release with its
`downloads.json` entry, the notices, this page and the README's "The AI inside" in the same
commit. SAM 2.1's bigger sizes are a choice beside the tiny one, never in its place.
