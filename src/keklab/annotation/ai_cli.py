# Role: CLI for AI-assisted annotation (task/import/review/stats/agreement).
# Connects to: annotation/ai, annotation/review, annotation/store, annotation/prompts.

from __future__ import annotations

import argparse
import json
from typing import Any

from keklab.annotation.ai import (
    build_tasks,
    import_proposals,
    proposal_agreement,
    proposal_stats,
)
from keklab.annotation.prompts import (
    GUIDELINE_VERSION,
    MODEL,
    PROMPT_VERSION,
    PROVIDER,
    prompt_manifest,
)
from keklab.annotation.review import run_review
from keklab.annotation.store import (
    load_annotations,
    load_proposals,
    load_reviews,
    load_samples,
    load_tasks,
    write_proposals,
    write_tasks,
)


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _cmd_ai_task(args: argparse.Namespace) -> int:
    samples = load_samples(args.input)
    gold = load_annotations(args.gold) if args.gold else []
    prompt = prompt_manifest()
    tasks, report = build_tasks(
        samples,
        gold=gold,
        guideline_version=args.guideline,
        prompt_version=PROMPT_VERSION,
        prompt_sha256=str(prompt["prompt_sha256"]),
        include_annotated=args.include_annotated,
        start=args.start,
        limit=args.limit,
    )
    if not tasks:
        print("No pending posts: every sample already has a gold annotation.")
        return 1

    write_tasks(tasks, args.out)
    report.update(
        {
            "input": str(args.input),
            "gold": str(args.gold) if args.gold else None,
            "output": str(args.out),
            "prompt": prompt,
        }
    )
    if args.json:
        _print_json(report)
    else:
        for key in (
            "samples",
            "unique_samples",
            "excluded_by_gold",
            "pending",
            "start",
            "limit",
            "selected",
            "guideline_version",
            "prompt_version",
            "output",
        ):
            print(f"{key}: {report[key]}")
        print(f"prompt_sha256: {report['prompt']['prompt_sha256']}")
    return 0


def _cmd_ai_import(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    if not tasks:
        raise ValueError(f"no tasks found in {args.tasks}")
    incoming = load_proposals(args.input)
    existing = load_proposals(args.out)
    merged, report = import_proposals(
        tasks, incoming, existing=existing, replace=args.replace
    )
    write_proposals(merged, args.out)
    report.update(
        {
            "tasks": str(args.tasks),
            "input": str(args.input),
            "output": str(args.out),
            "replace": args.replace,
        }
    )
    if args.json:
        _print_json(report)
    else:
        for key in (
            "tasks",
            "incoming",
            "added",
            "replaced",
            "total",
            "input",
            "output",
        ):
            print(f"{key}: {report[key]}")
    return 0


def _cmd_ai_review(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    proposals = load_proposals(args.proposals)
    if not proposals:
        raise ValueError(f"no proposals found in {args.proposals}")

    summary = run_review(
        tasks,
        proposals,
        gold_path=args.gold,
        reviews_path=args.reviews,
        reviewer=args.reviewer,
        guideline_version=args.guideline,
        blind=args.blind,
        revisit=args.revisit,
        limit=args.limit,
    )
    _print_json(summary)
    return 0


def _cmd_ai_stats(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    proposals = load_proposals(args.proposals)
    reviews = load_reviews(args.reviews)
    stats = proposal_stats(tasks, proposals, reviews)

    if args.json:
        _print_json(stats)
        return 0

    print(f"tasks: {stats['tasks']}")
    print(f"proposals: {stats['proposals']}")
    print(
        f"coverage: {stats['coverage']:.3f} "
        f"({stats['proposals_covered']}/{stats['tasks']} tasks)"
    )
    print(f"unresolved: {stats['unresolved']}")
    print(f"decisions: {json.dumps(stats['decisions'], sort_keys=True)}")
    print(
        "accept/edit/reject: "
        f"{stats['accept_rate']:.3f} / {stats['edit_rate']:.3f} / "
        f"{stats['reject_rate']:.3f}"
    )
    print(f"mean Jaccard proposal-final: {stats['mean_jaccard']:.3f}")
    print(
        "toxicity exact/MAE: "
        f"{stats['toxicity_exact_agreement']:.3f} / "
        f"{stats['toxicity_mean_absolute_error']:.3f}"
    )
    print(f"mean confidence: {stats['mean_confidence']:.3f}")
    print(
        "mean confidence by decision: "
        f"{json.dumps(stats['mean_confidence_by_decision'], sort_keys=True)}"
    )
    print(f"by model: {json.dumps(stats['by_model'], sort_keys=True)}")
    print("calibration:")
    for row in stats["calibration"]:
        print(
            f"  {row['bucket']}: proposals={row['proposals']} "
            f"resolved={row['resolved']} "
            f"accepted={row['accepted_without_edit']} "
            f"rate={row['acceptance_rate']:.3f}"
        )
    return 0


def _cmd_ai_agreement(args: argparse.Namespace) -> int:
    proposals = load_proposals(args.proposals)
    gold = load_annotations(args.gold)
    report = proposal_agreement(proposals, gold)

    if args.json:
        _print_json(report)
        return 0

    print(f"posts compared: {report['n_posts']}")
    print(f"only in proposals: {report['only_a']} | only in gold: {report['only_b']}")
    print(
        "exact frame-set match: "
        f"{report['exact_frame_set_match']:.3f} | "
        f"mean Jaccard: {report['mean_jaccard']:.3f}"
    )
    print(
        "macro kappa (active frames): "
        f"{report['macro_kappa_active_frames']:.3f}"
    )
    toxicity = report["toxicity"]
    print(
        f"toxicity: n={toxicity['n']} "
        f"quadratic_kappa={toxicity['quadratic_weighted_kappa']:.3f} "
        f"exact={toxicity['exact_agreement']:.3f} "
        f"MAE={toxicity['mean_absolute_error']:.3f}"
    )
    f1 = report["multilabel_f1"]
    print(
        f"multi-label F1: micro={f1['micro_f1']:.3f} "
        f"macro={f1['macro_f1']:.3f}"
    )
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def add_ai_parser(annotate_sub: Any) -> argparse.ArgumentParser:
    ai = annotate_sub.add_parser(
        "ai", help="AI-assisted pre-annotation with human validation"
    )
    ai_sub = ai.add_subparsers(dest="ai_command", required=True)

    p_task = ai_sub.add_parser(
        "task", help="Build blind tasks for posts that still have no gold"
    )
    p_task.add_argument("--input", required=True, help="Sample JSONL")
    p_task.add_argument(
        "--gold", help="Existing gold JSONL; its posts are excluded"
    )
    p_task.add_argument("--out", required=True)
    p_task.add_argument("--guideline", default=GUIDELINE_VERSION)
    p_task.add_argument(
        "--include-annotated",
        action="store_true",
        help="Do not exclude posts already present in --gold",
    )
    p_task.add_argument(
        "--start", type=int, default=1, help="1-based offset into pending posts"
    )
    p_task.add_argument("--limit", type=int)
    p_task.add_argument("--json", action="store_true")
    p_task.set_defaults(func=_cmd_ai_task)

    p_import = ai_sub.add_parser(
        "import", help="Validate proposal JSONL and merge it into a proposal file"
    )
    p_import.add_argument("--tasks", required=True)
    p_import.add_argument("--input", required=True, help="Proposal JSONL")
    p_import.add_argument("--out", required=True)
    p_import.add_argument(
        "--replace",
        action="store_true",
        help="Overwrite an existing proposal with the same proposal_id",
    )
    p_import.add_argument("--json", action="store_true")
    p_import.set_defaults(func=_cmd_ai_import)

    p_review = ai_sub.add_parser(
        "review", help="Validate proposals interactively and write gold"
    )
    p_review.add_argument("--tasks", required=True)
    p_review.add_argument("--proposals", required=True)
    p_review.add_argument("--gold", required=True)
    p_review.add_argument("--reviews", required=True)
    p_review.add_argument("--reviewer", required=True)
    p_review.add_argument("--guideline", default=GUIDELINE_VERSION)
    p_review.add_argument(
        "--blind",
        action="store_true",
        help="Hide rationale, evidence and confidence",
    )
    p_review.add_argument(
        "--revisit",
        action="store_true",
        help="Also show proposals that already have a decision",
    )
    p_review.add_argument("--limit", type=int)
    p_review.set_defaults(func=_cmd_ai_review)

    p_stats = ai_sub.add_parser(
        "stats", help="Coverage, decisions and calibration of AI proposals"
    )
    p_stats.add_argument("--tasks", required=True)
    p_stats.add_argument("--proposals", required=True)
    p_stats.add_argument("--reviews", required=True)
    p_stats.add_argument("--json", action="store_true")
    p_stats.set_defaults(func=_cmd_ai_stats)

    p_agreement = ai_sub.add_parser(
        "agreement",
        help="Compare proposals with gold on posts they share",
    )
    p_agreement.add_argument("--proposals", required=True)
    p_agreement.add_argument("--gold", required=True)
    p_agreement.add_argument("--json", action="store_true")
    p_agreement.set_defaults(func=_cmd_ai_agreement)

    return ai


__all__ = [
    "MODEL",
    "PROVIDER",
    "add_ai_parser",
]
