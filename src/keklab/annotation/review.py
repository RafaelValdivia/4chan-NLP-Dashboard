# Role: human validation of AI proposals (accept, edit, reject, skip, resume).
# Connects to: annotation/proposal, annotation/store, annotation/editing.

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from keklab.annotation.editing import apply_edit_command
from keklab.annotation.proposal import (
    ProposalRecord,
    ReviewRecord,
    TaskRecord,
    build_review,
    is_resolved,
    latest_reviews,
)
from keklab.annotation.schema import AnnotationRecord
from keklab.annotation.store import (
    AnnotationStore,
    load_reviews,
    upsert_review,
    write_reviews,
)

REVIEW_HELP = """\
Commands:
  a          accept the proposal as-is
  e          edit the proposed labels, then 's' to save the edit
  r          reject the proposal (no gold is written)
  s          skip for now (it will reappear next session)
  b          go back to the previous proposal
  q          quit without deciding this proposal
  ?          show this help

In edit mode:
  <numbers>  toggle frames, e.g. 1 3 7
  n          set frame to 'none'
  u          set frame to 'unclear'
  c          clear selected frames
  t          cycle toxicity 0 -> 1 -> 2 -> 3 -> 0
  s          save the edit and write gold
  x          cancel the edit and restore the proposal
"""


def _excerpt(text: str, limit: int = 700) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[...]"


def _proposal_block(proposal: ProposalRecord, *, blind: bool) -> list[str]:
    lines = [
        "",
        "Proposal: " + ", ".join(proposal.frame_labels),
        f"Proposal toxicity: {proposal.toxicity}",
    ]
    if blind:
        lines.append("(blind review: rationale, evidence and confidence hidden)")
        return lines

    lines.extend(
        [
            f"Confidence: {proposal.confidence:.2f}",
            f"Rationale: {proposal.rationale}",
        ]
    )
    if proposal.evidence:
        lines.append("Evidence:")
        lines.extend(f"  - {item}" for item in proposal.evidence)
    else:
        lines.append("Evidence: (none)")
    return lines


def render_review(
    task: TaskRecord,
    proposal: ProposalRecord,
    index: int,
    total: int,
    *,
    frames: Iterable[str],
    toxicity: int | None,
    blind: bool = False,
    editing: bool = False,
) -> str:
    frames = list(frames)
    timestamp = (
        task.timestamp_utc.strftime("%Y-%m-%d %H:%M UTC")
        if task.timestamp_utc
        else "unknown date"
    )
    lines = [
        "",
        "=" * 78,
        f"[{index}/{total}] {task.source} | {task.period or 'period?'} | "
        f"{timestamp} | thread {task.thread_id}",
    ]

    if task.subject:
        lines.append(f"Subject: {task.subject}")
    if task.stratum:
        lines.append(
            f"Stratum: {json.dumps(task.stratum, ensure_ascii=False)}"
        )

    if task.context.op is not None:
        lines.extend(
            [
                "",
                f"OP context ({task.context.op.post_id}):",
                _excerpt(task.context.op.text_raw, 450),
            ]
        )

    for parent in task.context.parents:
        lines.extend(
            [
                "",
                f"Quoted post ({parent.post_id}):",
                _excerpt(parent.text_raw, 450),
            ]
        )

    lines.extend(["", "Post text:"])
    raw = _excerpt(task.text_raw or task.text_clean or "(empty post)")
    lines.append(raw)
    if task.text_clean and task.text_clean.strip() != raw.strip():
        lines.extend(["", "Clean text:", _excerpt(task.text_clean)])

    lines.extend(_proposal_block(proposal, blind=blind))
    lines.extend(
        [
            "",
            "Selected frames: " + (", ".join(frames) if frames else "(none)"),
            "Selected toxicity: "
            + (str(toxicity) if toxicity is not None else "(unset)"),
            "",
            (
                "Edit mode: numbers toggle | n none | u unclear | c clear | "
                "t toxicity | s save edit | x cancel"
                if editing
                else "Commands: a accept | e edit | r reject | s skip | "
                "b back | q quit | ? help"
            ),
        ]
    )
    return "\n".join(lines)


def _gold_record(
    task: TaskRecord,
    *,
    reviewer: str,
    guideline_version: str,
    frames: list[str],
    toxicity: int,
    annotated_utc: datetime,
) -> AnnotationRecord:
    return AnnotationRecord(
        post_id=task.post_id,
        thread_id=task.thread_id,
        source=task.source,
        period=task.period,
        content_hash=task.content_hash,
        frame_labels=frames,
        toxicity=toxicity,
        annotator=reviewer,
        round=1,
        tier="gold",
        guideline_version=guideline_version,
        annotated_utc=annotated_utc,
        notes=f"stratum={json.dumps(task.stratum, ensure_ascii=False)}",
    )


def pending_proposals(
    tasks: Iterable[TaskRecord],
    proposals: Iterable[ProposalRecord],
    reviews: Iterable[ReviewRecord],
    *,
    revisit: bool = False,
) -> tuple[list[ProposalRecord], int]:
    """Proposals still waiting for a resolved human decision.

    Returns `(pending, orphans)`, where orphans are proposals whose task is
    missing from the task file.
    """
    task_ids = {task.task_id for task in tasks}
    latest = latest_reviews(list(reviews))
    pending: list[ProposalRecord] = []
    orphans = 0
    for proposal in proposals:
        if proposal.task_id not in task_ids:
            orphans += 1
            continue
        if not revisit and is_resolved(latest.get(proposal.proposal_id)):
            continue
        pending.append(proposal)
    return pending, orphans


def run_review(
    tasks: Iterable[TaskRecord],
    proposals: Iterable[ProposalRecord],
    *,
    gold_path: str | Path,
    reviews_path: str | Path,
    reviewer: str,
    guideline_version: str,
    blind: bool = False,
    revisit: bool = False,
    limit: int | None = None,
    prompt: Callable[[str], str] = input,
    emit: Callable[[str], None] = print,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Interactively validate proposals and write gold only on human approval."""
    now = now or (lambda: datetime.now(timezone.utc))
    tasks = list(tasks)
    proposals = list(proposals)
    reviews = load_reviews(reviews_path)
    queue, orphans = pending_proposals(
        tasks, proposals, reviews, revisit=revisit
    )
    if limit is not None:
        queue = queue[:limit]

    if not queue:
        emit("Nothing to review: every proposal already has a decision.")
        return {
            "reviewed": 0,
            "accepted": 0,
            "edited": 0,
            "rejected": 0,
            "skipped": 0,
            "remaining": 0,
            "quit": False,
            "orphans": orphans,
            "gold": str(gold_path),
            "reviews": str(reviews_path),
        }

    task_by_id = {task.task_id: task for task in tasks}
    latest = latest_reviews(reviews)
    gold_store = AnnotationStore(gold_path)

    accepted = edited = rejected = skipped = 0
    index = 0
    quit_requested = False

    while index < len(queue) and not quit_requested:
        proposal = queue[index]
        task = task_by_id[proposal.task_id]
        previous = latest.get(proposal.proposal_id)
        if previous is not None and previous.final_frame_labels is not None:
            frames = list(previous.final_frame_labels)
            toxicity = previous.final_toxicity
        else:
            frames = list(proposal.frame_labels)
            toxicity = proposal.toxicity

        editing = False
        while True:
            emit(
                render_review(
                    task,
                    proposal,
                    index + 1,
                    len(queue),
                    frames=frames,
                    toxicity=toxicity,
                    blind=blind,
                    editing=editing,
                )
            )
            try:
                command = prompt("> ").strip()
            except (EOFError, KeyboardInterrupt):
                emit("")
                quit_requested = True
                break

            if not command:
                continue
            lowered = command.lower()

            if editing:
                if lowered in {"s", "save"}:
                    if not frames:
                        emit("Select at least one frame (use n for none / u for unclear).")
                        continue
                    if toxicity is None:
                        emit("Set toxicity with 't' before saving.")
                        continue
                    timestamp = now()
                    review = build_review(
                        proposal,
                        reviewer=reviewer,
                        decision="edit",
                        final_frame_labels=frames,
                        final_toxicity=toxicity,
                        reviewed_utc=timestamp,
                    )
                    gold_store.upsert(
                        _gold_record(
                            task,
                            reviewer=reviewer,
                            guideline_version=guideline_version,
                            frames=frames,
                            toxicity=toxicity,
                            annotated_utc=timestamp,
                        )
                    )
                    reviews = upsert_review(reviews, review)
                    write_reviews(reviews, reviews_path)
                    latest[proposal.proposal_id] = review
                    edited += 1
                    index += 1
                    emit("Saved edit as gold.")
                    break

                if lowered in {"x", "cancel"}:
                    frames = list(proposal.frame_labels)
                    toxicity = proposal.toxicity
                    editing = False
                    emit("Edit cancelled.")
                    continue

                try:
                    result = apply_edit_command(frames, toxicity, command)
                except ValueError as exc:
                    emit(str(exc))
                    continue
                if result is None:
                    emit(f"Unknown edit command: {command!r} (x to cancel)")
                    continue
                frames, toxicity, message = result
                emit(message)
                continue

            if lowered in {"a", "accept"}:
                timestamp = now()
                review = build_review(
                    proposal,
                    reviewer=reviewer,
                    decision="accept",
                    final_frame_labels=list(proposal.frame_labels),
                    final_toxicity=proposal.toxicity,
                    reviewed_utc=timestamp,
                )
                gold_store.upsert(
                    _gold_record(
                        task,
                        reviewer=reviewer,
                        guideline_version=guideline_version,
                        frames=list(proposal.frame_labels),
                        toxicity=proposal.toxicity,
                        annotated_utc=timestamp,
                    )
                )
                reviews = upsert_review(reviews, review)
                write_reviews(reviews, reviews_path)
                latest[proposal.proposal_id] = review
                accepted += 1
                index += 1
                emit("Accepted and saved as gold.")
                break

            if lowered in {"e", "edit"}:
                editing = True
                frames = list(proposal.frame_labels)
                toxicity = proposal.toxicity
                emit("Edit mode: change labels and press 's' to save.")
                continue

            if lowered in {"r", "reject"}:
                review = build_review(
                    proposal,
                    reviewer=reviewer,
                    decision="reject",
                    reviewed_utc=now(),
                )
                reviews = upsert_review(reviews, review)
                write_reviews(reviews, reviews_path)
                latest[proposal.proposal_id] = review
                rejected += 1
                index += 1
                emit("Rejected; no gold written.")
                break

            if lowered in {"s", "skip"}:
                review = build_review(
                    proposal,
                    reviewer=reviewer,
                    decision="skip",
                    reviewed_utc=now(),
                )
                reviews = upsert_review(reviews, review)
                write_reviews(reviews, reviews_path)
                latest[proposal.proposal_id] = review
                skipped += 1
                index += 1
                emit("Skipped; it will reappear next session.")
                break

            if lowered in {"b", "back"}:
                if index > 0:
                    index -= 1
                    emit("Going back one proposal.")
                else:
                    emit("Already at the first proposal.")
                break

            if lowered in {"q", "quit"}:
                quit_requested = True
                break

            if lowered in {"?", "h", "help"}:
                emit(REVIEW_HELP)
                continue

            emit(f"Unknown command: {command!r} (press ? for help)")

    return {
        "reviewed": accepted + edited + rejected + skipped,
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "skipped": skipped,
        "remaining": max(0, len(queue) - index),
        "quit": quit_requested,
        "orphans": orphans,
        "gold": str(gold_path),
        "reviews": str(reviews_path),
    }
