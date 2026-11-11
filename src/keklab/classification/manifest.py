# Role: reproducible manifests for local LLM runs and silver artifacts.
# Connects to: classification/batch, classification/cli, common/paths.

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from keklab.common.paths import PROJECT_ROOT


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path, *, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).expanduser().open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: str | Path = PROJECT_ROOT) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return (result.stdout or "").strip() or None


def chat_template_sha256(model: Any) -> str | None:
    """Hash the chat template embedded in a GGUF model, when available."""
    template = None
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is not None:
        template = getattr(tokenizer, "chat_template", None)
    if template is None:
        metadata = getattr(model, "metadata", None) or {}
        template = metadata.get("tokenizer.chat_template")
    if not template:
        return None
    return sha256_text(str(template))


def write_manifest(path: str | Path, data: dict[str, Any]) -> Path:
    """Write a JSON manifest atomically."""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload.setdefault("created_utc", datetime.now(timezone.utc).isoformat())

    fd, tmp_name = tempfile.mkstemp(
        dir=out.parent, prefix=f".{out.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
            handle.write("\n")
        os.replace(tmp, out)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return out


def load_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
