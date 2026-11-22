# Upscaling (making a picture right for a screen or a print)

Mado makes a picture exactly the size a screen or a print wants: the shape it wants (cropped
around the subject, or its edges extended), four times bigger through an AI model on the graphics
card, then resized exactly. The models run on [ONNX Runtime](https://onnxruntime.ai) with
Microsoft's DirectML, on any DirectX 12 card. The screens are Picture-Size, Save and History on
the [Mado Screens canvas](../design/screens.html).

| Part | Where |
| --- | --- |
| The sizes (devices, prints at 300 dpi, the owner's screens, any other) | `mado/core/sizes.py` |
| The shape: crop around a focus point, or extend; where the subject is | `mado/core/framing.py` |
| What a picture is: photo, drawing, pixel art, screenshot | `mado/core/kind.py` |
| The models, and which one suits a picture | `mado/core/models.py` |
| The plan: shape, way, model, honest warning | `mado/core/recipe.py` |
| Tiles, and where each tile's result lands | `mado/core/tiles.py` |
| Format, quality and about how big | `mado/core/quality.py` |
| Time, from this PC's speeds | `mado/core/estimate.py` |
| Sessions on the card or the processor, and the one lock | `mado/directml.py` |
| The models' files and where they run | `mado/ai.py` |
| Through the model a tile at a time, and without AI | `mado/upscale.py` |
| Extending edges with LaMa | `mado/extend.py`, `mado/core/outpaint.py` |
| Making and saving, a job's work | `mado/making.py`, `mado/encode.py` |
| The jobs, one at a time with progress and Cancel | `mado/jobs.py` |
| The API | `mado/api/making.py`, `mado/api/jobs.py` |
| The Size tab, the stage, Save | `app/src/features/picture/` |

## The models

| Model | For | File | Licence | Ships |
| --- | --- | --- | --- | --- |
| Real-ESRGAN general (`realesr-general-x4v3`) | Fast, photos and drawings; cleans noise and JPEG blocks | 4.9 MB | BSD-3-Clause | inside Mado |
| Its weak-denoise twin (`realesr-general-wdn-x4v3`) | Fast with "Clean noise and blocks first" off: keeps grain | 4.9 MB | BSD-3-Clause | inside Mado |
| RealESRGAN x4plus anime 6B (`realesrgan-x4plus-anime-6b`) | Best for drawings, comics and flat colour | 18 MB | BSD-3-Clause and Apache-2.0 | inside Mado |
| RealESRGAN x4plus (`realesrgan-x4plus`) | Best for photos | 67 MB | BSD-3-Clause and Apache-2.0 | downloaded the first time Best is asked for on a photo |
| LaMa (`lama_fp32_dml.onnx`) | Extending edges | 209 MB | Apache-2.0 | downloaded the first time Extend is asked for |

They're Real-ESRGAN's official weights exported to ONNX (opset 17, full precision) and checked
against PyTorch, and LaMa's ONNX export reshaped to run on DirectML (its 5-D MatMuls folded to
4-D); the downloads are Mado's own release
[`models-1`](https://github.com/frankgrobbelaar/mado/releases/tag/models-1), each listed in
`downloads.json` with its size and SHA-256 and its licence files beside it. The shipped ones and
how they were made: `engine/src/mado/assets/README.md`.

Which one: pixel art (a small picture of few colours, or one made bigger by repeating its pixels)
grows by repeating its pixels, no AI; a screenshot (named so, or a screen-sized lossless picture
mostly of flat colour) is resized smoothly with a touch of sharpening, so no letters are
invented; everything else is a photo (a camera in its EXIF, or grain) or a drawing (much of it
flat colour), made with Fast or Best. Mado guesses; the owner can say otherwise ("Change" on the
Size tab). A picture already bigger than the size made is only made smaller (Lanczos).

**Faces.** GFPGAN, the shortlist's face model, can't ship: its licence carries NVIDIA's
non-commercial terms and CC BY-NC-SA parts. A face finder with the gentler model on faces is the
other way, but every face model worth having needs real faces to test on, and Mado's tests never
use a real person. So "Keep faces natural" is left out until 1.2's face restoring, which brings a
licence-clean face model with made-up faces to test it.

## Measured on the owner's PC

GTX 1660 Super 6 GB, i5-9600K, onnxruntime-directml 1.24.4 (its newest), 2026-11-22. Seconds for
a megapixel of tiles, the unit Mado keeps (`mado/core/estimate.py`'s `GUESS`, and each PC's own
once tested):

| Model | Card | Processor |
| --- | --- | --- |
| Real-ESRGAN general (and its twin) | 0.59 | 12.6 |
| x4plus anime 6B | 2.49 | 38 |
| x4plus | 7.40 | 128 |

A made-up 12-megapixel photo (4032 × 3024) made for TV 8K (7680 × 4320), end to end with saving
(decoding, the model a tile at a time, laying each tile in, a JPEG at 95): Fast 10 s, Best 87 s.
Extended to a 4K monitor's shape with LaMa: 2 s (4 s the first time, as LaMa's session is made).
The PC check (`mado check-model --time`, from the bundled engine) takes 10 s and times the three
models above within a few percent of the table.

## DirectML's rules

Tested on the owner's PC (the models agent, 2026-11-22) and kept by `mado/directml.py`:

1. **One call at a time.** Two threads making or running sessions at once can crash the graphics
   driver, so every DirectML call is made under `LOCK`, a tile at a time.
2. **Never let a session go.** Releasing one session crashed another still in use, five times out
   of five. A session, once made, stays until the engine ends (`Sessions`), and the PC check, which
   makes and drops its own, runs in a process of its own (`mado check-model`) that ends with
   `os._exit` so nothing is let go on the way out.
3. **Fixed sizes, kept per size.** A session with every free dimension pinned
   (`add_free_dimension_override_by_name`: batch, height, width) is fused into one compiled graph
   and runs faster; its first run compiles for that size (1 to 8 seconds). So the models only ever
   see one tile size each, and the sessions are kept per model and size.
4. **The high-performance card**, asked for with `performance_preference`, so a laptop with two
   uses its own card, not the processor's graphics.
5. **Never a quiet fall back.** ONNX Runtime falls back to the processor when DirectML can't start;
   Mado refuses that where the card should run a model ("it needs DirectX 12"). A PC whose card
   can't run them (the PC check found so) gets sessions on the processor, and every screen says
   the time there, not the card's.

## Tiles

A model sees one square at a time (512 px for the light models; 256 for the heavy ones on a card
with less than 8 GB of its own, where a 512 tile takes over 4 GB; 256 everywhere on the processor,
so progress and Cancel come often). Tiles overlap by 32 px (16 at 256), the last one pushed back to
end at the edge. Each tile's result, four times bigger, is resized straight to the size made with
Lanczos (Pillow's resize with a box, to the fraction of a pixel) and faded into place across the
overlap, a band of rows at a time: the picture four times bigger is never held whole, so an 8K
picture from a 12-megapixel photo needs a few hundred megabytes, not gigabytes. The model runs a
tile ahead on its own thread while the last is laid in, so the card and the processor work at
once (Fast for TV 8K went from 15 s to 10 s). A picture smaller than a tile is padded by
mirroring. Measured on Best's 8K result, no seam steps more than a level of brightness in flat
water.

## Extending edges

LaMa draws what's missing in a 512 square from what's around it, and well only when it sees the
whole scene: squares that saw a third of a 3024-pixel picture each came out grey and smeared. So
the canvas (the picture in the middle of the size's shape) is drawn on a copy whose short side is
512, in squares that span it, each a quarter new edge and three quarters what's there, stepping
outward; then the drawing is made the canvas's size and laid in only where the canvas was empty,
its colours matched to the picture's all along the join (fading out over a few reaches), fading in
from the picture's own smoothed edge, with grain like the picture's. The picture itself never
changes. What's drawn is soft: it carries skies, walls, water and grass on (on the made-up harbour
it even carried the row of boats on), while faces and busy detail at an edge smear, and the Size
tab says so before it's chosen. A picture with see-through parts gets new edges as see-through as
its own edge beside them: a sticker's nothing stays nothing, a solid picture's new edges are
solid. The canvas is whole pixels reaching just past the size's shape on every side
(`extend.canvas_around`), so a shape that falls between pixels (4000 × 3000 at 16:9 is 5333.3
across) is always inside what's drawn.

## Saving

A look chosen on the Looks tab is made after the size, at the size made, before saving; a new
picture's name then says both ("Harbour at dusk (TV 8K, Warm film).jpg"), and a job's stage says
"Giving it its look" ([looks.md](looks.md)). The format stays as it was when Mado writes it (JPEG, PNG, WebP, AVIF: CLAUDE.md, "The format
stays unless another is chosen"). Otherwise it suits what it's for: photos as JPEG (90 for a
phone, 92 for a laptop or monitor, 95 for a TV or a print), drawings, pixel art and screenshots
as PNG (`mado/core/quality.py`); JPEG XL waits for a writer Mado can ship. A picture with
see-through parts is never JPEG unless the owner asks, and then they're flattened onto white
(`encode._flattened`), never onto the colour hidden under them. Before growing such a picture,
its colours are carried into the see-through parts from the nearest it shows (`upscale.bled`,
pushed down and pulled back up), so the model and the resize don't pull that hidden colour, often
black, into its edges as a fringe; what shows, even faintly, stays as it is. The date taken and
the camera come over in the EXIF, turned
upright, the new size in it and the old thumbnail out; the location only when kept (off by
default, Settings › General). The colour profile comes over (a phone's Display P3 included: Mado
reads a HEIC's own profile from its layout); not kept, the colours are turned into sRGB, never
just stripped. Prints say 300 dpi. A picture is written beside its place (`.mado-partial`),
opened again whole and checked for its size, then put in place: a new name beside the original
("Harbour at dusk (TV 8K).jpg", "(2)" when taken) or a folder chosen, or the original's place,
the original set aside in quarantine on its own drive first and put back if anything fails.
History's line (`mado/history.py`) is written before any picture moves, naming where the original
goes, so a job cut short while saving (Mado closed, Windows shutting down) is finished or taken
back from it as the engine next starts (`jobs.recover`): done when its picture was in place,
otherwise the original put back and the line forgotten. Cancel works up to saving, never during
it. History takes a new picture away or puts an original back, and does it again ("Put it back",
"Replace it again"); a picture changed twice is undone newest first, as putting back an older
change would set aside the newer one's picture as if it were the made one. The daily clear-out
deletes what waited in quarantine more than 30 days, apart from a drive that isn't connected
(Windows reports nothing missing there, so it waits for the drive), and History says whether the
days or the owner cleared each picture out. A restored backup cancels the jobs it was waiting on:
making one again could replace what was made since.

## Gotchas

- `get_providers()` lists `CPUExecutionProvider` after `DmlExecutionProvider` even when every node
  runs on the card: it's there for nodes DirectML doesn't take. Check for DirectML's presence, not
  the list's length.
- ONNX Runtime's Windows builds report use to Microsoft unless told not to:
  `ort.disable_telemetry_events()` before the first session.
- The models are loaded only when first needed (`mado/directml.py` imports `onnxruntime` then), so
  the engine starts sooner and starts even where they can't load.
- Tests run the shipped Fast model on the processor on tiny made-up pictures; DirectML is never
  needed in CI (its runners have no graphics card).

## Upgrading

Look for a newer `onnxruntime-directml` (its builds lag plain ONNX Runtime's; 1.24.4 was the
newest on 2026-11-22) and newer Real-ESRGAN and LaMa weights at each update. A newer one is
measured on the same made-up pictures and timed before it's taken (see "Updating dependencies" in
[development.md](../development.md)); a new model export goes in a new `models-N` release, with
its `downloads.json` entry, the notices, this page and the README's "The AI inside" in the same
commit.
