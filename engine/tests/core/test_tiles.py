"""Cutting a picture into tiles and laying each tile's result in the size made."""

import numpy as np
import pytest

from mado.core.tiles import count, place, starts, tiles, weights


def test_tiles_overlap_and_the_last_one_ends_at_the_edge():
    assert starts(1000, 512, 32) == [0, 480, 488]
    assert starts(512, 512, 32) == [0]
    assert starts(300, 512, 32) == [0]  # smaller than a tile: one, padded
    assert count(1920, 1080, 512, 32) == 4 * 3


def test_a_tile_knows_which_edges_it_shares():
    cut = tiles(1000, 600, 512, 32)

    first, last = cut[0], cut[-1]
    assert (first.x, first.y) == (0, 0)
    assert not first.inside_left
    assert first.inside_right
    assert first.inside_bottom
    assert (last.x, last.y) == (488, 88)
    assert last.inside_left
    assert not last.inside_right
    assert not last.inside_bottom


def test_every_pixel_made_comes_from_a_tile_with_some_weight():
    width, height, size, overlap = 700, 500, 256, 16
    target = (1234, 881)
    origin, span = (3.25, 2.5), (690.5, 493.0)
    total = np.zeros((target[1], target[0]), np.float64)
    for tile in tiles(width, height, size, overlap):
        where = place(tile, origin, span, target, 4)
        assert where is not None
        across, down = weights(tile, where, origin, span, target, overlap)
        assert np.all(across > 0)
        assert np.all(down > 0)
        total[where.v0 : where.v1, where.u0 : where.u1] += np.outer(down, across)
        left, top, right, bottom = where.box
        assert 0 <= left < right <= tile.width * 4
        assert 0 <= top < bottom <= tile.height * 4
    assert total.min() > 0.5  # covered everywhere, the fades meeting


def test_a_tile_lands_where_its_share_of_the_canvas_does():
    tile = tiles(1000, 1000, 512, 32)[0]  # the canvas's top left quarter, about
    where = place(tile, (0.0, 0.0), (1000.0, 1000.0), (2000, 2000), 4)

    assert where is not None
    assert (where.u0, where.v0, where.u1, where.v1) == (0, 0, 1024, 1024)
    assert where.box == pytest.approx((0.0, 0.0, 2048.0, 2048.0))
