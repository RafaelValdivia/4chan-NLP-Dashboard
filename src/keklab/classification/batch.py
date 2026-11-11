# Role: batched, resumable local-LLM generation over blind annotation tasks.
# Connects to: annotation/prompts, annotation/proposal, classification/backends,
#             classification/silver.

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.prompts import render_prompt
from keklab.annotation.proposal import TaskRecord
from keklab.classification.silver import parse_json_object
from keklab.common.logging import get_logger

log = get_logger(__name__)


def load_raw_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path).expanduser()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _shard_slice(tasks: list[TaskRecord], shard: tuple[int, int]) -> list[TaskRecord]:
    index, total = shard
    if total < 1:
        raise ValueError("shard total must be >= 1")
    if not 1 <= index <= total:
        raise ValueError("shard index must be between 1 and total")
    if total == 1:
        return tasks
    return [task for position, task in enumerate(tasks) if position % total == index - 1]


def run_batch(
    tasks: Iterable[TaskRecord],
    backend: Any,
    out_path: str | Path,
    *,
    shard: tuple[int, int] = (1, 1),
    limit: int | None = None,
    resume: bool = True,
    retry_failed: bool = True,
    retries: int = 1,
    schema: dict[str, Any] | None = None,
    log_every: int = 50,
) -> dict[str, Any]:
    """Run one backend over tasks, appending raw rows for later conversion.

    Rows with a parsed `payload` are considered complete on resume. Failed
    rows are retried unless `retry_failed=False`. The raw file is append-only
    so a crash never loses completed work.
    """
    all_tasks = list(tasks)
    selected = _shard_slice(all_tasks, shard)
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        selected = selected[:limit]

    out = Path(out_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    existing = load_raw_rows(out) if resume else []
    completed_ok = {
        str(row.get("task_id"))
        for row in existing
        if isinstance(row.get("payload"), dict)
    }
    completed_any = {str(row.get("task_id")) for row in existing}
    skip_completed = completed_ok if retry_failed else completed_any

    if not resume and out.exists():
        out.unlink()

    model = str(getattr(backend, "name", "unknown"))
    provider = str(getattr(backend, "provider", "unknown"))

    ok = 0
    failed = 0
    skipped = 0
    started = time.monotonic()

    with out.open("a", encoding="utf-8") as handle:
        for position, task in enumerate(selected, start=1):
            if task.task_id in skip_completed:
                skipped += 1
                continue

            prompt = render_prompt(task)
            attempts = 0
            raw_text = ""
            payload: dict[str, Any] | None = None
            error: str | None = None
            attempt_started = time.monotonic()

            for attempt in range(retries + 1):
                attempts = attempt + 1
                try:
                    raw_text = backend.generate(prompt, schema=schema)
                    payload = parse_json_object(raw_text)
                    error = None
                    break
                except Exception as exc:  # noqa: BLE001 - record and retry
                    error = f"{type(exc).__name__}: {exc}"

            latency = time.monotonic() - attempt_started
            row = {
                "task_id": task.task_id,
                "post_id": task.post_id,
                "attempts": attempts,
                "raw_text": raw_text,
                "payload": payload,
                "error": error,
                "model": model,
                "provider": provider,
                "prompt_version": task.prompt_version,
                "guideline_version": task.guideline_version,
                "prompt_sha256": task.prompt_sha256,
                "latency_s": round(latency, 6),
                "created_utc": datetime.now(timezone.utc).isoformat(),
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()

            if payload is None:
                failed += 1
            else:
                ok += 1

            if log_every and position % log_every == 0:
                log.info(
                    "LLM batch: %d/%d rows, ok=%d failed=%d skipped=%d, %.0f s",
                    position,
                    len(selected),
                    ok,
                    failed,
                    skipped,
                    time.monotonic() - started,
                )

    elapsed = time.monotonic() - started
    report = {
        "tasks": len(all_tasks),
        "selected": len(selected),
        "ok": ok,
        "failed": failed,
        "skipped": skipped,
        "new_rows": ok + failed,
        "shard": list(shard),
        "limit": limit,
        "model": model,
        "provider": provider,
        "resume": resume,
        "retry_failed": retry_failed,
        "elapsed_s": round(elapsed, 2),
        "output": str(out),
    }
    log.info("LLM batch finished: %s", report)
    return report
