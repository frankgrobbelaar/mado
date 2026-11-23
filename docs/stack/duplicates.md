# Duplicates and bursts

How Mado finds pictures saved more than once, and shots of one moment, which of each it keeps,
and how the rest are set aside. All of it is Mado's own code on NumPy and Pillow: no new
dependency. The review's page has no board; it's drawn from the Queue, History and Library
boards.

| File | Does |
| --- | --- |
| `mado/core/likeness.py` | Pure: the fingerprint (64 bits), the finer fingerprint (256 bits), sharpness, and close fingerprints found in buckets |
| `mado/core/duplicates.py` | Pure: the groups (exact copies, saved again, bursts), what's never grouped, which to keep, a copy's name |
| `mado/duplicates.py` | The finder (a thread of its own), the owner's choices and "not the same", setting aside |
| `mado/api/duplicates.py` | `/duplicates` and its actions (see [architecture.md](../architecture.md#the-engines-api)) |
| `app/src/features/duplicates/` | The review: the groups, the compare card |

## Looking

The finder looks at each picture once the scan has read it (each scan's end wakes it, and it
looks round every 5 minutes besides), and again once its file changes (its print names the size
and time it was taken from):

1. **Fingerprints, from the thumbnail** the scan made (512 px, WebP 80), so nothing is decoded twice
   (a thumbnail the cache lost is made again only for a picture still in the library as it was,
   never for one whose folder was taken out meanwhile): a 32 × 32 and a 64 × 64 grey copy,
   box-averaged, give the fingerprint (a pHash: the lowest 8 × 8 of a DCT, each above or below their
   median) and the finer one (the lowest 16 × 16 of the larger copy's). The view the size of a
   screen isn't used: the cache holds it only for pictures opened, and the thumbnail is plenty for
   both.
2. **Digests** (blake2b, read a megabyte at a time) only of files that share their size with
   another, so exact copies are known for certain.
3. **Groups**, from what's been looked at, every 20 s while a first look goes on and once it's
   done; kept in memory, found again after every change the owner makes.
4. **Sharpness** of each burst's shots: the variance of the Laplacian on a grey copy of the
   picture itself, 1024 px on its longer side (smaller ones grown to it), kept with the print.

A thumbnail that can't be made (a HEIC before ffmpeg is there) leaves an empty print, tried again
as the engine next starts and as soon as ffmpeg is there. A camera RAW is looked at once its
reader has read it (a RAW still waiting for LibRaw isn't looked at): its thumbnail comes from the
preview its camera kept inside it, and a burst's sharpness from that preview at 1024 px when it's
that big, else from the RAW developed at half size (see [libraw.md](libraw.md)). Home and the
review say how far looking
has got ("Looked at 3,200 of 4,812", of the pictures read so far) while the finder looks or a scan
reads; a picture it can't look at now (its drive away) never keeps it "looking". A picture another
app held while the scan read it is left to read, and the scan looks again a minute on.

## Groups

| Kind | Joined when |
| --- | --- |
| Exact copies | The same digest |
| Saved again | Fingerprints within 6 bits (`NEAR`), shapes within 1% (`SHAPE`), finer fingerprints within 10 of 256 bits (`FINE`) |
| Burst | The same camera, folder and size, taken (by the camera's clock) within 2 s of a neighbour (`BURST_GAP`), fingerprints within 12 bits (`BURST`), names that aren't one's copy of the other |

Close fingerprints are found in buckets, not pair by pair: the 64 bits split into `NEAR` + 1
bands, so two within the limit share a band exactly, and only pictures sharing a band are
compared, a block at a time with NumPy's XOR and `bitwise_count`. Bursts compare only neighbours
in time. Pairs join the most alike first; a join that would put two pictures the owner said
aren't the same in one group, or two of one family, is left out. A group with a burst's join is
a burst.

**Never grouped**: pictures that won't open (not looked at), anything in a quarantine (any path
through a `Mado quarantine` folder), pictures the owner said aren't the same (each pair
remembered with both files' size and time: a change asks again), a family (History's made and
replaced lines join an original and every picture made from it, and from those, and no group
holds two of one family), and a camera RAW with a picture that isn't one. RAWs group among
themselves (copies of a RAW, bursts of RAWs, a DNG made from a camera's RAW), and a camera's RAW
and its JPEG of the same moment, or a JPEG made from a RAW, are never taken for copies: they're
two ways of keeping one picture, and the review never offers to set one aside for the other.

## Which to keep

- **Duplicates**: the most pixels; then the larger file of its format; then a name that isn't a
  copy's (`(2)`, `Copy`, `- Copy`, `Copy of`, `_copy`); then the older file.
- **Bursts**: the sharpest shot, each shot counted with its copies (its exact and saved-again
  joins) as one, by its best copy's sharpness, so a sharpened export never outranks its own
  original; then that shot's best copy, as duplicates are kept.
- Each group says which rule decided (`reason`: sharpest, pixels, larger, name, older), and the
  review says it in words.
- **The owner's**: a click keeps one instead, a tick keeps one as well (`choices`, each with its
  file's size and time: a change goes back to Mado's suggestion). A group always keeps one: a
  choice of none is refused, and one left with none keeps Mado's.

## Setting aside

The review names what it showed: each group's pictures and the ones kept (a group that changed
since, a picture joining it say, is left as it is with a sentence), or, to set every group of a
kind aside, the `version` of the groups it saw (any change since answers 409, and nothing moves).
Keeping one writes choices only for the pictures shown: one that joined unseen is left to Mado.

The rest of each group named (or of every group) goes, a picture at a time, into its own drive's
quarantine through `mado/quarantine.py`, under one review (`reviews`), each with a History line of
kind `aside` (the picture kept beside it) written before it moves. Each picture is checked first,
and left as it is with a sentence when it changed since it was compared (size and time), isn't
there, is on a drive that isn't connected, or is open in another app; the whole group stays when its
kept picture isn't there as it was, and a picture that's the kept one's own file under another name
(a link, a drive letter for a folder) stays too. Nothing is ever deleted: the clear-out takes what's
set aside after 30 days, as it does everything in quarantine. The library forgets a picture set
aside (`gone_at`) till it's put back: History's Put back (a picture, or a review whole) moves it
back and asks for a scan, which finds it as it was, its print and all, so it joins its group again.
A line whose picture never moved (Mado stopped between the two) is simply undone. A picture put back
on its own is one the owner keeps (a choice is written for it), so setting its group aside again
leaves it; a whole review put back is the review as it was.

## Measured

On made-up scenes drawn by code (`tests/drawn.py`'s `scene`: a sky, a sun, ridged hills, shapes,
a camera's grain; each seed a different scene), through Mado's own thumbnails, on the owner's PC
(i5-9600K; finding uses the processor only), 2026-11-23.

**Fingerprints** (40 scenes, 3000 × 2250), bits apart from the original:

| Variant | 64-bit | 256-bit |
| --- | --- | --- |
| 50% and 25% copies; JPEG 60, 75, 95; PNG; WebP 80; sharpened (radius 2, 60%); JPEG 60 at 25% | 0 to 4 | 0 to 6 |
| Cropped 1% each side (same shape) | 0 to 6 | 6 to 30 |
| Cropped 2% each side | 0 to 10 | 14 to 60 |
| Cropped 5% each side | 4 to 20 | 50 to 106 |
| Cropped 10% off one side (shape 10% off) | 6 to 22 | 58 to 126 |
| Burst shot, camera moved 0.5% / 1% / 2% / 3% | up to 4 / 6 / 12 / 18 | |
| Burst shot, the subject moved 2% | up to 8 | |
| Different scenes (the same generator, another seed; 780 pairs) | 18 at least, 32 typically | 98 at least |

A 64-bit dHash was tried first: up to 12 bits on JPEG 60 against 16 between different scenes,
too close. A 32 × 32 grey sketch's correlation also told 2% crops apart (re-saves 0.9993 at
least, a 2% crop 0.9971 at most), but at 1 KB a picture against the finer fingerprint's 32 bytes.
A crop under 2% is practically the same picture and may group; a gentle crop of 2% or more, and
any that changes the shape, doesn't.

**Sharpness** (20 bursts of five, blurred by σ 0, 0.6, 1.2, 2 and 3 px at full size before their
grain, each shot moved a little): the shots came out in order 20 times of 20 on a grey copy 1024
px across (the sharp one 3% sharper than σ 0.6 at the least), and at 1536 and 2048 too; on the
512 px thumbnail 14 of 20; at full size 3 of 20, the grain outweighing the detail.

**A library of 4,950 pictures** (1600 × 1200 JPEGs, 1.5 GB) with 150 saved again (half size at
JPEG 75, PNG, quarter size at JPEG 70, WebP, in other folders), 60 copied byte for byte, 60 bursts
of five (one sharp, the rest blurred 0.8 to 2 px) and 40 cropped 5% each side: the scan (reading
and thumbnails, which it does anyway) took 240 s; finding took 46 s (fingerprints on 4 threads,
digests, the 300 shots' sharpness, grouping); grouping again 0.36 s. It found the 270 groups
planted and nothing else: no crop, no false group; the sharp shot kept in all 60 bursts, the
original in all 210 duplicates.

**At 100,000 pictures** (made-up fingerprints): finding the close ones took 0.6 s, 3.8 s with a
fifth of them alike in half their bits; grouping took 0.8 s.

## Gotchas

- Fingerprints are signed 64-bit integers in SQLite; `near_pairs` views them as unsigned.
- The finer fingerprint only confirms: a picture without one is never "saved again", though it
  can still be in a burst.
- Groups are kept in memory, not in the database: the finder groups again as the engine starts,
  and after a look only when something changed. A group is named by its first picture's number
  (`key`), which stays as pictures join it: setting aside checks the members and kept ones the
  review showed, not the key alone. One gone altogether answers 404 to Keep and Not the same.
- Tests wait for the finder with `Finder.wait()`, after `Scanner.wait()` (a scan's end wakes it).
