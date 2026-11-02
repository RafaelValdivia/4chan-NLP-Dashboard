from __future__ import annotations

import hashlib
import json

from keklab.common.registry import (
    get_artifact,
    latest_artifact,
    list_artifacts,
    load_registry,
    register_artifact,
)


def test_register_hashes_existing_file(tmp_path):
    registry = tmp_path / "registry.jsonl"
    artifact = tmp_path / "posts.parquet"
    artifact.write_bytes(b"keklab")

    record = register_artifact(
        "dataset",
        "synthetic",
        artifact,
        source="fixture",
        params={"threads": 2},
        metrics={"f1": 0.5},
        registry_file=registry,
    )

    assert record.id.startswith("dataset-")
    assert record.path == str(artifact.resolve())
    assert record.sha256 == hashlib.sha256(b"keklab").hexdigest()
    assert record.size_bytes == 6
    assert record.params == {"threads": 2}
    assert record.metrics == {"f1": 0.5}


def test_register_allows_missing_output_path(tmp_path):
    registry = tmp_path / "registry.jsonl"

    record = register_artifact(
        "model", "future-model", tmp_path / "not-yet.pt", registry_file=registry
    )

    assert record.sha256 is None
    assert record.size_bytes is None
    assert record.path is not None


def test_load_and_filter_registry(tmp_path):
    registry = tmp_path / "registry.jsonl"
    first = register_artifact("dataset", "a", registry_file=registry)
    second = register_artifact("model", "b", registry_file=registry)

    records = load_registry(registry)
    assert [record.id for record in records] == [first.id, second.id]

    datasets = list_artifacts(kind="dataset", registry_file=registry)
    assert [record.id for record in datasets] == [first.id]

    assert list_artifacts(kind="report", registry_file=registry) == []
    assert latest_artifact("model", registry_file=registry).id == second.id


def test_get_artifact(tmp_path):
    registry = tmp_path / "registry.jsonl"
    record = register_artifact("run", "run-1", registry_file=registry)

    assert get_artifact(record.id, registry_file=registry).name == "run-1"
    assert get_artifact("run-missing", registry_file=registry) is None


def test_malformed_lines_are_skipped(tmp_path):
    registry = tmp_path / "registry.jsonl"
    registry.write_text('not-json\n{"broken": true}\n', encoding="utf-8")
    record = register_artifact("dataset", "ok", registry_file=registry)

    records = load_registry(registry)

    assert [item.id for item in records] == [record.id]


def test_registry_file_is_jsonl(tmp_path):
    registry = tmp_path / "registry.jsonl"
    register_artifact("dataset", "one", registry_file=registry)
    register_artifact("dataset", "two", registry_file=registry)

    lines = [line for line in registry.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "one"
