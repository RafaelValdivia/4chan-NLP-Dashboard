from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from keklab.annotation.schema import SamplePost
from keklab.annotation.proposal import TaskRecord
from keklab.classification.backends import FakeBackend
from keklab.classification.batch import run_batch
from keklab.classification.dataset import build_modeling_rows, frame_one_hot
from keklab.classification.grammar import output_json_schema
from keklab.classification.silver import (
    annotation_from_payload,
    convert_raw_rows,
    parse_json_object,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def make_sample(
    post_id: str,
    *,
    text: str = "a secret plot by elites",
    content_hash: str | None = None,
) -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="kek",
        period="hist_2016_2019",
        timestamp_utc=NOW,
        text_raw=text,
        text_clean=text,
        content_hash=content_hash or f"hash-{post_id}",
        stratum={"reason": "random", "month": "2018-01"},
    )


def make_task(post_id: str, *, text: str = "a secret plot by elites") -> TaskRecord:
    return TaskRecord.from_sample(
        make_sample(post_id, text=text),
        guideline_version="v0.2",
        prompt_version="v2",
        prompt_sha256="prompt-hash",
        created_utc=NOW,
    )


def payload(post_id: str = "1", **overrides):
    values = {
        "post_id": post_id,
        "frame_labels": ["conspiracy"],
        "toxicity": 2,
        "confidence": 0.8,
        "rationale": "The post claims a secret plot.",
        "evidence": ["secret plot"],
    }
    values.update(overrides)
    return values


def test_parse_json_object_strips_fences_and_preamble():
    text = 'Here is the result:\n```json\n{"post_id": "1", "toxicity": 0}\n```'

    assert parse_json_object(text) == {"post_id": "1", "toxicity": 0}


def test_parse_json_object_rejects_empty_or_non_object():
    with pytest.raises(ValueError, match="empty"):
        parse_json_object("")
    with pytest.raises(ValueError, match="not a JSON object"):
        parse_json_object("[1, 2, 3]")


def test_annotation_from_payload_builds_silver_record():
    task = make_task("1")
    annotation, issues = annotation_from_payload(
        task, payload("1"), model="qwen3", provider="llama.cpp"
    )

    assert issues == []
    assert annotation.tier == "silver"
    assert annotation.annotator == "llm/qwen3"
    assert annotation.frame_labels == ["conspiracy"]
    assert annotation.toxicity == 2
    notes = json.loads(annotation.notes)
    assert notes["evidence_valid"] is True
    assert notes["prompt_sha256"] == "prompt-hash"


def test_annotation_from_payload_records_non_verbatim_evidence():
    task = make_task("1")
    annotation, issues = annotation_from_payload(
        task,
        payload("1", evidence=["not in the post"]),
        model="qwen3",
        provider="llama.cpp",
    )

    assert "not verbatim" in issues[0]
    assert json.loads(annotation.notes)["evidence_valid"] is False


def test_annotation_from_payload_rejects_bad_labels_and_toxicity():
    task = make_task("1")
    with pytest.raises(ValueError, match="Unknown frame"):
        annotation_from_payload(
            task, payload("1", frame_labels=["not_a_frame"]), model="m", provider="p"
        )
    with pytest.raises(ValueError, match="non-empty"):
        annotation_from_payload(
            task, payload("1", frame_labels=[]), model="m", provider="p"
        )
    with pytest.raises(ValueError, match="integer 0-3"):
        annotation_from_payload(
            task, payload("1", toxicity=True), model="m", provider="p"
        )
    with pytest.raises(ValueError, match="out of range"):
        annotation_from_payload(
            task, payload("1", toxicity=4), model="m", provider="p"
        )


def test_annotation_from_payload_flags_post_id_mismatch():
    task = make_task("1")
    annotation, issues = annotation_from_payload(
        task, payload("2"), model="m", provider="p"
    )

    assert annotation.post_id == "1"
    assert "post_id mismatch" in issues[0]


def test_convert_raw_rows_reports_errors_and_keeps_good_rows():
    tasks = [make_task("1"), make_task("2")]
    rows = [
        {"task_id": tasks[0].task_id, "payload": payload("1")},
        {
            "task_id": tasks[1].task_id,
            "payload": None,
            "raw_text": "not json",
        },
    ]

    annotations, report = convert_raw_rows(rows, tasks, model="m", provider="p")

    assert len(annotations) == 1
    assert report["raw_rows"] == 2
    assert report["annotations"] == 1
    assert report["errors"] == 1
    assert report["frames"]["conspiracy"] == 1


def test_batch_shard_resume_and_retry(tmp_path):
    tasks = [make_task(str(index)) for index in range(1, 5)]
    out = tmp_path / "raw.jsonl"
    backend = FakeBackend(
        [
            "not json",
            json.dumps(payload("1")),
            json.dumps(payload("3")),
        ]
    )

    first = run_batch(tasks, backend, out, shard=(1, 2), retries=1, log_every=0)
    assert first["selected"] == 2
    assert first["ok"] == 2
    assert first["failed"] == 0

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [row["post_id"] for row in rows] == ["1", "3"]
    assert rows[0]["attempts"] == 2

    backend2 = FakeBackend([json.dumps(payload("2")), json.dumps(payload("4"))])
    second = run_batch(tasks, backend2, out, shard=(2, 2), log_every=0)
    assert second["skipped"] == 0
    assert second["ok"] == 2

    backend3 = FakeBackend([])
    third = run_batch(tasks, backend3, out, log_every=0)
    assert third["skipped"] == 4
    assert third["ok"] == 0


def test_batch_records_backend_failure(tmp_path):
    tasks = [make_task("1")]
    out = tmp_path / "raw.jsonl"
    backend = FakeBackend(["always broken"])

    report = run_batch(tasks, backend, out, retries=0, log_every=0)

    assert report["failed"] == 1
    row = json.loads(out.read_text().splitlines()[0])
    assert row["payload"] is None
    assert "JSONDecodeError" in row["error"]


def test_dataset_joins_text_and_one_hot():
    tasks = [make_task("1")]
    annotations, _ = convert_raw_rows(
        [{"task_id": tasks[0].task_id, "payload": payload("1")}],
        tasks,
        model="m",
        provider="p",
    )

    rows, report = build_modeling_rows(
        annotations,
        [make_sample("1")],
        split_assignment={"t-1": "train"},
    )

    assert report["rows"] == 1
    row = rows[0]
    assert row["split"] == "train"
    assert row["frame__conspiracy"] == 1
    assert row["head__conspiracy"] == 1
    assert row["toxicity_binary"] == 1
    assert row["text_raw"] == "a secret plot by elites"
    assert frame_one_hot(["none"])["frame__conspiracy"] == 0


def test_dataset_reports_missing_samples():
    tasks = [make_task("1")]
    annotations, _ = convert_raw_rows(
        [{"task_id": tasks[0].task_id, "payload": payload("1")}],
        tasks,
        model="m",
        provider="p",
    )

    rows, report = build_modeling_rows(annotations, [])

    assert rows == []
    assert report["missing_samples"] == 1


def test_dataset_dedupes_identical_content_across_threads():
    tasks = [make_task("1", text="bump"), make_task("2", text="bump")]
    annotations, _ = convert_raw_rows(
        [
            {"task_id": tasks[0].task_id, "payload": payload("1")},
            {"task_id": tasks[1].task_id, "payload": payload("2")},
        ],
        tasks,
        model="m",
        provider="p",
    )
    samples = [
        make_sample("1", text="bump", content_hash="hash-bump"),
        make_sample("2", text="bump", content_hash="hash-bump"),
    ]

    rows, report = build_modeling_rows(
        annotations,
        samples,
        split_assignment={"t-1": "train", "t-2": "test"},
    )

    assert report["rows_before_dedupe"] == 2
    assert report["duplicate_groups"] == 1
    assert report["duplicate_rows_removed"] == 1
    assert report["duplicate_post_ids"] == ["2"]
    assert report["rows"] == 1
    assert rows[0]["post_id"] == "1"


def test_dataset_keeps_duplicates_when_disabled():
    tasks = [make_task("1", text="bump"), make_task("2", text="bump")]
    annotations, _ = convert_raw_rows(
        [
            {"task_id": tasks[0].task_id, "payload": payload("1")},
            {"task_id": tasks[1].task_id, "payload": payload("2")},
        ],
        tasks,
        model="m",
        provider="p",
    )
    samples = [
        make_sample("1", text="bump", content_hash="hash-bump"),
        make_sample("2", text="bump", content_hash="hash-bump"),
    ]

    rows, report = build_modeling_rows(
        annotations,
        samples,
        dedupe_content=False,
    )

    assert len(rows) == 2
    assert report["duplicate_rows_removed"] == 0


def test_output_schema_requires_core_fields():
    schema = output_json_schema()

    assert schema["required"] == ["post_id", "frame_labels", "toxicity"]
    assert "none" in schema["properties"]["frame_labels"]["items"]["enum"]
    assert schema["properties"]["toxicity"]["enum"] == [0, 1, 2, 3]
