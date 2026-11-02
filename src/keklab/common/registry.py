# Role: append-only registry for datasets, models, runs and reports.
# Connects to: common/paths, ingest, classic, generative, eval, dashboard.
#
# The registry is a JSONL file (default: data/registry.jsonl). Each line is a
# validated `ArtifactRecord`; appending is cheap and safe for sequential runs.
# Set KEKLAB_REGISTRY_PATH to override the location.

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from keklab.common.logging import get_logger
from keklab.common.paths import DATA_DIR

log = get_logger(__name__)

ArtifactKind = Literal["dataset", "model", "run", "report", "config"]
VALID_KINDS: tuple[str, ...] = ("dataset", "model", "run", "report", "config")


class ArtifactRecord(BaseModel):
    """Metadata for a registered artifact."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ArtifactKind
    name: str
    path: str | None = None
    source: str | None = None
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sha256: str | None = None
    size_bytes: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


def registry_path(path: str | Path | None = None) -> Path:
    """Resolve the registry location (argument > KEKLAB_REGISTRY_PATH > data/)."""
    if path is not None:
        return Path(path).expanduser()
    return Path(os.environ.get("KEKLAB_REGISTRY_PATH", DATA_DIR / "registry.jsonl"))


def _sha256(path: Path, *, chunk_size: int = 1 << 20) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def register_artifact(
    kind: ArtifactKind,
    name: str,
    path: str | Path | None = None,
    *,
    source: str | None = None,
    params: dict[str, Any] | None = None,
    metrics: dict[str, float] | None = None,
    notes: str | None = None,
    artifact_id: str | None = None,
    registry_file: str | Path | None = None,
    hash_file: bool = True,
) -> ArtifactRecord:
    """
    Append an artifact to the registry.

    If `path` points to an existing file, its SHA256 and size are recorded.
    Missing paths are allowed (e.g. an output that will be produced later).
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"Invalid artifact kind {kind!r}; expected one of {VALID_KINDS}")

    artifact_path: Path | None = None
    sha256: str | None = None
    size_bytes: int | None = None

    if path is not None:
        artifact_path = Path(path).expanduser().resolve()
        if artifact_path.exists() and artifact_path.is_file():
            if hash_file:
                sha256, size_bytes = _sha256(artifact_path)
            else:
                size_bytes = artifact_path.stat().st_size
        else:
            log.debug("Registered path does not exist yet: %s", artifact_path)

    record = ArtifactRecord(
        id=artifact_id or f"{kind}-{uuid.uuid4().hex[:12]}",
        kind=kind,
        name=name,
        path=str(artifact_path) if artifact_path is not None else None,
        source=source,
        sha256=sha256,
        size_bytes=size_bytes,
        params=params or {},
        metrics=metrics or {},
        notes=notes,
    )

    destination = registry_path(registry_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as fh:
        fh.write(record.model_dump_json() + "\n")

    log.info("Registered %s %s (%s)", kind, name, record.id)
    return record


def load_registry(registry_file: str | Path | None = None) -> list[ArtifactRecord]:
    """Read all registry records, skipping malformed lines with a warning."""
    source = registry_path(registry_file)
    if not source.exists():
        return []

    records: list[ArtifactRecord] = []
    with source.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(ArtifactRecord.model_validate_json(line))
            except Exception as exc:
                log.warning("Skipping malformed registry line %s:%d (%s)", source, lineno, exc)
    return records


def list_artifacts(
    *,
    kind: ArtifactKind | None = None,
    name: str | None = None,
    registry_file: str | Path | None = None,
) -> list[ArtifactRecord]:
    """List records, optionally filtered by kind/name (newest last)."""
    records = load_registry(registry_file)
    if kind is not None:
        records = [record for record in records if record.kind == kind]
    if name is not None:
        records = [record for record in records if record.name == name]
    return records


def get_artifact(
    artifact_id: str,
    *,
    registry_file: str | Path | None = None,
) -> ArtifactRecord | None:
    """Return the record with `artifact_id`, or None."""
    for record in load_registry(registry_file):
        if record.id == artifact_id:
            return record
    return None


def latest_artifact(
    kind: ArtifactKind,
    name: str | None = None,
    *,
    registry_file: str | Path | None = None,
) -> ArtifactRecord | None:
    """Return the most recently registered artifact for a kind/name."""
    matches = list_artifacts(kind=kind, name=name, registry_file=registry_file)
    return matches[-1] if matches else None
