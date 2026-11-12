from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from keklab.annotation.proposal import TaskRecord
from keklab.annotation.schema import SamplePost
from keklab.classification.batch import run_batch
from keklab.classification.errors import SystemicError, TransportError

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def make_task(post_id: str = "1") -> TaskRecord:
    text = "a secret plot by elites"
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


def payload(post_id: str = "1") -> dict[str, Any]:
    return {
        "post_id": post_id,
        "frame_labels": ["conspiracy"],
        "toxicity": 2,
        "confidence": 0.8,
        "rationale": "The post claims a secret plot.",
        "evidence": ["secret plot"],
    }


class ScriptedBackend:
    """Backend that replays responses and exceptions in order."""

    name = "scripted"
    provider = "test"

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, schema: Any = None) -> str:
        self.prompts.append(prompt)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return str(item)


def test_batch_aborts_on_systemic_error_without_repair(tmp_path):
    tasks = [make_task(str(index)) for index in range(1, 4)]
    backend = ScriptedBackend([SystemicError("Context size has been exceeded")])
    out = tmp_path / "raw.jsonl"

    report = run_batch(tasks, backend, out, retries=3, log_every=0)

    assert report["aborted"] is True
    assert "systemic" in report["abort_reason"]
    assert report["failed"] == 1
    assert report["ok"] == 0
    assert report["error_kinds"] == {"systemic": 1}
    assert len(backend.prompts) == 1

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["error_kind"] == "systemic"
    assert rows[0]["attempts"] == 1


def test_batch_breaks_circuit_after_consecutive_transport_errors(tmp_path):
    tasks = [make_task(str(index)) for index in range(1, 6)]
    backend = ScriptedBackend([TransportError("llama-server unreachable")] * 5)
    out = tmp_path / "raw.jsonl"

    report = run_batch(
        tasks,
        backend,
        out,
        retries=0,
        log_every=0,
        max_consecutive_transport_errors=2,
        transport_backoff_s=0.0,
    )

    assert report["aborted"] is True
    assert "2 consecutive transport" in report["abort_reason"]
    assert report["failed"] == 2
    assert len(backend.prompts) == 2
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [row["error_kind"] for row in rows] == ["transport", "transport"]


def test_batch_transport_counter_resets_after_success(tmp_path):
    tasks = [make_task(str(index)) for index in range(1, 5)]
    backend = ScriptedBackend(
        [
            TransportError("llama-server unreachable"),
            json.dumps(payload("2")),
            TransportError("llama-server unreachable"),
            json.dumps(payload("4")),
        ]
    )
    out = tmp_path / "raw.jsonl"

    report = run_batch(
        tasks,
        backend,
        out,
        retries=0,
        log_every=0,
        max_consecutive_transport_errors=2,
        transport_backoff_s=0.0,
    )

    assert report["aborted"] is False
    assert report["ok"] == 2
    assert report["failed"] == 2
    assert report["error_kinds"] == {"transport": 2}


def test_batch_retries_transport_with_original_prompt(tmp_path):
    task = make_task("1")
    backend = ScriptedBackend(
        [
            TransportError("llama-server unreachable"),
            json.dumps(payload("1")),
        ]
    )
    out = tmp_path / "raw.jsonl"

    report = run_batch(
        [task],
        backend,
        out,
        retries=1,
        log_every=0,
        transport_backoff_s=0.0,
    )

    assert report["ok"] == 1
    assert report["repaired"] == 0
    assert len(backend.prompts) == 2
    assert backend.prompts[0] == backend.prompts[1]


def test_batch_circuit_breaker_can_be_disabled(tmp_path):
    tasks = [make_task(str(index)) for index in range(1, 4)]
    backend = ScriptedBackend([TransportError("llama-server unreachable")] * 3)
    out = tmp_path / "raw.jsonl"

    report = run_batch(
        tasks,
        backend,
        out,
        retries=0,
        log_every=0,
        max_consecutive_transport_errors=0,
        transport_backoff_s=0.0,
    )

    assert report["aborted"] is False
    assert report["failed"] == 3


def test_batch_classifies_contract_failures(tmp_path):
    tasks = [make_task("1")]
    backend = ScriptedBackend(["not json", "not json"])
    out = tmp_path / "raw.jsonl"

    report = run_batch(tasks, backend, out, retries=1, log_every=0)

    assert report["aborted"] is False
    assert report["failed"] == 1
    assert report["error_kinds"] == {"contract": 1}
    row = json.loads(out.read_text().splitlines()[0])
    assert row["error_kind"] == "contract"
    assert row["attempts"] == 2
