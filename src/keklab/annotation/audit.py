# Role: descriptive audit of annotation candidate samples.
# Connects to: annotation/schema, annotation/cli.

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from keklab.annotation.schema import SamplePost


def audit_samples(
    samples: Iterable[SamplePost],
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> dict[str, Any]:
    """Summarize a candidate sample without requiring annotations."""
    samples = list(samples)
    post_ids = [sample.post_id for sample in samples]
    thread_ids = [sample.thread_id for sample in samples]
    content_hashes = [sample.content_hash for sample in samples]
    timestamps = [
        sample.timestamp_utc for sample in samples if sample.timestamp_utc
    ]
    lengths = [
        len((sample.text_clean or sample.text_raw or "").strip())
        for sample in samples
    ]
    months = sorted(
        {
            str(sample.stratum.get("month", ""))
            for sample in samples
            if sample.stratum.get("month")
        }
    )
    reasons = Counter(
        str(sample.stratum.get("reason", "unknown")) for sample in samples
    )
    sources = Counter(sample.source for sample in samples)
    countries = Counter(
        sample.country for sample in samples if sample.country
    )

    outside = 0
    if window_start is not None or window_end is not None:
        for sample in samples:
            timestamp = sample.timestamp_utc
            if timestamp is None:
                outside += 1
            elif window_start is not None and timestamp < window_start:
                outside += 1
            elif window_end is not None and timestamp > window_end:
                outside += 1

    return {
        "posts": len(samples),
        "unique_posts": len(set(post_ids)),
        "unique_threads": len(set(thread_ids)),
        "duplicate_posts": len(post_ids) - len(set(post_ids)),
        "duplicate_threads": len(thread_ids) - len(set(thread_ids)),
        "duplicate_content_hashes": len(content_hashes)
        - len(set(content_hashes)),
        "empty_raw": sum(1 for sample in samples if not sample.text_raw.strip()),
        "empty_clean": sum(
            1 for sample in samples if not sample.text_clean.strip()
        ),
        "op_posts": sum(1 for sample in samples if sample.is_op),
        "by_reason": dict(sorted(reasons.items())),
        "by_source": dict(sorted(sources.items())),
        "by_month": dict(
            sorted(Counter(
                str(sample.stratum.get("month", "unknown"))
                for sample in samples
            ).items())
        ),
        "month_count": len(months),
        "first_month": months[0] if months else None,
        "last_month": months[-1] if months else None,
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "missing_timestamps": len(samples) - len(timestamps),
        "outside_window": outside,
        "top_countries": dict(countries.most_common(5)),
        "text_length": {
            "min": min(lengths) if lengths else 0,
            "median": statistics.median(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
        },
    }
