# Role: batched, resumable local-LLM generation over blind annotation tasks.
# Connects to: annotation/prompts, annotation/proposal, classification/backends,
#             classification/silver.

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.prompts import render_prompt
from keklab.annotation.proposal import TaskRecord
from keklab.classification.errors import classify_exception
from keklab.classification.silver import parse_json_object
from keklab.classification.validate import repair_prompt, validate_payload
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
    validate: bool = True,
    log_every: int = 50,
    max_consecutive_transport_errors: int = 3,
    abort_on_systemic: bool = True,
    transport_backoff_s: float = 1.0,
) -> dict[str, Any]:
    """Run one backend over tasks, appending raw rows for later conversion.

    Rows with a parsed `payload` are considered complete on resume. Failed
    rows are retried unless `retry_failed=False`. The raw file is append-only
    so a crash never loses completed work.

    With `validate=True` each parsed payload is checked against the
    annotation contract. A payload that breaks the contract is treated as a
    failure and, while attempts remain, the model is asked once to repair it.

    Backend failures are classified instead of blindly repaired:

    - `transport` (server unreachable, 5xx): retried with the original
      prompt, then the shard aborts after
      `max_consecutive_transport_errors` such failures in a row;
    - `systemic` (context exhausted, OOM, model not loaded): never retried
      and the shard aborts immediately, because no prompt can fix it;
    - `contract` (invalid JSON or payload): repaired once with
      `repair_prompt`, then recorded as a normal failure.

    Aborting stops the loop after writing the offending row; the remaining
    tasks stay pending and are picked up by a later resume.
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
    repaired = 0
    consecutive_transport = 0
    aborted = False
    abort_reason: str | None = None
    error_kinds: Counter[str] = Counter()
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
            error_kind: str | None = None
            validation_issues: list[str] = []
            attempt_started = time.monotonic()
            current_prompt = prompt
            used_repair = False

            for attempt in range(retries + 1):
                attempts = attempt + 1
                try:
                    raw_text = backend.generate(current_prompt, schema=schema)
                except Exception as exc:  # noqa: BLE001 - record and classify
                    error = f"{type(exc).__name__}: {exc}"
                    error_kind = classify_exception(exc)
                    payload = None
                    if error_kind == "systemic":
                        # A longer prompt cannot fix an exhausted context.
                        break
                    if error_kind == "transport":
                        # Retry the original prompt, never a repair prompt.
                        if attempt < retries:
                            if transport_backoff_s > 0:
                                time.sleep(
                                    min(
                                        transport_backoff_s * (attempt + 1),
                                        10.0,
                                    )
                                )
                            continue
                        break
                    if attempt < retries:
                        current_prompt = repair_prompt(prompt, raw_text, [error])
                        used_repair = True
                    continue

                error_kind = "contract"
                payload = None
                parse_error: str | None = None
                try:
                    parsed = parse_json_object(raw_text)
                    issues = (
                        validate_payload(parsed, task) if validate else []
                    )
                except Exception as exc:  # noqa: BLE001 - malformed JSON
                    parse_error = f"{type(exc).__name__}: {exc}"
                    issues = [f"unparseable JSON: {exc}"]
                if issues:
                    validation_issues = issues
                    error = parse_error or (
                        "invalid payload: " + "; ".join(issues)
                    )
                    if attempt < retries:
                        current_prompt = repair_prompt(prompt, raw_text, issues)
                        used_repair = True
                        continue
                    break
                payload = parsed
                error = None
                error_kind = None
                validation_issues = []
                break

            if used_repair and payload is not None:
                repaired += 1

            latency = time.monotonic() - attempt_started
            row = {
                "task_id": task.task_id,
                "post_id": task.post_id,
                "attempts": attempts,
                "raw_text": raw_text,
                "payload": payload,
                "error": error,
                "error_kind": error_kind,
                "validation_issues": validation_issues,
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
                error_kinds[error_kind or "other"] += 1
            else:
                ok += 1

            if error_kind == "transport":
                consecutive_transport += 1
            else:
                consecutive_transport = 0

            systemic_abort = abort_on_systemic and error_kind == "systemic"
            transport_abort = (
                max_consecutive_transport_errors > 0
                and consecutive_transport >= max_consecutive_transport_errors
            )
            if systemic_abort or transport_abort:
                aborted = True
                abort_reason = (
                    f"systemic backend error: {error}"
                    if systemic_abort
                    else (
                        f"{consecutive_transport} consecutive transport "
                        "errors"
                    )
                )
                log.error(
                    "LLM batch aborted after task %s: %s",
                    task.task_id,
                    abort_reason,
                )
                break

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
        "repaired": repaired,
        "new_rows": ok + failed,
        "shard": list(shard),
        "limit": limit,
        "model": model,
        "provider": provider,
        "resume": resume,
        "retry_failed": retry_failed,
        "validate": validate,
        "aborted": aborted,
        "abort_reason": abort_reason,
        "error_kinds": dict(error_kinds),
        "max_consecutive_transport_errors": max_consecutive_transport_errors,
        "abort_on_systemic": abort_on_systemic,
        "elapsed_s": round(elapsed, 2),
        "output": str(out),
    }
    log.info("LLM batch finished: %s", report)
    return report
