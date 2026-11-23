"""Duplicates and bursts: which pictures are one picture saved more than once, or shots of one
moment, which are never grouped, and which of each group to keep."""

from dataclasses import replace
from datetime import datetime, timedelta

from mado.core.duplicates import (
    BURST,
    BURST_GAP,
    FINE,
    NEAR,
    Known,
    copy_base,
    groups,
    is_copy_name,
    suggested,
)

MOMENT = datetime(2026, 11, 14, 10, 2, 14)
FINE_PRINT = bytes(range(32))


def flipped(value: int, bits: int) -> int:
    """A fingerprint `bits` bits from `value`."""
    unsigned = value & ((1 << 64) - 1)
    for bit in range(bits):
        unsigned ^= 1 << (bit * 7 % 64)
    return unsigned - (1 << 64) if unsigned >= 1 << 63 else unsigned


def fine_flipped(bits: int) -> bytes:
    data = bytearray(FINE_PRINT)
    for bit in range(bits):
        data[bit // 8] ^= 1 << (bit % 8)
    return bytes(data)


def known(picture_id: int, name: str, **changes: object) -> Known:
    """A made-up photo, 4032 × 3024, as finding duplicates sees it."""
    base = Known(
        id=picture_id,
        name=name,
        folder=r"D:\Pictures\Phone\2026",
        width=4032,
        height=3024,
        size=3_800_000,
        format="JPEG",
        modified=1_000 + picture_id,
        taken=None,
        camera=None,
        hash=0x1234_5678_9ABC_DEF0,
        fine=FINE_PRINT,
        digest=None,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def shot(picture_id: int, seconds: float, **changes: object) -> Known:
    """A shot of a burst on a made-up camera, `seconds` after the first: alike, but not so alike
    as a picture saved again (its finer fingerprint differs)."""
    made: dict[str, object] = {
        "camera": "Pixelworks PW-7",
        "taken": MOMENT + timedelta(seconds=seconds),
        "fine": fine_flipped(13 * picture_id),
        **changes,
    }
    return known(picture_id, f"IMG_{2040 + picture_id}.jpg", **made)


def test_exact_copies_are_one_group_keeping_the_name_that_isnt_a_copys():
    found = groups(
        [
            known(1, "IMG_2041 (2).jpg", digest="abc", modified=900),
            known(2, "IMG_2041.jpg", digest="abc"),
            known(3, "Red canyon.jpg", hash=flipped(0x1234_5678_9ABC_DEF0, 30), digest="def"),
        ]
    )

    assert len(found) == 1
    assert (found[0].kind, found[0].exact, found[0].keep) == ("duplicates", True, 2)
    assert set(found[0].members) == {1, 2}


def test_a_picture_saved_again_smaller_keeps_the_one_with_the_most_pixels():
    found = groups(
        [
            known(1, "Harbour.jpg", width=1008, height=756, size=400_000),
            known(2, "Harbour.png", hash=flipped(0x1234_5678_9ABC_DEF0, NEAR), size=9_000_000),
            known(3, "Harbour.webp", fine=fine_flipped(FINE), size=1_000_000, width=2016,
                  height=1512),
        ]
    )  # fmt: skip

    assert len(found) == 1
    assert found[0].kind == "duplicates"
    assert not found[0].exact
    assert found[0].keep == 2
    assert found[0].members == (2, 3, 1)  # biggest first


def test_a_different_shape_or_a_finer_fingerprint_too_far_isnt_the_same_picture():
    found = groups(
        [
            known(1, "Pier.jpg"),
            known(2, "Pier wide.jpg", width=4032, height=2268),  # cropped to 16:9
            known(3, "Pier cropped.jpg", fine=fine_flipped(FINE + 4)),  # a gentle crop
            known(4, "Pier far.jpg", hash=flipped(0x1234_5678_9ABC_DEF0, NEAR + 1)),
        ]
    )

    assert found == []


def test_a_shape_within_one_per_cent_is_the_same():
    found = groups([known(1, "Pier.jpg"), known(2, "Pier small.jpg", width=1000, height=753)])

    assert len(found) == 1


def test_shots_of_one_moment_are_a_burst_and_the_sharpest_is_kept():
    found = groups(
        [
            shot(1, 0, sharpness=40.0),
            shot(2, 1, hash=flipped(0x1234_5678_9ABC_DEF0, BURST), fine=None, sharpness=95.0),
            shot(3, 2, hash=flipped(0x1234_5678_9ABC_DEF0, 9), fine=None, sharpness=60.0),
        ]
    )

    assert len(found) == 1
    assert (found[0].kind, found[0].keep) == ("burst", 2)
    assert found[0].members == (1, 2, 3)  # in time


def test_a_burst_goes_shot_by_shot_each_within_a_couple_of_seconds_of_the_one_before():
    gap = BURST_GAP.total_seconds()
    found = groups([shot(1, 0), shot(2, gap), shot(3, 2 * gap), shot(4, 3 * gap + 0.5)])

    assert [set(group.members) for group in found] == [{1, 2, 3}]


def test_bursts_need_the_same_camera_folder_and_size():
    found = groups(
        [
            shot(1, 0, hash=flipped(0x1234_5678_9ABC_DEF0, 10), fine=None),
            shot(2, 1, camera="Lumen X100"),
            shot(3, 1, folder=r"D:\Pictures\Camera"),
            shot(4, 1, width=3024, height=4032),
        ]
    )

    assert found == []


def test_pictures_the_owner_said_arent_the_same_stay_apart_even_when_a_third_joins():
    found = groups(
        [known(1, "Pier.jpg"), known(2, "Pier again.jpg"), known(3, "Pier third.jpg")],
        not_same=[(1, 2)],
    )

    assert len(found) == 1
    assert set(found[0].members) in ({1, 3}, {2, 3})


def test_what_mado_made_is_never_a_duplicate_of_its_original_or_of_a_copy_of_it():
    found = groups(
        [
            known(1, "Beach.jpg", family=7, width=2016, height=1512, digest="abc"),
            known(2, "Beach (TV 8K).jpg", family=7, width=7680, height=5760),
            known(3, "Beach copy.jpg", width=2016, height=1512, digest="abc"),
            known(4, "Beach (TV 8K) (2).jpg", family=7, width=7680, height=5760),
        ]
    )

    assert len(found) == 1
    assert set(found[0].members) == {1, 3}
    assert found[0].keep == 1


def test_a_cameras_raw_and_its_jpeg_of_the_same_moment_are_never_grouped():
    # Both kept as the camera wrote them: the RAW to develop, the JPEG ready to share.
    found = groups(
        [
            shot(1, 0, format="CR3", size=25_000_000, raw=True, sharpness=50.0),
            shot(2, 0, format="JPEG", hash=0x1234_5678_9ABC_DEF0, sharpness=50.0),
            known(3, "Beach.dng", raw=True, digest="abc"),
            known(4, "Beach.jpg", digest="abc"),  # the same bytes: still never set aside for it
        ]
    )

    assert found == []


def test_raws_group_among_themselves_copies_and_bursts_alike():
    found = groups(
        [
            known(1, "_MG_0042.CR3", format="CR3", raw=True, digest="abc"),
            known(2, "_MG_0042 (2).CR3", format="CR3", raw=True, digest="abc"),
            shot(3, 0, format="NEF", raw=True, sharpness=30.0),
            shot(
                4, 1, format="NEF", raw=True, hash=flipped(0x1234_5678_9ABC_DEF0, 9), sharpness=80.0
            ),
        ]
    )

    assert [(group.kind, set(group.members), group.keep) for group in found] == [
        ("duplicates", {1, 2}, 1),
        ("burst", {3, 4}, 4),
    ]


def test_the_larger_file_of_one_format_wins_then_a_plain_name_then_the_older_file():
    def keep(*members: Known) -> int:
        return suggested(members, "duplicates").id

    assert keep(known(1, "A.jpg", size=1_000), known(2, "A - Copy.jpg", size=2_000)) == 2
    assert keep(known(1, "A (2).jpg"), known(2, "A.jpg")) == 2
    assert keep(known(1, "A.png", format="PNG", size=9_000), known(2, "A.jpg", modified=1)) == 2
    assert keep(known(1, "A.jpg", modified=5), known(2, "B.jpg", modified=3)) == 2


def test_equally_sharp_shots_are_kept_as_duplicates_are():
    keep = suggested([shot(1, 0, sharpness=50.0, size=1), shot(2, 1, sharpness=50.0)], "burst")

    assert keep.id == 2


def test_a_burst_keeps_its_sharpest_shot_never_a_sharpened_copy_of_one():
    def burst(a: float, b: float) -> int:
        shots = [shot(1, 0, sharpness=a), shot(2, 1, sharpness=b), shot(3, 2, sharpness=30.0)]
        export = replace(  # a smaller copy of shot 2, sharpened as it was exported
            shots[1],
            id=4,
            name="IMG_2042 export.jpg",
            width=2016,
            height=1512,
            size=900_000,
            sharpness=90.0,
        )
        [group] = groups([*shots, export])
        assert group.kind == "burst"
        assert set(group.members) == {1, 2, 3, 4}
        assert group.reason == "sharpest"
        return group.keep

    assert burst(50.0, 40.0) == 1  # the sharpest shot, not the copy of a softer one
    assert burst(50.0, 60.0) == 2  # that shot's own picture, not its smaller copy


def test_a_group_says_what_decided_which_to_keep():
    def reason(*members: Known) -> str:
        [group] = groups(list(members))
        return group.reason

    assert reason(known(1, "A.jpg", width=1008, height=756), known(2, "B.jpg")) == "pixels"
    assert reason(known(1, "A.jpg", size=1), known(2, "B.jpg", size=2)) == "larger"
    assert reason(known(1, "A (2).jpg"), known(2, "A.jpg")) == "name"
    assert reason(known(1, "A.png", format="PNG"), known(2, "A.jpg")) == "older"
    assert reason(shot(1, 0, sharpness=1.0), shot(2, 1, sharpness=2.0)) == "sharpest"


def test_a_big_folder_of_shots_is_grouped_without_comparing_every_pair():
    import time

    pictures = [
        known(
            at,
            f"IMG_{at}.jpg",
            camera="Pixelworks PW-7",
            taken=MOMENT + timedelta(seconds=at * 0.5),
            hash=at * 1_000_003,
            fine=None,
        )
        for at in range(1, 20_001)
    ]

    started = time.perf_counter()
    groups(pictures)

    assert time.perf_counter() - started < 5  # neighbours in time only


def test_a_copys_name_is_its_original_name_with_a_mark():
    assert copy_base("IMG_2041 (2).jpg") == "img_2041"
    assert copy_base("IMG_2041 - Copy.jpg") == "img_2041"
    assert copy_base("IMG_2041 - Copy (3).JPG") == "img_2041"
    assert copy_base("Copy of Beach.png") == "beach"
    assert copy_base("beach_copy.png") == "beach"
    assert copy_base("Holiday (2026).jpg") == "holiday (2026)"
    assert copy_base("Copy.jpg") == "copy"
    assert is_copy_name("Beach (2).jpg")
    assert is_copy_name("Beach copy.jpg")
    assert not is_copy_name("Beach.jpg")
    assert not is_copy_name("IMG_2041.jpg")
