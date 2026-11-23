"""What a picture looks like in numbers: fingerprints that stay close for a picture saved again and
far for another, a finer one that tells a crop, sharpness, and finding close fingerprints in
buckets without comparing every pair."""

import itertools

import numpy as np
import pytest

from mado.core.likeness import (
    FINE_SIDE,
    SIDE,
    _bands,  # pyright: ignore[reportPrivateUsage]
    apart,
    fine,
    fine_apart,
    fingerprint,
    near_pairs,
    sharpness,
)


def scene(seed: int, side: int = 256) -> np.ndarray:
    """A made-up grey scene: soft shapes and a gradient, different for every seed."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:side, 0:side].astype(np.float32) / side
    image = 255 * (rng.uniform(0.2, 0.8) * y + rng.uniform(-0.3, 0.3) * x)
    for _ in range(6):
        cx, cy, r = rng.uniform(0, 1), rng.uniform(0, 1), rng.uniform(0.05, 0.3)
        image += rng.uniform(-90, 90) * ((x - cx) ** 2 + (y - cy) ** 2 < r * r)
    return np.clip(image + 40, 0, 255).astype(np.float32)


def shrunk(image: np.ndarray, side: int) -> np.ndarray:
    """A box-averaged copy `side` × `side`, as Mado makes from a thumbnail."""
    step = image.shape[0] // side
    return image.reshape(side, step, side, step).mean(axis=(1, 3)).astype(np.float32)


def test_a_fingerprint_is_64_bits_kept_as_sqlite_keeps_an_integer():
    found = [fingerprint(shrunk(scene(seed), SIDE)) for seed in range(20)]

    assert all(-(1 << 63) <= each < (1 << 63) for each in found)
    assert any(each < 0 for each in found)  # the top bit is used too


def test_a_picture_saved_again_stays_within_a_few_bits_and_another_is_far():
    original = scene(1)
    noisy = original + np.random.default_rng(9).normal(0, 3, original.shape).astype(np.float32)
    brighter = np.clip(original * 1.04 + 5, 0, 255)

    first = fingerprint(shrunk(original, SIDE))
    assert apart(first, fingerprint(shrunk(noisy, SIDE))) <= 4
    assert apart(first, fingerprint(shrunk(brighter, SIDE))) <= 4
    assert apart(first, fingerprint(shrunk(scene(2), SIDE))) >= 12


def test_the_finer_fingerprint_tells_a_crop_from_a_copy():
    original = scene(3, 1024)
    noisy = original + np.random.default_rng(4).normal(0, 3, original.shape).astype(np.float32)
    cropped = original[32:-32, 32:-32]  # three per cent off each side, the same shape

    whole = fine(shrunk(original, FINE_SIDE))
    assert len(whole) == 32
    assert fine_apart(whole, fine(shrunk(noisy, FINE_SIDE))) <= 6
    assert fine_apart(whole, fine(shrunk(cropped, FINE_SIDE))) > 14


def test_fingerprints_are_taken_from_copies_of_one_size():
    with pytest.raises(ValueError, match="32"):
        fingerprint(np.zeros((16, 16), np.float32))
    with pytest.raises(ValueError, match="64"):
        fine(np.zeros((32, 32), np.float32))


def test_finer_fingerprints_that_cant_be_told_are_as_far_apart_as_can_be():
    assert fine_apart(b"", bytes(32)) == 256
    assert fine_apart(bytes(32), bytes(32)) == 0


def test_a_blurred_copy_is_less_sharp_and_a_flat_one_not_sharp_at_all():
    original = scene(5)
    blurred = ((original + np.roll(original, 1, 0) + np.roll(original, 1, 1)) / 3).astype(
        np.float32
    )

    assert sharpness(original) > sharpness(blurred) > 0
    assert sharpness(np.full((64, 64), 128, np.float32)) == 0
    assert sharpness(np.zeros((2, 2), np.float32)) == 0


def test_close_fingerprints_are_found_in_buckets_every_pair_once():
    rng = np.random.default_rng(11)
    hashes = rng.integers(-(1 << 63), (1 << 63) - 1, 600, dtype=np.int64)
    for at in range(0, 60, 3):  # plant pictures a few bits from others
        flips = rng.choice(64, size=int(rng.integers(0, 7)), replace=False)
        value = int(hashes[at]) & ((1 << 64) - 1)
        for bit in flips:
            value ^= 1 << int(bit)
        hashes[at + 1] = value - (1 << 64) if value >= 1 << 63 else value

    found = list(near_pairs(hashes, 6))

    brute = {
        (a, b): apart(int(hashes[a]), int(hashes[b]))
        for a, b in itertools.combinations(range(len(hashes)), 2)
        if apart(int(hashes[a]), int(hashes[b])) <= 6
    }
    assert {(a, b): distance for a, b, distance in found} == brute
    assert len(found) == len(brute) >= 20


def test_a_bucket_bigger_than_a_block_is_still_compared_whole():
    hashes = np.zeros(1200, np.int64)  # every picture alike, as dark ones are
    hashes[600:] = 0b111

    found = list(near_pairs(hashes, 2))

    assert len(found) == 600 * 599  # each half's pairs, and no pair across (3 bits apart)


def test_the_bits_split_into_one_band_more_than_the_bits_allowed_apart():
    for within in (0, 2, 6, 12):
        bands = _bands(within)
        assert len(bands) == within + 1
        assert sum(width for _shift, width in bands) == 64
        assert [shift for shift, _ in bands] == list(
            itertools.accumulate([0] + [width for _, width in bands[:-1]])
        )
