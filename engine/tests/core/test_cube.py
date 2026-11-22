"""Reading a .cube file: 3D tables of any size the format allows, the range its inputs cover, 1D
tables, and a plain sentence for one Mado can't use."""

from collections.abc import Callable

import numpy as np
import pytest

from mado.core.cube import CubeError, read
from mado.core.grids import MOST, Grid, identity, sample


def _rows(grid: Grid) -> str:
    """A grid's rows as a .cube lists them, red changing fastest."""
    return "\n".join(f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in grid.reshape(-1, 3).tolist())


def _same(rgb: Grid) -> Grid:
    return rgb


def _cube(points: int, look: Callable[[Grid], Grid] = _same, header: str = "") -> str:
    grid = look(identity(points))
    return f"{header}LUT_3D_SIZE {points}\n{_rows(grid)}\n"


def _inverted(rgb: Grid) -> Grid:
    return (1.0 - rgb).astype(np.float32)


def _beyond(rgb: Grid) -> Grid:
    """Values past both ends of 0 to 1, as an HDR look's can be."""
    return (rgb * 1.5 - 0.25).astype(np.float32)


def test_a_3d_table_with_its_title_and_comments_is_read():
    text = (
        "# Made by hand\n"
        'TITLE "Harbour warm"\n'
        "\n"
        "LUT_3D_SIZE 2\n"
        "# black, then red, green, yellow, blue, magenta, cyan, white\n"
        "0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n"
    )

    cube = read(text)

    assert cube.title == "Harbour warm"
    assert cube.points == 2
    assert np.allclose(cube.grid, identity(2))


def test_keywords_and_numbers_may_be_set_apart_by_tabs():
    text = 'TITLE\t"Tabbed"\nLUT_3D_SIZE\t2\n' + "0\t0\t0\n" * 8

    cube = read(text)

    assert cube.title == "Tabbed"
    assert cube.points == 2


def test_its_rows_go_red_first_then_green_then_blue():
    inverted = read(_cube(3, _inverted))

    colours = np.array([[0.25, 0.5, 1.0], [1.0, 0.0, 0.0]], np.float32)
    assert np.allclose(sample(inverted.grid, colours), 1.0 - colours, atol=1e-5)


def test_a_table_bigger_than_pillow_takes_is_sampled_down_to_65_points():
    cube = read(_cube(67, _inverted))

    assert cube.points == 67  # as the file has it
    assert cube.grid.shape == (MOST, MOST, MOST, 3)
    assert np.allclose(cube.grid, 1.0 - identity(MOST), atol=1e-5)


def test_the_range_its_inputs_cover_is_kept():
    # Inputs from 0 to 2, the table's outputs half its inputs: a picture's colours (0 to 1) use
    # the first half of the table, and come out half as bright.
    cube = read(_cube(3, header="DOMAIN_MIN 0 0 0\nDOMAIN_MAX 2 2 2\n"))

    colours = np.array([[0.5, 0.25, 1.0], [0.1, 0.9, 0.0]], np.float32)
    assert np.allclose(sample(cube.grid, colours), colours * 0.5, atol=1e-5)
    resolve = read(_cube(3, header="LUT_3D_INPUT_RANGE 0 2\n"))
    assert np.allclose(resolve.grid, cube.grid)


def test_values_outside_0_to_1_are_held_to_it():
    cube = read(_cube(2, _beyond))

    assert cube.grid.min() == 0.0
    assert cube.grid.max() == 1.0


def test_a_1d_table_becomes_a_3d_one():
    text = "LUT_1D_SIZE 3\n1 1 0\n0.5 0.5 0.5\n0 0 1\n"  # red and green turned over, blue kept

    cube = read(text)

    colours = np.array([[0.0, 0.25, 0.75], [1.0, 1.0, 0.5]], np.float32)
    expected = np.stack([1.0 - colours[:, 0], 1.0 - colours[:, 1], colours[:, 2]], axis=-1)
    assert cube.grid.shape == (MOST, MOST, MOST, 3)
    assert np.allclose(sample(cube.grid, colours), expected, atol=1e-4)


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("", "It isn't a .cube file: it has no table of colours in it."),
        ("hello there\n", "It isn't a .cube file: it has no table of colours in it."),
        ("0 0 0\n1 1 1\n", "It doesn't say how big its table is (LUT_3D_SIZE)"),
        (
            "LUT_3D_SIZE 300\n0 0 0\n",
            "Its table is 300 points a side; a .cube file's are 2 to 256.",
        ),
        ("LUT_3D_SIZE 1\n0 0 0\n", "Its table is 1 point a side; a .cube file's are 2 to 256."),
        ("LUT_3D_SIZE 2\n0 0 0\n1 1 1\n", "a 2-point table has 8 rows, and it has 2"),
        ("LUT_3D_SIZE 2\n" + "0 0 0\n" * 7 + "0 0\n", "Line 9 isn't three numbers: “0 0”."),
        ("LUT_3D_SIZE 2\n" + "0 0 0\n" * 7 + "0 nan 0\n", "Line 9 has a number Mado can't use"),
        (
            "LUT_1D_SIZE 2\nLUT_3D_SIZE 2\n" + "0 0 0\n" * 10,
            "It has two tables, a 1D one before a 3D one",
        ),
        ("LUT_3D_SIZE 2\nLUT_IN_VIDEO_RANGE\n" + "0 0 0\n" * 8, "“LUT_IN_VIDEO_RANGE”"),
        ("LUT_3D_SIZE 2\n" + "0 0 0\n" * 4 + 'TITLE "late"\n' + "0 0 0\n" * 4, "Line 6"),
        (
            "DOMAIN_MIN 1 0 0\nDOMAIN_MAX 1 1 1\nLUT_3D_SIZE 2\n" + "0 0 0\n" * 8,
            "Its DOMAIN_MIN isn't below its DOMAIN_MAX",
        ),
        ("LUT_3D_SIZE two\n0 0 0\n", "LUT_3D_SIZE says “two”, not a number of points."),
    ],
)
def test_a_file_mado_cant_use_says_why_in_a_sentence(text: str, said: str):
    with pytest.raises(CubeError) as refused:
        read(text)

    assert said in str(refused.value)
    assert str(refused.value).endswith(".")
