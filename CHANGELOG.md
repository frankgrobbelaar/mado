# Changelog

Every change to Mado you'd notice, newest first. Versions follow
[semantic versioning](https://semver.org): a new major number means something you have to act on,
a new minor number brings features, a new patch number fixes things. Every version can be
downloaded from the [downloads page](https://frankgrobbelaar.github.io/mado/), and an installed Mado
shows these notes when it offers the update.

## Unreleased

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

