# Wallpaper (the studio, the daily change, the owner's own put back)

The wallpaper studio makes a picture for each of the owner's monitors (or one laid across them
all), at exactly each monitor's pixels, and sets it as Windows' own per-monitor wallpaper; every
day's change does the same from the favourites. Windows is reached through its own APIs by
ctypes, with no package: IDesktopWallpaper for the wallpaper, the display APIs and DisplayConfig
for the monitors. The screens are the studio's (`app/src/features/wallpaper/`); no design board
covers them, so they follow the picture page's pattern (a stage, and a tools column with its tabs
and its one primary action at its foot).

| Part | Where |
| --- | --- |
| The rules: the arrangement, the gap for the bezels, where a part is cut, laying one across, which pictures suit a monitor, the day's picks | `mado/core/wallpaper.py` |
| Windows: the monitors, IDesktopWallpaper, the slideshow, spotlight; `Desktop`, the seam, and `NoDesktop` | `mado/desktop.py` |
| The studio: its choices, making parts (the jobs' worker), setting them, saving them, keeping and putting back the owner's own, the daily change, tidying | `mado/wallpaper.py` |
| Favourites: the heart, following a picture moved or renamed | `mado/favourites.py` |
| The API | `mado/api/wallpaper.py`, `PUT /pictures/{id}/favourite` in `mado/api/pictures.py` |
| The studio's screen, the heart | `app/src/features/wallpaper/`, `app/src/components/heart.tsx` |

## What Windows does to a wallpaper file

- **A JPEG is made again.** Setting a JPEG, Windows writes its own copy,
  `%APPDATA%\Microsoft\Windows\Themes\TranscodedWallpaper` (no extension), and draws the desktop
  from it. Checked on the owner's PC (reading the file's header only, 2026-11-23): their
  wallpaper is a JPEG, and Windows' copy is a JPEG whose quantisation tables are those of quality
  85, the default of `JPEGImportQuality` (60 to 100, under `HKCU\Control Panel\Desktop`). Raising
  it would change a Windows setting, which Mado never does.
- **At the picture's own size.** The copy keeps the picture's pixels (a 1920 × 1200 picture on a
  1920 × 1080 monitor stays 1920 × 1200; an earlier 3840 × 2400 one stayed that size too), and
  Windows fits, fills or crops it as it draws. A picture exactly a monitor's pixels is shown pixel
  for pixel under fill, fit, stretch, centre or tile. Spanned, Windows lays one picture across
  every monitor and per-monitor wallpapers don't show.
- **A PNG isn't made again at a quality**, by every account found (the `JPEGImportQuality`
  setting is for JPEGs alone), so it arrives on the desktop with the pixels Mado made. Not yet
  seen on this PC: see the last section.
- **Colours in sRGB look right either way.** Whether or not the desktop honours a picture's colour
  profile, a picture in sRGB shows as it should, so each part is turned into sRGB from its own.

So Mado writes each part as **PNG, 8-bit sRGB, exactly its monitor's pixels**, see-through parts
on black (a wallpaper is never see-through), into its data folder. When Windows has wallpapers
spanned, Mado lays them to fill before setting its own (a span shows one picture), and spans them
again when the owner's own goes back, unless they chose another fit since. It changes no other
setting.

## Where it's set, and what's kept

- **Mado's data folder only**: `wallpapers\made\<number>\` (one folder a wallpaper, a PNG a
  monitor) and `wallpapers\yours\` (its copies of the owner's own). The owner's folders see only a
  Save as pictures, which is a Save like any other (a folder they pick, "(2)" for a name taken,
  History's line before it's put in place).
- **The owner's own, kept.** Each time Mado sets a wallpaper over one that isn't Mado's, it first
  copies each monitor's file into `wallpapers\yours` (a copy that failed is made the next time,
  while their file is there). Windows may hold the picture only in its own cache: when the file
  Windows names is gone and one picture shows on every monitor, Windows' `TranscodedWallpaper` is
  copied instead; with a picture of its own on each monitor, Windows keeps a copy for each
  (`Transcoded_000`, …) in an order it doesn't document, so Mado doesn't guess, and that monitor
  can't be put back once its file is gone. A monitor showing a colour has nothing to copy, and
  gets its colour back. The owner's file is only ever read. How Windows showed it (spanned or not,
  a slideshow with its folder, interval and shuffle, or spotlight) is noted the first time, and
  again only once no monitor shows Mado's: while one does, Windows shows what Mado left.
- **Put back**, monitor by monitor: every monitor showing Mado's (one the owner gave a wallpaper
  of their own since is theirs, and left), or the one asked for; their own file when it's there,
  else Mado's copy. A monitor Windows refuses is said and doesn't stop the rest. Windows' slideshow
  is started again (`IDesktopWallpaper::SetSlideshow`) unless a monitor shows a wallpaper the
  owner chose since, and a span spanned again while Windows still has the fill Mado laid.
  Spotlight has no API to turn it on, so Mado says where: Settings › Personalisation ›
  Background. Putting back every monitor stops the daily change first, and once all are back the
  note of how Windows showed them goes.
- **Kept and let go**: Mado's wallpapers a monitor shows now (whatever the records say) and those
  set in the last 3 days stay; so do those made ahead for their day, till the day has passed.
  Older ones, and those saved, cancelled or failed, are deleted, only PNGs in `wallpapers\made`,
  never one asked for while the tidy looked. The daily change's records stay, as what it showed
  which day.
- **Stopped, or cut short**: a wallpaper being made says how long it has left (by its pace), and
  Stop stops it, its parts let go. One the owner asked to set or save isn't finished days later
  when Mado's closing cut it short: it says so, and a Save's half-written picture (noted before
  each is written) and its line in History are cleared away, as the queue's are.

## The daily change

Off till it's turned on. At its time (07:00 at first) it changes the wallpaper; Mado has to be
running, open or in the tray (Start with Windows sits beside it), and closed at the time, it
changes as Mado next starts. A day's change comes only at a time after the change was turned on
or its time last set (`daily_since`), so one set once the day's time has passed first changes the
next day, and a time typed through others on the way (08:00 passes 00:00) changes nothing it
shouldn't; the window sends the time once it settles. From 12 hours before (19:00 the evening
before a 07:00 change) the day's pictures are picked and made by the jobs' worker, before the
queue's pictures as See it first's are, so the change is instant; when they weren't made ahead,
or making them ahead failed, they're made then, once; failing then, the day's change is given up
and says why. A day's wallpaper never set (Mado closed all that day) goes once its day has
passed. A monitor's pick suits it: its way round (a square either way) and, cropped to its shape,
made less than 6 times bigger (the Size tab's honest limit). Among those, the one not shown for
longest goes first, never-shown first, so none comes back till every one that suits has been;
ties go one way all day and another the next. One across all picks one picture for the whole
arrangement. A favourite gone, moved since or on a drive that isn't connected is skipped and
counted: the pick looks at each file, while the studio's counts (asked every few seconds) go by
Mado's records and each drive, looked at once a minute. The monitors changed since the day's
wallpaper was made (unplugged, resized, turned): it's made again. Its library folder taken out of
the library, the change turns off and says why, rather than turning to the favourites.

## Favourites

Kept by the picture's number. A Save in a picture's place keeps its number, so it stays a
favourite. A move or a rename is one picture gone and one found by the same scan: the heart goes to
the one found then with the same size and file time (Windows keeps both through a move), the same
name first, then the same folder. Two different files written in the same instant can share a
size and a time, so a picture that was there before never counts. A favourite whose picture stays
gone 30 days (the quarantine's month) is forgotten; one from outside the library is never let go
while it's a favourite.

## The monitors

Windows names a monitor by its device path (`\\?\DISPLAY#…#{e6f07b5f-…}`), IDesktopWallpaper's
monitor ID; Mado keeps it, and gives the window a short key from it. The display APIs, on a
thread made per-monitor DPI aware for the call (`SetThreadDpiAwarenessContext`), give each
monitor's place and own pixels, its scale (`GetDpiForMonitor`) and turn (`EnumDisplaySettingsExW`)
and the main one; DisplayConfig gives its own name ("24G4" on the owner's PC) and device path.
Read on the owner's PC: one monitor, 1920 × 1080 at 100%, main, its wallpaper the owner's JPEG.

One across all lays the picture over the monitors in Windows' own arrangement, its desktop pixels
(as Windows' display settings place them and its span lays a picture), a gap of up to 200 pixels
left between neighbours for the bezels: each line where monitors meet moves those past it on by
the gap, so a row or a column keeps its line.

## The lock screen

Left out: Windows lets only packaged apps (an MSIX with an identity) set the lock screen
(`Windows.System.UserProfile.LockScreen`), and Mado is an unsigned, unpackaged app.

## Untested till the owner first sets one

No test sets a real wallpaper (they use `tests/fake_desktop.py`; only `mado serve` hands the
studio `WindowsDesktop`), and the real desktop was only ever read. Untested, then: that
`SetWallpaper` sets each monitor and Windows shows the PNG pixel for pixel; that Windows'
`TranscodedWallpaper` for a PNG is a PNG (check it then); that setting a picture turns the
slideshow and spotlight off for good; `SetPosition`, `SetSlideshow` and `SetSlideshowOptions`
putting things back; setting an empty path for a monitor that had a colour; a monitor plugged in
or out while it's set; the slideshow's folder read through `IShellItemArray`; spotlight told by
`BackgroundType` 3 under `Explorer\Wallpapers` (read only on a PC with spotlight off); and
Windows' copy of one picture shown on several monitors (the owner's PC has one).

## Gotchas

- COM is opened on the calling thread for each call and closed after (the engine's threads call
  it: the API's, the jobs' worker, the daily change's); one already open another way
  (`RPC_E_CHANGED_MODE`) is left as it was.
- `GetMonitorDevicePathCount` counts monitors that aren't showing: `GetMonitorRECT` answers
  `S_FALSE` for them, and they're left out.
- The monitors' pixels come only from a per-monitor DPI aware thread; anything else gets them
  scaled to the main monitor's DPI.
- A `tests/test_desktop.py` test reads the real desktop (never sets it), so a build server without
  a desktop session says so in words and passes.
- Windows' refusals reach the owner in words ("Windows wouldn't set the wallpaper.", with what's on
  the desktop then); the code it answered (`0x80070005`…) goes to the log.
