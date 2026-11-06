# Role: AI-assistance records (task, proposal, review) and their validation.
# Connects to: annotation/schema, annotation/labels, annotation/ai, annotation/review.

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from keklab.annotation.labels import normalize_frame_labels
from keklab.annotation.schema import SampleContext, SamplePost

# Keys from `SamplePost.stratum` that are safe to expose to the annotator.
# `frame` and `term` identify the targeted frame and would leak the answer.
SAFE_STRATUM_KEYS: frozenset[str] = frozenset({"reason", "month"})

ReviewDecision = Literal["accept", "edit", "reject", "skip"]


# ---------------------------------------------------------------------------
# Deterministic identifiers
# ---------------------------------------------------------------------------
def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def task_id_for(
    *,
    source: str,
    post_id: str,
    content_hash: str,
    guideline_version: str,
    prompt_version: str,
) -> str:
    return _stable_id(
        "task",
        source,
        post_id,
        content_hash,
        guideline_version,
        prompt_version,
    )


def proposal_id_for(
    *,
    task_id: str,
    model: str,
    prompt_version: str,
) -> str:
    return _stable_id("prop", task_id, model, prompt_version)


def review_id_for(*, proposal_id: str, reviewer: str) -> str:
    return _stable_id("rev", proposal_id, reviewer)


# ---------------------------------------------------------------------------
# Task records (blind input for the AI)
# ---------------------------------------------------------------------------
def sanitize_stratum(stratum: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only non-identifying stratum fields (drop targeted frame/term)."""
    if not stratum:
        return {}
    return {
        key: value
        for key, value in stratum.items()
        if key in SAFE_STRATUM_KEYS
    }


class TaskRecord(BaseModel):
    """One post prepared for AI pre-annotation, without gold labels."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    post_id: str
    thread_id: str
    source: Literal["kek", "fourplebs"]
    period: Literal["hist_2016_2019", "recent_2020_plus"] | None = None
    timestamp_utc: datetime | None = None
    subject: str | None = None
    text_raw: str = ""
    text_clean: str = ""
    quotes: list[str] = Field(default_factory=list)
    content_hash: str
    is_op: bool = False
    country: str | None = None
    stratum: dict[str, Any] = Field(default_factory=dict)
    context: SampleContext = Field(default_factory=SampleContext)
    guideline_version: str
    prompt_version: str
    created_utc: datetime

    @field_validator("task_id", "post_id", "thread_id", "content_hash")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("value must not be empty")
        return str(value)

    @classmethod
    def from_sample(
        cls,
        sample: SamplePost,
        *,
        guideline_version: str,
        prompt_version: str,
        created_utc: datetime | None = None,
    ) -> "TaskRecord":
        return cls(
            task_id=task_id_for(
                source=sample.source,
                post_id=sample.post_id,
                content_hash=sample.content_hash,
                guideline_version=guideline_version,
                prompt_version=prompt_version,
            ),
            post_id=sample.post_id,
            thread_id=sample.thread_id,
            source=sample.source,
            period=sample.period,
            timestamp_utc=sample.timestamp_utc,
            subject=sample.subject,
            text_raw=sample.text_raw,
            text_clean=sample.text_clean,
            quotes=list(sample.quotes),
            content_hash=sample.content_hash,
            is_op=sample.is_op,
            country=sample.country,
            stratum=sanitize_stratum(sample.stratum),
            context=sample.context,
            guideline_version=guideline_version,
            prompt_version=prompt_version,
            created_utc=created_utc or datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Proposal records (AI output, never gold by itself)
# ---------------------------------------------------------------------------
def _normalize_whitespace(text: str) -> str:
    return " ".join(str(text).split())


def evidence_in_text(evidence: str, texts: list[str] | tuple[str, ...]) -> bool:
    """True when `evidence` is a verbatim fragment of any of `texts`.

    Exact substring matching is tried first, then a whitespace-insensitive
    comparison so line breaks and repeated spaces do not cause false negatives.
    """
    needle = str(evidence).strip()
    if not needle:
        return False
    for text in texts:
        haystack = str(text or "")
        if not haystack:
            continue
        if needle in haystack:
            return True
        normalized_needle = _normalize_whitespace(needle)
        if normalized_needle and normalized_needle in _normalize_whitespace(haystack):
            return True
    return False


class ProposalRecord(BaseModel):
    """An AI proposal for one task. Only a human review can turn it into gold."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    task_id: str
    post_id: str
    thread_id: str
    source: Literal["kek", "fourplebs"]
    content_hash: str
    frame_labels: list[str]
    toxicity: int = Field(ge=0, le=3)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    model: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    prompt_version: str
    guideline_version: str
    created_utc: datetime

    @field_validator("frame_labels", mode="before")
    @classmethod
    def _validate_frames(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        return normalize_frame_labels(value or [])

    @field_validator("rationale")
    @classmethod
    def _rationale_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rationale must not be blank")
        return value.strip()

    @field_validator("evidence")
    @classmethod
    def _evidence_not_blank(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value]
        cleaned = [item for item in cleaned if item]
        return cleaned

    @model_validator(mode="after")
    def _id_matches_fields(self) -> "ProposalRecord":
        expected = proposal_id_for(
            task_id=self.task_id,
            model=self.model,
            prompt_version=self.prompt_version,
        )
        if self.proposal_id != expected:
            raise ValueError(
                f"proposal_id {self.proposal_id!r} does not match its fields "
                f"(expected {expected!r})"
            )
        return self

    def validate_against_task(self, task: TaskRecord) -> None:
        """Fail when the proposal does not describe exactly this task."""
        if self.task_id != task.task_id:
            raise ValueError(
                f"proposal {self.proposal_id}: task_id {self.task_id!r} "
                f"does not match task {task.task_id!r}"
            )
        for field in ("post_id", "thread_id", "source", "content_hash"):
            left = getattr(self, field)
            right = getattr(task, field)
            if left != right:
                raise ValueError(
                    f"proposal {self.proposal_id}: {field} {left!r} "
                    f"does not match task ({right!r})"
                )
        if self.guideline_version != task.guideline_version:
            raise ValueError(
                f"proposal {self.proposal_id}: guideline_version "
                f"{self.guideline_version!r} != {task.guideline_version!r}"
            )
        if self.prompt_version != task.prompt_version:
            raise ValueError(
                f"proposal {self.proposal_id}: prompt_version "
                f"{self.prompt_version!r} != {task.prompt_version!r}"
            )

        missing = [
            item
            for item in self.evidence
            if not evidence_in_text(item, [task.text_raw, task.text_clean])
        ]
        if missing:
            preview = "; ".join(repr(item[:80]) for item in missing[:3])
            raise ValueError(
                f"proposal {self.proposal_id}: evidence not found verbatim "
                f"in the post text: {preview}"
            )


def build_proposal(
    task: TaskRecord,
    *,
    frame_labels: list[str],
    toxicity: int,
    confidence: float,
    rationale: str,
    evidence: list[str] | None = None,
    model: str,
    provider: str,
    created_utc: datetime | None = None,
) -> ProposalRecord:
    """Build a proposal with the deterministic id derived from its fields."""
    prompt_version = task.prompt_version
    return ProposalRecord(
        proposal_id=proposal_id_for(
            task_id=task.task_id,
            model=model,
            prompt_version=prompt_version,
        ),
        task_id=task.task_id,
        post_id=task.post_id,
        thread_id=task.thread_id,
        source=task.source,
        content_hash=task.content_hash,
        frame_labels=frame_labels,
        toxicity=toxicity,
        confidence=confidence,
        rationale=rationale,
        evidence=list(evidence or []),
        model=model,
        provider=provider,
        prompt_version=prompt_version,
        guideline_version=task.guideline_version,
        created_utc=created_utc or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Review records (human validation log, source of truth for provenance)
# ---------------------------------------------------------------------------
class ReviewRecord(BaseModel):
    """One human decision about one proposal."""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    proposal_id: str
    task_id: str
    post_id: str
    reviewer: str = Field(min_length=1)
    decision: ReviewDecision
    proposed_frame_labels: list[str]
    proposed_toxicity: int = Field(ge=0, le=3)
    final_frame_labels: list[str] | None = None
    final_toxicity: int | None = Field(default=None, ge=0, le=3)
    notes: str | None = None
    guideline_version: str
    reviewed_utc: datetime

    @field_validator("proposed_frame_labels", "final_frame_labels", mode="before")
    @classmethod
    def _validate_frames(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = [value]
        return normalize_frame_labels(value or [])

    @model_validator(mode="after")
    def _decision_has_final_labels(self) -> "ReviewRecord":
        expected = review_id_for(
            proposal_id=self.proposal_id, reviewer=self.reviewer
        )
        if self.review_id != expected:
            raise ValueError(
                f"review_id {self.review_id!r} does not match its fields "
                f"(expected {expected!r})"
            )
        if self.decision in {"accept", "edit"}:
            if self.final_frame_labels is None or self.final_toxicity is None:
                raise ValueError(
                    "accept/edit reviews need final_frame_labels and final_toxicity"
                )
        return self


def build_review(
    proposal: ProposalRecord,
    *,
    reviewer: str,
    decision: ReviewDecision,
    final_frame_labels: list[str] | None = None,
    final_toxicity: int | None = None,
    notes: str | None = None,
    reviewed_utc: datetime | None = None,
) -> ReviewRecord:
    return ReviewRecord(
        review_id=review_id_for(
            proposal_id=proposal.proposal_id, reviewer=reviewer
        ),
        proposal_id=proposal.proposal_id,
        task_id=proposal.task_id,
        post_id=proposal.post_id,
        reviewer=reviewer,
        decision=decision,
        proposed_frame_labels=list(proposal.frame_labels),
        proposed_toxicity=proposal.toxicity,
        final_frame_labels=final_frame_labels,
        final_toxicity=final_toxicity,
        notes=notes,
        guideline_version=proposal.guideline_version,
        reviewed_utc=reviewed_utc or datetime.now(timezone.utc),
    )


def latest_reviews(reviews: list[ReviewRecord]) -> dict[str, ReviewRecord]:
    """Index reviews by proposal id, keeping the most recent per proposal."""
    latest: dict[str, ReviewRecord] = {}
    for review in reviews:
        current = latest.get(review.proposal_id)
        if current is None or review.reviewed_utc >= current.reviewed_utc:
            latest[review.proposal_id] = review
    return latest


RESOLVED_DECISIONS: frozenset[str] = frozenset({"accept", "edit", "reject"})


def is_resolved(review: ReviewRecord | None) -> bool:
    return review is not None and review.decision in RESOLVED_DECISIONS
