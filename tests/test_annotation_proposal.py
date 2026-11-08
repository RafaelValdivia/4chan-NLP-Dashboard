from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from keklab.annotation.prompts import render_prompt
from keklab.annotation.proposal import (
    ProposalRecord,
    ReviewRecord,
    TaskRecord,
    build_proposal,
    build_review,
    evidence_in_text,
    proposal_id_for,
    review_id_for,
    sanitize_stratum,
    task_id_for,
)
from keklab.annotation.schema import ContextPost, SampleContext, SamplePost

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def make_sample(
    post_id: str = "1",
    *,
    text_raw: str = "hello world",
    stratum: dict | None = None,
) -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="kek",
        period="hist_2016_2019",
        timestamp_utc=NOW,
        subject="subject",
        text_raw=text_raw,
        text_clean=text_raw,
        quotes=[],
        content_hash=f"hash-{post_id}",
        is_op=False,
        country=None,
        stratum=stratum or {"reason": "random", "month": "2018-01"},
        context=SampleContext(
            op=ContextPost(post_id="op", text_raw="OP text", is_op=True)
        ),
    )


def make_task(post_id: str = "1", *, text_raw: str = "hello world") -> TaskRecord:
    return TaskRecord.from_sample(
        make_sample(post_id, text_raw=text_raw),
        guideline_version="v0.1",
        prompt_version="v1",
        created_utc=NOW,
    )


def make_proposal(task: TaskRecord | None = None, **overrides):
    task = task or make_task()
    values = dict(
        frame_labels=["conspiracy"],
        toxicity=1,
        confidence=0.8,
        rationale="The post claims a secret plot.",
        evidence=["hello world"],
        model="big-pickle",
        provider="opencode",
        created_utc=NOW,
    )
    values.update(overrides)
    return build_proposal(task, **values)


def test_task_sanitizes_targeted_stratum():
    sample = make_sample(
        stratum={
            "reason": "targeted",
            "frame": "rusophobia",
            "term": "putin",
            "month": "2018-01",
        }
    )
    task = TaskRecord.from_sample(
        sample,
        guideline_version="v0.1",
        prompt_version="v1",
        created_utc=NOW,
    )

    assert task.stratum == {"reason": "targeted", "month": "2018-01"}
    assert "frame" not in task.model_dump(mode="json")["stratum"]
    assert "frame_labels" not in task.model_dump(mode="json")
    assert sanitize_stratum({"frame": "x", "term": "y"}) == {}
    # Text-only task: context and subject are dropped.
    assert task.subject is None
    assert task.context.op is None
    assert task.context.parents == []


def test_prompt_contains_only_target_post_text():
    task = make_task()
    prompt = render_prompt(task)

    assert task.text_raw in prompt
    assert "OP text" not in prompt
    assert "Subject:" not in prompt
    assert '"context"' not in prompt


def test_task_and_proposal_ids_are_deterministic():
    first = make_task("1")
    second = make_task("1")
    other = make_task("2")

    assert first.task_id == second.task_id
    assert first.task_id != other.task_id
    assert first.task_id == task_id_for(
        source="kek",
        post_id="1",
        content_hash="hash-1",
        guideline_version="v0.1",
        prompt_version="v1",
    )

    proposal = make_proposal(first)
    assert proposal.proposal_id == proposal_id_for(
        task_id=first.task_id, model="big-pickle", prompt_version="v1"
    )
    assert proposal.proposal_id == make_proposal(first).proposal_id


def test_proposal_rejects_invalid_labels_and_scales():
    task = make_task()

    with pytest.raises(ValidationError):
        make_proposal(task, frame_labels=["not-a-frame"])

    with pytest.raises(ValidationError):
        make_proposal(task, frame_labels=["none", "conspiracy"])

    with pytest.raises(ValidationError):
        make_proposal(task, frame_labels=["unclear", "none"])

    with pytest.raises(ValidationError):
        make_proposal(task, toxicity=4)

    with pytest.raises(ValidationError):
        make_proposal(task, confidence=1.5)

    with pytest.raises(ValidationError):
        make_proposal(task, rationale="   ")


def test_proposal_id_must_match_its_fields():
    proposal = make_proposal()
    data = proposal.model_dump(mode="json")
    data["proposal_id"] = "prop_deadbeefdeadbeef"

    with pytest.raises(ValidationError):
        ProposalRecord.model_validate(data)


def test_evidence_matching_is_verbatim_and_whitespace_tolerant():
    assert evidence_in_text("hello world", ["hello world"])
    assert evidence_in_text("hello   world", ["hello world"])
    assert evidence_in_text("hello\nworld", ["hello world"])
    assert not evidence_in_text("hello mars", ["hello world"])
    assert not evidence_in_text("   ", ["hello world"])


def test_validate_against_task_rejects_mismatch_and_missing_evidence():
    task = make_task()
    proposal = make_proposal(task)
    proposal.validate_against_task(task)

    other = make_task("2")
    with pytest.raises(ValueError, match="does not match task"):
        proposal.validate_against_task(other)

    missing = make_proposal(task, evidence=["not in the post"])
    with pytest.raises(ValueError, match="evidence not found"):
        missing.validate_against_task(task)


def test_review_requires_final_labels_for_accept_and_edit():
    proposal = make_proposal()

    accepted = build_review(
        proposal,
        reviewer="flynnso",
        decision="accept",
        final_frame_labels=["conspiracy"],
        final_toxicity=1,
        reviewed_utc=NOW,
    )
    assert accepted.review_id == review_id_for(
        proposal_id=proposal.proposal_id, reviewer="flynnso"
    )
    assert accepted.final_frame_labels == ["conspiracy"]

    rejected = build_review(
        proposal, reviewer="flynnso", decision="reject", reviewed_utc=NOW
    )
    assert rejected.final_frame_labels is None
    assert rejected.final_toxicity is None

    with pytest.raises(ValidationError):
        ReviewRecord.model_validate(
            {
                **accepted.model_dump(mode="json"),
                "decision": "edit",
                "final_frame_labels": None,
                "final_toxicity": None,
            }
        )
