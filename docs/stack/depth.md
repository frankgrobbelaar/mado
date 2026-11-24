# Depth (portrait blur, fog, tilt-shift and 3D photos)

The Depth tab reads how far away each part of a picture is, once, with Depth Anything V2 Small,
then blurs it as a lens would (portrait blur), hazes it with distance (fog), keeps a band in focus
as a miniature looks (tilt-shift), or makes a 3D photo: a short video of the picture with the view
moving gently through it by its depth. The three tools are a step of the picture's one recipe,
made by the same Save as the size and the look; a 3D photo is a video, made into the cache, played
on the page and saved on its own. No board draws them: the tab is the Fix tab's patterns.

| Part | Where |
| --- | --- |
| The depth step and its words; the model's square, nearness, a flat picture; placing it on what's made; the lens blur in layers and its join; fog; tilt-shift's band | `mado/core/depth.py` |
| A 3D photo's path, finding each frame backwards, what the view uncovers, its size, the encoders' commands | `mado/core/motion.py` |
| Reading depth and keeping it (`cache/depth`); the tools worked out on a copy and joined at full size | `mado/depth.py` |
| Making a 3D photo: the layer behind filled, the frames, ffmpeg or an animated WebP, saving | `mado/motion.py` |
| The model's session | `mado/ai.py` (`depth_reader`, `subject_finder`) |
| The subject's mask, as Cut out finds it, empty when the model isn't sure there's one | `mado/editing.py` (`Editor.subject`) |
| The API | `mado/api/depth.py`, `mado/api/motion.py`, `mado/api/making.py` |
| The tab, its stage, the 3D photo | `app/src/features/picture/depth-tab.tsx`, `depth-stage.tsx`, `depth.ts`, `motion.ts` |
| Depth as a batch's step | `mado/core/batch.py`, `app/src/features/batch/` |

## The model

| Model | For | File | Licence | Comes | Runs |
| --- | --- | --- | --- | --- | --- |
| Depth Anything V2 Small (`depth-anything-v2-small`) | How near each part of a picture is | 99 MB | Apache-2.0 | downloaded the first time depth is asked for (`models-2`) | the card while it has room for it (it keeps 0.4 GB there), else the processor |

onnx-community's conversion of the authors' weights, byte for byte (its SHA-256 in `downloads.json`
and the release notes). Only the Small size: Base, Large and Giant are CC-BY-NC-4.0.

It reads the whole picture squeezed to one fixed 518 × 518 square, as SAM squeezes to 1024, its
size pinned through free-dimension overrides (`batch_size`, `height`, `width`), so one session
serves every picture of any shape. Measured on made-up scenes with known depth (`tests/depth_scenes.py`):

| How it's read | Rank correlation with the truth | Error at depth edges | Card | Processor |
| --- | --- | --- | --- | --- |
| Squeezed to 518 × 518 (Mado's) | 0.994 to 0.996 | 0.042 to 0.048 | 67 ms | 0.48 s |
| Its shape kept, short side 518 (924 × 518 at 16:9) | 0.991 to 0.995 | 0.046 to 0.054 | 130 to 156 ms | 0.87 to 1.2 s |
| Squeezed to 700 × 700 | 0.991 to 0.994 | 0.052 to 0.061 | 160 ms | 1.1 s |

The square was as good or better on every scene, twice as quick, and one session (sizes kept per
shape would each hold their share of the card for good). The model's numbers grow the nearer a
place is, at a scale of its own; Mado makes them 0 (the farthest) to 1 (the nearest) by the
picture's own 2nd and 98th percentiles, and keeps them in the cache as a 16-bit picture by the
picture's version and its edits (`cache/depth`, as the edits' masks are; gone after a month
unused, read again when gone). The previews and Save use the same.

**A flat picture.** A scan or a screenshot has no depth to speak of: the model's numbers spread
little for their size (2nd to 98th percentile over their mean, under 1.2) and never jump (the 99.5th
percentile of their change from pixel to pixel over their mean, under 0.03). On made-up pictures a
page (0.98 and 0.011) and a screen (0.62 and 0.008) are flat, the field (2.96, 0.24), the harbour
and a cartoon (1.99, 0.027) aren't, and a subject before a wall has an edge however little the
numbers spread. A screenshot or pixel art (by what Mado takes the picture for) is flat too. The tab
says so; the tools still work.

## Portrait blur

What's farther or nearer than the point in focus blurs as a lens's does: the circle each point
blurs to grows with how far its nearness is from the focus's (a lens's circle grows with the
difference of inverse distances, which the model gives), up to 3% of the picture's shorter side at
f/1.4 for a whole nearness away, f/2.8 half that, f/16 a tenth. In focus at the subject (u2netp at
Fast, BiRefNet lite at Best, as Cut out finds it: the middle of what it's sure of), or where the
picture is clicked; with no subject, where Mado found the most to look at.

It's made in layers by nearness on a copy 1024 pixels across (a blurred place has no fine detail
to lose): twelve at most, nearest first, one exactly at the focus (so what's in focus is never
blurred by a share of a neighbour layer); each layer blurred by its own disc (two boxes when it's
small, a disc on a smaller copy when it's big), what's behind a nearer layer carried on under it
from the layer's own colours (so the background never takes the subject's colour), and a layer in
focus left to the picture itself. Bright, small places (a lamp, the sun, a glint: bright, and
little of what's round them bright) are made brighter before they're blurred, so they bloom into
round discs as a lens draws them; a pale sky doesn't. Then it's joined with the picture at its own
size a band of rows at a time: the picture's own pixels where it's in focus (under what's blurred
in front of it), the blur elsewhere.

**Edges.** The model's edges are soft, so they're made to follow the copy's own edges (a guided
filter), and the subject's mask (refined to the picture's edges at full size, as Cut out's is;
hair as well as the mask allows) gives the subject its own nearness inside it and what's behind it
round it, so its edge stays sharp and the blur behind it never smears it. A part of the mask that
isn't as near as the subject (a cut-out model also picks a sun) isn't kept with it. The mask is
made firm first, all the subject above 70% and none of it below 30%: U²-Net's jumps from about a
quarter to four fifths at an edge the picture draws crisply, then fades on for some pixels each
side, and taken as it was, the ball's rim on the made-up field came out blurred over 15 pixels at
12 MP and a dark halo grew round it. On the copy, a pixel the subject's edge crosses is all the
subject's, so none of its colour is blurred into what's behind it (`tests/test_depth.py`).

**Edit's "Blur what's behind it"** blurs everything outside a part picked by the same amount, a
disc 1.2% of the shorter side, with no depth: the even blur of a backdrop. Kept apart from
portrait blur, as they answer different pictures: the even blur suits a part on a flat backdrop, a
drawing or a screenshot, where depth means nothing, and needs no 99 MB model; portrait blur
suits a scene, where a lens's blur grows with distance in front and behind. Made one, Edit's would
need the model and change what saved recipes make. The tab's words say the difference.

## Fog

Haze that thickens with distance: each point shows `exp(-3.2 × density × far²)` of itself, `far`
being one less its nearness, so the near stays clear (a twelfth of the picture nearest gets under
2% haze at density 60%) and the farthest fades nearly whole at full density. In the picture's own
haze (the light of its farthest twentieth, made paler, as distance makes a sky or a far hill) or a
colour (Mist, Warm, Cool). Made in linear light, at full size, by the depth's edges as they follow
the picture's.

## Tilt-shift

A band kept in focus, dragged into place on the picture (its edges dragged to make it taller), and
blur growing up and down from it, to its most (2% of the shorter side at full strength) at the
farther of the top and the foot; colours made 12% richer, each pixel's light kept, as a model
town's paint is. **By place, not by depth**: rendered both ways on made-up scenes (rows of little
houses seen from above, the field), by place read as a miniature on both, as a tilt-shift lens
seen from above makes one; by depth, the band becomes a focus distance, portrait blur's job, and on
the field it blurred the ball in the band. By place it needs no depth: it works before the model's
downloaded and on a flat picture.

The band is placed on the whole picture, where it's dragged on the Depth tab's stage, and made
through whatever the size step keeps of it (`span_of`): cropped for a screen, the band stays on the
same part of the picture and the blur still grows to its most at the picture's top or foot. Taken
as fractions of the crop, it moved and thinned. The stage's focus and band each have a handle the
keyboard moves (the arrow keys; Shift for bigger steps; the band's left and right make it shorter
or taller), and with portrait blur on too, a click inside the band chooses what's in focus while
the band moves by its edges and its grip.

## Where they live

A tab of their own, not touches in Looks: they need the depth model and the card; portrait blur
takes a click on the picture and tilt-shift a band dragged on it, where the Looks stage's clicks
pick a part; the Looks tab's small copies would each need the depth read; and the touches are
drawn by code, always there. So the Depth tab holds the three and the 3D photo, sharing the model,
its download, and what it read (flat, the subject).

## In the recipe

The depth step comes after the size and before a painting style and the look
(`{"portrait": …, "fog": …, "tilt": …}`): made at the size made, so the upscaler sees the picture
sharp and the lens's blur is drawn at the picture's own detail; before the painting, as a lens and
the air come before a painter paints what they saw (a painting blurred afterwards would look like
a photograph of one, its brush strokes smeared); the look grades the fog with the rest. The depth is read from the picture as
its edits leave it and placed as the size step places it (cropped, or on an extended canvas where
what's at its edge carries on). A preview of all of it is made from the fitted picture; a part at
full detail is joined to the blur worked out on the whole, so it matches the picture saved. A new
picture is named after them ("Harbour at dusk (Portrait blur).jpg"; "Depth" for more than one),
and History's `depth` column (migration 13) says "portrait blur at f/2.8, fog and tilt-shift". A
batch's Depth step has each picture in focus at its own subject; the band is the same fractions on
every picture.

## 3D photos

A short video of the picture: a slow push in and back out, a sway from side to side, or a circle,
3, 5 or 8 seconds at 30 frames a second, round and round (every path comes back where it started).
What's as near as the subject stays put; nearer things move one way and farther ones the other,
up to 3.5% of the shorter side at full amount, and the whole is made a little bigger so the frame's
edges never show past the picture.

Each frame is found backwards: where each of its points came from in the picture, found again a
few times by the nearness where it was last found, on a grid three pixels apart and made the
frame's size smoothly; the picture's colours there. Where the view uncovers what near things hid,
the frame is stretched (a point takes little of its own area from the picture) or never settles;
there it shows a layer behind: the picture with the near things' edges filled from farther away,
and its nearness that of what's behind them, so it moves as the background does. It's filled
three times as far into a near thing as the view moves, so what fills the part the view can
uncover is nearer what's farther than the near thing's own colours: filled only as far as the view
moves, a red post's edge came out as red as the blue ground behind it at Fast and purple at Best
(`tests/test_motion.py`). Fast stretches what's round it in (carried in by halving and pulled back
up, then smoothed); Best draws over that with LaMa, a square at a time, so a square never takes
the near thing's colours from the next. Frames are made four at a time and handed to ffmpeg as
they're made.

**The encoder.** The LGPL ffmpeg build Mado downloads has `h264_mf`, `h264_nvenc`, `h264_amf`,
`h264_qsv`, `h264_d3d12va`, `h264_vulkan` and `libopenh264`. Mado tries Windows' own (Media
Foundation's) first, then NVIDIA's, AMD's and Intel's, a fifth of a second of grey with each, and
keeps the first that works for the engine's life; never OpenH264, whose patent licence covers only
Cisco's own builds. On the owner's PC that's `h264_mf`. H.264 in MP4, 4:2:0, at 12 Mb/s for 1080p
(40 at 4K), ready to play as it loads. With no ffmpeg yet, the tab offers it (77 MB); with no
encoder that works, an animated WebP (Pillow, no ffmpeg), which the tab says; an encoder found is
kept for the engine's life, none found is looked for again next time. No GIF: its 256 colours
band a photo's skies, its files are several times a WebP's, and an animated WebP plays wherever a
picture does.

**Colour.** A video has no colour profile, so the frames are made in sRGB first (a camera RAW
developed into Display P3, a phone's HEIC, turned by the picture's own profile; taken as they
were, they came out dull), turned to video's colours by HD's own matrix (`scale=out_color_matrix=
bt709:out_range=tv`; ffmpeg's default is SD's) and tagged so: `h264_metadata` writes HD's
primaries and matrix, sRGB's curve and video's range into the stream itself, as `h264_mf` writes
none of `-colorspace`'s tags (ffprobe read them as unknown).

**ffmpeg's end.** What ffmpeg says is read as it says it, on a thread of its own, so a talkative
one never waits on Mado while Mado waits on it. An encoder that refuses the frames (on Windows a
write to a pipe it closed raises `EINVAL`, not a broken pipe) is told in its own words; whatever
goes wrong, ffmpeg is stopped and no part of the file is left (`tests/test_motion.py`).

**Sizes.** The video keeps the picture's shape, its longer side 1920 (1080p) or 3840 (4K, offered
only when the picture has that many pixels across: more would only stretch it), never bigger than
the picture, each side even. An animated WebP is 1280 across at most, as its files grow fast. A
picture past 100 megapixels isn't read: the Size tab makes a smaller copy first.

**Saving.** It's made into `cache/motion` (the newest few kept, cleared as the engine starts),
played on the stage, and saved only when the owner says: beside the picture or into a folder
picked ("Harbour at dusk (3D photo).mp4", "(2)" when taken), written beside first under a name of
its own and moved in, one save at a time, History's line ("into a 3D photo, swaying for 5 s")
written before it moves, so History takes it away and puts it back as any picture made. A folder
that's gone (its drive unplugged) is said, never made again. It stays made while the page's other
tabs are looked at; another picture, or this one changed, lets it go, and one stopped or let go
leaves no file. The picture itself never changes. A batch doesn't make
3D photos: a batch's saving, See it first, what it takes and History all work on pictures, and
each 3D photo wants its motion and what it uncovers looked at before it's kept.

## The small things

| | |
| --- | --- |
| The model to download first | The tab's card says what it's for and its size (99 MB), with its progress; tilt-shift works meanwhile |
| The card busy with the queue | "Waiting for the graphics card: Holiday prints lets it go after the tile it's on": reading depth waits at most a tile |
| A huge picture | Read from a copy at the model's square, so it's read in moments; Save says how long its tools take from 40 megapixels; past 100, the Size tab first |
| A flat picture | Said, with tilt-shift still working; a 3D photo barely moves |
| No subject | In focus where Mado found the most to look at, till a click says where |
| See-through parts | Kept as they are; a video has none, so they show on black |
| Grey pictures | Kept grey, unless the fog has a colour |
| No ffmpeg, or no H.264 encoder | ffmpeg offered; with no encoder, an animated WebP |
| A video too big | 4K at most, and only when the picture has the pixels; its size said before it's made |

## Measured on the owner's PC

GTX 1660 Super 6 GB, i5-9600K, onnxruntime-directml 1.24.4, 2026-11-24, the card and the processor
otherwise idle (checked before each run), through Mado's own code on a made-up 12-megapixel field
(4032 × 3024; `tests/depth_scenes.py`). Medians after a first run.

| | Card | Processor |
| --- | --- | --- |
| Reading its depth | 0.14 s | 0.52 s |
| The subject (u2netp, Fast) | 0.76 s | 0.76 s |
| Card memory the depth session keeps | 0.4 GB | |

| At 12 MP, on the card | Time |
| --- | --- |
| Portrait blur at f/2.8 | 4.0 s |
| Portrait blur at f/1.4 | 4.6 s |
| Fog at 60% | 2.0 s |
| Tilt-shift | 3.9 s |
| All three | 7.3 s |

Their crops before and after (the ball's edge, the far hills, the sun) were looked at for each.

| A 5-second 3D photo of it | Time | File | Card memory added |
| --- | --- | --- | --- |
| 1080p (1920 × 1440), push in, Fast | 54 s | 1.9 MB | none |
| 1080p, sway, Best (LaMa) | 61 s | 1.6 MB | 1.0 GB |
| 4K (3840 × 2880), circle, Fast | 3.7 min | 23 MB | none |
| Animated WebP, 1280 × 960, push in | 42 s | 1.5 MB | none |

Most of a frame's time is sampling the picture where each point came from: 0.57 s a frame at
1920 × 1440 on one thread, four made at once. The made-up field is smooth, so `h264_mf` used far
less than its 16 Mb/s there; a photo's detail takes more of it, which the tab's "about" says.

**What fills what's uncovered**, measured on the made-up layers whose truth is known (a post before
a board of squares before a wall of stripes, swaying at full amount, 960 × 540): each fill's frame
against the frame made with what's truly behind the post, in the pixels the view uncovered, at a
quarter and three quarters of the way round (PSNR):

| Layer behind | A quarter | Three quarters |
| --- | --- | --- |
| None: the picture only stretched | 16.5 dB | 17.9 dB |
| Fast | 21.9 dB | 20.9 dB |
| Best | 20.7 dB | 21.2 dB |
| Fast, filled only as far as the view moves | 23.1 dB | 18.5 dB |
| Best, filled only as far as the view moves | 15.3 dB | 16.6 dB |

Both fills beat stretching the picture by 3 to 5 dB. Filled only as far as the view moves, Best
drew the post's red into what's behind it, as LaMa takes the near thing beside its square for
what to carry on; filled three times as far, with Fast's stretch round it, it's as good as Fast by
this measure, which rewards a fill that's smooth over one with texture: Best's carries on the board's
squares where Fast's smooths them. Filled further still (six and ten times), a nearer board was
taken for what's behind the post too, and both scored 16 to 18 dB.

## Gotchas

- The model's numbers are inverse depth at a scale of its own: Mado normalises them per picture,
  so "nearness" compares places within one picture, never across pictures.
- Pillow 13 refuses `Image.fromarray(values, "I;16")`: a `uint16` array makes a 16-bit grey picture
  by itself.
- A Windows environment variable set to an empty string is removed, so the tests' fake ffmpeg
  takes `MADO_FAKE_ENCODERS=none` for "no encoder works".
- `h264_mf` takes `-rate_control pc_vbr` with `-b:v`; it settles well under the rate on a smooth,
  drawn picture.

## Upgrading

Depth Anything's newer releases (V3) and bigger sizes are measured on the same made-up scenes
(rank correlation, the edge error, times, the card memory it keeps) before one is taken; a bigger
or non-commercial one never replaces the Small. A new export goes in a new `models-N` release, with
its `downloads.json` entry, the notices, this page and the README's "The AI inside" in the same
commit.
