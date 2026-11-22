"""Where LaMa's squares go to extend a picture's edges."""

from mado.core.outpaint import Square, squares


def _covers(
    found: list[Square], width: int, height: int, picture: tuple[int, int, int, int]
) -> bool:
    left, top, right, bottom = picture
    covered = [[False] * width for _ in range(height)]
    for square in found:
        for y in range(square.y, min(square.y + square.size, height)):
            for x in range(square.x, min(square.x + square.size, width)):
                covered[y][x] = True
    return all(
        covered[y][x]
        for y in range(height)
        for x in range(width)
        if not (left <= x < right and top <= y < bottom)
    )


def test_squares_cover_both_new_sides_and_reach_back_over_the_picture():
    width, height, picture = 120, 60, (20, 0, 100, 60)

    found = squares(width, height, picture)

    assert found
    assert all(square.size == 60 for square in found)
    assert _covers(found, width, height, picture)
    assert all(square.x + square.size > 20 for square in found if square.x < 20)


def test_a_band_wider_than_half_a_square_is_drawn_in_steps_outward():
    found = squares(400, 100, (150, 0, 250, 100))

    left = [square.x for square in found if square.x < 150]
    assert left == sorted(left, reverse=True)  # nearest the picture first
    assert len(set(left)) >= 3


def test_squares_go_down_the_top_and_bottom_when_the_canvas_is_taller():
    found = squares(60, 120, (0, 20, 60, 100))

    assert _covers(found, 60, 120, (0, 20, 60, 100))


def test_a_picture_that_fills_its_canvas_needs_no_squares():
    assert squares(60, 40, (0, 0, 60, 40)) == []
