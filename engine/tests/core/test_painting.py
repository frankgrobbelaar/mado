"""Painting styles by their rules (mado/core/painting.py): Mado's painters and the classic means,
the working canvas the networks paint on, a style mixed with the picture at a strength or in the
picture's own colours, the classic means drawn by code, and a style picture judged."""

import re

import numpy as np
import numpy.typing as npt
import pytest
from PIL import Image, ImageDraw

from mado.core.painting import (
    CANVAS,
    CLASSICS,
    NAMED,
    PAINTERS,
    SMALL_CANVAS,
    Painting,
    classic,
    code_of,
    code_text,
    enlarged,
    label,
    mado_style,
    mixed,
    named_after,
    off_canvas,
    on_canvas,
    phrase,
    picture_style,
    unsuited,
    working_size,
)
from tests.drawn import scene

type Pixels = npt.NDArray[np.uint8]


def _style(style_id: str):
    found = mado_style(style_id)
    assert found is not None
    return found


def _pixels(image: Image.Image) -> npt.NDArray[np.float32]:
    return np.asarray(image.convert("RGB"), np.float32)


def test_mados_painters_are_named_plainly_after_the_painter():
    assert [style.name for style in PAINTERS] == [
        "After Van Gogh",
        "After Hokusai",
        "After Monet",
        "After Seurat",
    ]
    for style in PAINTERS:
        assert style.kind == "painter"
        assert style.download is not None
        assert style.download.startswith("style-")
        assert style.painting  # the public-domain painting it learned from


def test_the_classic_means_each_have_one_setting():
    assert [(style.name, style.setting) for style in CLASSICS] == [
        ("Pencil sketch", "Darkness"),
        ("Coloured pencil", "Darkness"),
        ("Oil paint", "Brush"),
        ("Cartoon", "Colours"),
    ]
    assert all(style.kind == "classic" and style.download is None for style in CLASSICS)
    # No anime look: CLAUDE.md rules it out.
    assert not any(re.search(r"anime|manga", s.name, re.IGNORECASE) for s in (*PAINTERS, *CLASSICS))


def test_a_style_is_found_by_its_id_and_a_name_it_isnt_is_none():
    assert _style("van-gogh").name == "After Van Gogh"
    assert _style("oil").name == "Oil paint"
    assert mado_style("klimt") is None  # left out: it didn't earn its place
    assert mado_style("yours-3") is None


@pytest.mark.parametrize(
    ("size", "made"),
    [
        ((4032, 3024), (1392, 1044)),
        ((3024, 4032), (1044, 1392)),
        ((2000, 2000), (1392, 1392)),
        ((640, 480), (1392, 1044)),  # a small picture is painted at the same size, then shrunk
        ((7680, 4320), (1392, 783)),
        ((100_000, 10), (1392, 4)),
    ],
)
def test_the_working_size_gives_the_long_side_the_canvas(
    size: tuple[int, int], made: tuple[int, int]
):
    assert working_size(*size) == made


def test_a_picture_sits_on_the_canvas_with_the_rest_mirrored():
    pixels = np.zeros((100, 200, 3), np.uint8)
    pixels[:10] = (255, 0, 0)  # its top rows red
    pixels[-10:] = (0, 0, 255)  # its bottom rows blue

    canvas, at = on_canvas(pixels)

    assert canvas.shape == (1, 3, CANVAS, CANVAS)
    assert canvas.dtype == np.float32
    top, left = at
    assert (top, left) == ((CANVAS - 100) // 2, (CANVAS - 200) // 2)
    shown = canvas[0].transpose(1, 2, 0)
    assert np.allclose(shown[top : top + 100, left : left + 200], pixels / 255.0)
    # Just above the picture, its own top rows mirrored; just below, its bottom rows.
    assert np.allclose(shown[top - 5, left + 50], (1.0, 0.0, 0.0))
    assert np.allclose(shown[top + 104, left + 50], (0.0, 0.0, 1.0))


def test_a_small_copy_is_painted_on_a_smaller_canvas_a_multiple_of_4():
    pixels = np.asarray(scene(3, (256, 192)))

    size = working_size(256, 192, side=SMALL_CANVAS)
    canvas, at = on_canvas(np.asarray(Image.fromarray(pixels).resize(size)), side=SMALL_CANVAS)

    assert SMALL_CANVAS % 4 == 0
    assert SMALL_CANVAS < CANVAS
    assert size == (SMALL_CANVAS, round(SMALL_CANVAS * 192 / 256))
    assert canvas.shape == (1, 3, SMALL_CANVAS, SMALL_CANVAS)
    assert off_canvas(canvas, at, size).shape == (size[1], size[0], 3)


def test_off_the_canvas_the_picture_comes_back_as_it_was():
    pixels = np.asarray(scene(3, (300, 180)))

    canvas, at = on_canvas(pixels)
    back = off_canvas(canvas, at, (300, 180))

    assert back.shape == (180, 300, 3)
    assert np.abs(back.astype(int) - pixels.astype(int)).max() <= 1


def test_strength_mixes_the_painting_with_the_picture_as_it_was():
    picture = Image.new("RGB", (8, 8), (200, 40, 40))
    painting = Image.new("RGB", (8, 8), (40, 40, 200))

    assert _pixels(mixed(painting, picture, 1.0, colours=False))[0, 0].tolist() == [40, 40, 200]
    assert _pixels(mixed(painting, picture, 0.0, colours=False))[0, 0].tolist() == [200, 40, 40]
    half = _pixels(mixed(painting, picture, 0.5, colours=False))[0, 0]
    assert np.allclose(half, (120, 40, 120), atol=1)


def test_the_pictures_own_colours_keep_its_colour_with_the_paintings_lightness():
    picture = Image.new("RGB", (8, 8), (200, 40, 40))  # red
    painting = Image.new("RGB", (8, 8), (40, 60, 220))  # blue, darker than the red

    made = _pixels(mixed(painting, picture, 1.0, colours=True))[0, 0]

    assert made[0] > made[1]
    assert made[0] > made[2]
    assert abs(_light(made) - _light(np.array([40, 60, 220], np.float32))) < 3


def test_a_grey_picture_in_its_own_colours_stays_grey():
    picture = Image.new("RGB", (8, 8), (120, 120, 120))
    painting = Image.new("RGB", (8, 8), (30, 80, 200))

    made = _pixels(mixed(painting, picture, 1.0, colours=True))[0, 0]

    assert max(made) - min(made) <= 1


def test_a_painting_is_said_by_its_name_and_its_strength():
    van_gogh = _style("van-gogh")

    assert label(Painting(van_gogh, 0.8)) == "After Van Gogh"
    assert phrase(Painting(van_gogh, 1.0)) == "After Van Gogh"
    assert phrase(Painting(van_gogh, 0.8)) == "After Van Gogh at 80%"
    assert phrase(Painting(van_gogh, 0.8, colours=True)) == (
        "After Van Gogh at 80%, in the picture's own colours"
    )
    # On a part, said before its colours.
    assert phrase(Painting(van_gogh, 0.8, colours=True), on="on a part") == (
        "After Van Gogh at 80% on a part, in the picture's own colours"
    )
    # A classic one's setting is its own; its colours are its own anyway.
    assert phrase(Painting(_style("cartoon"), 1.0, colours=True, setting=70)) == "Cartoon"


def test_a_pictures_style_is_named_after_the_picture_however_long_its_name():
    assert named_after("Night market") == "Night market"
    assert named_after("x" * 240) == "x" * NAMED
    assert named_after("   ") == "A picture"


def test_a_pictures_style_is_named_after_the_picture_and_carries_its_code():
    code = np.linspace(-1, 1, 512, dtype=np.float32)

    style = picture_style("Night market", code)

    assert style.kind == "picture"
    assert style.name == "Night market style"
    assert style.code is not None
    assert np.array_equal(style.code, code)
    with pytest.raises(ValueError, match="512"):
        picture_style("Short", code[:100])
    with pytest.raises(ValueError, match="numbers"):
        picture_style("Broken", np.full(512, np.nan, np.float32))


def _light(colour: npt.NDArray[np.float32]) -> float:
    return float(0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2])


def _edge(size: tuple[int, int] = (240, 160)) -> Image.Image:
    """A flat red left half and a flat pale blue right half: one strong edge."""
    image = Image.new("RGB", size, (190, 40, 40))
    ImageDraw.Draw(image).rectangle([size[0] // 2, 0, size[0], size[1]], fill=(150, 190, 230))
    return image


def test_a_pencil_sketch_is_grey_white_where_the_picture_is_flat_and_dark_at_its_edges():
    made = _pixels(classic(_edge(), _style("pencil"), 50, reach=1.6))

    assert np.array_equal(made[..., 0], made[..., 1])
    assert np.array_equal(made[..., 1], made[..., 2])
    assert made[80, 30, 0] > 235  # flat: paper
    assert made[80, 117:123, 0].min() < 150  # the edge: a line


def test_darker_pencil_draws_darker_lines():
    light = _pixels(classic(_edge(), _style("pencil"), 0, reach=1.6))
    dark = _pixels(classic(_edge(), _style("pencil"), 100, reach=1.6))

    assert dark[80, 110:130].mean() < light[80, 110:130].mean() - 10


def test_coloured_pencil_keeps_each_colour_lightly_on_paper():
    made = _pixels(classic(_edge(), _style("coloured-pencil"), 50, reach=1.6))

    red, blue = made[80, 30], made[80, 200]
    assert red[0] > red[1] + 20  # still red
    assert blue[2] > blue[0]  # still blue
    assert red.mean() > np.array([190, 40, 40]).mean()  # lighter, as pencil on paper is


def test_oil_paint_keeps_flat_parts_flat_and_edges_sharp():
    made = _pixels(classic(_edge(), _style("oil"), 50, reach=1.6))

    assert np.allclose(made[80, 20:40].mean(axis=0), (190, 40, 40), atol=12)
    # The edge stays within a few pixels: no smear across it.
    assert made[80, 112, 0] > 160
    assert made[80, 128, 2] > 200


def test_a_cartoon_has_fewer_colours_its_own_hues_and_drawn_edges():
    picture = scene(5, (320, 240))
    made = _pixels(classic(picture, _style("cartoon"), 20, reach=2.4))
    edge = _pixels(classic(_edge(), _style("cartoon"), 40, reach=1.6))

    light = (made @ np.array([0.299, 0.587, 0.114])).round()
    assert len(np.unique(light)) < len(
        np.unique((_pixels(picture) @ np.array([0.299, 0.587, 0.114])).round())
    )
    assert edge[80, 30, 0] > edge[80, 30, 1] + 40  # the red stays red
    assert edge[80, 110:130].min() < 60  # ink along the edge


@pytest.mark.parametrize("style_id", ["pencil", "coloured-pencil", "oil", "cartoon"])
def test_a_classic_style_looks_the_same_in_a_preview_as_in_the_picture_saved(style_id: str):
    big = scene(7, (1600, 1200))
    small = big.resize((800, 600), Image.Resampling.LANCZOS)

    saved = classic(big, _style(style_id), 50, reach=12.0).resize((800, 600), Image.Resampling.BOX)
    preview = classic(small, _style(style_id), 50, reach=6.0)

    assert np.abs(_pixels(saved) - _pixels(preview)).mean() < 8


@pytest.mark.parametrize("style_id", ["pencil", "coloured-pencil", "oil", "cartoon"])
def test_a_classic_style_gives_the_same_picture_each_time(style_id: str):
    picture = scene(9, (200, 150))

    one = classic(picture, _style(style_id), 50, reach=1.5)
    two = classic(picture, _style(style_id), 50, reach=1.5)

    assert one.tobytes() == two.tobytes()


def test_a_style_picture_too_small_or_too_plain_is_said_so():
    flat = np.full((400, 600, 3), (120, 140, 160), np.uint8)
    noise = np.random.default_rng(1).normal(0, 2, flat.shape)
    nearly = np.clip(flat + noise, 0, 255).astype(np.uint8)
    lively = np.asarray(scene(11, (600, 400)))

    assert unsuited(np.asarray(scene(11, (80, 60)))) == "small"
    assert unsuited(flat) == "plain"
    assert unsuited(nearly) == "plain"
    assert unsuited(lively) is None


def test_a_pictures_style_travels_in_a_recipe_as_text_and_comes_back_the_same():
    code = np.random.default_rng(4).normal(0, 1, 512).astype(np.float32)

    text = code_text(code)

    assert np.array_equal(code_of(text), code)
    with pytest.raises(ValueError, match="512"):
        code_of(code_text(code[:10]))
    with pytest.raises(ValueError, match="written"):
        code_of("not base64 at all!")


def test_a_painting_made_far_bigger_than_its_painted_says_its_strokes_are_soft_close_up():
    van_gogh = Painting(_style("van-gogh"))

    assert enlarged(van_gogh, 4032, 3024) is None  # 12 megapixels: under three times
    said = enlarged(van_gogh, 7680, 4320)  # TV 8K
    assert said is not None
    assert "1392 × 783" in said
    assert "6 times" in said
    # A classic means is drawn at the size made: nothing to say.
    assert enlarged(Painting(_style("pencil")), 7680, 4320) is None
