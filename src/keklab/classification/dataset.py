# Role: modeling dataset export from silver annotations and thread splits.
# Connects to: annotation/labels, annotation/taxonomy, annotation/store,
#             classification/cli.

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.labels import FRAME_LABELS
from keklab.annotation.schema import AnnotationRecord, SamplePost
from keklab.annotation.store import _atomic_write_rows
from keklab.annotation.taxonomy import COARSE_HEADS, collapse_frames


def frame_one_hot(labels: Iterable[str]) -> dict[str, int]:
    selected = set(labels)
    return {f"frame__{label}": int(label in selected) for label in FRAME_LABELS}


def coarse_one_hot(labels: Iterable[str]) -> dict[str, int]:
    selected = set(collapse_frames(labels))
    return {f"head__{head}": int(head in selected) for head in COARSE_HEADS}


def toxicity_binary(toxicity: int | None) -> int | None:
    if toxicity is None:
        return None
    return int(int(toxicity) >= 2)


def _post_sort_key(post_id: str) -> tuple[int, str]:
    """Sort numeric 4chan ids numerically, other ids lexicographically last."""
    try:
        return (int(post_id), post_id)
    except (TypeError, ValueError):
        return (sys.maxsize, str(post_id))


def build_modeling_rows(
    annotations: Iterable[AnnotationRecord],
    samples: Iterable[SamplePost],
    *,
    split_assignment: dict[str, str] | None = None,
    dedupe_content: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join silver annotations with their post text and optional split.

    When `dedupe_content` is true, posts sharing a `content_hash` collapse to
    one deterministic representative (the lowest numeric `post_id`). The
    silver sample may contain copypasta across threads, and splitting by
    thread would otherwise leak identical text into train and test.
    """
    annotations = list(annotations)
    sample_by_post = {sample.post_id: sample for sample in samples}
    rows: list[dict[str, Any]] = []
    hash_by_post: dict[str, str] = {}
    missing_samples: list[str] = []
    missing_toxicity = 0

    for annotation in annotations:
        sample = sample_by_post.get(annotation.post_id)
        if sample is None:
            missing_samples.append(annotation.post_id)
            continue
        if annotation.toxicity is None:
            missing_toxicity += 1
        hash_by_post[annotation.post_id] = sample.content_hash

        row: dict[str, Any] = {
            "post_id": annotation.post_id,
            "thread_id": annotation.thread_id,
            "source": annotation.source,
            "period": annotation.period,
            "text_raw": sample.text_raw,
            "text_clean": sample.text_clean,
            "frame_labels": list(annotation.frame_labels),
            "coarse_heads": collapse_frames(annotation.frame_labels),
            "toxicity": annotation.toxicity,
            "toxicity_binary": toxicity_binary(annotation.toxicity),
        }
        row.update(frame_one_hot(annotation.frame_labels))
        row.update(coarse_one_hot(annotation.frame_labels))
        if split_assignment is not None:
            row["split"] = split_assignment.get(str(annotation.thread_id))
        rows.append(row)

    rows_before_dedupe = len(rows)
    duplicate_groups = 0
    duplicate_post_ids: list[str] = []
    if dedupe_content:
        groups: dict[str, list[str]] = defaultdict(list)
        for post_id, content_hash in hash_by_post.items():
            if content_hash:
                groups[content_hash].append(post_id)
        drop: set[str] = set()
        for post_ids in groups.values():
            if len(post_ids) < 2:
                continue
            duplicate_groups += 1
            keep = min(post_ids, key=_post_sort_key)
            dropped = sorted(
                (post_id for post_id in post_ids if post_id != keep),
                key=_post_sort_key,
            )
            drop.update(dropped)
            duplicate_post_ids.extend(dropped)
        if drop:
            rows = [row for row in rows if str(row["post_id"]) not in drop]

    splits = Counter(row.get("split") for row in rows)
    report = {
        "annotations": rows_before_dedupe + len(missing_samples),
        "rows": len(rows),
        "rows_before_dedupe": rows_before_dedupe,
        "duplicate_groups": duplicate_groups,
        "duplicate_rows_removed": rows_before_dedupe - len(rows),
        "duplicate_post_ids": duplicate_post_ids[:20],
        "missing_samples": len(missing_samples),
        "missing_sample_ids": missing_samples[:20],
        "missing_toxicity": missing_toxicity,
        "splits": {name: splits.get(name, 0) for name in ("train", "dev", "test")},
        "frames": len(FRAME_LABELS),
        "coarse_heads": len(COARSE_HEADS),
    }
    return rows, report


def export_dataset(
    annotations: Iterable[AnnotationRecord],
    samples: Iterable[SamplePost],
    out_path: str | Path,
    *,
    split_assignment: dict[str, str] | None = None,
) -> dict[str, Any]:
    rows, report = build_modeling_rows(
        annotations, samples, split_assignment=split_assignment
    )
    _atomic_write_rows(out_path, rows)
    report["output"] = str(out_path)
    return report
