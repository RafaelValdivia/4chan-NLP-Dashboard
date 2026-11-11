# Role: modeling dataset export from silver annotations and thread splits.
# Connects to: annotation/labels, annotation/taxonomy, annotation/store,
#             classification/cli.

from __future__ import annotations

from collections import Counter
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


def build_modeling_rows(
    annotations: Iterable[AnnotationRecord],
    samples: Iterable[SamplePost],
    *,
    split_assignment: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join silver annotations with their post text and optional split."""
    sample_by_post = {sample.post_id: sample for sample in samples}
    rows: list[dict[str, Any]] = []
    missing_samples: list[str] = []
    missing_toxicity = 0

    for annotation in annotations:
        sample = sample_by_post.get(annotation.post_id)
        if sample is None:
            missing_samples.append(annotation.post_id)
            continue
        if annotation.toxicity is None:
            missing_toxicity += 1

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

    splits = Counter(row.get("split") for row in rows)
    report = {
        "annotations": len(rows) + len(missing_samples),
        "rows": len(rows),
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
