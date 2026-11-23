from mado.core.raw import (
    Inset,
    Problem,
    developed_size,
    orientation,
    preview_turn,
    problem,
    shown_crop,
    turned_box,
    wanted,
)


class TestOrientation:
    def test_says_which_way_up_as_exif_does(self) -> None:
        assert orientation(0) == 1
        assert orientation(3) == 3
        assert orientation(6) == 6  # turned a quarter clockwise to show
        assert orientation(5) == 8  # a quarter anticlockwise
        assert orientation(1) == 2  # mirrored
        assert orientation(7) == 7

    def test_a_flip_it_doesnt_know_is_upright(self) -> None:
        assert orientation(-1) == 1
        assert orientation(9) == 1


class TestCrop:
    def test_the_raws_own_crop_inside_its_picture(self) -> None:
        inset = Inset(left=110, top=60, width=1000, height=700)
        found = shown_crop(inset, width=1200, height=800, left_margin=10, top_margin=10)
        assert found == (100, 50, 1000, 700)

    def test_none_when_it_says_none(self) -> None:
        assert shown_crop(Inset(0xFFFF, 0xFFFF, 0, 0), width=1200, height=800) is None
        assert shown_crop(None, width=1200, height=800) is None

    def test_the_whole_picture_is_no_crop(self) -> None:
        assert shown_crop(Inset(0, 0, 1200, 800), width=1200, height=800) is None

    def test_one_running_past_the_picture_is_kept_inside_it(self) -> None:
        found = shown_crop(Inset(100, 0, 1200, 800), width=1200, height=800)
        assert found == (100, 0, 1100, 800)

    def test_one_keeping_less_than_half_isnt_believed(self) -> None:
        assert shown_crop(Inset(0, 0, 500, 800), width=1200, height=800) is None


class TestTurnedBox:
    def test_upright_stays(self) -> None:
        assert turned_box((10, 20, 30, 40), (100, 80), 0) == (10, 20, 30, 40)

    def test_half_round(self) -> None:
        assert turned_box((10, 20, 30, 40), (100, 80), 3) == (60, 20, 30, 40)

    def test_a_quarter_clockwise(self) -> None:
        # A part at the stored picture's top left ends at the shown picture's top right.
        assert turned_box((0, 0, 30, 40), (100, 80), 6) == (40, 0, 40, 30)

    def test_a_quarter_anticlockwise(self) -> None:
        # Its top left ends at the bottom left.
        assert turned_box((0, 0, 30, 40), (100, 80), 5) == (0, 70, 40, 30)


class TestDevelopedSize:
    def test_as_shown_cropped_and_turned(self) -> None:
        assert developed_size(1200, 800, None, 0) == (1200, 800)
        assert developed_size(1200, 800, (100, 50, 1000, 700), 0) == (1000, 700)
        assert developed_size(1200, 800, (100, 50, 1000, 700), 6) == (700, 1000)


class TestWanted:
    def test_the_cameras_preview_when_its_big_enough_and_the_same_shape(self) -> None:
        assert wanted((1600, 1067), (6000, 4000), 512) == "preview"

    def test_developed_at_half_size_when_the_preview_is_too_small(self) -> None:
        assert wanted((160, 120), (6000, 4000), 512) == "half"

    def test_developed_when_the_preview_is_another_shape(self) -> None:
        assert wanted((1600, 900), (6000, 4000), 512) == "half"

    def test_developed_when_there_is_none(self) -> None:
        assert wanted(None, (6000, 4000), 512) == "half"

    def test_at_full_size_when_half_isnt_enough(self) -> None:
        assert wanted(None, (1200, 800), 1024) == "full"
        assert wanted(None, (6000, 4000), None) == "full"

    def test_never_the_preview_at_full_size(self) -> None:
        assert wanted((6000, 4000), (6000, 4000), None) == "full"

    def test_never_the_preview_for_the_view_the_size_of_a_screen(self) -> None:
        # The page and its tabs show what Save makes: the picture developed, not the camera's.
        assert wanted((6000, 4000), (6000, 4000), 2560) == "half"

    def test_a_small_picture_takes_a_preview_its_own_size(self) -> None:
        assert wanted((400, 267), (400, 266), 512) == "preview"


class TestPreviewTurn:
    def test_stored_as_the_sensor_was_held(self) -> None:
        assert preview_turn((1600, 1067), (4000, 6000), 6) == 6

    def test_already_upright(self) -> None:
        assert preview_turn((1067, 1600), (4000, 6000), 6) == 0

    def test_upright_raws_preview(self) -> None:
        assert preview_turn((1600, 1067), (6000, 4000), 0) == 0

    def test_none_when_its_shape_isnt_the_pictures_either_way(self) -> None:
        assert preview_turn((1600, 900), (6000, 4000), 0) is None


class TestProblem:
    def test_a_file_it_doesnt_know(self) -> None:
        found = problem(-2, "open")
        assert found.kind == "unknown"
        assert "doesn't know" in found.sentence

    def test_damaged_data(self) -> None:
        assert problem(-100008, "unpack").kind == "damaged"
        assert problem(-100009, "open").kind == "damaged"

    def test_too_big_for_the_memory(self) -> None:
        assert problem(-100007, "develop").kind == "memory"
        assert problem(-100012, "develop").kind == "memory"
        assert problem(12, "develop").kind == "memory"  # ENOMEM, as its picture's copy says it

    def test_anything_else_says_its_code(self) -> None:
        found = problem(-4, "develop")
        assert found == Problem("other", found.sentence)
        assert "-4" in found.sentence
