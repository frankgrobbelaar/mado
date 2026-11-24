# HDR photos (gain maps) and saving as it is

A recent phone's HDR photo is an ordinary picture with a gain map beside it: a smaller picture,
grey or in colour, that tells an HDR screen how many times brighter each part may go. An app that
knows nothing of gain maps shows the ordinary picture; an HDR screen shows the brightness the
camera saw. Mado reads the gain map, keeps it through every tool, writes it again in JPEG and
AVIF, and shows the photo in HDR where Windows has HDR on. All of it is Mado's own code, on Pillow
and NumPy: nothing new ships and nothing is downloaded.

Saving as it is came with it: Save with nothing made saves the picture at its own size in the
format chosen (a camera RAW developed at full size, an HDR photo with its gain map, a HEIC as a
JPEG), always as a new picture.

| Part | Where |
| --- | --- |
| A gain map's numbers in Mado's own terms (`Info`, `GainMap`); Adobe's XMP, ISO 21496-1's numbers and Apple's headroom read and written; the values as gains and back; the renditions | `mado/core/gainmap.py` |
| A JPEG's segments, its MPF, where its gain map is; an Ultra HDR JPEG put together | `mado/core/jpegs.py` |
| HEIF files written box by box: a gain map item alone, an AVIF with a `tmap` item | `mado/core/heif_writer.py` |
| What every tool does to the gain map (size, edits, restoring, looks, painting styles, fixes) | `mado/core/gains.py` |
| The depth tools' gain map, made again from both renditions | `mado/depth.py` (`gains_depthed`) |
| Whether a picture carries one, from its headers; the gain map decoded as stops | `mado/hdr.py` |
| The scan's tag (`pictures.hdr`, migration 15) and the pictures read before it | `mado/library.py`, `mado/scan.py` |
| The view as an Ultra HDR JPEG | `mado/previews.py` |
| Keeping it through a recipe and writing it | `mado/making.py`, `mado/encode.py` (`with_gain_map`) |
| Which formats keep it (JPEG, AVIF), the plan's words, saving as it is | `mado/core/quality.py` (`HDR_FORMATS`), `mado/core/recipe.py` (`asks_nothing`, `hdr_lost`), `mado/api/making.py` |
| The grid's tag, the page's facts, the save dialog's "Its HDR (the gain map)" | `app/src/features/library/thumbnail.tsx`, `features/picture/picture-page.tsx`, `save-dialog.tsx` |
| HDR photos made by code for the tests | `tests/hdr_files.py` |

## Which gain maps

What phones and cameras write now, and what Mado reads:

| Written by | File | The gain map | Its numbers | Mado |
| --- | --- | --- | --- | --- |
| Android's camera (Ultra HDR, Android 14 on) and photo apps exporting it | JPEG | a second JPEG after the picture, listed by the picture's MPF segment and its XMP directory | Adobe's XMP (`hdrgm`), and ISO 21496-1's in an APP2 segment from Android 15 | reads either, ISO's first |
| Apps writing ISO 21496-1 only | JPEG | the same | ISO 21496-1's alone | reads it |
| Apple's camera (iPhone 12 on) | HEIC | an auxiliary picture (`urn:com:apple:photo:2020:aux:hdrgainmap`), HEVC | a headroom in its XMP or the photo's MakerNote (tags 33 and 48); the values linear after the sRGB curve | reads it, its gains made stops |
| Apple's camera (iOS 18 on) and others writing ISO's HEIF | HEIC | a hidden item, with a `tmap` item made from the picture and it | ISO 21496-1's, in the `tmap` item | reads it |
| libavif, browsers and photo apps | AVIF | a hidden AV1 item, with a `tmap` item | ISO 21496-1's | reads it |

Not gain maps, so not this: a camera's 10-bit HEIF in PQ or HLG (shown as ffmpeg decodes it,
as before), and JPEG XL's gain maps (Mado doesn't read JPEG XL yet).

A gain map of a version Mado doesn't know (hdrgm's other than 1.0, ISO's other than 0), made
backwards from the HDR picture (ISO's backward direction, which Mado doesn't keep yet), saying
nothing of how much brighter it goes, or with numbers that make no sense is read as
"unreadable": the picture is shown and saved as it is,
without its HDR, and its page says why under its name ("Its gain map is version 2.0, which Mado
doesn't know yet. Mado shows and saves it as an ordinary picture.").

## Reading

- **From the headers alone.** `hdr.facts` reads a JPEG's first 64 KB (its XMP and APP2
  segments, its MPF), then the gain map picture's own first segments where the MPF (or, without
  one, the XMP directory's length counted from the end) says it starts. A HEIF's are its `meta`
  box: the `tmap` item and its numbers, or Apple's auxiliary item and its XMP or the MakerNote.
  An ordinary JPEG stops at its first segments: nothing more is read. Measured below: the scan
  takes no longer.
- **Kept with the picture's facts**: `pictures.hdr`, 0 none, 1 one Mado reads, 2 one it can't
  (migration 15). Pictures read before it are looked at by the next scan, their headers alone,
  once (`hdr_unlooked`; those in formats that can't carry one are marked at once). A picture's
  page reads them again as the file is now, so a picture saved over since says so.
- **"HDR"** shows where a picture's kind shows: a tag on its tile in the grid (as "RAW") and in
  its page's facts ("JPEG · HDR · 4032 × 3024 · …"), whose tooltip says how far it goes ("up to
  3 stops (8 times) brighter").
- **The gain map itself** (`hdr.read`) is decoded only when a picture is made or its view is: a
  JPEG's by Pillow at a reduced scale where it's bigger than 4096 pixels (`draft`); a HEIF's gain
  map item is written out as a HEIF of its own (`heif_writer.one_item`), decoded by Pillow
  (libavif) in memory for an AVIF, and by ffmpeg for a HEIC (HEVC) from a file in `cache/hdr`,
  deleted straight after. It's turned as its picture's EXIF turns it (a HEIC's `irot` and
  `imir`), so it lies on the picture as shown.
- **As Mado keeps it**: each place's gain in stops (log2 of how much brighter the HDR rendition
  is than the ordinary one), one channel or three, with what the gain map said (`Info`): how far
  each rendition goes past ordinary white (its headroom), the offsets, which rendition is the
  base, and whether the gains apply in the base's colours. A gain map at a quarter of the
  picture's size (the usual) or at its full size is kept at that share: a quarter stays a
  quarter. Any copy is 4096 pixels on its longer side at most: a huge photo's full-size gain map
  is smooth, and a 48 MP photo's quarter is 2016 × 1512.
- **A base that's the HDR rendition** (Adobe's `BaseRenditionIsHDR`; in ISO 21496-1's numbers,
  a base headroom past the other's): its ordinary rendition divides by the gains, as ISO 21496-1
  and libavif have it. Chromium draws it so: a flat grey picture (140) as an HDR base, its gains
  saying the HDR rendition is a stop below the ordinary one on its right half, showed that half
  at 192 on an ordinary screen, where 191.6 was worked out (checked in the shooting script's
  Edge). Mado's tools work on the base, as stored, and the gain map is written again with the
  same direction.
- **A gain map whose pixels won't decode** (its numbers whole), whatever its decoder raises (a
  damaged AVIF item, a frame header claiming billions of pixels), or one that comes out another
  shape than its own (ffmpeg giving one tile of a grid), is no gain map: the picture is shown and
  saved as it is. The view tries it once for each version of the picture. Where a JPEG's MPF
  doesn't lead to a picture, its XMP's directory is tried; a grid's tiles stay hidden as they
  were when its gain map is written out alone. `cache/hdr` is emptied as the engine starts.

## Shown in HDR

WebView2 is Chromium, which shows an Ultra HDR JPEG in HDR on an HDR screen and as its ordinary
picture on any other. So an HDR photo's view (2560 pixels) is made as an Ultra HDR JPEG at quality
88, its gain map the same share of it as of the photo; at 100% a JPEG or AVIF is shown as it is,
and a HEIC's full-size copy is an Ultra HDR JPEG at quality 95. On an ordinary screen everything
looks as it did. The thumbnails stay WebP, and what the tabs show while a tool is chosen is
ordinary: the picture saved keeps its HDR. Mado never turns Windows' HDR on or off.

## Through every tool

The AI models work on the picture alone; the gain map follows it (`mado/core/gains.py`). Each tool
was decided and tested on made-up HDR photos (`tests/test_hdr_tools.py`,
`tests/core/test_gains.py`):

- **Size**: the gain map is cropped, its edges extended (the gain at each edge carried on) and
  resized with the picture, plainly (bilinear): it's smooth.
- **Edit**: where a part is erased, the gain map is filled from round it as the picture is (a
  lamp erased from a wall leaves the wall's gain, not the lamp's), smoothly. Behind a cut-out on a
  colour it's none: a flat colour is the same on any screen. Behind a part blurred (a cut-out on
  the rest blurred, or Blur what's behind it) it's blurred the same way, the part's own gain left
  out of the blur. A cut-out on nothing saves as PNG or WebP, which hold no gain map, and Save
  says so.
- **Looks**: a look grades the ordinary picture and the gain map is kept, so the HDR rendition is
  the graded picture brighter where it was; a colour gain map is made one channel first, as its
  colours would bring back what the look took out (a black and white look stays black and white
  on an HDR screen).
- **Painting styles**: a painter's style, a picture's style, oil paint and cartoon keep the
  photo's light where it was, so the gain map is kept (a lamp painted still glows). A pencil
  sketch, coloured or not, is paper and lines, so its gain fades with the style's strength; at
  full strength on the whole picture there's no HDR left, and Save says so.
- **Restoring**: where scratches and dust are filled, the gain map is filled from round them as
  an erase's is, from the mask restoring filled (a white scratch on a photographed print would
  glow on again on an HDR screen); colouring a black and white picture, or bringing faded
  colours back, keeps it, one channel, as a look does: the light was where it was.
- **Fixes** (noise, blur, JPEG blocks, dark photos, local contrast): the gain map is kept as it
  is. They clean or brighten the ordinary picture; brightening's curve keeps the highlights below
  white, and the gain map opens them up again on an HDR screen.
- **Depth** (portrait blur, fog, tilt-shift): made again from both renditions. The ordinary
  picture and its HDR rendition, at the gain map's size (1024 pixels at most, as the tools work
  out their blur), are each given the same tool in linear light, and the gain between them taken
  again: fog thins the gain with distance as it thins the light, and a lamp blurred into a disc
  glows as a disc.
- **A 3D photo** is an ordinary video, H.264 in sRGB with HD colour tags: the Depth tab says an
  HDR photo's extra brightness isn't kept in it.
- **The wallpaper studio**: Windows shows a wallpaper as an ordinary picture, so the studio stays
  as it is and says so under an HDR photo's choice.
- **Many at once, recipes and watch folders** keep it the same way; a batch's Saving has "An HDR
  photo's HDR (its gain map)".
- **Duplicates and bursts** compare thumbnails, which are the ordinary picture: an HDR photo and
  its ordinary copy are duplicates, as they look the same.
- A gain map left flat (no gain anywhere) isn't written.

## Writing

`with_gain_map` encodes the picture as asked, then the gain map as its own picture at quality 90
(grey, or colour when its gains are in colour), its least and most gains made afresh from what's
there, the curve straight (gamma 1), the headrooms and offsets as the photo had them, ISO's
fractions to a millionth.

- **JPEG** is written as Android writes Ultra HDR, so phones, browsers and Windows read it
  whichever way they look: the picture with its XMP (hdrgm's version and a directory naming the
  gain map by its length), an APP2 with ISO 21496-1's version, and an MPF segment listing both
  pictures; then the gain map with its own XMP (Adobe's numbers) and APP2 (ISO's).
- **AVIF**: Pillow's libavif can't write a gain map through Pillow, so Mado encodes the picture
  and the gain map as AVIFs with Pillow, takes their AV1 items, and writes a new file around them
  (`heif_writer.avif_with_gain_map`): the picture the primary item, the gain map a hidden item, a
  `tmap` item made from both holding ISO's numbers, the two named alternatives (`altr`, the HDR
  one first), and the `tmap` brand. An app that knows no gain maps shows the picture.
- **PNG and WebP** have no room for one. Saved in them, an HDR photo is an ordinary picture,
  and the save dialog says so before Save, under "Its HDR (the gain map)", which is greyed.
- "Keep from the original" has **"Its HDR (the gain map)"**, on by default; off, the picture is
  saved without it.

## Saving as it is

- **On a picture's page**, Save is there before anything is chosen, quiet (secondary) till a
  tool asks for something: the page reads as it did, and the Size tab, while nothing's chosen on
  any tab, says "Save keeps it as it is, in the format you pick; pick a screen or a print to make
  it for one." A separate "As it is" size would have been one more choice among sizes that all
  make something.
- **It's an empty recipe**: no size, edits, restoring, fixes, depth, painting style or look. Steps
  that change nothing (a fix with nothing on) still say so, as before. Its plan, which a picture's
  page asks for as it opens, is made at a glance (`Sight.glance`): from the picture's thumbnail
  and its size as the library read it, so going through pictures decodes none of them whole (a
  camera RAW developed, a huge picture) while another's tools wait.
- **Never replaces the original**, however Saving is set: the dialog doesn't offer Replace and
  says why ("saved as it is, it's a copy in the format you pick, and the original stays exactly
  as it is"); the API refuses it (409). A batch that's just Save turns Replace to a new picture
  and says the same.
- **In the format it's already in**, it saves a fresh copy beside it ("(2)"), and the dialog says
  so; a JPEG starts at the quality it was saved at (read from its quantisation tables), so the
  copy isn't needlessly bigger or worse. A fresh copy is what was asked for: refusing would leave
  the owner nothing to do with a picture whose EXIF or location they wanted gone.
- **A camera RAW** comes out developed at full size, into Display P3 as every tool has it. While
  Mado's RAW reader is still coming, its page says it can be saved as it is once the reader is
  here, and a batch leaves it out till then, saying why, as for any other step.
- **A HEIC** starts as a JPEG (it can't be written as HEIC: no HEVC encoder Mado may ship).
- **Many at once**: a batch can be just Save, changing many pictures' format at once; See it first
  says there's nothing to see first (each copy is the picture itself), and makes none; a recipe
  and a watch folder can be just Save too.
- **History** names it: "Saved Harbour.HEIC as JPEG", a batch "Saved 240 pictures as JPEG";
  Home's card for a batch done, "Saved as JPEG, as new pictures beside the originals".
- **"Always save this way"** isn't offered where Save can only make a new picture (saved as it
  is, a camera RAW, a paste), and the engine keeps no way from such a save: the owner's own
  stays as it was.

## Checked with second readers

- **Pillow's MPO reader** opens what Mado writes as two pictures, the MPF's offsets right.
- **libavif** (Pillow's AVIF reader) opens the AVIF Mado writes; it refuses a `tmap` cut short or
  with a zero denominator, so the tests make it read every AVIF they write.
- **Chromium**, in the shooting script's Edge: the four ways (XMP and ISO, XMP only, ISO only, and
  AVIF's `tmap`) each applied the gain map the same, and an ordinary base's control was unchanged
  on an ordinary screen. This is what found the HDR base's direction.

## Measured

On the owner's PC (i5-9600K, GTX 1660 Super), with made-up photos drawn by code (the dusk scene
with a camera's grain, its gain map a quarter of its size), the medians of several runs. The
ordinary JPEGs compared are the HDR ones without their gain maps, byte for byte otherwise.

**Reading.**

| What | 12 MP | 48 MP |
| --- | --- | --- |
| Whether it carries a gain map, from its headers (`hdr.facts`): HDR, ordinary | 0.3 ms, 0.1 ms | 0.3 ms, 0.1 ms |
| All a scan reads of it (`read_facts`): HDR, ordinary | 0.7 ms, 0.4 ms | 0.6 ms, 0.4 ms |
| Its gain map decoded as stops (`hdr.read`), when it's made | 7 to 8 ms | 23 to 30 ms |

A scan of 1,000 made-up JPEGs (1600 × 1200, their facts read and thumbnails made) took 55.3 and
52.1 s without gain maps and 57.7 and 52.0 s with them, two runs each, turn about: the same,
within the spread from run to run. Reading the headers adds 0.3 ms a picture; the scan's time is
decoding the pictures for their thumbnails.

**Each tool's extra time for the gain map** (its own work beside the picture's; a 12 MP photo's
gain map is 1008 × 756, a 48 MP one's 2016 × 1512):

| Tool | 12 MP | 48 MP |
| --- | --- | --- |
| Size: the whole picture made 8K | 23 ms | 33 ms |
| Size: cropped for a 4K monitor | 9 ms | 18 ms |
| Size: edges extended for a 4K monitor | 11 ms | 26 ms |
| Edit: a part erased, filled from round it | 50 ms | 190 ms |
| Edit: a cut-out on a colour | 21 ms | 81 ms |
| Edit: Blur what's behind it | 81 ms | 322 ms |
| Look: a grey gain map, kept | none | none |
| Look: a colour gain map made one channel | 3 ms | 9 ms |
| Painting style: oil paint (kept), a pencil sketch at 60% | none, 3 ms | none, 9 ms |
| Fixes (kept as it is) | none | none |
| Depth: fog | 0.53 s | 0.71 s |
| Depth: portrait blur at f/2.8 | 2.0 s | 2.3 s |
| Depth: tilt-shift | 3.0 s | 3.2 s |
| Saving as JPEG 92: with its gain map, the same without | 160 ms, 148 ms | 633 ms, 589 ms |
| Saving as AVIF 80: with its gain map, the same without | 765 ms, 702 ms | |

The depth tools are the dear ones: their gain map is the copy-level work of each tool done twice
(once for each rendition, at the gain map's size, 1024 pixels at most), most of it tilt-shift's
and the lens's blurs (`stack_blur`, `spread`). Working it out smaller would blur the gain map's
own detail where the picture stays sharp, so it isn't.

**Saving as it is**, through the engine's API, from Save to the job done:

| What | Time |
| --- | --- |
| A 12 MP JPEG, as JPEG 92 | 0.37 to 0.44 s |
| A 12 MP HDR JPEG, as JPEG 92 with its gain map | 0.45 to 0.48 s |
| The same, "Its HDR" turned off | 0.43 s |
| A 24 MP camera RAW (a made-up DNG), developed at full size, as JPEG 92 | 3.8 to 3.9 s |
| A batch of just Save: 1,000 PNGs (1600 × 1200) as JPEG 90 | 145 s, 0.15 s each |

## Tested only through files made by code

Every gain map in the tests is written by code from drawn scenes: Ultra HDR JPEGs (XMP and ISO,
XMP alone, ISO alone, the gain map at a quarter and at full size, in colour, an HDR base, turned
by EXIF, a version Mado doesn't know), AVIFs with a `tmap` item, and HEICs built box by box around
AV1-coded items (Pillow decodes them) with Apple's auxiliary gain map (its headroom in XMP or the
MakerNote) or ISO's `tmap`. A HEIC whose gain map is HEVC goes through ffmpeg; the tests use
ffmpeg's stand-in there, as no HEVC encoder may be used to make one. No real photo was read.
