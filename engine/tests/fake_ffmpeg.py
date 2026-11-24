"""Stands in for ffmpeg in tests: python fake_ffmpeg.py <ffmpeg's arguments>.

It answers the commands Mado builds, without the real program:

- decoding a HEIF to a PNG on its output (mado/pictures.py), without reading the file: it draws a
  made-up picture MADO_FAKE_SIZE big ("64x48" unless told), made smaller as the command's scale
  asks. MADO_FAKE_FAIL makes it fail as ffmpeg does on a file it can't decode, saying so on its
  error output.
- an encoder's check (mado/motion.py: a moment of grey from lavfi): it works for the encoders
  MADO_FAKE_ENCODERS names (comma-separated; "h264_mf" unless told), and fails as ffmpeg does for
  the rest. One named "libopenh264" never works here: Mado must never ask for it.
- making a video from frames on its input (rawvideo), with an encoder that works: it reads them
  all, checks they're a whole number of frames the size it was told, and writes a made-up MP4 (an
  "ftyp" box and the frames' count) to the path it was given last. MADO_FAKE_REFUSE makes the
  encoder refuse them at once, as one does a size it can't make, before reading any;
  MADO_FAKE_CHATTY makes it say a great deal on its error output before it reads them, as a
  verbose ffmpeg does.
"""

import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main(arguments: list[str]) -> int:
    if "lavfi" in arguments:
        return _check(arguments)
    if "rawvideo" in arguments:
        return _video(arguments)
    if os.environ.get("MADO_FAKE_FAIL"):
        sys.stderr.write("Invalid data found when processing input\n")
        return 1
    width, height = (int(n) for n in os.environ.get("MADO_FAKE_SIZE", "64x48").split("x"))
    if "-vf" in arguments:
        longest = int(re.findall(r"min\(iw,(\d+)\)", arguments[arguments.index("-vf") + 1])[0])
        scale = min(1.0, longest / max(width, height))
        width, height = max(1, round(width * scale)), max(1, round(height * scale))
    image = Image.new("RGB", (width, height), (120, 170, 230))
    ImageDraw.Draw(image).ellipse([1, 1, 1 + width // 6, 1 + width // 6], fill=(250, 220, 120))
    image.save(sys.stdout.buffer, format="PNG")
    return 0


def _works(arguments: list[str]) -> bool:
    """Whether the encoder asked for works here."""
    encoder = arguments[arguments.index("-c:v") + 1] if "-c:v" in arguments else ""
    working = os.environ.get("MADO_FAKE_ENCODERS", "h264_mf").split(",")
    if encoder == "libopenh264" or encoder not in working:
        sys.stderr.write(f"Error while opening encoder for output stream: {encoder}\n")
        return False
    return True


def _check(arguments: list[str]) -> int:
    return 0 if _works(arguments) else 1


def _video(arguments: list[str]) -> int:
    if not _works(arguments):
        return 1
    if os.environ.get("MADO_FAKE_REFUSE"):
        sys.stderr.write("Error: the encoder can't make video this size\n")
        return 1
    if os.environ.get("MADO_FAKE_CHATTY"):
        for line in range(20000):
            sys.stderr.write(f"frame={line} fps=30 q=28.0 size=0kB time=00:00:00.00 speed=1x\n")
        sys.stderr.flush()
    width, height = (int(n) for n in arguments[arguments.index("-s") + 1].split("x"))
    data = sys.stdin.buffer.read()
    frame = width * height * 3
    if not data or len(data) % frame:
        sys.stderr.write("Invalid frame size\n")
        return 1
    Path(arguments[-1]).write_bytes(
        b"\x00\x00\x00\x18ftypmp42" + b"frames=%d" % (len(data) // frame)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
