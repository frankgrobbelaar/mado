# The queue

How Many at once runs: a batch is many pictures made one after another by the jobs' worker, the
same one that makes a picture's own Save, so the graphics card does one picture at a time. See
it first, recipes and watch folders feed it. The boards are `docs/design/screens/Batch.html`,
`Queue.html` and `Recipes.html`.

| File | Does |
| --- | --- |
| `mado/core/batch.py` | Pure: nights (23:00 to 07:00), which pictures See it first makes, reckoning the rest by them, room on a drive, a batch's steps in Mado's order and the words for them |
| `mado/jobs.py` | The worker and the queue: choosing the next job, pausing, cancelling, moving ticked pictures, trying again, room, keeping the PC awake, recovering after a crash, telling the owner a batch is done |
| `mado/batches.py` | The pictures a batch is made of (ticked, a folder, a search, files and folders dropped or picked), what it takes, putting it in the queue |
| `mado/samples.py` | See it first: three pictures made in full, not saved, by the worker before the queue |
| `mado/recipes.py`, `mado/watching.py` | Recipes, and watch folders with the thread that looks round them |
| `mado/api/batches.py`, `queue.py`, `recipes.py` | Their routes (see [architecture.md](../architecture.md#the-engines-api)) |

## A batch

- **In the database** (migration 5): a row in `batches` (its name, where its pictures came from,
  the folder they share, its steps and saving as JSON, when it starts, and when it began, ended
  and was seen on Home) and a job each picture, with `batch_id` and its place in the queue
  (`position`). A job's order (JSON) holds its recipe, its saving, what it's made for and with,
  its reckoned seconds and bytes, and, when See it first made it, that picture.
- **Steps** are a list, each `{"step": "size", ...}` or `{"step": "look", ...}`, the Size and
  Looks tabs' choices, so later pieces add kinds of their own; they're made in Mado's order (the
  size, then the look) whatever order they're listed in. A size step has no point to crop
  around: each picture's subject is found as it's made, and its model chosen by what it is
  unless Fast or Best is said.
- **Saving**: new pictures beside their originals (`folder` null), into a folder by name beside
  each (`"Edited"`), or into one folder (a path); or in the originals' places, each original into
  quarantine for 30 days. New names are "Name (TV 8K).jpg", "(2)" when one is taken.
- **Pictures outside the library** are made like any other: a job takes its file's path
  (`picture_id` null). One picture dropped or picked opens its page when it's in the library;
  any other opens Many at once.

## The order

1. A picture's own Save (its job has no batch) goes first, even while the queue is paused, and
   before See it first's pictures.
2. Then the batches' pictures by `position`. "Now" puts a batch ahead of everything waiting (the
   picture being made finishes first); "after what's in the queue" and "tonight" put it behind.
3. A batch for tonight starts pictures only from 23:00 till 07:00; the one being made at 07:00
   finishes. While a batch's picture is made, Windows doesn't sleep (`SetThreadExecutionState`).
4. A picture whose drive, or the folder it saves into, isn't connected waits while the others go;
   one whose drive goes while it's made (before anything moved) goes back in line to wait for it,
   not counted as a try (`DriveGoneError`). Each drive is asked about once a look round the
   queue, as an unplugged share can take a while to answer.

The worker takes a job in one statement (`UPDATE … WHERE id = ? AND state = 'queued'`), so one
cancelled or taken out as it's chosen is never started. Pausing stops the batch's picture being
made at its next tile and puts it back first in line; so does Mado stopping. Neither counts as a
try: only a crash does, and a picture a crash cut short twice is marked as not working rather
than tried for ever (`recover`). Resuming before the next tile lets the picture go on; a picture
cancelled while it waited, then tried again, is made afresh. Once nothing of a batch waits, it's
marked done and the owner is told (`notify`), unless they cancelled the queue (Cancel all marks
its batches seen) or nothing of it was made; one picture cancelled still lets the rest be told.
`settle_all` finishes a batch whose last picture was made as Mado stopped. `/jobs` lists only
pictures' own Saves (a picture's page and the status bar follow those); the queue's are
`/queue`'s.

## Room on a drive

Each picture's bytes are reckoned before the batch goes in (by the format and its pixels, moved
by what See it first's came to). Before a picture starts, its drive must keep 256 MB free after
it. Without room the queue pauses itself (`queue_room`: `{"drive": "D:", "fit": false}`) and
tells the owner once what the rest needs; it carries on by itself once the first picture waiting
there fits. "Make the 11 that fit now" (`fit: true`) lets those that fit go while the rest wait
for room, till none waits there. A drive that filled up as a picture was saved records what was
free then, and waits till 64 MB more than that is free and the picture fits with its margin,
or the owner resumes: the reckoning was wrong once, so it isn't trusted alone to say when. The
Queue's card and the notification say the same figure: what's wanted past what's free, the
margin kept (`Room.more`). "Empty D:'s quarantine first" empties it (asked
again) and resumes. Mado never puts new pictures on another drive.

## A picture that doesn't work

A picture that won't open, has gone, or is open in another app (its original can't be read, or
moved to quarantine) fails with a sentence saying so, and its batch goes on. Try again puts it
back at the end of the queue. With nothing waiting, the Queue keeps the latest batch done in the
last week whose pictures didn't all work (`finished`), so Home's "the queue says why" holds,
till Clear (`POST /queue/clear`, `batches.cleared_at`) or Try again; History still says which.

History undoes a whole batch only once nothing of it waits (`409` while it does, its line
`working`: "Still being made"), as what's made after would be left as it is. A picture's own line
can be undone any time: History's lock (`history.MOVES`) holds while a picture's line is written
and its pictures move, so an undo never comes between them. A batch made overnight is one line,
on the day of its newest picture.

## See it first

Three pictures spread across the batch (by the golden ratio, so each round takes three others
from across it) are made in full by the worker before the queue's pictures, written as Save
would into `cache/samples`, with a copy before and after (WebP, 1280 px) to show. Their times
and sizes against Mado's guesses move the whole batch's reckoning: time held to a third to three
times, space to a tenth to three times (bytes a pixel vary far more with what a picture holds).
Putting the batch in the queue copies them to `cache/samples/kept`, named in their jobs' orders
by each picture's file (not its place in the list, which Change which can alter): a job copies its
picture into place, checks it and saves it as any other, rather than making it again, as long as
it's the very picture it was made from and hasn't changed, so What it takes counts them as
moments each. The copy goes once its job has saved it; a set let go as its picture is made goes
as that picture stops.

Measured on the owner's GTX 1660 Super (2026-11-23, driver 621.24, a fresh data folder): 20
made-up 12-megapixel JPEGs made for TV 8K with Warm film at 60%, JPEG 95. See it first made its
three in 36 s (11.3 to 11.8 s each); the batch then took 193 s, 17 made at 11 to 12 s each (about
11.3 s) and See it first's three kept in moments. What it takes said 224 s and 365 MB before See
it first, by this PC's speeds alone, and 198 s and 50 MB after it; the batch came to 193 s and
51 MB.

A set asked for again, or left, is let go (the picture being made stops at its next tile); only
files in `cache/samples` are ever deleted, and `tidy` clears what an earlier run left as the
engine starts.

## Recipes

A recipe is a batch's steps and saving kept by name (`recipes`), with how often and when it was
used. Changing one leaves batches already in the queue as they were asked for. One a watch
folder runs can't be deleted till that folder runs another or stops, and one of the owner's own
looks can't be deleted while a recipe uses it or pictures waiting in the queue are made with it.

## Watch folders

A watch folder (`watch_folders`) has its recipe and where its new pictures go (a folder by name
inside it, or anywhere). Every 5 s the watching thread looks through it and the folders in it,
passing over its results folder, quarantines and Windows' own folders.

- **Only what's finished copying**: a picture is taken once its size and time have stayed the
  same for 5 s and it opens; one that still won't open after 2 minutes is left alone.
- **No loops**: it never takes a picture in its results folder, however that's named (a short
  name, a junction: real paths are compared), nor any picture Mado wrote (any History line's or
  job's result, by its path or, saved through another name for the folder, as the same file), and
  it never follows a link to another folder, so its results and other batches' can't feed it
  again.
- **New only**: what's in a folder as it's watched, or turned on again, is noted in `watched`
  and left alone; what arrived while Mado was closed is taken as it opens.
- Its new pictures join its batch that still has pictures waiting, or start one behind what
  waits, saved as new pictures where it says, whatever its recipe's saving says. With "Big
  batches wait for the night" on (Settings › General), a batch of more than 20 waits for 23:00.
- **A problem says so**: when its pictures can't go in the queue (a model to download, a recipe
  Mado can't make), its row says why (`watch_folders.problem`, logged once), and it rests 5
  minutes before it tries again; the problem goes once they do.

## Gotchas

- Tests drive the worker with `Jobs.wait()`, which returns once nothing can be made now; a
  change (`wake()`) clears it first, and the worker only rests once it has seen every change.
- `Jobs.busy()` is true while See it first makes a picture too, so the PC check doesn't time a
  card that's working.
- The API's step discriminator is `step`, not `kind`: a size step's `kind` is what the picture
  is (photo, drawing…).
