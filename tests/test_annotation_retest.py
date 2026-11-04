from __future__ import annotations

from datetime import datetime, timezone

import pytest

from keklab.annotation.retest import retest_size, select_retest
from keklab.annotation.schema import SamplePost


def make_sample(post_id: str) -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="kek",
        content_hash=f"hash-{post_id}",
        stratum={"reason": "random", "month": "2018-01"},
        timestamp_utc=datetime(2018, 1, 1, tzinfo=timezone.utc),
    )


def test_retest_size_rounds_and_requires_a_fraction():
    assert retest_size(200, 0.2) == 40
    assert retest_size(30, 0.2) == 6
    assert retest_size(3, 0.2) == 1
    assert retest_size(0, 0.2) == 0
    with pytest.raises(ValueError):
        retest_size(10, 0.0)


def test_select_retest_is_deterministic_and_order_preserving():
    samples = [make_sample(str(index)) for index in range(20)]

    first = select_retest(samples, fraction=0.2, seed=7)
    second = select_retest(samples, fraction=0.2, seed=7)
    other = select_retest(samples, fraction=0.2, seed=8)

    assert [sample.post_id for sample in first] == [
        sample.post_id for sample in second
    ]
    assert [sample.post_id for sample in first] != [
        sample.post_id for sample in other
    ]
    assert len(first) == 4
    assert {sample.post_id for sample in first} <= {
        sample.post_id for sample in samples
    }
    assert [sample.post_id for sample in first] == sorted(
        (sample.post_id for sample in first), key=int
    )


def test_select_retest_deduplicates_and_can_take_everything():
    samples = [make_sample("1"), make_sample("1"), make_sample("2")]

    selected = select_retest(samples, fraction=1.0, seed=1)

    assert [sample.post_id for sample in selected] == ["1", "2"]
