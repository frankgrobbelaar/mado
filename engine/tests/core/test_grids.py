"""A look as a table of colours: the grid, mixing between its points, strength, and keeping it in
few bytes."""

import numpy as np
import pytest

from mado.core.grids import MOST, SIDE, blended, identity, packed, resized, sample, unpacked


def _inverted(n: int) -> np.ndarray:
    """A look that turns every colour to its opposite: straight lines, so mixing is exact."""
    return (1.0 - identity(n)).astype(np.float32)


def test_the_identity_grid_leaves_every_colour_as_it_was():
    grid = identity(5)

    assert grid.shape == (5, 5, 5, 3)
    assert grid.dtype == np.float32
    # [blue][green][red]: red changes fastest, as .cube files and Pillow list them.
    assert grid[0, 0, 4].tolist() == [1.0, 0.0, 0.0]
    assert grid[4, 0, 0].tolist() == [0.0, 0.0, 1.0]
    colours = np.random.default_rng(1).random((50, 3), dtype=np.float32)
    assert np.allclose(sample(grid, colours), colours, atol=1e-6)


def test_colours_between_points_are_mixed_from_the_eight_around_them():
    colours = np.array([[0.1, 0.5, 0.9], [0.33, 0.0, 1.0], [1.0, 1.0, 1.0]], np.float32)

    assert np.allclose(sample(_inverted(3), colours), 1.0 - colours, atol=1e-6)


def test_strength_mixes_a_look_with_the_colours_as_they_were():
    look = _inverted(SIDE)

    assert np.allclose(blended(look, 0.0), identity(SIDE))
    assert np.allclose(blended(look, 1.0), look)
    assert np.allclose(blended(look, 0.6)[0, 0, 0], [0.6, 0.6, 0.6])  # black, 60% of the way


def test_a_grid_is_made_another_size_by_sampling_it():
    made = resized(_inverted(MOST), SIDE)

    assert made.shape == (SIDE, SIDE, SIDE, 3)
    assert np.allclose(made, _inverted(SIDE), atol=1e-6)


def test_a_grid_is_kept_in_few_bytes_and_comes_back_as_it_was():
    rng = np.random.default_rng(2)
    look = np.clip(identity(MOST) ** 0.8 + rng.normal(0, 0.002, (MOST, MOST, MOST, 3)), 0, 1)

    kept = packed(look.astype(np.float32))
    back = unpacked(kept, MOST)

    assert np.abs(back - look).max() <= 0.5 / 65535 + 1e-7
    assert len(packed(identity(MOST))) < 64 * 1024  # a smooth look: tiny beside its 7 MB .cube
    assert len(kept) < MOST**3 * 3 * 2  # never more than its 16-bit steps


def test_bytes_that_arent_a_grid_that_size_are_refused():
    with pytest.raises(ValueError, match="isn't a 33-point table"):
        unpacked(packed(identity(17)), SIDE)
    with pytest.raises(ValueError, match="isn't a 33-point table"):
        unpacked(b"not a table", SIDE)
