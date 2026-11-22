# Looks (a picture's colours and finishing touches)

The Looks tab gives a picture a look at a strength, then finishing touches, and one Save makes
it together with the size the Size tab chose. Every look is a 3D table of colours (a LUT), so
Mado's own, an imported `.cube` file and a mix the owner kept all take the same path: Pillow's
`ImageFilter.Color3DLUT`, in C, each colour mixed from the eight points around it. No AI. The
screen is Picture-Looks on the [Mado Screens canvas](../design/screens.html).

| Part | Where |
| --- | --- |
| A table of colours: identity, strength, sampling, packing it small | `mado/core/grids.py` |
| Mado's looks, made by code; a look's one table and its words | `mado/core/looks.py` |
| Reading a `.cube` file | `mado/core/cube.py` |
| The touches' shapes and numbers (grain's hash, the specks, the leak) | `mado/core/touches.py` |
| The recipe of steps (size, then look) and its plan | `mado/core/recipe.py` |
| Laying a look and its touches on a picture | `mado/looks.py` |
| The owner's looks in the database | `mado/own_looks.py` |
| The API | `mado/api/looks.py`, and `mado/api/making.py` for plans, previews and Save |
| The Looks tab, its stage, Save's foot | `app/src/features/picture/looks-tab.tsx`, `looks-stage.tsx`, `save-section.tsx` |

## Mado's looks

Fourteen, the original first, then the board's eight (Warm film, Cool film, Faded, Teal and
orange, Silver, Golden hour, Night neon, Duotone) and five of Mado's own (Bold colour, Sepia
print, Moody blue, Cross-processed, Soft pastel). Each is a few lines of code on the identity
grid of 33 points a side: tone curves (a monotone cubic through a few points, so a tone never
turns back on itself), colour pushed into shadows, mid-tones and highlights, saturation and
vibrance, a channel mix, a hue turned round the greys, black and white from chosen shares of red,
green and blue, and light mapped through colours for the toned ones. Silver stays exactly grey.
A test keeps every name clear of film brands, camera makers and apps' filter names.

A look at a strength is its table mixed with the identity table: for a look that only changes
colours, that's exactly the same as mixing the pictures. Fade, the one touch that only changes
colours, goes into the same table, so a picture goes through one table, once.

## What a `.cube` file may be

| Read | As |
| --- | --- |
| 3D tables as the format allows (2 to 256 points a side), in a file of up to 100 MB, which holds about 129 | as they are up to 65 points; bigger ones sampled down to 65, the most Pillow takes |
| 1D tables of 2 to 65,536 points | a 3D table of 65 points |
| `DOMAIN_MIN` and `DOMAIN_MAX`, `LUT_3D_INPUT_RANGE`, `LUT_1D_INPUT_RANGE` | sampled to cover 0 to 1 (inputs outside the range take its edge) |
| `TITLE` | the look's name; else the file's, cut to fit with "(2)" when it's taken |
| Values outside 0 to 1 | held to it, after sampling: Mado's pictures are 8 bits a channel |
| UTF-8, or UTF-16 with its mark; comments anywhere; spaces or tabs between words | |

Refused, each with a sentence: a file that isn't text or has no table, a table whose size isn't
said or is out of range, rows that are missing or aren't three numbers (the line is named), a
number that isn't one, a keyword Mado doesn't know (`LUT_IN_VIDEO_RANGE`, say), a keyword after
the rows, a 1D table before a 3D one (Resolve's shaper: "export it as one 3D table"), a range
whose minimum isn't below its maximum, and a file over 100 MB (a 129-point table is about 60 MB).

## Your looks, kept small

A look the owner keeps is a row of `looks` (migration 4): its name (unique in any case, never one
of Mado's), whether it's a `.cube` file or a mix, its table's points a side, where it came from,
a mix's touches, and the table itself packed: each value in 16-bit steps, kept as its difference
from the one before it along red, zlib'd. A smooth 65-point table packs to about 50 KB where its
`.cube` file is 7 MB; a 33-point one to about 10 KB. A kept mix is its look at its strength made
into one table, so it never changes under the owner if Mado's look does, or the look it came from
is deleted. A look's number (`yours-3`) is never given to another (`AUTOINCREMENT`), so a job
that names one deleted since fails with a sentence rather than making another look. Names are
compared by Python's `casefold`, not SQLite's `NOCASE`, which folds only A to Z ("Été" and "ÉTÉ"
are one name). The export lists them in `looks.json` and writes each as a `.cube` file another
app opens (`looks/Holiday warm.cube`); backups carry the database as it is.

## Finishing touches

Grain, vignette, glow, fade, light leak and dust, each 0 to 100 and off by default, all drawn by
code. They're placed and sized in the picture made, relative to its short side, and grow from a
number the picture gives (`seed_of`, its path), so a preview the size of a screen shows the touches
the picture saved at full size gets: the same grain, the same specks in the same places
(`Placement` says where a preview, or a part of one at full detail, sits in the picture made).
They go on after the look, at the size made, so grain and dust never grow into blobs.

| Touch | How |
| --- | --- |
| Grain | a field of specks, 1,400 across the short side, each a fixed number for its place (a hash), smoothed to the pixels; the same in red, green and blue, strongest in the mid-tones; added a band of rows at a time |
| Vignette | darker towards the corners, softly, worked out on a small grid and multiplied in |
| Glow | the bright parts of a small copy, blurred as far as 2.5% of the short side, screened over |
| Fade | black lifted and white brought down, in the look's table |
| Light leak | warm light at the left or right edge, as the picture's number says, screened over |
| Dust | specks of uneven outline and the odd hair, light (a scan of film) or dark (a print), drawn last |

A preview's grain is kept for the next look tried on it. Two tests hold the promise: a preview
the size of a screen against the saved picture made smaller (within 1.5 levels on average), and
a part at full detail against the same part of the whole (within 2 levels).

## Colours, see-through parts, grey pictures

A look works on the picture as Mado reads it, 8 bits a channel (a 16-bit picture comes in as 8,
as the Size tab makes it), on its colours as they're stored, in its own colour space, and the
colour profile stays with it: a phone's Display P3 photo is warmed in P3 and saved with P3, so
its wide colours stay wide. A `.cube` made for sRGB looks a little stronger on a wide picture than
on an sRGB one, which is the price of not flattening it. See-through parts are left exactly as
they were (Pillow's filter keeps alpha, and the touches only touch colour). A grey picture stays
grey unless its look or touches give it colour (Silver, grain and a vignette keep it grey;
Duotone doesn't). A picture of few colours (a GIF's palette) is read as RGB, so a look can give it
as many as it likes, and it's saved as a full-colour picture.

## Previews

- **The small copies**: each look's from the picture's thumbnail (made as the library reads it;
  asked for all at once, it's made once), 256 px, WebP with the picture's colour profile, kept
  by the window, as their addresses carry the picture's and the look's versions (a look's is a
  checksum of its table).
- **The big preview**: the picture made, fitted to the stage, from the screen-sized view (cut as
  the Size tab's crop says; from the picture itself when the view has fewer pixels than asked
  for; an extended canvas from LaMa's drawing), with the look and its touches. The picture with
  its look and without are asked for together, and what they share is made once (`Sight`);
  asked for once the look stops changing (150 ms), an answer to an older ask dropped, the last one
  shown while the next is made. The fitted picture is kept, so the next look is only the look.
  It comes as JPEG at 92 with full colour detail (WebP when it has see-through parts): WebP took
  166 ms to write a grainy screen-sized picture where JPEG takes 7.
- **Hold to see the original**: the picture without its look, while the button, Space, Enter or
  the \ key is held.

## Measured on the owner's PC

i5-9600K (the looks run on the processor; the upscaler on the GTX 1660 Super), 2026-11-22, a
made-up 12-megapixel photo (4032 × 3024) through the engine's API:

| What | Time |
| --- | --- |
| All 14 small copies | 0.23 s one at a time (16 ms each); 0.10 s six at a time, as the window asks |
| The big preview (1536 × 1152), the first for a picture | 1.2 s (making its screen-sized view) |
| The big preview, a look alone | 49 ms |
| The big preview, with grain, a vignette and dust | 177 ms |
| The big preview, with all six touches | 249 ms |
| A look's step at 12 MP: the table; with grain, vignette and dust; with all six | 0.23 s; 1.24 s; 1.57 s |
| The same at 8K (33 MP) | 0.62 s; 3.21 s; 4.09 s |
| Saving Warm film at 60% alone, as a new JPEG | 0.57 s end to end |
| The same with all six touches | 1.95 s |
| TV 8K alone on the card (Fast); TV 8K then Warm film with grain, vignette and dust | 11.0 s; 13.7 s |

Before the touches were worked out on small grids and grain's field was kept, a preview with
grain, a vignette and dust took 544 ms.

## Gotchas

- `Color3DLUT` takes a NumPy table of shape (blue, green, red, 3), red changing fastest, the
  order a `.cube` file lists its rows in, and at most 65 points a side.
- It refuses grey pictures: they're made RGB first, and grey again after when nothing gave them
  colour.
- Pillow writes a picture's colour profile only when it's passed in to `save`, not from its
  `info`; previews pass it, so a wide-colour picture's preview shows its colours.
- A sticky element in a scrolling column sticks inside the column's padding; Save's foot is
  pinned past it (`-bottom-4`).
