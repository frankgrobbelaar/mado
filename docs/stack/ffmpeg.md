# ffmpeg (picture and video formats)

[ffmpeg](https://ffmpeg.org) 9.0.2 is the program Mado leans on for formats the engine's own
libraries don't read or write (a phone's HEIC now; JPEG XL and the short videos a 3D photo becomes
as the tools come). Mado doesn't ship it: Setup downloads one pinned build, from the list in
[engine/src/mado/downloads.json](../../engine/src/mado/downloads.json), the same list the installer
shows (see [releasing.md](../releasing.md)).

## What Mado runs it for

| For | Command | Where |
| --- | --- | --- |
| A HEIC's pixels, for its thumbnail, its view and its full-size copy | `ffmpeg -v error -nostdin -noautorotate -i <picture> -frames:v 1 [-vf scale=…] -f image2pipe -c:v png -pix_fmt rgb24 -` | `_decode_heif` in [mado/pictures.py](../../engine/src/mado/pictures.py) |

- **Its facts aren't ffmpeg's.** A HEIC's size, turn and Exif come from Mado's own reading of its
  layout (see [pillow.md](pillow.md#heic-and-heif)), so the library lists a HEIC without ffmpeg.
- **Mado turns it, not ffmpeg.** `-noautorotate` has ffmpeg decode it as stored; Mado then turns
  it as the layout's `irot` and `imir` say, the same way it turns every other picture. Checked
  with a HEIF-family file libavif wrote, turned a quarter round: ffmpeg gives it as stored, and it
  comes out upright.
- **The whole picture or none.** A phone's HEIC is a grid of tiles; ffmpeg 7.1 and later puts
  them together. A decoded picture whose shape isn't the layout's isn't shown as the whole, and
  says why.
- **Scaled in ffmpeg** for a thumbnail (`scale='min(iw,512)':'min(ih,512)':
  force_original_aspect_ratio=decrease`, never larger than it is), so a 12-megapixel picture
  isn't piped whole for a 512-pixel copy.
- A run that fails says ffmpeg's last line ("Invalid data found when processing input"), and the
  picture is listed as one that won't open. `tests/fake_ffmpeg.py` stands in for ffmpeg in the
  tests.

## Which build, and why

- **BtbN's LGPL shared build for Windows** (`ffmpeg-n9.0.2-…-win64-lgpl-shared-9.0.zip`,
  77 MB): the release branch with nothing under the GPL, so Mado's MIT code may drive it. The
  shared build keeps ffmpeg's libraries as separate DLLs.
- **Pinned to a month's last build.** BtbN keeps the last build of each month for two years, while
  "latest" changes daily. `downloads.json` names one such build with its size and SHA-256, and
  Mado uses the download only when both match.
- **Downloaded from BtbN, not from Mado.** The PC fetches it from where it's published, with its
  licence and source there.

## Where it lives

`%LOCALAPPDATA%\Mado\tools\ffmpeg\` holds the build's `bin` folder (ffmpeg.exe, ffprobe.exe and
their DLLs), its licence (`LICENSE.txt`, from the archive's top: `notices` in `downloads.json`)
and `mado-download.json`, which names the build and every file unpacked from it. When
`downloads.json` moves to a new build, the next start sees the difference and offers the download
again; the new build replaces the old one. A file that goes missing (an antivirus, say) makes
ffmpeg "missing" again, and Setup offers the download.
[mado/tools.py](../../engine/src/mado/tools.py) does the downloading, checking and unpacking, and
finds the programs.

In development, set `MADO_FFMPEG_DIR` to a folder holding `ffprobe.exe` and `ffmpeg.exe` to skip
the download.

## Running it

What Kura learnt running ffmpeg under its window holds for Mado: run it as a child process with
`CREATE_NO_WINDOW`, so no console window flashes, and give it nothing on standard input
(`stdin=DEVNULL`). Under the window the engine's standard input is a pipe from the app, and an
ffmpeg looking at it for key presses can stop for good part way through a file.

## Moving to a newer build

1. Pick the last build of a month on [BtbN's releases](https://github.com/BtbN/FFmpeg-Builds/releases)
   (`autobuild-YYYY-MM-<last day>-…`) and its `win64-lgpl-shared` zip for the newest release branch.
2. Put its address, size and SHA-256 (the release lists each asset's digest) in `downloads.json`.
3. Run the engine tests, and check the download in Setup before releasing.

A new pin means every copy of Mado downloads ffmpeg again (77 MB), so it moves for a new release
or a month's last build, not for each day's.
