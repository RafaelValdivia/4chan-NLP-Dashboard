"""`keklab training` command group."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from keklab.training import queue


def _cmd_init(args: argparse.Namespace) -> int:
    print(queue.ensure_queue(Path(args.queue_dir)))
    return 0


def _cmd_enqueue(args: argparse.Namespace) -> int:
    for job_id in queue.enqueue_default(queue_dir=Path(args.queue_dir)):
        print(job_id)
    return 0


def _cmd_launch(args: argparse.Namespace) -> int:
    print(json.dumps(queue.launch(queue_dir=Path(args.queue_dir)), indent=2))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    value = queue.status(Path(args.queue_dir))
    if args.json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(value["counts"], sort_keys=True))
    for job in value["latest"]:
        print(f"{job['id']}  {job['state']:<8} {job.get('name', '')}  {job.get('log', '')}")
    return 0


def _cmd_worker(args: argparse.Namespace) -> int:
    return queue.worker(once=args.once, poll_s=args.poll, queue_dir=Path(args.queue_dir))


def _cmd_submit(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    for item in args.param or []:
        key, separator, value = item.partition("=")
        if not separator:
            raise ValueError(f"expected KEY=VALUE, got {item!r}")
        params[key] = value
    print(
        queue.submit_job(
            args.type,
            params=params,
            depends_on=args.dep or [],
            name=args.name,
            max_retries=args.retries,
            timeout_s=args.timeout,
            queue_dir=Path(args.queue_dir),
        )
    )
    return 0


def add_training_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("training", help="Crash-safe training/evaluation queue")
    training_sub = parser.add_subparsers(dest="training_command", required=True)

    for name, handler, help_text in (
        ("init", _cmd_init, "Create the queue directories"),
        ("enqueue-default", _cmd_enqueue, "Enqueue the full Laya/GLiNER/baseline pipeline"),
        ("launch", _cmd_launch, "Launch a detached worker"),
        ("status", _cmd_status, "Show queue state"),
        ("worker", _cmd_worker, "Run the worker in the foreground"),
    ):
        child = training_sub.add_parser(name, help=help_text)
        child.add_argument("--queue-dir", default=str(queue.QUEUE_DIR))
        child.set_defaults(func=handler)
        if name == "status":
            child.add_argument("--json", action="store_true")
        if name == "worker":
            child.add_argument("--once", action="store_true")
            child.add_argument("--poll", type=float, default=10.0)

    child = training_sub.add_parser("submit", help="Submit one job")
    child.add_argument("type")
    child.add_argument("--queue-dir", default=str(queue.QUEUE_DIR))
    child.add_argument("--param", action="append", metavar="KEY=VALUE")
    child.add_argument("--dep", action="append", metavar="JOB_ID")
    child.add_argument("--name")
    child.add_argument("--timeout", type=int, default=86400)
    child.add_argument("--retries", type=int, default=1)
    child.set_defaults(func=_cmd_submit)


__all__ = ["add_training_parser"]
