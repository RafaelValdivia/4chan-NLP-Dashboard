from __future__ import annotations

from datetime import datetime, timezone

from keklab.annotation.proposal import TaskRecord
from keklab.annotation.schema import SamplePost
from keklab.classification.batch import run_batch
from keklab.classification.backends import FakeBackend
from keklab.classification.validate import (
    repair_prompt,
    rule_violations,
    validate_payload,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def make_task(post_id: str = "1", *, text: str = "a secret plot by elites"):
    sample = SamplePost(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="kek",
        period="hist_2016_2019",
        timestamp_utc=NOW,
        text_raw=text,
        text_clean=text,
        content_hash=f"hash-{post_id}",
    )
    return TaskRecord.from_sample(
        sample,
        guideline_version="v0.2",
        prompt_version="v2",
        prompt_sha256="prompt-hash",
        created_utc=NOW,
    )


def payload(**overrides):
    values = {
        "post_id": "1",
        "frame_labels": ["conspiracy"],
        "toxicity": 2,
        "confidence": 0.8,
        "rationale": "The post claims a secret plot.",
        "evidence": ["secret plot"],
    }
    values.update(overrides)
    return values


def test_valid_payload_has_no_issues():
    assert validate_payload(payload(), make_task()) == []


def test_unknown_frame_label_is_reported():
    issues = validate_payload(payload(frame_labels=["not_a_frame"]), make_task())

    assert any("unknown frame labels" in issue for issue in issues)


def test_exclusive_label_combination_is_reported():
    issues = validate_payload(payload(frame_labels=["none", "racism"]), make_task())

    assert any("cannot be combined" in issue for issue in issues)


def test_invalid_toxicity_and_confidence_are_reported():
    issues = validate_payload(
        payload(toxicity=4, confidence=1.5), make_task()
    )

    assert any("toxicity" in issue for issue in issues)
    assert any("confidence" in issue for issue in issues)


def test_non_verbatim_evidence_is_reported():
    issues = validate_payload(payload(evidence=["not in the post"]), make_task())

    assert any("not verbatim" in issue for issue in issues)


def test_post_id_mismatch_is_reported():
    issues = validate_payload(payload(post_id="2"), make_task())

    assert any("post_id" in issue for issue in issues)


def test_rule_violations_detect_specific_with_generic():
    violations = rule_violations(["antisemitism", "racism"])

    assert violations == ["specific prejudice combined with generic prejudice"]


def test_rule_violations_detect_exclusive_combination():
    violations = rule_violations(["none", "conspiracy"])

    assert violations == ["none combined with other frames"]


def test_rule_violations_empty_for_consistent_labels():
    assert rule_violations(["antisemitism", "conspiracy"]) == []


def test_repair_prompt_mentions_the_issue_and_previous_answer():
    prompt = repair_prompt("BASE", '{"frame_labels": ["nope"]}', ["unknown label"])

    assert "BASE" in prompt
    assert "unknown label" in prompt
    assert "nope" in prompt


def test_batch_repairs_an_invalid_payload(tmp_path):
    task = make_task()
    out = tmp_path / "raw.jsonl"
    backend = FakeBackend(
        [
            '{"post_id": "1", "frame_labels": ["not_a_frame"], "toxicity": 1}',
            '{"post_id": "1", "frame_labels": ["conspiracy"], "toxicity": 2}',
        ]
    )

    report = run_batch([task], backend, out, retries=1, log_every=0)

    assert report["ok"] == 1
    assert report["failed"] == 0
    assert report["repaired"] == 1


def test_batch_reports_failure_when_the_repair_also_fails(tmp_path):
    task = make_task()
    out = tmp_path / "raw.jsonl"
    backend = FakeBackend(
        [
            '{"post_id": "1", "frame_labels": ["not_a_frame"], "toxicity": 1}',
            '{"post_id": "1", "frame_labels": ["still_wrong"], "toxicity": 1}',
        ]
    )

    report = run_batch([task], backend, out, retries=1, log_every=0)

    assert report["ok"] == 0
    assert report["failed"] == 1


def test_batch_can_skip_validation(tmp_path):
    task = make_task()
    out = tmp_path / "raw.jsonl"
    backend = FakeBackend(
        ['{"post_id": "1", "frame_labels": ["not_a_frame"], "toxicity": 1}']
    )

    report = run_batch([task], backend, out, retries=0, log_every=0, validate=False)

    assert report["ok"] == 1
    assert report["failed"] == 0
