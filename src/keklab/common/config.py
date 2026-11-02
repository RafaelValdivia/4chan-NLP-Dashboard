# Role: YAML configuration loading + Pydantic validation.
# Connects to: common/paths, common/cli, ingest, formal, classic, generative, eval.
#
# Precedence: explicit path > KEKLAB_CONFIG > configs/default.yaml > built-in
# defaults. Environment variables of the form ${VAR} / $VAR are expanded before
# validation; relative paths are resolved against the repository root.

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from keklab.common.paths import (
    CACHE_DIR,
    CONFIGS_DIR,
    DATA_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
    REPORTS_DIR,
)
from keklab.common.seeds import DEFAULT_SEED

_ENV_PATTERN = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
)


class _Section(BaseModel):
    """Base for config sections: reject unknown keys to catch typos early."""

    model_config = ConfigDict(extra="forbid")


class PathsConfig(_Section):
    raw_dir: Path = Field(default_factory=lambda: RAW_DIR)
    processed_dir: Path = Field(default_factory=lambda: PROCESSED_DIR)
    cache_dir: Path = Field(default_factory=lambda: CACHE_DIR)
    configs_dir: Path = Field(default_factory=lambda: CONFIGS_DIR)
    reports_dir: Path = Field(default_factory=lambda: REPORTS_DIR)
    registry_path: Path = Field(default_factory=lambda: DATA_DIR / "registry.jsonl")

    def resolved(self, root: str | Path = PROJECT_ROOT) -> PathsConfig:
        """Return a copy with relative paths anchored at `root`."""
        root = Path(root).expanduser()

        def _resolve(value: Path) -> Path:
            value = Path(value).expanduser()
            return value if value.is_absolute() else root / value

        return self.model_copy(
            update={
                name: _resolve(getattr(self, name))
                for name in type(self).model_fields
            }
        )


class FourplebsConfig(_Section):
    base_url: str = "https://a.4cdn.org/pol"
    cache_dir: Path | None = None
    sleep: float = Field(default=1.0, ge=0.0)
    timeout: float = Field(default=30.0, gt=0.0)


class SampleConfig(_Section):
    target_per_month: int = Field(default=50, gt=0)
    random_state: int = DEFAULT_SEED


class IngestConfig(_Section):
    source: Literal["kek", "fourplebs"] = "kek"
    batch_size: int = Field(default=50_000, gt=0)
    chunk_size: int = Field(default=50_000, gt=0)
    fourplebs: FourplebsConfig = Field(default_factory=FourplebsConfig)
    sample: SampleConfig = Field(default_factory=SampleConfig)


class FormalConfig(_Section):
    source: Literal["kek", "fourplebs"] = "kek"
    max_text_chars: int = Field(default=2000, gt=0)
    use_glc: bool = False


class LoggingConfig(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("level", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value


class KeklabConfig(_Section):
    """Validated configuration for a keklab run/experiment."""

    name: str = "keklab"
    seed: int = DEFAULT_SEED
    paths: PathsConfig = Field(default_factory=PathsConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    formal: FormalConfig = Field(default_factory=FormalConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def with_resolved_paths(self, root: str | Path = PROJECT_ROOT) -> KeklabConfig:
        root = Path(root).expanduser()
        paths = self.paths.resolved(root)

        cache_dir = self.ingest.fourplebs.cache_dir
        if cache_dir is not None:
            cache_dir = Path(cache_dir).expanduser()
            if not cache_dir.is_absolute():
                cache_dir = root / cache_dir
            fourplebs = self.ingest.fourplebs.model_copy(update={"cache_dir": cache_dir})
            ingest = self.ingest.model_copy(update={"fourplebs": fourplebs})
        else:
            ingest = self.ingest

        return self.model_copy(update={"paths": paths, "ingest": ingest})


def default_config() -> KeklabConfig:
    """Return the built-in configuration (no file is read)."""
    return KeklabConfig()


def _yaml_module():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError(
            "PyYAML is required to read/write YAML configs. "
            "Install it with `pip install PyYAML`."
        ) from exc
    return yaml


def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} / $VAR in strings; unknown vars are left as-is."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda match: os.environ.get(
                match.group(1) or match.group(2), match.group(0)
            ),
            value,
        )
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() in {".yaml", ".yml"}:
        data = _yaml_module().safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"Unsupported config format: {path.suffix} ({path})")

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping, got {type(data).__name__}")
    return data


def _default_config_path() -> Path | None:
    env_path = os.environ.get("KEKLAB_CONFIG")
    if env_path:
        return Path(env_path).expanduser()

    candidate = CONFIGS_DIR / "default.yaml"
    return candidate if candidate.exists() else None


def resolve_config_path(path: str | Path | None = None) -> Path | None:
    """Return the config path that `load_config` would use (None = built-ins)."""
    if path is not None:
        return Path(path).expanduser()
    return _default_config_path()


def load_config(
    path: str | Path | None = None,
    *,
    overrides: dict[str, Any] | None = None,
    resolve_paths: bool = True,
    root: str | Path = PROJECT_ROOT,
) -> KeklabConfig:
    """
    Load, expand and validate a keklab config.

    No `path` means: `KEKLAB_CONFIG`, then `configs/default.yaml`, then the
    built-in defaults. `overrides` are deep-merged on top of the file.
    """
    config_path = resolve_config_path(path)
    data: dict[str, Any] = _read_config_file(config_path) if config_path else {}

    if overrides:
        data = _deep_merge(data, overrides)

    config = KeklabConfig.model_validate(_expand_env(data))
    return config.with_resolved_paths(root) if resolve_paths else config


def dump_config(
    config: KeklabConfig,
    path: str | Path,
    *,
    root: str | Path = PROJECT_ROOT,
) -> Path:
    """Write a validated config as YAML/JSON (arguments resolved if relative)."""
    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path(root) / out
    out.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json")
    if out.suffix.lower() in {".yaml", ".yml"}:
        text = _yaml_module().safe_dump(data, sort_keys=False, allow_unicode=True)
    elif out.suffix.lower() == ".json":
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Unsupported config format: {out.suffix} ({out})")

    out.write_text(text, encoding="utf-8")
    return out
