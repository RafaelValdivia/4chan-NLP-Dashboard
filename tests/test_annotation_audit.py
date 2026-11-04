from __future__ import annotations

from datetime import datetime, timezone

from keklab.annotation.audit import audit_samples
from keklab.annotation.schema import SamplePost


def make_sample(
    post_id: str,
    *,
    thread_id: str | None = None,
    text: str = "hello",
    reason: str = "random",
    month: str = "2018-01",
    timestamp: datetime | None = None,
) -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=thread_id or f"t-{post_id}",
        source="kek",
        content_hash=f"hash-{post_id}",
        text_raw=text,
        text_clean=text,
        stratum={"reason": reason, "month": month},
        timestamp_utc=timestamp or datetime(2018, 1, 1, tzinfo=timezone.utc),
    )


def test_audit_samples_reports_counts_and_months():
    samples = [
        make_sample("1", text="aaaa"),
        make_sample("2", text="bb", month="2018-02", reason="targeted"),
        make_sample("1", thread_id="t-1b", text="cc"),
    ]

    report = audit_samples(samples)

    assert report["posts"] == 3
    assert report["unique_posts"] == 2
    assert report["unique_threads"] == 3
    assert report["duplicate_posts"] == 1
    assert report["by_reason"] == {"random": 2, "targeted": 1}
    assert report["month_count"] == 2
    assert report["first_month"] == "2018-01"
    assert report["last_month"] == "2018-02"
    assert report["text_length"] == {"min": 2, "median": 2, "max": 4}


def test_audit_samples_detects_empty_text_and_window_violations():
    samples = [
        make_sample("1", text="ok"),
        make_sample(
            "2",
            text="   ",
            timestamp=datetime(2019, 6, 1, tzinfo=timezone.utc),
        ),
    ]

    report = audit_samples(
        samples,
        window_start=datetime(2018, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2019, 1, 1, tzinfo=timezone.utc),
    )

    assert report["empty_raw"] == 1
    assert report["empty_clean"] == 1
    assert report["outside_window"] == 1
    assert report["first_timestamp"] == datetime(2018, 1, 1, tzinfo=timezone.utc)
    assert report["last_timestamp"] == datetime(2019, 6, 1, tzinfo=timezone.utc)
