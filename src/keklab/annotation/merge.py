# Role: merge sampled candidate files with strict deduplication.
# Connects to: annotation/schema, annotation/store, annotation/cli.

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.schema import SamplePost
from keklab.annotation.store import load_samples


def merge_samples(
    paths: Iterable[str | Path],
    *,
    strict: bool = True,
) -> tuple[list[SamplePost], dict[str, Any]]:
    """Merge sample files, keeping the first occurrence of each post/thread.

    Deduplication key is `(post_id, thread_id)`: a post is skipped when either
    identifier was already seen. This preserves the one-post-per-thread policy
    used by the ROTLK pilot and prevents thread-level leakage.
    """
    paths = [Path(path).expanduser() for path in paths]
    seen_posts: set[str] = set()
    seen_threads: set[str] = set()
    merged: list[SamplePost] = []
    duplicate_posts: list[str] = []
    duplicate_threads: list[str] = []
    rows_read = 0
    reasons: Counter[str] = Counter()
    sources: Counter[str] = Counter()

    for path in paths:
        for sample in load_samples(path, strict=strict):
            rows_read += 1
            if sample.post_id in seen_posts:
                duplicate_posts.append(sample.post_id)
                continue
            if sample.thread_id in seen_threads:
                duplicate_threads.append(sample.thread_id)
                continue
            seen_posts.add(sample.post_id)
            seen_threads.add(sample.thread_id)
            merged.append(sample)
            reasons[str(sample.stratum.get("reason", "unknown"))] += 1
            sources[sample.source] += 1

    timestamps = [
        sample.timestamp_utc for sample in merged if sample.timestamp_utc
    ]
    months = sorted(
        {
            str(sample.stratum.get("month", ""))
            for sample in merged
            if sample.stratum.get("month")
        }
    )
    report: dict[str, Any] = {
        "inputs": [str(path) for path in paths],
        "rows_read": rows_read,
        "kept": len(merged),
        "duplicates": len(duplicate_posts) + len(duplicate_threads),
        "duplicate_posts": duplicate_posts,
        "duplicate_threads": duplicate_threads,
        "by_reason": dict(sorted(reasons.items())),
        "by_source": dict(sorted(sources.items())),
        "unique_posts": len(seen_posts),
        "unique_threads": len(seen_threads),
        "months": months,
        "month_count": len(months),
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
    }
    return merged, report


def check_expected_counts(
    report: dict[str, Any],
    *,
    total: int | None = None,
    random: int | None = None,
    targeted: int | None = None,
) -> None:
    """Raise ValueError when a merged sample misses an expected count."""
    if total is not None and report["kept"] != total:
        raise ValueError(f"expected {total} posts, got {report['kept']}")
    by_reason = report.get("by_reason", {})
    if random is not None and by_reason.get("random", 0) != random:
        raise ValueError(
            f"expected {random} random posts, got {by_reason.get('random', 0)}"
        )
    if targeted is not None and by_reason.get("targeted", 0) != targeted:
        raise ValueError(
            f"expected {targeted} targeted posts, got {by_reason.get('targeted', 0)}"
        )
