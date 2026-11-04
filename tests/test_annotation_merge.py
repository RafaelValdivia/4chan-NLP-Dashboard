from __future__ import annotations

from datetime import datetime, timezone

import pytest

from keklab.annotation.merge import check_expected_counts, merge_samples
from keklab.annotation.schema import SamplePost
from keklab.annotation.store import write_samples


def make_sample(
    post_id: str,
    *,
    thread_id: str | None = None,
    reason: str = "random",
    month: str = "2018-01",
) -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=thread_id or f"t-{post_id}",
        source="kek",
        period="hist_2016_2019",
        timestamp_utc=datetime(2018, 1, 1, tzinfo=timezone.utc),
        text_raw=f"text {post_id}",
        text_clean=f"text {post_id}",
        content_hash=f"hash-{post_id}",
        stratum={"reason": reason, "month": month},
    )


def test_merge_keeps_first_occurrence_and_deduplicates(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    write_samples(
        [make_sample("1"), make_sample("2"), make_sample("3", reason="targeted")],
        first,
    )
    write_samples(
        [
            make_sample("1"),  # duplicate post
            make_sample("4"),  # duplicate thread of post 4? no, unique
            make_sample("5", thread_id="t-4"),  # duplicate thread
            make_sample("6", month="2018-02"),
        ],
        second,
    )

    merged, report = merge_samples([first, second])

    assert [sample.post_id for sample in merged] == ["1", "2", "3", "4", "6"]
    assert report["rows_read"] == 7
    assert report["kept"] == 5
    assert report["duplicates"] == 2
    assert report["duplicate_posts"] == ["1"]
    assert report["duplicate_threads"] == ["t-4"]
    assert report["by_reason"] == {"random": 4, "targeted": 1}
    assert report["unique_threads"] == 5
    assert report["month_count"] == 2
    assert report["first_timestamp"] == datetime(2018, 1, 1, tzinfo=timezone.utc)


def test_merge_reports_empty_input(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")

    merged, report = merge_samples([empty])

    assert merged == []
    assert report["kept"] == 0
    assert report["first_timestamp"] is None


def test_check_expected_counts_raises_on_mismatch():
    report = {"kept": 10, "by_reason": {"random": 8, "targeted": 2}}

    check_expected_counts(report, total=10, random=8, targeted=2)
    with pytest.raises(ValueError, match="expected 11 posts"):
        check_expected_counts(report, total=11)
    with pytest.raises(ValueError, match="expected 9 random"):
        check_expected_counts(report, random=9)
