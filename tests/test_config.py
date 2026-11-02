from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from keklab.common.config import (
    KeklabConfig,
    default_config,
    dump_config,
    load_config,
    resolve_config_path,
)
from keklab.common.paths import PROJECT_ROOT


def test_default_config_is_valid():
    config = default_config()

    assert isinstance(config, KeklabConfig)
    assert config.ingest.source == "kek"
    assert config.ingest.batch_size > 0
    assert config.formal.max_text_chars > 0


def test_load_default_file_resolves_paths():
    assert resolve_config_path() == PROJECT_ROOT / "configs" / "default.yaml"

    config = load_config()

    assert config.paths.raw_dir == PROJECT_ROOT / "data" / "raw"
    assert config.paths.registry_path == PROJECT_ROOT / "data" / "registry.jsonl"
    assert (
        config.ingest.fourplebs.cache_dir
        == PROJECT_ROOT / "data" / "cache" / "fourplebs"
    )


def test_load_yaml_expands_env_and_deep_merges_overrides(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    monkeypatch.setenv("KEKLAB_TEST_RAW", str(raw_dir))

    path = tmp_path / "config.yaml"
    path.write_text(
        """
name: test-run
seed: 7
paths:
  raw_dir: ${KEKLAB_TEST_RAW}
ingest:
  source: fourplebs
  batch_size: 10
""",
        encoding="utf-8",
    )

    config = load_config(path, overrides={"ingest": {"chunk_size": 5}})

    assert config.name == "test-run"
    assert config.seed == 7
    assert config.ingest.source == "fourplebs"
    assert config.ingest.batch_size == 10
    assert config.ingest.chunk_size == 5
    assert config.paths.raw_dir == raw_dir


def test_load_json_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"name": "json-run", "logging": {"level": "debug"}}))

    config = load_config(path)

    assert config.name == "json-run"
    assert config.logging.level == "DEBUG"


def test_load_rejects_unknown_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("ingest:\n  unknown_option: 1\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)


def test_load_rejects_invalid_values(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("ingest:\n  batch_size: 0\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist.yaml")


def test_dump_config_roundtrip(tmp_path):
    config = load_config(overrides={"name": "roundtrip"})
    out = dump_config(config, tmp_path / "dumped.json")

    assert out.exists()
    reloaded = load_config(out)
    assert reloaded.name == "roundtrip"
    assert reloaded.model_dump(mode="json") == config.model_dump(mode="json")
