# Role: CLI for silver annotation, local LLM batches and modeling dataset export.
# Connects to: classification/backends, batch, silver, dataset, manifest,
#             annotation/store, annotation/splits.

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from keklab.annotation.store import (
    load_annotations,
    load_samples,
    load_tasks,
    write_annotations,
)
from keklab.annotation.splits import read_split_manifest
from keklab.classification.backends import FakeBackend, LlamaCppBackend
from keklab.classification.batch import load_raw_rows, run_batch
from keklab.classification.dataset import export_dataset
from keklab.classification.grammar import output_json_schema
from keklab.classification.manifest import (
    git_commit,
    sha256_file,
    write_manifest,
)
from keklab.classification.silver import convert_raw_rows
from keklab.common.logging import get_logger
from keklab.common.paths import DEFAULT_LLM_MODEL

log = get_logger(__name__)


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _parse_shard(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(value))
    if not match:
        raise ValueError("--shard must look like INDEX/TOTAL, e.g. 1/4")
    return int(match.group(1)), int(match.group(2))


def _fake_backend() -> FakeBackend:
    """Deterministic backend for plumbing smoke tests, not for real labels."""

    def respond(prompt: str) -> str:
        match = re.search(r'"post_id":\s*"([^"]+)"', prompt)
        post_id = match.group(1) if match else "unknown"
        return json.dumps(
            {
                "post_id": post_id,
                "frame_labels": ["none"],
                "toxicity": 0,
                "confidence": 0.5,
                "rationale": "fake backend",
                "evidence": [],
            }
        )

    return FakeBackend(respond, name="fake")


def _cmd_classify_llm(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    if not tasks:
        raise ValueError(f"no tasks found in {args.tasks}")

    if args.backend == "fake":
        backend: Any = _fake_backend()
    else:
        backend = LlamaCppBackend(
            args.model,
            n_ctx=args.n_ctx,
            n_batch=args.n_batch,
            n_gpu_layers=args.n_gpu_layers,
            temperature=args.temperature,
            seed=args.seed,
            max_tokens=args.max_tokens,
            disable_thinking=not args.allow_thinking,
            verbose=args.verbose,
        )

    report = run_batch(
        tasks,
        backend,
        args.out,
        shard=_parse_shard(args.shard),
        limit=args.limit,
        resume=not args.no_resume,
        retry_failed=args.retry_failed,
        retries=args.retries,
        schema=output_json_schema(),
    )

    manifest: dict[str, Any] = {
        "kind": "llm_batch",
        "tasks": str(args.tasks),
        "output": str(args.out),
        "backend": args.backend,
        "model": report["model"],
        "provider": report["provider"],
        "git_commit": git_commit(),
        "shard": list(_parse_shard(args.shard)),
        "limit": args.limit,
        "resume": not args.no_resume,
        "retry_failed": args.retry_failed,
    }
    if args.backend == "llama_cpp":
        manifest.update(
            {
                "model_path": str(Path(args.model).expanduser()),
                "model_sha256": (
                    sha256_file(args.model)
                    if Path(args.model).expanduser().exists()
                    else None
                ),
                "n_ctx": args.n_ctx,
                "n_batch": args.n_batch,
                "n_gpu_layers": args.n_gpu_layers,
                "temperature": args.temperature,
                "seed": args.seed,
                "max_tokens": args.max_tokens,
                "disable_thinking": not args.allow_thinking,
            }
        )
        if hasattr(backend, "metadata"):
            manifest["backend_metadata"] = backend.metadata()
    report["manifest"] = None
    if args.manifest:
        write_manifest(args.manifest, manifest)
        report["manifest"] = str(args.manifest)

    if args.json:
        _print_json(report)
    else:
        for key in ("selected", "ok", "failed", "skipped", "elapsed_s", "output"):
            print(f"{key}: {report[key]}")
        if report["manifest"]:
            print(f"manifest: {report['manifest']}")
    return 0 if report["failed"] == 0 else 1


def _cmd_classify_silver(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    if not tasks:
        raise ValueError(f"no tasks found in {args.tasks}")
    annotations, report = convert_raw_rows(
        load_raw_rows(args.raw),
        tasks,
        model=args.model,
        provider=args.provider,
    )
    if not annotations:
        raise ValueError("no annotations could be built from the raw output")

    write_annotations(annotations, args.out)
    report.update(
        {
            "tasks": str(args.tasks),
            "raw": str(args.raw),
            "output": str(args.out),
            "model": args.model,
            "provider": args.provider,
        }
    )
    if args.manifest:
        write_manifest(
            args.manifest,
            {
                "kind": "silver_annotations",
                "tasks": str(args.tasks),
                "raw": str(args.raw),
                "output": str(args.out),
                "model": args.model,
                "provider": args.provider,
                "git_commit": git_commit(),
                "report": report,
            },
        )
        report["manifest"] = str(args.manifest)
    if args.json:
        _print_json(report)
    else:
        for key in (
            "raw_rows",
            "annotations",
            "errors",
            "warnings",
            "missing_tasks",
            "output",
        ):
            print(f"{key}: {report[key]}")
        print("toxicity: " + json.dumps(report["toxicity"], sort_keys=True))
        if report.get("manifest"):
            print(f"manifest: {report['manifest']}")
    return 0 if report["errors"] == 0 else 1


def _cmd_classify_dataset(args: argparse.Namespace) -> int:
    annotations = load_annotations(args.silver)
    samples = load_samples(args.samples)
    assignment = read_split_manifest(args.splits) if args.splits else None
    report = export_dataset(
        annotations,
        samples,
        args.out,
        split_assignment=assignment,
    )
    if args.json:
        _print_json(report)
    else:
        for key in (
            "rows",
            "missing_samples",
            "missing_toxicity",
            "frames",
            "coarse_heads",
            "output",
        ):
            print(f"{key}: {report[key]}")
        print("splits: " + json.dumps(report["splits"], sort_keys=True))
    return 0


def _cmd_classify_store(args: argparse.Namespace) -> int:
    """Store L1 predictions as partitioned Parquet for the analytics layer."""
    import json as _json

    from keklab.classification.predictions import write_predictions

    def rows() -> Any:
        with open(args.input, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield _json.loads(line)
                except _json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON in {args.input}: {exc}") from exc

    manifest = write_predictions(
        rows(),
        args.out,
        model=args.model,
        run_id=args.run_id,
    )
    if args.json:
        print(_json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        print(f"rows: {manifest['rows']}")
        print(f"rows_skipped: {manifest['rows_skipped']}")
        print(f"months: {len(manifest['months'])}")
        print(f"out: {args.out}")
    return 0


def add_classify_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "classify", help="Silver annotation and modeling dataset"
    )
    classify_sub = parser.add_subparsers(dest="classify_command", required=True)

    p_llm = classify_sub.add_parser(
        "llm", help="Run the local LLM over blind tasks"
    )
    p_llm.add_argument("--tasks", required=True)
    p_llm.add_argument("--out", required=True, help="Raw JSONL output")
    p_llm.add_argument("--model", default=str(DEFAULT_LLM_MODEL))
    p_llm.add_argument(
        "--backend", choices=["llama_cpp", "fake"], default="llama_cpp"
    )
    p_llm.add_argument("--shard", default="1/1", help="INDEX/TOTAL")
    p_llm.add_argument("--limit", type=int)
    p_llm.add_argument("--n-ctx", type=int, default=2048)
    p_llm.add_argument("--n-batch", type=int, default=256)
    p_llm.add_argument("--n-gpu-layers", type=int, default=0)
    p_llm.add_argument("--temperature", type=float, default=0.0)
    p_llm.add_argument("--seed", type=int, default=13)
    p_llm.add_argument("--max-tokens", type=int, default=512)
    p_llm.add_argument("--allow-thinking", action="store_true")
    p_llm.add_argument("--no-resume", action="store_true")
    p_llm.add_argument(
        "--no-retry-failed",
        dest="retry_failed",
        action="store_false",
        help="Do not retry rows that previously failed",
    )
    p_llm.set_defaults(retry_failed=True)
    p_llm.add_argument("--retries", type=int, default=1)
    p_llm.add_argument("--manifest")
    p_llm.add_argument("--verbose", action="store_true")
    p_llm.add_argument("--json", action="store_true")
    p_llm.set_defaults(func=_cmd_classify_llm)

    p_silver = classify_sub.add_parser(
        "silver", help="Convert raw LLM output into silver annotations"
    )
    p_silver.add_argument("--tasks", required=True)
    p_silver.add_argument("--raw", required=True)
    p_silver.add_argument("--out", required=True)
    p_silver.add_argument("--model", default="qwen3-8b-q4_k_m")
    p_silver.add_argument("--provider", default="llama.cpp")
    p_silver.add_argument("--manifest")
    p_silver.add_argument("--json", action="store_true")
    p_silver.set_defaults(func=_cmd_classify_silver)

    p_dataset = classify_sub.add_parser(
        "dataset", help="Join silver labels with text and splits"
    )
    p_dataset.add_argument("--silver", required=True)
    p_dataset.add_argument("--samples", required=True)
    p_dataset.add_argument("--splits")
    p_dataset.add_argument("--out", required=True)
    p_dataset.add_argument("--json", action="store_true")
    p_dataset.set_defaults(func=_cmd_classify_dataset)

    p_store = classify_sub.add_parser(
        "store", help="Store L1 predictions as partitioned Parquet"
    )
    p_store.add_argument("--input", required=True, help="JSONL of predictions")
    p_store.add_argument("--out", required=True, help="Output directory")
    p_store.add_argument("--model", default="")
    p_store.add_argument("--run-id", default="")
    p_store.add_argument("--json", action="store_true")
    p_store.set_defaults(func=_cmd_classify_store)

    return parser


__all__ = ["add_classify_parser"]
