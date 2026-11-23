# Changelog

Every change to Mado you'd notice, newest first. Versions follow
[semantic versioning](https://semver.org): a new major number means something you have to act on,
a new minor number brings features, a new patch number fixes things. Every version can be
downloaded from the [downloads page](https://frankgrobbelaar.github.io/mado/), and an installed Mado
shows these notes when it offers the update.

## Unreleased

### Added
- Duplicates and bursts: Mado looks at every picture as it's read, and finds the ones saved more
  than once (the same file twice, or saved again at another size, quality or format) and bursts
  (shots a second or two apart). Home's Needs you says how many there are, and how far Mado has
  got while it's still looking.
- Review shows each group with the one Mado keeps: a burst's sharpest, otherwise the copy with the
  most pixels. Click another to keep it instead, tick to keep more than one, open one big beside
  the one kept at Fit or 100%, or say they're not the same, which Mado remembers unless a file
  changes. Duplicates and bursts can be shown apart.
- Set aside the rest of every group at once ("Set aside 212, freeing 1.4 GB"), or one group at a
  time. Each picture waits in quarantine for 30 days; History shows the whole review as one line,
  and puts back one picture or all of them. A picture that changed since Mado compared it, is open
  in another app, or is on a drive that isn't connected is left exactly as it is, and Mado says
  so.
- Won't open: Home lists the pictures whose files are damaged or were only half copied. See which
  shows each with why, to show in its folder, try again, or mark as damaged, so it isn't asked
  about again unless its file changes. A picture's own page offers Mark as damaged too.
- Space: Home shows the room on the drive most of your library is on (what's free, what your
  pictures use, what quarantine holds and what the queue needs), with a line for each other drive
  the library uses.

### Changed
- A picture open in another app no longer stops its job. The queue, or a Save, waits and tries
  again by itself every 30 seconds for 10 minutes while the others go on, and a note at the
  window's foot says so, with Try again now and Skip it. A Save that would replace it waits before
  making the picture, not after.
- A picture another app had open while Mado read it is read again a minute later, rather than
  listed as one that won't open; Try again on such a picture says it's open elsewhere and leaves
  it as it was.

## 0.3.0 - 2026-11-22

### Added
- Many at once: tick pictures in the Library and choose Many at once, or choose it from a folder's
  menu or beside a search, and make them all for a screen or a print, give them a look, or both,
  then save them as new pictures (into a folder of your choosing, "Holiday (TV 8K).jpg", "(2)"
  when a name is taken) or in place of their originals, each original waiting in quarantine for
  30 days.
- Drop pictures on Mado's window, anywhere, or pick them or a folder on Home: one picture from
  your library opens its page, and anything else opens Many at once, pictures outside your
  library too.
- See it first: three of a batch's pictures are made in full before you start, timed and sized,
  each shown before and after; open one to look closely at 100% or 400%, or try three others. The
  batch keeps them rather than making them again.
- What it takes: how long a batch will take on your PC, how much space it needs, and what's free
  on the drive, before you put it in the queue.
- The Queue, in the rail: one picture at a time on the graphics card, now, after what's waiting,
  or tonight from 23:00 till 07:00, with the PC kept awake while it works. See how far it's got
  and how long is left, pause it, cancel it all (Mado asks first), move ticked pictures next or to
  the end or take them out, and try again a picture that didn't work, with why it didn't in a
  sentence. Once a batch is done, the pictures that didn't work stay in the Queue, with Try
  again, till you clear them. The rail's badge says how far it's got, or how many wait.
- When a drive fills up, the queue pauses and says how much it needs: make the pictures that fit
  now, empty that drive's quarantine first (Mado asks once more), or wait, and it carries on by
  itself once there's room. A picture on a drive that isn't connected waits for it while the
  others go, even one whose drive is unplugged while it's being made, and a picture open in
  another app is passed over with a sentence, to try again.
- Recipes: keep a batch's steps by name, "TV 8K, then Warm film at 60%, then JPEG 95 into
  Edited", and start any batch from one; see how often and when each was used. One of your own
  looks that a recipe uses isn't deleted from under it: Mado says which recipe to change first.
- Watch folders: every new picture put in a folder is made to its recipe once it has finished
  copying, and saved as a new picture where you say, its original left as it is. What arrived
  while Mado was closed is made as it opens, and a watch folder never takes its own results or
  anything else Mado made, however its folders are named. When its new pictures can't go in the
  queue (a model to download first, say), its row says why, and it tries again a few minutes
  later. Settings can have big batches wait for the night.
- A Windows notification when a batch is done, and on Home, "Holiday is ready for the TV" with its
  folder to open, and what was made today.
- History shows a batch as one line, "Made 47 pictures for the TV overnight", with Take them away
  (or Put the originals back) for all of it, once it's all made; each picture's own line is
  still there under it. A batch made overnight stays one line, on the day it finished.

### Fixed
- A picture open in another app says so, rather than that it's damaged.
- The window's colour under the page is Graphite's, and Aluminium's in light, not another app's.

## 0.2.0 - 2026-11-22

### Added
- Give a picture a look: on its page, the Looks tab shows every look as a small copy of your
  picture (Original, Warm film, Cool film, Faded, Teal and orange, Silver, Golden hour, Night
  neon, Duotone, and Mado's own Bold colour, Sepia print, Moody blue, Cross-processed and Soft
  pastel), and the one you pick, or rest the pointer on, on the picture itself. The arrow keys go
  through them, and Strength sets how much of the look you want.
- Finishing touches: grain, a vignette, glow, fade, a light leak and dust, each with its own
  amount, drawn by Mado and the same on the preview as on the picture you save.
- Hold to see the original, or hold the \ key, to compare the picture with and without its look.
- Your own looks: import a .cube file (the kind Adobe's apps and DaVinci Resolve export), or keep
  the mix you've made, its look, strength and touches, under a name; rename them and delete them,
  Mado asking first. Backups and the export carry them, and the export holds each as a .cube file
  other apps open.
- One picture, one recipe: what you set on the Size and Looks tabs is made by one Save, so a
  picture can be made for a TV 8K and given Warm film at once ("Harbour at dusk (TV 8K, Warm
  film).jpg"), or given a look alone at its own size ("Harbour at dusk (Warm film).jpg"). History
  says what each picture was made with.
- Save stays at the foot of a picture's tools however long the column grows.

### Changed
- Open it, on a picture Mado has just made, shows the new picture as it is, without the size or
  look that made it chosen again.

### Fixed
- Previews of a picture with wide colours (a phone's Display P3) show its colours as they are.
- The export's History spreadsheet put when a picture was cleared out under the wrong heading.

## 0.1.0 - 2026-11-22

### Added
- Make a picture right for a screen or a print: on its page, the Size tab offers a phone, a
  tablet, a laptop, a 4K monitor, an ultrawide and an 8K TV, your own screens (remembered), and
  prints at 300 dpi (10 × 15 cm, A4, A3 or any size). Mado crops it around its subject, with a
  point you can drag, or draws more at its edges, and makes it exactly the size with an AI model
  on your graphics card, the photo or the drawing model as suits the picture (pixel art stays
  blocky, screenshots keep their letters), saying about how long it takes on your PC.
- Before and after at full detail: zoom to 100% or 400% on the Size tab and drag the line
  between them, or the picture, to look anywhere.
- Fast and Best: the Fast models come with Mado; Best for photos (67 MB) and LaMa, which draws
  more of a picture at its edges (209 MB), are downloaded the first time they're asked for, each
  listed in the installer and checked.
- Save as a new picture beside the original ("Harbour at dusk (TV 8K).jpg", "(2)" when that's
  taken) or in a folder you choose, or replace the original, which waits 30 days in quarantine;
  in JPEG, PNG, WebP or AVIF, keeping the date taken, the camera and the colours (a phone's wide
  colours too), and leaving out where it was taken unless you keep it. The format stays as it
  was unless you choose another (a HEIC photo, which Mado can't write, becomes JPEG); a picture
  with see-through parts keeps them, never JPEG unless you ask, and then they turn white.
- Cancel stops a picture being made at once, up to the moment it's saved; and if Mado is closed
  while it saves, the picture is finished or the original put back the next time Mado opens.
- When something goes wrong inside Mado, the window says so in plain words, not that Mado's
  engine didn't answer.
- History, in the rail: what Mado made, a week at a time; take a new picture away, put it back,
  put a replaced original back, or replace it again. A picture changed twice is put back newest
  first. What waits in quarantine is cleared out after 30 days, or emptied by hand in Settings ›
  Your data; a drive that isn't plugged in keeps its quarantine till it is.
- Settings › General has Saving: what Save offers first, where new pictures go, and whether they
  keep where a picture was taken.
- Settings › About shows This PC: its graphics card, whether the AI models run on it, how long a
  picture takes each way, which way each kind starts on, and Test again; and every download, with
  Download it again for one that's gone missing.
- Setup carries on to your folders while ffmpeg downloads, and says what your PC can do.
- Your library: add the folders your pictures live in, in Setup or later from Home or the
  Library, and Mado reads every picture in them where it is (JPEG, HEIC, PNG, WebP, AVIF, TIFF,
  BMP and GIF; camera RAW is listed, to be read later), changing nothing.
- The Library shows your pictures by the day they were taken, newest or oldest first, with your
  folders down its side as a tree; search a folder by name, and tick pictures to show them in
  their folders or copy their paths.
- A picture's page shows it large, fitted or at 100% or 400%, with when it was taken, its camera,
  its size and whether it carries a location, the pictures either side of it (the arrow keys go
  along them), and Show in folder.
- Mado keeps watching your folders: pictures you add, change or delete show within seconds, and
  what changed while Mado was closed shows as it opens.
- Home shows your library in numbers, and when Mado last read it.
- Pictures that won't open (damaged or half copied) are listed as they are, with why, and can be
  tried again once mended.
- The export now holds your library's folders, and every picture with what Mado read of it, as a
  spreadsheet.
- Mado's first window, on the foundations Kura and Maku share: Setup fetches ffmpeg, the one tool
  Mado downloads, from the list the installer shows; Settings has light or dark, Start with
  Windows, keeping Mado running when its window closes, updates, nightly backups you can restore,
  and an export of your data; and records damaged past use are offered the newest backup that
  opens.
- Mado's own mark, a round window lit in green with a hill seen through it, on its icon, in its
  window and on the downloads page.
- Mado's own look, Graphite: a mid-grey window that never tints your pictures, one green accent,
  IBM Plex type, the rail down the side and a line of facts at the foot. Its light, Aluminium,
  follows Windows, or choose it in Settings › General, where each choice shows a little picture of
  the window.

