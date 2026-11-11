# Role: convert raw local-LLM output into validated silver annotations.
# Connects to: annotation/schema, annotation/labels, annotation/proposal,
#             classification/batch, classification/cli.

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from keklab.annotation.proposal import TaskRecord, evidence_in_text
from keklab.annotation.schema import AnnotationRecord
from keklab.annotation.taxonomy import COARSE_HEADS, collapse_frames


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse one JSON object from a model response.

    Handles the common failure modes of local models: Markdown fences and a
    short preamble before the object. It never repairs malformed JSON.
    """
    candidate = str(text or "").strip()
    if not candidate:
        raise ValueError("empty model response")
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(candidate[start : end + 1])

    if not isinstance(value, dict):
        raise ValueError("model response is not a JSON object")
    return value


def _confidence(payload: dict[str, Any]) -> tuple[float | None, list[str]]:
    value = payload.get("confidence")
    if value is None:
        return None, []
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, ["confidence is not a number"]
    number = float(value)
    if not 0.0 <= number <= 1.0:
        return None, [f"confidence out of range: {number}"]
    return number, []


def annotation_from_payload(
    task: TaskRecord,
    payload: dict[str, Any],
    *,
    model: str,
    provider: str,
    annotated_utc: datetime | None = None,
) -> tuple[AnnotationRecord, list[str]]:
    """Validate one model payload and build a silver annotation.

    Raises `ValueError` when the payload cannot produce a valid annotation.
    Non-fatal issues (bad confidence, non-verbatim evidence, post_id mismatch)
    are returned as strings and preserved in `notes`.
    """
    issues: list[str] = []

    response_post_id = payload.get("post_id")
    if response_post_id is not None and str(response_post_id) != task.post_id:
        issues.append(
            f"post_id mismatch: response {response_post_id!r}, task {task.post_id!r}"
        )

    frame_labels = payload.get("frame_labels")
    if isinstance(frame_labels, str):
        frame_labels = [frame_labels]
    if not isinstance(frame_labels, list) or not frame_labels:
        raise ValueError("frame_labels must be a non-empty list")

    toxicity = payload.get("toxicity")
    if isinstance(toxicity, bool) or not isinstance(toxicity, int):
        raise ValueError(f"toxicity must be an integer 0-3, got {toxicity!r}")
    if not 0 <= toxicity <= 3:
        raise ValueError(f"toxicity out of range: {toxicity}")

    confidence, confidence_issues = _confidence(payload)
    issues.extend(confidence_issues)

    rationale = payload.get("rationale")
    rationale_text = str(rationale).strip() if rationale is not None else ""

    evidence = payload.get("evidence")
    if evidence is None:
        evidence_items: list[str] = []
    elif isinstance(evidence, list):
        evidence_items = [str(item).strip() for item in evidence if str(item).strip()]
    else:
        evidence_items = [str(evidence).strip()]
        issues.append("evidence is not a list")

    invalid_evidence = [
        item
        for item in evidence_items
        if not evidence_in_text(item, [task.text_raw, task.text_clean])
    ]
    if invalid_evidence:
        issues.append(f"{len(invalid_evidence)} evidence fragment(s) not verbatim")

    notes = {
        "model": model,
        "provider": provider,
        "prompt_sha256": task.prompt_sha256,
        "confidence": confidence,
        "rationale": rationale_text,
        "evidence": evidence_items,
        "evidence_valid": not invalid_evidence,
        "issues": issues,
    }
    annotation = AnnotationRecord(
        post_id=task.post_id,
        thread_id=task.thread_id,
        source=task.source,
        period=task.period,
        content_hash=task.content_hash,
        frame_labels=frame_labels,
        toxicity=toxicity,
        annotator=f"llm/{model}",
        round=1,
        tier="silver",
        guideline_version=task.guideline_version,
        annotated_utc=annotated_utc or datetime.now(timezone.utc),
        notes=json.dumps(notes, ensure_ascii=False, sort_keys=True),
    )
    return annotation, issues


def convert_raw_rows(
    rows: Iterable[dict[str, Any]],
    tasks: Iterable[TaskRecord],
    *,
    model: str,
    provider: str,
) -> tuple[list[AnnotationRecord], dict[str, Any]]:
    """Convert raw batch rows to silver annotations and an audit report."""
    task_by_id = {task.task_id: task for task in tasks}
    annotations: list[AnnotationRecord] = []
    failures: list[dict[str, Any]] = []
    missing_tasks = 0
    raw_rows = 0

    for row in rows:
        raw_rows += 1
        task_id = str(row.get("task_id") or "")
        task = task_by_id.get(task_id)
        if task is None:
            missing_tasks += 1
            continue

        payload = row.get("payload")
        if not isinstance(payload, dict):
            try:
                payload = parse_json_object(str(row.get("raw_text") or ""))
            except Exception as exc:
                failures.append(
                    {"task_id": task_id, "post_id": task.post_id, "error": str(exc)}
                )
                continue

        try:
            annotation, issues = annotation_from_payload(
                task, payload, model=model, provider=provider
            )
        except Exception as exc:
            failures.append(
                {"task_id": task_id, "post_id": task.post_id, "error": str(exc)}
            )
            continue

        annotations.append(annotation)
        if issues:
            failures.append(
                {
                    "task_id": task_id,
                    "post_id": task.post_id,
                    "warning": "; ".join(issues),
                }
            )

    by_post = {item.post_id: item for item in annotations}
    frame_counts: Counter[str] = Counter()
    coarse_counts: Counter[str] = Counter()
    toxicity_counts: Counter[int] = Counter()
    for annotation in annotations:
        frame_counts.update(annotation.frame_labels)
        coarse_counts.update(collapse_frames(annotation.frame_labels))
        if annotation.toxicity is not None:
            toxicity_counts[annotation.toxicity] += 1

    warnings = [item for item in failures if "warning" in item]
    errors = [item for item in failures if "error" in item]
    report = {
        "raw_rows": raw_rows,
        "annotations": len(annotations),
        "unique_posts": len(by_post),
        "duplicate_posts": len(annotations) - len(by_post),
        "missing_tasks": missing_tasks,
        "errors": len(errors),
        "warnings": len(warnings),
        "error_details": errors[:20],
        "warning_details": warnings[:20],
        "frames": dict(sorted(frame_counts.items())),
        "coarse_heads": {
            head: coarse_counts.get(head, 0) for head in COARSE_HEADS
        },
        "toxicity": {level: toxicity_counts.get(level, 0) for level in range(4)},
    }
    return annotations, report
