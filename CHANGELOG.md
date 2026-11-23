# Changelog

Every change to Mado you'd notice, newest first. Versions follow
[semantic versioning](https://semver.org): a new major number means something you have to act on,
a new minor number brings features, a new patch number fixes things. Every version can be
downloaded from the [downloads page](https://frankgrobbelaar.github.io/mado/), and an installed Mado
shows these notes when it offers the update.

## Unreleased

## 0.9.0 - 2026-11-23

### Added
- Search by describing a picture: the Library's search box finds pictures by what they show
  ("a red boat on the sea", "snowy mountain"), the closest first, as well as by their names. A
  search for something that isn't there finds nothing, rather than the least bad pictures.
- Search by the words in a picture: a sign, a page or a screenshot is found by the words it shows,
  however they're written (capitals and accents don't matter, and a Chinese or Japanese word is
  found anywhere in a line), with the matching words shown under each picture.
- More like this, on a picture's page: the library's pictures most like it, the most alike first.
- The results come in groups, by the words in the pictures, by what they show and by their names,
  each picture once. Many at once starts from them, and a picture opened from them goes along the
  results with the arrow keys.
- Mado reads the library for search in the background, as it looks for duplicates: it says how far
  it has got ("Read 2,340 of 18,200 so far: search covers those") in the Library, on Home and in
  Settings › General › Search, can be paused, and takes turns with the queue on the graphics card.
  A picture changed is read again; a drive that isn't connected keeps what was read of its
  pictures, and they're found, shown as away. Pictures from outside the library, in a quarantine
  or marked as damaged are never read. A picture that couldn't be read is counted and tried again
  after the next scan, and a reader that can't run says so, with Try again.
- Its reader of pictures, SigLIP (208 MB), and its reader of words at Best, PP-OCRv6 (31 MB), come
  the first time you search, each checked before it's used, as the installer's first page lists
  them; till then, a search finds pictures by name. Fast reads words with Windows' own reader, with
  nothing to download, in the languages Windows has. As this PC suits, Best where the graphics card
  makes it quick; Settings › General › Search changes it.
- A search in another language says that describing works in English, and one in a writing the
  words reader can't read (Greek, say, where Windows reads only English) says so.

### Changed
- The Library's search shows what it finds in groups, the first 500 of each, saying how many more
  there are; Many at once from a search takes every one.
- Settings › Your data shows what search keeps (search.db) once there's some, and the export holds
  the words read in each picture (words.csv).

## 0.8.0 - 2026-11-23

### Added
- Camera RAW is read, where it was only listed: CR3, NEF, ARW, DNG and the rest show by the day
  they were taken, with their camera and their size as shown, and every tool works on them as on
  any picture: Size, Looks, Edit, Many at once, recipes and watch folders, the wallpaper studio
  and favourites. The grid's tile comes from the preview the camera kept inside the RAW; the
  picture's page, its tabs and Save develop the RAW itself, with the camera's white balance, its
  own crop and turn, into Display P3, so a camera's wide colours stay wide. A RAW is never
  written: Save makes a new picture beside it, and says why Replace isn't offered.
- Mado's RAW reader, LibRaw, comes the first time Mado reads a camera RAW: a 3.5 MB download from
  LibRaw's own site, checked before it's used, as the installer's first page lists it. While it
  comes, a RAW's tile, its page, a batch and a watch folder say so, with its progress, and why if
  it didn't come (offline, or not the file the list names), with Try again. Settings › About says
  whether it's there.
- Duplicates and bursts look at camera RAW too: copies of a RAW, and bursts of RAWs, are grouped
  and reviewed as any are. A camera's RAW and its JPEG of the same moment are never taken for
  copies of each other.
- A RAW that won't develop (half copied, say) joins the pictures that won't open, and one from a
  camera Mado's RAW reader doesn't know yet says so.

### Changed
- Pick pictures offers camera RAW, and Home's drop zone lists it.
- ffmpeg's licence now comes with it, kept beside it in Mado's tools folder, and
  THIRD-PARTY-NOTICES.txt names what Mado downloads to the PC, apart from what ships inside it.

### Fixed
- Home's Made today says what an edit alone made of a picture (Cut out, Erased, Blurred or Edited)
  beside its name, where it said nothing.
- Many at once's Saving said "Into ." till a step was picked: it says only that the originals stay
  as they are till it knows where the new pictures go.
- The arrows in See it first's sizes, a recipe's steps and a watch folder's line are drawn in
  Mado's own look, where they came in another font.

## 0.7.0 - 2026-11-23

### Added
- The wallpaper studio, a new place in the rail: your monitors drawn as Windows arranges them,
  each with its name, its size and the wallpaper on it now. Pick a picture for each (from your
  favourites or the library, dropped on the window, pasted, or sent from a picture's page with
  "Make it a wallpaper"), or one laid across them all with a gap for the bezels. Each monitor's
  part is made at exactly its pixels, as the Size tab makes a picture: cropped around the subject
  (drag it to move where it's cut, zoom with the wheel, the keys or the slider) or its edges
  extended, made bigger with Fast or Best where it needs it, and honest when it's too small to
  look real. Set it as Windows' own wallpaper, or save the parts, or one picture of them all, as
  new pictures in a folder you pick. While it's made, the studio says how long it has left, and
  Stop stops it.
- Favourites: a heart on a picture's page, and on its tile in the grid (shown as you point at it,
  and always once given). The Library has Favourites of its own, searched and ordered like the
  rest, with Many at once from them. A favourite stays one when its file is moved or renamed, and
  a picture from outside your library can be one too.
- The wallpaper can change every day, once you turn it on: at 07:00 or a time you pick, a favourite
  (or a picture from one library folder) that suits each monitor, its way round and big enough,
  none again till every one has been. It's made the evening before, so the change is instant;
  closed at the time, Mado changes it as it next starts.
- Before it first sets one, Mado keeps a copy of your own wallpaper, and "Put back your own
  wallpaper" brings it back on each monitor, Windows' slideshow included. Mado's wallpapers stay
  in its own folder (those showing and the last 3 days' kept), and Settings › Your data shows
  them.

## 0.6.0 - 2026-11-23

### Added
- Pictures from anywhere: one picture from outside your library opens on its own page, with Size,
  Looks, Edit and Save as for one in it. Where the library's breadcrumb would be, it shows the
  folder it's in (a click shows it there) and "Add its folder to the library". It's never listed
  in the Library, counted or looked at for duplicates; add its folder later and it's the
  library's, its History intact. Its page follows its file: changed elsewhere (or by a Save in
  its place) it's read again, and gone it says so, or that its drive isn't connected. Several
  pictures, or a folder, open Many at once as before.
- Paste with Ctrl+V anywhere in the window (a text field still pastes words). Files copied in File
  Explorer open as if dropped; a screenshot, or a picture copied from a browser or another app,
  opens on its page, kept in Mado's own folder till you save it (as a new picture, as it is or
  made for a screen, PNG or the format you choose, into Pictures or a folder you pick); a path
  copied as words opens what it names.
- "Open in Mado" in File Explorer's right-click menu, on pictures in every format Mado reads (HEIC,
  AVIF and camera RAW too) and on folders: on Windows 11 it's under Show more options. Several
  selected open Many at once with them chosen, up to 100 at once (Windows opens nothing past that:
  open their folder instead). Mado is in Open with for its pictures too, without
  ever becoming what opens them: which app does stays yours. Settings › General turns it off, and
  uninstalling takes it away.
- `mado.exe` opens the pictures and folders named after it, quoted or not, long paths, network
  paths and any alphabet included. A Mado already running, or waiting in the tray, comes forward
  with them; one only just starting opens them once it's ready.
- A picture from outside the library not opened for a month is let go, with its copies, unless
  the queue or History still needs it; an unsaved paste goes then too. Settings › Your data shows
  what's pasted, once there is some.
- The Library tags a picture kept from a group, as its board draws it: "burst of 5", "2 copies".
  A click opens the review at that group.
- The small things: a file Mado can't read (it says the formats it reads), a path gone or a drive
  not connected, a picture too big to paste (over 67 megapixels, all Windows' clipboard hands the
  window), pictures among other files (it takes the pictures and says what it left out), a picture
  waiting in quarantine (opened to look at only), camera RAW from outside (shown as the library
  shows it), and the same picture opened twice (one page).

### Fixed
- A library folder holding Mado's own data folder no longer reads Mado's cache as pictures, and
  what Mado writes there no longer starts scans.
- A picture copied into a library folder while a scan was under way is no longer taken for gone.
- Mado no longer stops as it starts when Windows hands it a name it can't put in letters.

## 0.5.0 - 2026-11-23

### Added
- Edit by clicking: a picture's Edit tab picks a part with a click (Select), and every click after
  the first is instant. Click again to add a part, Alt-click to take some of one away, and step
  through Mado's three answers with Bigger, Smaller or the mouse wheel; Esc lets go. Parts get
  plain names, Part 1 and Part 2, never a guess at what they are.
- With what you picked: erase it (Fast, or Best for big parts and busy places), cut it out onto
  nothing (PNG or WebP), a colour or the rest of the picture blurred, blur what's behind it like a
  big camera lens, or give just that part a look.
- Erase's brush paints what clicking can't pick, such as a wire, a scratch or a sign, Alt taking
  away. Cut out finds the picture's subject without a click (Fast, or Best with the finest edges).
- Undo the last edit or start again, and hold \ to see the original. Edits are a step of the
  picture's one recipe with its size and look, made again at full size by the same Save, as a new
  picture or in the original's place with the original in quarantine. History says what was
  edited.
- Looks on just a part: the Looks tab's "Only on a part" puts a look and its touches only where you
  click, with a soft edge; Whole picture goes back. The looks' small copies show the picture as
  you've edited it.
- Cut out the subject is a step for many at once and for recipes, such as "Cut out the subject,
  then PNG into Cut-outs", with See it first, what it takes and the queue as for any step.
- The AI models for editing come the first time they're needed, each with its size and progress:
  SAM 2.1 to pick parts (156 MB), MI-GAN to erase at Fast (28 MB) and BiRefNet lite to cut out at
  Best (224 MB); LaMa erases at Best. Cutting out at Fast comes with Mado, so it works offline.
- The small things: a model to download first, and what to do offline; the graphics card busy with
  the queue; an erase that came out smooth where the picture has detail, offering Best; a picture
  changed since Mado read it; a picture too big to edit (over 100 megapixels); and Save waiting
  for a model still downloading.

## 0.4.0 - 2026-11-23

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

