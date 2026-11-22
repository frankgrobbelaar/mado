# ffmpeg (picture and video formats)

[ffmpeg](https://ffmpeg.org) 9.0.2 is the program Mado's tools will lean on for formats the
engine's own libraries don't read or write well (an iPhone's HEIC, AVIF, JPEG XL), and for the
short videos a 3D photo becomes. Mado doesn't ship it: Setup downloads one pinned build, from the
list in [engine/src/mado/downloads.json](../../engine/src/mado/downloads.json), the same list the
installer shows (see [releasing.md](../releasing.md)). Nothing in Mado runs it yet; the first tool
that does says how here.

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
their DLLs) and `mado-download.json`, which names the build and every file unpacked from it. When
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
