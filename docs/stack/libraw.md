# LibRaw (reading camera RAW)

[LibRaw](https://www.libraw.org) 0.22.3 reads camera RAW for Mado: CR3, NEF, ARW, DNG and the
rest. It is LGPL-2.1 or CDDL-1.0, so Mado never ships it: the PC downloads LibRaw's own Windows
build the first time Mado reads a RAW, from the address
[engine/src/mado/downloads.json](../../engine/src/mado/downloads.json) names, and uses it only when
its size and SHA-256 match the list, as the installer's first page lists it. Its three licence
files (`LICENSE.LGPL`, `LICENSE.CDDL`, `COPYRIGHT`) come with it, kept beside it.

| File | Does |
| --- | --- |
| `mado/libraw.py` | LibRaw's DLL through ctypes: a RAW's facts, its camera's preview, the picture developed; `Reader`, which fetches LibRaw the first time it's needed |
| `mado/core/raw.py` | Pure: LibRaw's flip as EXIF's orientation, the RAW's own crop, its size as shown, preview or develop, LibRaw's errors in Mado's words |
| `mado/core/icc.py` | Pure: Mado's own Display P3 profile, written by code |
| `mado/pictures.py` | `read_facts`, `decode` and `read_exif` for a RAW, through the reader |
| `tests/dng_files.py` | Made-up DNGs for the tests (a Bayer mosaic under a camera's tags, with or without previews) |

## Which build, and which part

- **LibRaw's own build**: `LibRaw-0.22.3-Win64.zip` (3.5 MB, built with MSVC 2022), from LibRaw's
  download page, released 2026-10-24. Of it Mado keeps `libraw.dll`, from its `bin` folder
  (`"only"` in `downloads.json`: not LibRaw's sample programs), and its licence files. Never a
  build of Mado's or anyone else's. `MADO_LIBRAW_DIR` stands in with a copy for an engine run from
  its source (the tests); the installed engine never takes one, only what it downloaded and checked.
- **Its DLL, not its programs.** Both were measured (below). The DLL wins on every count: a RAW's
  facts take 0.5 ms against `raw-identify`'s 26 ms (a process each, so a scan of a thousand RAWs
  would spend half a minute starting programs); its programs take a file's name in the PC's old
  code page, so `raw-identify` couldn't open `東京 Café\写真.dng` ("Cannot decode ??.dng"), while
  `libraw_open_wfile` does; and the programs that take a camera's preview out (`simple_dcraw -e`,
  `mem_image`) write it beside the RAW as `<name>.thumb.jpg`, where Mado writes nothing before
  Save. Developing is the same code either way, the DLL 10 to 25% quicker without a process and a
  pipe.
- **In the engine.** Each file gets a LibRaw of its own (`libraw_init`, opened read-only, closed
  after), so threads never share one; ctypes lets go of Python's lock for each call. A fault inside
  LibRaw that ctypes turns into an error makes that RAW one that won't open. Every read through
  LibRaw (a scan's, a page's, a tab's, the queue's, See it first's, the studio's, the duplicates'
  sharpness) notes its RAW while it reads, in a file of its own in the data folder's `reading-raw`
  folder named for the engine's run (`Reader.reading`); a clean stop clears its own. As the engine
  starts, before its scan, its duplicates and its queue, a note an earlier run left marks its RAW as
  one that won't open (`scan.stopped_on`), so a RAW that stopped the engine outright never stops it
  again. A power cut during a read leaves such a note too: the RAW is marked though nothing's wrong
  with it, and Try again reads it again.

## Reading a RAW

| What | How |
| --- | --- |
| Its facts | `libraw_open_wfile` and LibRaw's structs, never unpacking: its size as shown (`libraw_adjust_sizes_info_only`, after the RAW's own crop and turn), when it was taken (LibRaw reads EXIF's local time with `mktime`; Mado turns it back with `fromtimestamp`), the camera (Make and Model, the maker named once), its turn as EXIF's orientation, and whether it says where |
| A small copy (the grid's thumbnail, a burst's sharpness, 1024 px at most) | The preview its camera kept inside it (`libraw_unpack_thumb`, `libraw_dcraw_make_mem_thumb`), JPEG decoded at a smaller scale first, laid out upright by the RAW's turn (or as it is, when the camera kept it upright already), when it's at least the size asked for and the picture's shape within 1%; else developed at half size, as when its preview won't hand over or decode (no fault of the RAW's) |
| The view the size of a screen, and full size | Always developed: at half size when that's at least 2560 px, else full. The camera's preview is its own rendering (its tone curve, its sharpening), and the page, the tabs' stages and Save must show one picture. The Looks tab's small copies and the Edit tab's "With what you picked" come from the view too |
| Its EXIF, for a picture made from it | Written from LibRaw's facts: Make, Model, DateTimeOriginal, ISO, exposure, aperture, focal length, lens, and GPS (kept only when the owner keeps the place) |

**Developing** (`LibRaw.develop`) follows the camera:

- **White balance**: the camera's as shot (`use_camera_wb`), so a grey comes out grey.
- **The RAW's own crop and turn**: LibRaw's `raw_inset_crops[0]` (a DNG's default crop with any
  user crop, a maker's own crop), placed in the picture LibRaw develops and cut after developing,
  turned as LibRaw lays it out (`turned_box`), so the colour pattern never shifts; a crop that would
  keep less than half of either side isn't believed. The crop follows the size developing made:
  LibRaw halves only a colour filter array's pixels, so a linear RAW (some phones', a monochrome
  camera's) asked for at half size comes out whole, and is cut whole. LibRaw turns the picture
  upright itself.
- **Into Display P3**, not sRGB: a camera's colours go past sRGB (a flower, a sunset), and Mado
  keeps a picture's own colour space through every tool (looks, edits, sizes) into the picture it
  saves, so they stay. Display P3 is what wide screens and phones show (a RAW and a phone's photo
  of one moment look alike), and 8 bits over it band far less than over Adobe RGB or ProPhoto,
  which screens can't show anyway. LibRaw's `DCI-P3 D65` (`output_color` 7) on sRGB's curve
  (`gamma` 2.4, toe slope 12.92), with Mado's own profile (`core/icc.py`: Display P3's primaries
  seen in D50, sRGB's parametric curve) attached, as LibRaw's in-memory picture carries none.
- **At 8 bits**, the depth Mado's pipeline works in.
- Otherwise LibRaw's own: AHD demosaicing, and its brightening (the brightest 1% of pixels at
  white). It's a neutral develop: no picture style, lens corrections or sharpening.

LibRaw's C API has no call for half size or the camera's white balance, so `develop` writes them
into LibRaw's options struct (`libraw_output_params_t`), mirrored with ctypes, at the place
`_OPTIONS_AT` names for the version (5232 bytes into `libraw_data_t` for 0.22.3, measured from its
header). Before writing, `LibRaw._confirm` sets seven options through LibRaw's own setters and reads
them back through the mirror; any that doesn't match, or a version Mado doesn't know, and Mado
doesn't use that LibRaw (it's fetched again). The struct holding the sizes sits right after the
picture's pointer, and its size is checked against where `libraw_get_iparams` says the next one is.
A half-size develop through the DLL matched `dcraw_emu -w -h -o 7 -g 2.4 12.92` byte for byte.

## When it isn't there

The first time a RAW is read or opened (a scan reading one, its page, a file dropped or opened from
File Explorer, a watch folder), `Reader.library` starts the download (`Tools.start`), again a
minute after a try that failed, and says the RAW waits (`NeedsReaderError`); Try again starts it at
once. RAWs listed while they wait (by Mado 0.7.0, which listed RAW as it found it, or before a
failed download and a restart) ask too: a scan that finds any asks (`Reader.ask`), as does opening
one's page. A download that didn't match the list isn't fetched again by itself (the file online
isn't the one listed): only Try again fetches it. Till it's there:

- the scan lists a RAW as it is (`read_at` set, no size: `library.WAITING`, state `waiting`), by its
  file's time, and leaves it while the reader is away; once it arrives, `Tools.arrived` asks for a
  scan, which reads the RAWs waiting;
- a RAW's tile says "Getting the RAW reader · 46%", "Needs the RAW reader" (it didn't come) or
  "Waiting for the RAW reader" (in a page's strip of pictures, "RAW · 46%" or "RAW", the rest on
  hover); its page shows the download in its place (its size, progress, or why it didn't come, in
  the download's own words: offline, or not the file the list names, with Try again) and reads the
  RAW the moment it's there; Home counts the RAWs waiting;
- a batch leaves its RAWs out, each saying why (`waiting`), shows the download, and asks for its
  pictures again once it's there, and every 3 s after while the scan reads them ("It's a camera RAW
  Mado is reading now: it joins once it's read");
- a watch folder waits with them, never giving up on them as pictures that won't open, its row
  saying they wait for the reader till none do;
- Settings › About lists LibRaw with the other downloads: there, or "fetched the first time Mado
  reads a camera RAW".

## RAWs it can't read

| Which | What Mado says |
| --- | --- |
| Damaged, half copied | Its tags and its camera's preview may be all there, so the scan lists it with its thumbnail; developing it (its page's view, its full size, a Save) fails with LibRaw's data error, and the RAW joins Won't open: "The file is damaged or was only half copied: Mado's RAW reader stopped partway through it." |
| A kind LibRaw doesn't know (a camera newer than it), or not a RAW at all | `LIBRAW_FILE_UNSUPPORTED` as it opens: "Mado's RAW reader doesn't know this kind of RAW file yet (a camera newer than it, say), or it isn't one." A DNG compressed lossily fails here too, as this build without libjpeg doesn't take it for a picture at all |
| One it can read but not unpack: JPEG XL (Adobe's DNG SDK), deflate (zlib) | The decoder LibRaw chose, asked before unpacking (`libraw_get_decoder_info`: a failed unpack forgets it), against what this build has (`libraw_capabilities`): "Mado's RAW reader can read its details but not its picture: it's packed in a way the reader doesn't know yet." Never told as damage |
| Open in another app | LibRaw opens a file sharing only reads, so one another app writes to won't open to it: `opens_to_read` opens it the same way first, and Windows' sharing violation says it's in use, read a minute on, never kept as one that won't open |
| Too big for the memory free (LibRaw's own errors, or ENOMEM as it copies the picture out) | "It's too big to develop with the memory free now. Close other apps, then try again." It passes, so it's never kept as one that won't open: the scan reads it again a minute on |

**A phone's DNG** is read as any DNG: a Bayer DNG (most phones) or a linear one (some phones' own
RAW). This build has no JPEG library, zlib or Adobe's DNG SDK, so DNGs compressed lossily, with
deflate (an HDR merge's floating point) or with JPEG XL don't develop and say why. Phones' DNGs
often carry no preview, or a small one: their thumbnails are developed at half size. LibRaw
doesn't apply a DNG's opcode lists (a phone's lens shading), so a phone's DNG can look darker at
its corners than the phone's own picture.

**A huge RAW** (100 megapixels): its facts and its camera's preview come as fast as any; its view
is developed at half size in about a second and a half; at full size it takes about 13 s and some
2 GB of memory while LibRaw works, so a picture's page says "Developing the RAW at full size: 101
megapixels take a while…" as it's zoomed to 100%, and Save waits for it too. Edit's limit of 100
megapixels applies as to any picture.

## Measured

On the owner's PC (i5-9600K, 6 cores; LibRaw's build is single-threaded), on made-up DNGs drawn by
code, 2026-11-23, while a training run had the graphics card (developing needs only the processor).
Medians:

| | 24 MP (6000 × 4000) | 100 MP (12288 × 8192) |
| --- | --- | --- |
| Facts: `raw-identify` (a process) | 26 ms | 27 ms |
| Facts: the DLL | 0.5 ms | 0.4 ms |
| Facts: Mado's `read_facts` | 0.7 ms | 0.7 ms |
| Thumbnail from the camera's preview | 68 ms | 181 ms |
| Thumbnail with no preview (developed at half size) | 352 ms | 1.37 s |
| The view (developed at half size, 2560 px) | 427 ms | 1.63 s |
| Developed at half size: `dcraw_emu` / the DLL | 411 / 325 ms | 1.61 / 1.31 s |
| Full size: `dcraw_emu` / the DLL | 3.33 / 3.05 s | 13.8 / 12.9 s |
| Full size through `decode` | 3.13 s | 13.1 s |

**A scan of 1,000 made-up DNGs** (1600 × 1200, each with a full-size preview, 4.3 GB in all), its
facts and thumbnails: 49.6 s, 50 ms a RAW, against 50.7 s for the same scenes as JPEGs (0.4 GB). A
folder of RAWs scans as quickly as one of JPEGs, its thumbnails coming from the previews the camera
kept.

## Tested only through DNG

The tests read DNGs written by code (`tests/dng_files.py`): no real photo, and no sample RAW from
the web, is ever used. Among them: Bayer and linear DNGs, with and without previews (whole, small,
cut short), turned, cropped, half copied, and one saying it's packed with deflate. CR2, CR3, CRW,
NEF, NRW, ARW, SR2, SRF, RAF, ORF, RW2, RWL, PEF, SRW, ERF, KDC, MOS, MRW, IIQ, 3FR, X3F and RAW
were tested only through DNG: they're LibRaw's to read, as its own camera list says.

## Moving to a newer LibRaw

1. On [LibRaw's download page](https://www.libraw.org/download), take the new release's
   `-Win64.zip`; put its address, size and SHA-256 in `downloads.json`.
2. Measure where its options struct sits: compile a few lines printing
   `offsetof(libraw_data_t, params)` against its `libraw/libraw_types.h` (MSVC, `/DWIN32`), and add
   it to `_OPTIONS_AT` with the version. Check `libraw_output_params_t`'s fields still read as
   `_Params` has them (the `_confirm` check and the tests catch a moved field).
3. Run the engine tests: the `libraw_folder` fixture fetches the new build as Mado will.

A new pin means every copy of Mado downloads LibRaw again (3.5 MB), the first time it next reads a
RAW.
