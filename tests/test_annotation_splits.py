from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from keklab.annotation.schema import SamplePost
from keklab.annotation.splits import (
    assign_thread_splits,
    split_counts,
    write_split_manifest,
)


def make_sample(post_id: str, thread_id: str | None = None) -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=thread_id or f"t-{post_id}",
        source="kek",
        content_hash=f"hash-{post_id}",
        stratum={"reason": "random"},
        timestamp_utc=datetime(2018, 1, 1, tzinfo=timezone.utc),
    )


def test_assign_thread_splits_counts_and_covers_every_thread():
    samples = [make_sample(str(index)) for index in range(10)]

    assignment = assign_thread_splits(samples, seed=3)

    assert len(assignment) == 10
    assert split_counts(assignment) == {"train": 6, "dev": 2, "test": 2}
    assert set(assignment) == {sample.thread_id for sample in samples}


def test_assign_thread_splits_is_deterministic_and_keeps_threads_together():
    samples = [
        make_sample("1", "t-a"),
        make_sample("2", "t-a"),
        make_sample("3", "t-b"),
        make_sample("4", "t-c"),
        make_sample("5", "t-d"),
    ]

    first = assign_thread_splits(samples, seed=5)
    second = assign_thread_splits(samples, seed=5)

    assert first == second
    assert set(first) == {"t-a", "t-b", "t-c", "t-d"}
    assert split_counts(first) == {"train": 2, "dev": 1, "test": 1}


def test_assign_thread_splits_validates_ratios():
    samples = [make_sample("1")]
    with pytest.raises(ValueError, match="must sum"):
        assign_thread_splits(samples, ratios=(0.5, 0.2, 0.2))
    with pytest.raises(ValueError, match="3 values"):
        assign_thread_splits(samples, ratios=(1.0,))
    with pytest.raises(ValueError, match="non-negative"):
        assign_thread_splits(samples, ratios=(1.2, -0.1, -0.1))


def test_write_split_manifest_is_sorted_jsonl(tmp_path):
    out = tmp_path / "splits.jsonl"
    write_split_manifest({"t-b": "dev", "t-a": "train"}, out)

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows == [
        {"thread_id": "t-a", "split": "train"},
        {"thread_id": "t-b", "split": "dev"},
    ]
