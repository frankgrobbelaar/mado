"""Search's real readers on made-up pictures drawn by code: PP-OCRv6 (fetched as Mado fetches it,
once, into pytest's cache), Windows' own reader (where Windows has an OCR language) and SigLIP
(only where MADO_SIGLIP_BASE_PATCH16_224_DIR names a copy on the PC: 208 MB is too much to fetch
for every run)."""

import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from mado.config import DataPaths
from mado.core.search import CUT, described, unit
from mado.directml import Sessions
from mado.ocr import PPOCR, Best, Fast
from mado.siglip import SIGLIP, Siglip
from mado.tools import Tools


@pytest.fixture(scope="session")
def ocr_tools(pytestconfig: pytest.Config, tmp_path_factory: pytest.TempPathFactory) -> Tools:
    """PP-OCRv6 small as Mado gets it, checked against the list's sizes and SHA-256s, once
    (MADO_PP_OCRV6_SMALL_DIR stands in with a copy on the PC)."""
    cache: pytest.Cache | None = getattr(pytestconfig, "cache", None)
    kept = cache.mkdir("ppocr") if cache else tmp_path_factory.mktemp("ppocr")
    tools = Tools(DataPaths(kept))
    if tools.folder(PPOCR) is None:
        tools.start(PPOCR)
        tools.wait(PPOCR, timeout=600)
    if tools.folder(PPOCR) is None:
        said = next((p.problem for item, p in tools.status() if item.id == PPOCR), None)
        if os.environ.get("CI"):
            pytest.fail(f"The tests couldn't fetch PP-OCRv6: {said}")
        pytest.skip(f"The tests couldn't fetch PP-OCRv6 (offline?): {said}")
    return tools


def sign(
    words: list[str], *, turn: float = 0.0, size: tuple[int, int] = (1200, 800)
) -> Image.Image:
    """A made-up sign: dark words on a light board over a sky, turned a little if asked."""
    picture = Image.new("RGB", size, (120, 170, 225))
    board = Image.new("RGB", (900, 120 * len(words) + 60), (240, 236, 222))
    pen = ImageDraw.Draw(board)
    font = ImageFont.load_default(size=72)
    for at, line in enumerate(words):
        pen.text((40, 30 + at * 120), line, fill=(30, 30, 40), font=font)
    board = board.rotate(turn, expand=True, fillcolor=(120, 170, 225))
    picture.paste(board, ((size[0] - board.width) // 2, (size[1] - board.height) // 2))
    return picture


def landscape() -> Image.Image:
    """A made-up landscape with no words in it."""
    picture = Image.new("RGB", (1200, 800), (130, 180, 230))
    pen = ImageDraw.Draw(picture)
    pen.polygon([(0, 800), (0, 520), (600, 430), (1200, 560), (1200, 800)], fill=(60, 120, 60))
    pen.ellipse([900, 90, 1020, 210], fill=(250, 220, 120))
    return picture


def test_best_reads_the_words_on_a_made_up_sign_turned_or_not(ocr_tools: Tools):
    best = Best(Sessions(), ocr_tools, lambda: "processor")

    straight = best.read(sign(["ZUMI 73", "Harbour lights"]))
    turned = best.read(sign(["ZUMI 73", "Harbour lights"], turn=10))

    assert straight.text == "ZUMI 73\nHarbour lights"
    assert straight.lines == 2
    assert turned.text == "ZUMI 73\nHarbour lights"  # each line cut out straight


def test_best_looks_first_and_finds_text_only_where_there_is_some(ocr_tools: Tools):
    best = Best(Sessions(), ocr_tools, lambda: "processor")

    def thumbnail(picture: Image.Image) -> Image.Image:
        small = picture.copy()
        small.thumbnail((512, 512))
        return small

    assert best.glance(thumbnail(sign(["ZUMI 73"])))
    # So it isn't read in full. (A plain sky that small can pass for text: the library's read
    # in full then, and finds none. docs/stack/search.md says how often.)
    assert not best.glance(thumbnail(boat()))


def test_windows_own_reader_reads_the_same_sign_where_windows_has_a_language():
    fast = Fast()
    if not fast.languages():
        pytest.skip("Windows here has no OCR language")

    read = fast.read(sign(["ZUMI 73", "Harbour lights"]))

    assert "ZUMI 73" in read.text
    assert "Harbour lights" in read.text
    assert read.language in fast.languages()


SIGLIP_COPY = os.environ.get("MADO_SIGLIP_BASE_PATCH16_224_DIR")


def boat() -> Image.Image:
    picture = Image.new("RGB", (800, 600), (135, 190, 235))
    pen = ImageDraw.Draw(picture)
    pen.rectangle([0, 330, 800, 600], fill=(30, 80, 170))
    pen.polygon([(260, 360), (540, 360), (500, 420), (300, 420)], fill=(200, 30, 30))
    pen.rectangle([395, 210, 405, 360], fill=(90, 60, 30))
    pen.polygon([(405, 215), (405, 350), (500, 350)], fill=(245, 245, 245))
    return picture


def forest() -> Image.Image:
    picture = Image.new("RGB", (800, 600), (170, 210, 240))
    pen = ImageDraw.Draw(picture)
    pen.rectangle([0, 470, 800, 600], fill=(70, 120, 50))
    for x in range(30, 800, 90):
        pen.polygon([(x, 480), (x + 40, 260), (x + 80, 480)], fill=(20, 90, 40))
        pen.rectangle([x + 34, 480, x + 46, 520], fill=(90, 60, 30))
    return picture


@pytest.mark.skipif(not SIGLIP_COPY, reason="no copy of SigLIP on this PC")
def test_siglip_finds_a_described_picture_and_nothing_for_whats_not_there(tmp_path: Path):
    siglip = Siglip(Sessions(), Tools(DataPaths(tmp_path)))
    assert siglip.ready(), f"SigLIP's files aren't in {SIGLIP_COPY} as downloads.json names them"
    pictures = [boat(), forest(), landscape(), sign(["ZUMI 73"])]
    vectors = unit([siglip.picture(each) for each in pictures])

    boats = described(vectors, siglip.search("a red boat on the sea"))
    trees = described(vectors, siglip.search("a forest of pine trees"))
    absent = described(vectors, siglip.search("a giraffe eating leaves"))

    assert boats.rows[:1] == (0,)
    assert trees.rows[:1] == (1,)
    assert all(score >= CUT for score in boats.scores)
    assert absent.rows == ()
    assert SIGLIP == "siglip-base-patch16-224"
