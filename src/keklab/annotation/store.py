# Role: JSONL persistence for samples/annotations, resume keys and CSV export.
# Connects to: annotation/schema, annotation/cli, annotation/agreement.

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.labels import FRAME_LABELS
from keklab.annotation.proposal import (
    ProposalRecord,
    ReviewRecord,
    TaskRecord,
)
from keklab.annotation.schema import (
    AnnotationRecord,
    SamplePost,
    annotation_key,
    annotation_sample_key,
    sample_key,
)
from keklab.annotation.taxonomy import (
    COARSE_HEADS,
    coarse_counts,
    collapse_frames,
)
from keklab.common.io import iter_ndjson
from keklab.common.logging import get_logger
from keklab.formal.schema import Annotation

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# JSONL reading/writing
# ---------------------------------------------------------------------------
def _atomic_write_rows(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    """Write JSON objects to `path` atomically (temp file + os.replace)."""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=out.parent, prefix=f".{out.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, out)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return out


def load_annotations(
    path: str | Path,
    *,
    strict: bool = True,
) -> list[AnnotationRecord]:
    """Load and validate annotations from JSONL."""
    p = Path(path).expanduser()
    if not p.exists():
        return []

    records: list[AnnotationRecord] = []
    for obj in iter_ndjson(p, skip_errors=not strict):
        try:
            records.append(AnnotationRecord.model_validate(obj))
        except Exception as exc:  # pydantic ValidationError
            if strict:
                raise ValueError(f"{p}: invalid annotation record: {exc}") from exc
            log.warning("Skipping invalid annotation in %s: %s", p, exc)
    return records


def write_annotations(records: Iterable[AnnotationRecord], path: str | Path) -> Path:
    """Write annotations as JSONL, sorted by their stable key."""
    rows = [
        record.model_dump(mode="json")
        for record in sorted(
            records,
            key=lambda item: tuple("" if value is None else value for value in annotation_key(item)),
        )
    ]
    return _atomic_write_rows(path, rows)


def load_samples(path: str | Path, *, strict: bool = True) -> list[SamplePost]:
    """Load and validate annotation candidates from JSONL."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(p)

    samples: list[SamplePost] = []
    for obj in iter_ndjson(p, skip_errors=not strict):
        try:
            samples.append(SamplePost.model_validate(obj))
        except Exception as exc:
            if strict:
                raise ValueError(f"{p}: invalid sample record: {exc}") from exc
            log.warning("Skipping invalid sample in %s: %s", p, exc)
    return samples


def write_samples(samples: Iterable[SamplePost], path: str | Path) -> Path:
    """Write annotation candidates as JSONL."""
    rows = [sample.model_dump(mode="json") for sample in samples]
    return _atomic_write_rows(path, rows)


# ---------------------------------------------------------------------------
# AI-assistance files: tasks, proposals, reviews
# ---------------------------------------------------------------------------
def _load_records(
    path: str | Path,
    model: type[Any],
    *,
    strict: bool,
    label: str,
) -> list[Any]:
    p = Path(path).expanduser()
    if not p.exists():
        return []
    records: list[Any] = []
    for obj in iter_ndjson(p, skip_errors=not strict):
        try:
            records.append(model.model_validate(obj))
        except Exception as exc:  # pydantic ValidationError
            if strict:
                raise ValueError(f"{p}: invalid {label} record: {exc}") from exc
            log.warning("Skipping invalid %s in %s: %s", label, p, exc)
    return records


def load_tasks(
    path: str | Path, *, strict: bool = True
) -> list[TaskRecord]:
    return _load_records(path, TaskRecord, strict=strict, label="task")


def write_tasks(tasks: Iterable[TaskRecord], path: str | Path) -> Path:
    rows = [
        task.model_dump(mode="json")
        for task in sorted(tasks, key=lambda item: item.task_id)
    ]
    return _atomic_write_rows(path, rows)


def load_proposals(
    path: str | Path, *, strict: bool = True
) -> list[ProposalRecord]:
    return _load_records(path, ProposalRecord, strict=strict, label="proposal")


def write_proposals(
    proposals: Iterable[ProposalRecord], path: str | Path
) -> Path:
    rows = [
        proposal.model_dump(mode="json")
        for proposal in sorted(
            proposals, key=lambda item: item.proposal_id
        )
    ]
    return _atomic_write_rows(path, rows)


def load_reviews(
    path: str | Path, *, strict: bool = True
) -> list[ReviewRecord]:
    return _load_records(path, ReviewRecord, strict=strict, label="review")


def write_reviews(reviews: Iterable[ReviewRecord], path: str | Path) -> Path:
    rows = [
        review.model_dump(mode="json")
        for review in sorted(
            reviews, key=lambda item: (item.reviewed_utc, item.review_id)
        )
    ]
    return _atomic_write_rows(path, rows)


def upsert_review(
    reviews: Iterable[ReviewRecord], record: ReviewRecord
) -> list[ReviewRecord]:
    """Replace an existing review by id or append the new one."""
    items = list(reviews)
    for index, existing in enumerate(items):
        if existing.review_id == record.review_id:
            items[index] = record
            return items
    items.append(record)
    return items


# ---------------------------------------------------------------------------
# Resume helpers
# ---------------------------------------------------------------------------
def completed_sample_keys(
    records: Iterable[Annotation],
    *,
    round: int,
    annotator: str,
) -> set[tuple[str, str | None, str | None]]:
    """Sample keys already annotated in a given round/annotator."""
    return {
        annotation_sample_key(record)
        for record in records
        if record.round == round and record.annotator == annotator
    }


def pending_samples(
    samples: Iterable[SamplePost],
    records: Iterable[Annotation],
    *,
    round: int,
    annotator: str,
) -> list[SamplePost]:
    """Samples that still need an annotation for this round/annotator."""
    done = completed_sample_keys(records, round=round, annotator=annotator)
    pending: list[SamplePost] = []
    seen: set[tuple[str, str, str]] = set()
    for sample in samples:
        key = sample_key(sample)
        if key in seen or key in done:
            continue
        seen.add(key)
        pending.append(sample)
    return pending


class AnnotationStore:
    """Small JSONL store with atomic upsert-by-key semantics."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def load(self) -> list[AnnotationRecord]:
        return load_annotations(self.path)

    def save(self, records: Iterable[AnnotationRecord]) -> Path:
        return write_annotations(records, self.path)

    def get(self, record: Annotation) -> AnnotationRecord | None:
        key = annotation_key(record)
        for existing in self.load():
            if annotation_key(existing) == key:
                return existing
        return None

    def upsert(self, record: AnnotationRecord) -> AnnotationRecord:
        records = self.load()
        key = annotation_key(record)
        for index, existing in enumerate(records):
            if annotation_key(existing) == key:
                records[index] = record
                break
        else:
            records.append(record)
        self.save(records)
        return record


# ---------------------------------------------------------------------------
# CSV / JSONL export
# ---------------------------------------------------------------------------
CSV_BASE_FIELDS: tuple[str, ...] = (
    "post_id",
    "thread_id",
    "source",
    "period",
    "content_hash",
    "frame_labels",
    "coarse_labels",
    "toxicity",
    "annotator",
    "round",
    "tier",
    "guideline_version",
    "annotated_utc",
    "notes",
)


def _csv_rows(records: Iterable[Annotation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        data = record.model_dump(mode="json")
        row: dict[str, Any] = {
            field: data.get(field) for field in CSV_BASE_FIELDS
        }
        row["frame_labels"] = "|".join(record.frame_labels)
        coarse = collapse_frames(record.frame_labels)
        row["coarse_labels"] = "|".join(coarse)
        for label in FRAME_LABELS:
            row[label] = 1 if label in record.frame_labels else 0
        for head in COARSE_HEADS:
            row[f"coarse_{head}"] = 1 if head in coarse else 0
        rows.append(row)
    return rows


def export_csv(
    records: Iterable[Annotation],
    path: str | Path | None = None,
) -> str:
    """Export annotations to CSV (frame one-hot columns included).

    Returns the CSV text. When `path` is given, also writes it there.
    """
    rows = _csv_rows(records)
    fieldnames = (
        list(CSV_BASE_FIELDS)
        + list(FRAME_LABELS)
        + [f"coarse_{head}" for head in COARSE_HEADS]
    )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    text = buffer.getvalue()

    if path is not None:
        out = Path(path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="")
    return text


def export_jsonl(
    records: Iterable[Annotation],
    path: str | Path | None = None,
) -> str:
    """Export annotations as JSONL text, optionally writing to a file."""
    text = "".join(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, default=str)
        + "\n"
        for record in records
    )
    if path is not None:
        out = Path(path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------
def annotation_stats(records: Iterable[Annotation]) -> dict[str, Any]:
    records = list(records)
    frame_counts = Counter(
        label for record in records for label in record.frame_labels
    )
    toxicity_counts = Counter(
        record.toxicity for record in records if record.toxicity is not None
    )
    by_annotator = Counter(
        f"{record.annotator}#r{record.round}" for record in records
    )

    return {
        "annotations": len(records),
        "unique_posts": len({record.post_id for record in records}),
        "annotators": sorted({record.annotator for record in records}),
        "rounds": sorted({record.round for record in records}),
        "guideline_versions": sorted(
            {record.guideline_version for record in records}
        ),
        "tiers": dict(Counter(record.tier for record in records)),
        "by_annotator_round": dict(sorted(by_annotator.items())),
        "frame_counts": {
            label: frame_counts.get(label, 0) for label in FRAME_LABELS
        },
        "coarse_counts": coarse_counts(
            record.frame_labels for record in records
        ),
        "toxicity_counts": {
            str(level): toxicity_counts.get(level, 0) for level in range(4)
        },
        "mean_frames_per_annotation": (
            sum(len(record.frame_labels) for record in records) / len(records)
            if records
            else 0.0
        ),
    }
