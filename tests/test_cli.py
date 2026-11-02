from __future__ import annotations

import json

import duckdb
import pytest

from keklab.common.cli import main

THREAD = {
    "no": 1,
    "posts": [
        {"no": 1, "time": 1500000000, "com": "OP with >>2"},
        {"no": 2, "resto": 1, "time": 1500000100, "com": "reply"},
    ],
}


@pytest.fixture()
def ndjson_file(tmp_path):
    path = tmp_path / "threads.ndjson"
    path.write_text(json.dumps(THREAD) + "\n", encoding="utf-8")
    return path


def test_version(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_config_show_json(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("name: cli-test\nseed: 9\n", encoding="utf-8")

    assert main(["--config", str(path), "config", "show", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "cli-test"
    assert payload["seed"] == 9


def test_config_validate(capsys):
    assert main(["config", "validate"]) == 0
    assert "OK:" in capsys.readouterr().out


def test_ingest_pipeline_and_stats(ndjson_file, tmp_path, capsys):
    expanded = tmp_path / "expanded.parquet"
    canonical = tmp_path / "canonical.parquet"

    assert main(["ingest", "expand", str(ndjson_file), str(expanded)]) == 0
    assert expanded.exists()

    assert (
        main(
            [
                "ingest",
                "canonicalize",
                str(expanded),
                str(canonical),
                "--chunk-size",
                "10",
            ]
        )
        == 0
    )
    assert canonical.exists()

    capsys.readouterr()
    assert main(["ingest", "stats", str(canonical), "--json"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["posts"] == 2
    assert stats["threads"] == 1
    assert stats["op_posts"] == 1


def test_dedupe(ndjson_file, tmp_path):
    expanded = tmp_path / "expanded.parquet"
    canonical = tmp_path / "canonical.parquet"
    deduped = tmp_path / "deduped.parquet"

    assert main(["ingest", "expand", str(ndjson_file), str(expanded)]) == 0
    assert main(["ingest", "canonicalize", str(expanded), str(canonical)]) == 0
    assert main(["dedupe", str(canonical), str(deduped)]) == 0

    rows = duckdb.sql(f"SELECT count(*) FROM read_parquet('{deduped}')").fetchall()[0][0]
    assert rows == 2


def test_registry_add_list_show(tmp_path, capsys):
    registry = tmp_path / "registry.jsonl"
    artifact = tmp_path / "posts.parquet"
    artifact.write_bytes(b"data")

    assert (
        main(
            [
                "registry",
                "add",
                "dataset",
                "demo",
                "--path",
                str(artifact),
                "--param",
                "threads=1",
                "--metric",
                "f1=0.5",
                "--registry-file",
                str(registry),
            ]
        )
        == 0
    )
    artifact_id = capsys.readouterr().out.strip()

    assert main(["registry", "list", "--json", "--registry-file", str(registry)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1
    assert listed[0]["id"] == artifact_id

    assert (
        main(["registry", "show", artifact_id, "--json", "--registry-file", str(registry)])
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["name"] == "demo"
    assert shown["params"] == {"threads": "1"}
    assert shown["metrics"] == {"f1": 0.5}


def test_registry_show_missing_returns_error(tmp_path):
    assert (
        main(
            [
                "registry",
                "show",
                "dataset-missing",
                "--registry-file",
                str(tmp_path / "registry.jsonl"),
            ]
        )
        == 1
    )
