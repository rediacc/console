"""`literal_sources.near_miss` over hyphenated labels: two real region ids are not typos of each other, a typo or a swap inside a part is."""

from __future__ import annotations

import pytest

from rediacc_ci.quality import literal_sources as ls

SUFFIX = ".fixtureco.com"


def near(a: str, b: str) -> bool:
    return ls.near_miss(a + SUFFIX, b + SUFFIX, 2)


@pytest.mark.parametrize(
    ("typo", "real"),
    [
        ("bench-ue", "bench-eu"),
        ("bench-su", "bench-us"),
        ("bench-asix", "bench-asia"),
        ("bench-aisa", "bench-asia"),
        ("relases", "releases"),
    ],
)
def test_a_typo_or_a_swap_inside_a_label_part_is_a_near_miss(typo: str, real: str) -> None:
    assert near(typo, real)
    assert near(real, typo)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("bench-us", "bench-eu"),
        ("bench-eu", "bench-asia"),
        ("bench-us", "bench-asia"),
        ("us", "eu"),
        ("bench-eu", "bench-eu"),
    ],
)
def test_two_real_region_ids_and_an_identical_label_are_not_typos(a: str, b: str) -> None:
    assert not near(a, b)


def test_a_swap_in_a_part_of_another_label_count_is_not_judged_part_by_part() -> None:
    assert not near("bench-ue", "bench-eu-x")
