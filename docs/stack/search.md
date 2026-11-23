# Search (by describing a picture, by the words in it, and More like this)

How the Library's search box finds pictures by what they show and by the words in them, as well as
by name, and how a picture's page finds the ones most like it. The library is read in the
background, as duplicates are looked for ([duplicates.md](duplicates.md)); nothing in a picture
changes, and nothing leaves the PC. No board draws search's results or its reading: they're drawn
in the Library grid's own pattern, and Settings' panels'.

| File | Does |
| --- | --- |
| `mado/core/search.py` | Pure: a search as SigLIP reads it (canonical, 64 tokens), its score and the cut, ranking, More like this, a search's language and writing, which reader reads words, word queries for FTS5 and the words marked |
| `mado/core/ocr.py` | Pure: PP-OCRv6's pre- and post-processing, ported from RapidOCR (Apache-2.0, `LICENSE-RapidOCR.txt` beside it): the detector's canvas, lines from its map, each cut out straight, the recogniser's input and its answer decoded |
| `mado/siglip.py` | SigLIP base: a picture's vector, a search's, on the processor |
| `mado/ocr.py` | The readers of words: Best (PP-OCRv6 through ONNX Runtime, on the card when it has room) and Fast (Windows' own, through pywinrt) |
| `mado/search.py` | The reading thread, the vectors in search.db and in memory, the words in the database, finding |
| `mado/api/search.py` | `/search`, `/search/like/{id}`, `/search/state`, pausing (see [architecture.md](../architecture.md#the-engines-api)) |
| `app/src/features/library/search-results.tsx` | The results in groups, the notes above them, nothing found |
| `app/src/features/settings/search-panel.tsx` | Settings › General › Search: how far reading has got, and the words reader |

## The models

| Model | For | Files | Licence | Where it runs |
| --- | --- | --- | --- | --- |
| SigLIP base, patch 16, 224 (int8) | What a picture shows: a picture's vector and a search's, 768 numbers each | vision 94 MB, text 111 MB, tokenizer 2.4 MB | Apache-2.0 (Google; Xenova's ONNX conversion) | the processor |
| PP-OCRv6 small, detector and recogniser | Best: the words in a picture (Latin with accents, Greek, Chinese, Japanese) | 9.9 MB and 21 MB | Apache-2.0 (PaddleOCR's weights, RapidOCR's conversion) | the card when it has room, else the processor |
| Windows.Media.Ocr | Fast: the words, in the languages Windows has OCR for | Windows' own | Windows' | the processor |

Both downloads are Mado's `models-3` release, listed in `downloads.json` with their sizes,
SHA-256s and licence files, and fetched the first time the library is searched (PP-OCRv6 only
where the words are read at Best). SigLIP replaces CLIP from the scoping's shortlist: on the
round-three scenes it found every scene from a plain description and 98% from a paraphrase, where
CLIP ViT-B/32 found 91% and 83%, at a third of CLIP's 606 MB. SigLIP base was trained on English;
SigLIP 2, which reads other languages, is 378 MB as int8 and was left for later. Python reads its
tokenizer.json with Hugging Face's `tokenizers` (Apache-2.0).

## Reading the library

A thread of its own (`Search`) reads each library picture once the scan has read it, newest file
first, and again once its file changes (by its size and time, as a print is kept); a scan's end,
a model arriving, a change of words reader and the owner's Go on wake it. It never reads a picture
from outside the library, one in a quarantine, one that won't open or is marked as damaged, a
camera RAW still waiting for its reader, nor one on a drive that isn't connected: those keep
what was read of them, so a search still finds them, and their tiles say "Away". A picture that
can't be read now (its thumbnail can't be made, a HEIC before ffmpeg; it's open in another app)
is counted apart ("2 pictures couldn't be read for search") and tried again after the next scan,
or once ffmpeg or the RAW reader comes. A reader that can't run (a model error) says so, in the
Library's notes and Settings, with Try again; reading rests it till then, or the next scan, rather
than try it on every picture, and the other reader reads on.

1. **What it shows**: SigLIP's vision model reads the thumbnail the scan made (512 px, WebP),
   squeezed to 224 × 224, so nothing is decoded twice.
2. **Its words, at Best**: the detector looks first, at the same thumbnail on a 512 × 512 canvas;
   only a picture where it finds text is decoded, 2048 px at most on its longer side, and read in
   full: the detector on a 1280 × 1280 canvas (the picture fitted, the rest padded), each line cut
   out straight and read 48 px high. On the thumbnail, a "line" thicker than a quarter of the
   picture's shorter side is a plain sky or wall the detector took for text, never words (in full,
   a big headline can be that thick, and the detector doesn't take skies for text there); a line
   read as fewer than two letters or digits (a shape read as "1", "O" or "人") isn't kept, at Fast
   too.
3. **Its words, at Fast**: the picture decoded 1280 px at most and read by Windows at twice that
   (Windows misses small print otherwise), 10,000 px at most.

Reading can be paused (kept across restarts) and says how far it has got: pictures read, by every
reader there is now, of the library's pictures that open (those the scan hasn't read yet among them,
as they're to come; those on a drive away once read). The window asks again every few seconds till
it's done, so the count moves between turns and while the scan reads. It takes turns at the card's
one lock (`mado/directml.py`) with the queue and edits, a model's run at a time; while the queue
makes a picture, it rests nine times as long as each turn on the card took, so the queue keeps
nearly all of it.

**Fast or Best**: as this PC suits (Settings › General › Search), Best where the AI runs on a
graphics card, where a picture's words take a third of a second; Fast on the processor alone,
where Best takes two seconds; Best where Windows has no OCR language. A change reads the words
again in the background, the old ones found till then.

## Keeping what was read

| What | Where | Why |
| --- | --- | --- |
| Each picture's words, as read, a line of text to a line, and its terms: folded, each Chinese and Japanese letter a word of its own | `words` (FTS5, `unicode61 remove_diacritics 2`; `text` unindexed, `terms` matched), with `words_read` (the file read, the reader, Windows' language, how many lines) | Small; matched however they're written; in backups and the export (`words.csv`) |
| Each picture's vector | `search.db` beside the database: 768 16-bit floats a picture (1.5 KB), with the file read | Read again whenever it's lost: 207 MB at 100,000 pictures, 21 MB at 10,000, kept out of backups and the export |

`search.db` is read again from the start when it's lost, damaged or of another version, and is
never in a backup or the export: at 100,000 pictures it holds 207 MB that every nightly backup
(seven kept) would copy and check, for numbers reading makes again. A picture's words go with it
when its row does (a trigger), and the vectors of pictures no longer in the library go once
reading has nothing left.

## Finding

The search box's words go three ways at once; each picture shows once, in the first group that
holds it, so a words match shows its words:

1. **With the words**: every word of the search must start a word read in the picture (FTS5's
   prefix query), best matches first (bm25), the matched words bold on the tile. Capitals fold
   away, and the accents of Latin, Greek and Cyrillic letters (Greek capitals go without them),
   both in the terms kept and in the search (`core/search.py`'s `folded`); a mark that makes
   another letter stays (Japanese "ガ" isn't "カ"). Chinese and Japanese are written without
   spaces, and FTS5's unicode61 would take a whole run for one word, found only from its start:
   each of their letters is kept as a word of its own, and a word of them searched for is its
   letters in a row (a phrase), anywhere in a line.
2. **Looks like**: SigLIP's text model reads the search (lower case, no punctuation, single
   spaces, ended by `</s>` and padded with it to exactly 64 tokens, as its tower reads the last
   place), on the processor at once; each picture's score is SigLIP's own, the sigmoid of the
   vectors' product times its learned scale (117.3) plus its bias (-12.93); a picture is shown
   when its score passes 0.01 (a product of 0.071), the closest first. A search for what
   isn't there finds nothing.
3. **In the name**: every word in the file's name, in the list's order.

Each group shows its first 500 pictures and says how many more it found; Many at once and a
picture's neighbours take every one.

Within a folder, or the favourites, as the Library shows. A search in another language (letters
of another writing, or another language's little words with no English one beside them) isn't
described, and says so: SigLIP base reads English. A search in a writing the words reader can't
read (Windows' languages, at Fast; at Best, Cyrillic, Arabic, Hebrew, Korean, Thai, Devanagari)
says so (a writing no reader names isn't). **More like this** is the pictures whose vectors are
nearest a library picture's (their product 0.6 at least, 60 at most), read there and then when it
hasn't been yet, on reading's own session, and only for a picture reading reads. A picture opened
from either has the results' order for its neighbours, and Many at once takes what was found. A
picture that won't open, or is marked as damaged, since it was read isn't found by what was read
of it.

**The vectors in memory**: loaded (as 32-bit floats) when a search comes, kept up to date with
what reading adds, and let go after ten minutes without one, rather than held for the engine's
life: at 100,000 pictures that's 307 MB an engine in the tray would otherwise hold all day,
and loading them again takes 850 ms.

## Measured on the owner's PC

GTX 1660 Super 6 GB, i5-9600K, onnxruntime-directml 1.24.4, 2026-11-23, made-up pictures drawn by
code. Another agent's work shared the card during this round: every timing waited for the card
and the processor to be quiet, and memory on the card is this process's own (DirectX's
`QueryVideoMemoryInfo`), not nvidia-smi's, which counts every process's.

**A picture's reading time**

| Model, at its size | Card | Processor | Card memory kept |
| --- | --- | --- | --- |
| SigLIP vision (224 × 224) | 61 ms | 69 ms (6 threads), 85 ms (4), 106 ms (3), 147 ms (2), 282 ms (1) | 1,116 MB |
| SigLIP text (a search, 64 tokens) | | 18 ms | |
| PP-OCRv6 detector, the first look (512 × 512) | 6 ms | 72 ms | 116 MB |
| PP-OCRv6 detector, in full (1280 × 1280) | 34 ms | 1,115 ms | 570 MB |
| PP-OCRv6 recogniser, a line (48 × 320 / 960 / 2560) | 4 / 16 / 19 ms | 12 / 40 / 91 ms | 34 / 70 / 118 MB |

So SigLIP runs on the processor (no faster on the card, and over a gigabyte of the card's memory
kept for good), and reads the library on two of its six cores: about as little work a picture as
on one, twice as quick, with two-thirds of the processor left to the owner and the queue (a
search's words, and a picture More like this reads there and then, use them all). PP-OCRv6 runs
on the card when it has room for its 910 MB and the queue's heaviest model beside it (`ai.HELD`),
as its detector is 30 times quicker there.

**Words, on the 47 round-three text pictures** (signs at angles, screens, small print, light on
dark, blur, 15 fonts; 40,217 characters of made-up words):

| Reader | Character errors | Words found | A picture |
| --- | --- | --- | --- |
| Best on the card (detector at 1280, recogniser on the card) | 1.1% | 99.5% | 0.34 s |
| Best, recogniser on the processor | 1.1% | 99.6% | 1.37 s |
| Best on the processor | 1.1% | 99.6% | 2.06 s |
| Best, detector at 1024 / 1600 | 1.0% / 1.1% | 99.6% / 99.4% | |
| Fast (Windows' own, en-GB, at 2x) | 5.2% | 93.6% | 0.17 s |

Mado's own port reads as RapidOCR's pipeline did (1.0% and 99.6%). The first look found text in
all 47, in 21 ms on the card (110 on the processor), the thumbnail already made. The first row and
the first look on the card were measured again once the port gave the models blue, green and red
(Gotchas), with the card to itself; the other rows are from before, when it gave them red, green
and blue, which read the same to within 0.02 points.

**The made-up library read** (1,997 pictures: 1,650 landscapes drawn by `tests/drawn.py`'s
`scene`, 1600 × 1200 with no words, the 300 round-three scenes and the 47 text pictures; through
Mado's own engine, SigLIP on two cores, Best on the card; the scan before it took 84 s):

| How | Reading | A picture | Read in full | Found with words |
| --- | --- | --- | --- | --- |
| Best, looking first | 8.5 min | 0.26 s | 196 | 123 |
| Best, every picture in full | 16.6 min | 0.50 s | 1,997 | 124 |
| Fast (Windows' own, en-GB, every picture) | 12.9 min | 0.39 s | 1,997 | 128 |

So the first look stays: it halves the time on a library of photos and missed one picture with words
of 124. Before a "line" as thick as a quarter of the thumbnail counted as a plain sky (Gotchas), it
passed on 1,798 of the 1,997, the read took 20 minutes, and 736 pictures came out with "words",
nearly all of one letter. (These reads held the full reads to the same rule, which may have left a
thick line or two unread there; the rule is the first look's alone now.)

**Recall on the round-three scenes** (300 scenes drawn by code, 30 kinds, 10 of each, read from
Mado's own thumbnails among the made-up library's 1,997 pictures, searched through Mado's own
code): a plain description put a scene of its kind first every time (recall at 1, 5 and 10: 100%),
a few words did too (100%), and a paraphrase ("a striped tower that guides ships along the coast")
98.3% at 1, 99.3% at 5 and 100% at 10. Past the cut, 294 of the 300 by description with 5 of
other kinds let in, 281 by a few words with 7, and 239 by paraphrase with 1. Ten searches for
what isn't in the library ("a giraffe", "a grand piano", "a cat sleeping on a sofa") found nothing
among all 1,997. Other cuts, over the same 900 searches' scenes:

| Cut | Right scenes past it | Others let in | Searches for what isn't there that found any |
| --- | --- | --- | --- |
| 0.003 | 860 of 900 | 98 | 1 of 10 |
| 0.005 | 841 | 63 | 0 |
| **0.01** | **814** | **13** | **0** |
| 0.02 | 770 | 3 | 0 |
| 0.05 | 683 | 0 | 0 |

So the cut stays at 0.01: below it, other kinds come in fast; above it, right ones go.

**Searching the vectors** (made-up vectors in search.db, through Mado's own `Vectors`):

| Pictures | search.db | First search (loading them) | A search after | More like this | Held in memory | The engine's memory grew |
| --- | --- | --- | --- | --- | --- | --- |
| 10,000 | 21 MB | 92 ms | 4.2 ms | 3.9 ms | 31 MB | 63 MB |
| 100,000 | 207 MB | 850 ms | 18.5 ms | 16.6 ms | 307 MB | 338 MB |

A search's own words take SigLIP's text model 18 ms more; through the API, a whole search of the
made-up library (words, described and name, each picture's tile) took 53 ms, 338 ms the first time
(its text model made).

**The queue while the library is read** (12 made-up photos, 2400 × 1800, made for a 4K monitor
at Fast on the card one after another, through Mado's own engine): 3.64 s a picture with reading
paused, and 3.61 s while the made-up library was read from the start at Best on the card, no
difference to measure, reading 28 pictures meanwhile, as it rests nine times its turn on the card
while the queue makes a picture.

## Gotchas

- SigLIP's tokenizer.json doesn't canonicalise (SiglipTokenizer does in Python): Mado lower-cases,
  takes punctuation out and pads to 64 itself; a shorter input reads wrong, as the text tower
  pools at the last place.
- The vision and text models' second output is `pooler_output`, the vector; the first is every
  patch's.
- The recogniser's characters are in its file (`character`, a line each); a blank goes first and a
  space last, 18,710 in all.
- PaddleOCR's models were trained on pictures as OpenCV loads them, blue, green, red: Mado's port
  turns Pillow's red, green, blue round for both, as RapidOCR's pipeline gets them.
- The detector on a thumbnail takes a plain sky for text, in either order of colours: the whole
  sky one "line". On the made-up library's own thumbnails the first look passed on 218 of 239
  landscapes, and with lines thicker than a quarter of the thumbnail left out, 6 (and 23 of 230
  scenes with no words), every scene with words still found; looking at 768 or 1024 instead
  passed on more, and took three and six times as long. In full, the same skies came back as
  "words" of one letter ("1", "人", "口"), hence the two letters a line needs. A round sun can read
  as "O", as in RapidOCR's own pipeline, and a single short line on a wide board can go unseen at
  an angle where two lines are read (RapidOCR alike); the tests draw two.
- search.db busy for a moment (two threads making it at once, as measuring the queue did, or a
  write) is waited for, never taken for damaged: only a file that isn't a database, a damaged one
  or one of another version is started again. It's made with the write lock taken first, as two
  making it at once would otherwise trip on each other's snapshot.
- int8 runs no faster on a GTX 16 card than on six cores, and fp16 slower than fp32 (report-3);
  fp16 files fail to load on the processor at `ORT_ENABLE_ALL` in 1.24.4.
- Tests stand SigLIP and the readers of words in with `tests/fake_search.py` (a picture is its
  colour); `tests/test_search_models.py` runs PP-OCRv6 (fetched once into pytest's cache, as
  LibRaw is), Windows' reader where it has a language, and SigLIP where
  `MADO_SIGLIP_BASE_PATCH16_224_DIR` names a copy.

## Upgrading

A newer SigLIP (SigLIP 2, once a multilingual search is wanted), PP-OCR or ONNX Runtime is measured
on the same made-up pictures in the same way, through Mado's own code (reading time, recall at 1, 5
and 10, the cut on searches for what isn't there) before it's taken; a new export goes in a new
`models-N` release, with `downloads.json`, the notices, this page and the README's "The AI inside"
in the same commit. A new SigLIP's vectors aren't comparable with the old: search.db's version moves
on, and the library is read again.
