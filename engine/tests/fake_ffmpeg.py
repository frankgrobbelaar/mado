"""Stands in for ffmpeg in tests: python fake_ffmpeg.py <ffmpeg's arguments>.

It answers the one command mado/pictures.py builds, decoding a HEIF to a PNG on its output,
without reading the file: it draws a made-up picture MADO_FAKE_SIZE big ("64x48" unless told),
made smaller as the command's scale asks. MADO_FAKE_FAIL makes it fail as ffmpeg does on a file
it can't decode, saying so on its error output.
"""

import os
import re
import sys

from PIL import Image, ImageDraw


def main(arguments: list[str]) -> int:
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
