# Role: AI-assistance orchestration (task building, import, stats, agreement).
# Connects to: annotation/proposal, annotation/store, annotation/agreement.

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from keklab.annotation.agreement import agreement_report
from keklab.annotation.proposal import (
    ProposalRecord,
    ReviewRecord,
    TaskRecord,
    is_resolved,
    latest_reviews,
)
from keklab.annotation.schema import (
    AnnotationRecord,
    SamplePost,
    annotation_sample_key,
    sample_key,
)
from keklab.formal.schema import Annotation


# ---------------------------------------------------------------------------
# Task building
# ---------------------------------------------------------------------------
def build_tasks(
    samples: Iterable[SamplePost],
    *,
    gold: Iterable[AnnotationRecord] = (),
    guideline_version: str,
    prompt_version: str,
    prompt_sha256: str | None = None,
    include_annotated: bool = False,
    start: int = 1,
    limit: int | None = None,
    created_utc: datetime | None = None,
) -> tuple[list[TaskRecord], dict[str, Any]]:
    """Build blind tasks for the posts that still have no gold annotation.

    `start` is 1-based. Gold posts are skipped unless `include_annotated=True`,
    and the targeted `stratum.frame`/`stratum.term` are always removed.
    """
    if start < 1:
        raise ValueError("start must be >= 1")
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0")

    samples = list(samples)
    excluded = {annotation_sample_key(record) for record in gold}

    pending: list[SamplePost] = []
    seen: set[tuple[str, str, str]] = set()
    for sample in samples:
        key = sample_key(sample)
        if key in seen:
            continue
        seen.add(key)
        if not include_annotated and key in excluded:
            continue
        pending.append(sample)

    selected = pending[start - 1 :]
    if limit is not None:
        selected = selected[:limit]

    tasks = [
        TaskRecord.from_sample(
            sample,
            guideline_version=guideline_version,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            created_utc=created_utc,
        )
        for sample in selected
    ]
    report = {
        "samples": len(samples),
        "unique_samples": len(seen),
        "excluded_by_gold": len(seen) - len(pending),
        "pending": len(pending),
        "start": start,
        "limit": limit,
        "selected": len(tasks),
        "guideline_version": guideline_version,
        "prompt_version": prompt_version,
    }
    return tasks, report


# ---------------------------------------------------------------------------
# Proposal import
# ---------------------------------------------------------------------------
def import_proposals(
    tasks: Iterable[TaskRecord],
    incoming: Iterable[ProposalRecord],
    *,
    existing: Iterable[ProposalRecord] = (),
    replace: bool = False,
) -> tuple[list[ProposalRecord], dict[str, Any]]:
    """Validate proposals against their tasks and merge them by proposal id."""
    task_by_id = {task.task_id: task for task in tasks}
    merged = {proposal.proposal_id: proposal for proposal in existing}

    added = 0
    replaced = 0
    seen: set[str] = set()
    incoming_count = 0
    for proposal in incoming:
        incoming_count += 1
        if proposal.proposal_id in seen:
            raise ValueError(
                f"duplicate proposal in this batch: {proposal.proposal_id}"
            )
        seen.add(proposal.proposal_id)

        task = task_by_id.get(proposal.task_id)
        if task is None:
            raise ValueError(
                f"proposal {proposal.proposal_id}: unknown task "
                f"{proposal.task_id!r}; generate or import its task first"
            )
        proposal.validate_against_task(task)

        if proposal.proposal_id in merged:
            if not replace:
                raise ValueError(
                    f"proposal already exists: {proposal.proposal_id} "
                    "(use --replace to overwrite)"
                )
            replaced += 1
        else:
            added += 1
        merged[proposal.proposal_id] = proposal

    report = {
        "tasks": len(task_by_id),
        "incoming": incoming_count,
        "added": added,
        "replaced": replaced,
        "total": len(merged),
    }
    return list(merged.values()), report


# ---------------------------------------------------------------------------
# Review statistics
# ---------------------------------------------------------------------------
def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set & right_set) / len(left_set | right_set)


_CONFIDENCE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0.00-0.50", 0.0, 0.50),
    ("0.50-0.70", 0.50, 0.70),
    ("0.70-0.85", 0.70, 0.85),
    ("0.85-1.00", 0.85, 1.0000001),
)


def proposal_stats(
    tasks: Iterable[TaskRecord],
    proposals: Iterable[ProposalRecord],
    reviews: Iterable[ReviewRecord],
) -> dict[str, Any]:
    """Coverage, review decisions, proposal/final agreement and calibration."""
    tasks = list(tasks)
    proposals = list(proposals)
    reviews = list(reviews)
    latest = latest_reviews(reviews)

    task_ids = {task.task_id for task in tasks}
    proposal_ids = {proposal.proposal_id for proposal in proposals}
    proposed_tasks = {
        proposal.task_id
        for proposal in proposals
        if proposal.task_id in task_ids
    }
    covered = len(proposed_tasks)

    decisions = Counter(
        latest[proposal_id].decision
        for proposal_id in proposal_ids
        if proposal_id in latest
    )
    resolved = [
        latest[proposal.proposal_id]
        for proposal in proposals
        if is_resolved(latest.get(proposal.proposal_id))
    ]
    accepted_or_edited = [r for r in resolved if r.decision in {"accept", "edit"}]

    jaccards = [
        _jaccard(r.proposed_frame_labels, r.final_frame_labels or [])
        for r in accepted_or_edited
    ]
    toxicity_pairs = [
        (r.proposed_toxicity, r.final_toxicity)
        for r in accepted_or_edited
        if r.final_toxicity is not None
    ]

    by_model = Counter(proposal.model for proposal in proposals)
    confidence_by_decision: dict[str, list[float]] = {}
    confidence_values = {p.proposal_id: p.confidence for p in proposals}
    for review in resolved:
        confidence_by_decision.setdefault(review.decision, []).append(
            confidence_values.get(review.proposal_id, 0.0)
        )

    calibration: list[dict[str, Any]] = []
    for label, low, high in _CONFIDENCE_BUCKETS:
        bucket = [
            proposal
            for proposal in proposals
            if low <= proposal.confidence < high
        ]
        resolved_bucket = [
            latest[proposal.proposal_id]
            for proposal in bucket
            if is_resolved(latest.get(proposal.proposal_id))
        ]
        accepted = sum(
            1 for review in resolved_bucket if review.decision == "accept"
        )
        calibration.append(
            {
                "bucket": label,
                "proposals": len(bucket),
                "resolved": len(resolved_bucket),
                "accepted_without_edit": accepted,
                "acceptance_rate": (
                    accepted / len(resolved_bucket)
                    if resolved_bucket
                    else 0.0
                ),
            }
        )

    def _rate(count: int) -> float:
        return count / len(resolved) if resolved else 0.0

    return {
        "tasks": len(tasks),
        "proposals": len(proposals),
        "proposals_covered": covered,
        "coverage": covered / len(tasks) if tasks else 0.0,
        "tasks_without_proposal": len(task_ids - proposed_tasks),
        "duplicate_proposal_ids": len(proposals) - len(proposal_ids),
        "by_model": dict(sorted(by_model.items())),
        "decisions": {
            decision: decisions.get(decision, 0)
            for decision in ("accept", "edit", "reject", "skip")
        },
        "resolved": len(resolved),
        "unresolved": len(proposals) - len(resolved),
        "accept_rate": _rate(decisions.get("accept", 0)),
        "edit_rate": _rate(decisions.get("edit", 0)),
        "reject_rate": _rate(decisions.get("reject", 0)),
        "mean_jaccard": (
            sum(jaccards) / len(jaccards) if jaccards else 0.0
        ),
        "toxicity_exact_agreement": (
            sum(1 for a, b in toxicity_pairs if a == b) / len(toxicity_pairs)
            if toxicity_pairs
            else 0.0
        ),
        "toxicity_mean_absolute_error": (
            sum(abs(a - b) for a, b in toxicity_pairs) / len(toxicity_pairs)
            if toxicity_pairs
            else 0.0
        ),
        "mean_confidence": (
            sum(confidence_values.values()) / len(confidence_values)
            if confidence_values
            else 0.0
        ),
        "mean_confidence_by_decision": {
            decision: sum(values) / len(values)
            for decision, values in sorted(confidence_by_decision.items())
            if values
        },
        "calibration": calibration,
    }


# ---------------------------------------------------------------------------
# AI vs human agreement
# ---------------------------------------------------------------------------
def _as_annotation(proposal: ProposalRecord) -> Annotation:
    return Annotation(
        post_id=proposal.post_id,
        thread_id=proposal.thread_id,
        source=proposal.source,
        content_hash=proposal.content_hash,
        frame_labels=list(proposal.frame_labels),
        toxicity=proposal.toxicity,
        annotator=f"{proposal.provider}/{proposal.model}",
        round=1,
        tier="silver",
        guideline_version=proposal.guideline_version,
        notes=f"proposal_id={proposal.proposal_id}",
    )


def proposal_agreement(
    proposals: Iterable[ProposalRecord],
    gold: Iterable[Annotation],
) -> dict[str, Any]:
    """Compare proposals with human gold on the posts they share.

    On a clean run this is empty because tasks exclude gold posts. It stays
    available for designed AI-vs-human comparisons on overlapping samples.
    """
    return agreement_report([_as_annotation(p) for p in proposals], list(gold))
