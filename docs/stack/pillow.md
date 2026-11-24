# Pillow (reading pictures)

[Pillow](https://python-pillow.org) 13.0 (MIT-CMU) reads the pictures in the library: what each
one is (its size, format and EXIF), and its pixels for the smaller copies the window shows. Its
wheels carry the libraries it decodes with (libjpeg-turbo, libpng, libtiff, libwebp, libavif with
dav1d and aom, OpenJPEG, Little CMS), all under permissive licences that its own licence file
repeats, so THIRD-PARTY-NOTICES.txt carries them with it.

## What Mado reads with it

| Format | Read by | Notes |
| --- | --- | --- |
| JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF | Pillow | `kind_of` in `mado/core/files.py` decides by extension |
| HEIC, HEIF (a phone's) | Mado's own reader and ffmpeg | Pillow has no HEIF decoder; see below |
| Camera RAW (CR3, NEF, ARW, DNG…) | LibRaw, downloaded the first time a RAW is read | Its facts without developing it, a small copy from the camera's own preview, anything bigger developed into Display P3 (see [libraw.md](libraw.md)); Pillow then makes the copies as for any picture |
| An HDR photo's gain map: JPEG (Ultra HDR, ISO 21496-1), AVIF, HEIC (Apple's, ISO 21496-1's) | Mado's own reader (`mado/hdr.py`); the gain map's pixels by Pillow, or ffmpeg for HEVC | Found from the headers alone as a picture is read; the picture itself is read as its format always is (Pillow sees an Ultra HDR JPEG as a JPEG, its first picture); see [hdr.md](hdr.md) |

## Files

| File | What it does |
| --- | --- |
| `mado/pictures.py` | `read_facts` (header and EXIF, no decoding) and `decode` (pixels, turned upright); a camera RAW's through `mado/libraw.py` |
| `mado/core/facts.py` | EXIF's values in Mado's words: when it was taken, the camera, which way up, a location |
| `mado/core/heif.py` | A HEIF's layout: its size, its turn (`irot`, `imir`) and where its Exif is |
| `mado/hdr.py`, `mado/core/gainmap.py`, `mado/core/jpegs.py`, `mado/core/heif_writer.py` | An HDR photo's gain map: found from the headers, decoded as gains, written again as Ultra HDR JPEG or an AVIF's `tmap` item (see [hdr.md](hdr.md)) |
| `mado/previews.py` | The copies the window shows, kept in the data folder's cache |
| `mado/looks.py` | Looks through `ImageFilter.Color3DLUT`, and the soft touches through `ImageChops` (see [looks.md](looks.md)) |
| `tests/drawn.py` | Made-up pictures for the tests, with EXIF written the way a camera writes it |
| `tests/hdr_files.py` | Made-up HDR photos: Ultra HDR JPEGs, AVIFs with a `tmap` item, HEICs built box by box |

## The facts

- **When it was taken** is EXIF's DateTimeOriginal, the camera's clock as it was set, kept as
  local time without a zone. A picture without one (a screenshot, a scan) goes by its file's
  time. A clock never set writes zeros, which count as no date.
- **The camera** is Make and Model, the maker named once ("Lumen X100", not "Lumen Lumen X100").
- **Its size** is as it's shown: a picture its orientation turns on its side is taller than wide.
- **A location** is a GPS latitude and longitude both; Mado only notes that it carries one.
- `getexif()` reads EXIF without decoding the picture, so a scan reads a picture's facts fast.
  Damaged EXIF leaves the picture readable, its facts unknown.

## The copies

| Copy | Size | Format | Made |
| --- | --- | --- | --- |
| Thumbnail | 512 px on its longer side | WebP, quality 80 | as the scan reads each picture, or when first asked for |
| View | 2560 px | WebP, quality 88; an HDR photo's an Ultra HDR JPEG at 88, its gain map with it | when a picture's page first opens |
| Full size | as it is | the picture itself (JPEG, PNG, WebP, AVIF, GIF, BMP), else PNG; an HDR HEIC's an Ultra HDR JPEG at 95 | when it's zoomed to 100% |

- A JPEG decodes at a smaller scale first (`draft`), so a thumbnail of a 12-megapixel photo takes
  a few milliseconds.
- `ImageOps.exif_transpose` turns each copy the way the picture is shown, and drops the turn from
  it, so the window never turns it twice.
- Pixels the window can't show become ones it can: 16-bit grey (a scanner's) keeps each pixel's
  high byte, print colours (CMYK) go through their colour profile to screen colours, and palette
  and see-through pictures keep their transparency (WebP holds it).
- A picture's own colour profile (Display P3, Adobe RGB) goes into its copies, so wide colours
  stay wide in the window.
- Decoding is the damage check: a half-copied file has its header but not its pixels, and making
  its thumbnail says so ("The file is damaged or was only half copied").
- Copies are named after the picture's version (its file's time and size), written beside their
  place and then moved in, so a picture that changes gets new ones and a copy is never half there.
  Only the newest eight full-size copies are kept; anything in the cache can go.
- Windows won't replace or delete a file the window is reading. A copy made twice at once keeps
  the one already there (the same version of the same picture), and one that can't be taken away
  yet stays, harmless, as its name says its version. A copy Mado can't keep at all (the data
  folder's drive full) is no fault of the picture's: it stays readable, the window says why, and
  the copy is made when it's next asked for.

## HEIC and HEIF

Pillow can't decode HEIF, and the readers that can (libheif) come with LGPL and GPL parts, so
Mado reads a HEIF's facts itself and has ffmpeg decode its pixels:

- `core/heif.py` walks the file's boxes to its layout (the `meta` box): the primary item's size
  (`ispe`), how it's turned and mirrored (`irot`, `imir`, as an EXIF orientation), and where its
  Exif item is, which Pillow then reads like any EXIF. So a HEIC's date, camera and location are
  read without ffmpeg.
- ffmpeg decodes it to a PNG on its output (`-noautorotate`, scaled down in ffmpeg for a
  thumbnail), and Mado turns it as the layout says. A decoded picture whose shape isn't the
  layout's (one tile of a grid) isn't shown as the whole.
- Without ffmpeg, a HEIC is read and listed, and its copies wait for it.

## Limits

Pillow refuses pictures over 89 megapixels, a guard for servers taking strangers' files. Mado's
pictures are the owner's own, and panoramas and scans can be bigger, so Mado raises the limit to a
gigapixel (about 3 GB to decode); a bigger picture is listed as one Mado doesn't open.

## Upgrading

`uv lock --upgrade`, then run the tests: they decode every format, mode and orientation Mado
handles, from pictures they draw. Pillow's typing is partly unknown to Pyright around colour
management, which `pictures.py` calls through `Any`.
