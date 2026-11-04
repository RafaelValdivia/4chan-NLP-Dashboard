# Role: terminal annotation CLI (sample/run/export/stats/agreement).
# Connects to: annotation/sampler, annotation/store, annotation/agreement, common/cli.

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from keklab.annotation.agreement import agreement_report
from keklab.annotation.audit import audit_samples
from keklab.annotation.labels import (
    FRAME_LABELS,
    TOXICITY_DESCRIPTIONS,
    apply_frame_toggle,
    format_frame_menu,
    parse_frame_numbers,
)
from keklab.annotation.merge import check_expected_counts, merge_samples
from keklab.annotation.retest import select_retest
from keklab.annotation.sampler import (
    FourplebsArchiveClient,
    sample_fourplebs,
    sample_rotlk,
    sample_rotlk_stream,
)
from keklab.annotation.schema import (
    AnnotationRecord,
    SamplePost,
    annotation_sample_key,
    sample_key,
)
from keklab.annotation.splits import (
    assign_thread_splits,
    split_counts,
    write_split_manifest,
)
from keklab.annotation.store import (
    AnnotationStore,
    annotation_stats,
    export_csv,
    export_jsonl,
    load_annotations,
    load_samples,
    pending_samples,
    write_samples,
)
from keklab.common.logging import get_logger
from keklab.common.paths import default_rotlk_dataset
from keklab.formal.schema import Annotation

log = get_logger(__name__)


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _excerpt(text: str, limit: int = 700) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[...]"


def _find_existing(
    records: Iterable[Annotation],
    sample: SamplePost,
    *,
    round: int,
    annotator: str,
) -> Annotation | None:
    key = sample_key(sample)
    for record in records:
        if (
            record.round == round
            and record.annotator == annotator
            and annotation_sample_key(record) == key
        ):
            return record
    return None


# ---------------------------------------------------------------------------
# Interactive session
# ---------------------------------------------------------------------------
HELP_TEXT = """\
Commands:
  <numbers>  toggle frames, e.g. 1 3 7
  n          set frame to 'none'
  u          set frame to 'unclear'
  c          clear selected frames
  t          cycle toxicity 0 -> 1 -> 2 -> 3 -> 0
  s          save this annotation and continue
  b          go back to the previous post
  q          save nothing else and quit
  ?          show this help
"""


def render_sample(
    sample: SamplePost,
    index: int,
    total: int,
    frames: Iterable[str],
    toxicity: int | None,
) -> str:
    frames = list(frames)
    timestamp = (
        sample.timestamp_utc.strftime("%Y-%m-%d %H:%M UTC")
        if sample.timestamp_utc
        else "unknown date"
    )
    lines = [
        "",
        "=" * 78,
        f"[{index}/{total}] {sample.source} | {sample.period or 'period?'} | "
        f"{timestamp} | thread {sample.thread_id}",
    ]

    if sample.subject:
        lines.append(f"Subject: {sample.subject}")
    if sample.stratum:
        lines.append(f"Stratum: {json.dumps(sample.stratum, ensure_ascii=False)}")

    if sample.context.op is not None:
        lines.extend(
            [
                "",
                f"OP context ({sample.context.op.post_id}):",
                _excerpt(sample.context.op.text_raw, 450),
            ]
        )

    for parent in sample.context.parents:
        lines.extend(
            [
                "",
                f"Quoted post ({parent.post_id}):",
                _excerpt(parent.text_raw, 450),
            ]
        )

    lines.extend(["", "Post text:"])
    raw = _excerpt(sample.text_raw or sample.text_clean or "(empty post)")
    lines.append(raw)
    if sample.text_clean and sample.text_clean.strip() != raw.strip():
        lines.extend(["", "Clean text:", _excerpt(sample.text_clean)])

    lines.extend(
        [
            "",
            "Selected frames: " + (", ".join(frames) if frames else "(none)"),
            "Toxicity: "
            + (
                f"{toxicity} — {TOXICITY_DESCRIPTIONS[toxicity]}"
                if toxicity is not None
                else "(unset)"
            ),
            "",
            "Commands: numbers toggle | n none | u unclear | c clear | "
            "t toxicity | s save | b back | q quit | ? help",
        ]
    )
    return "\n".join(lines)


def run_session(
    samples: Iterable[SamplePost],
    output_path: str | Path,
    *,
    annotator: str,
    guideline: str,
    round: int = 1,
    tier: str = "gold",
    resume: bool = True,
    prompt: Callable[[str], str] = input,
    emit: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run the interactive annotation loop.

    `prompt` and `emit` are injectable so the loop can be tested without a TTY.
    """
    samples = list(samples)
    store = AnnotationStore(output_path)
    existing = store.load() if resume else []
    queue = pending_samples(samples, existing, round=round, annotator=annotator)

    if not queue:
        emit("Nothing to annotate: all samples already have annotations.")
        return {
            "saved": 0,
            "remaining": 0,
            "quit": False,
            "output": str(output_path),
        }

    saved = 0
    index = 0
    quit_requested = False

    # The menu is needed to use the numeric toggles: with 18 frames it does
    # not fit on every sample, so show it once at the start of the session.
    emit(format_frame_menu())

    while index < len(queue) and not quit_requested:
        sample = queue[index]
        current = _find_existing(
            store.load(), sample, round=round, annotator=annotator
        )
        frames = list(current.frame_labels) if current else []
        toxicity = current.toxicity if current else None

        while True:
            emit(render_sample(sample, index + 1, len(queue), frames, toxicity))
            try:
                command = prompt("> ").strip()
            except (EOFError, KeyboardInterrupt):
                emit("")
                quit_requested = True
                break

            if not command:
                continue

            lowered = command.lower()

            if lowered in {"s", "save"}:
                if not frames:
                    emit("Select at least one frame (use n for none / u for unclear).")
                    continue
                if toxicity is None:
                    emit("Set toxicity with 't' before saving.")
                    continue

                record = AnnotationRecord(
                    post_id=sample.post_id,
                    thread_id=sample.thread_id,
                    source=sample.source,
                    period=sample.period,
                    content_hash=sample.content_hash,
                    frame_labels=frames,
                    toxicity=toxicity,
                    annotator=annotator,
                    round=round,
                    tier=tier,
                    guideline_version=guideline,
                    annotated_utc=datetime.now(timezone.utc),
                    notes=f"stratum={json.dumps(sample.stratum, ensure_ascii=False)}",
                )
                store.upsert(record)
                saved += 1
                index += 1
                emit(f"Saved ({saved} this session).")
                break

            if lowered in {"q", "quit"}:
                quit_requested = True
                break

            if lowered in {"b", "back"}:
                if index > 0:
                    index -= 1
                    emit("Going back one post.")
                else:
                    emit("Already at the first post.")
                break

            if lowered in {"?", "h", "help"}:
                emit(HELP_TEXT)
                continue

            if lowered in {"n", "none"}:
                frames = apply_frame_toggle(frames, ["none"])
                emit("frames: none")
                continue

            if lowered in {"u", "unclear"}:
                frames = apply_frame_toggle(frames, ["unclear"])
                emit("frames: unclear")
                continue

            if lowered in {"c", "clear"}:
                frames = []
                emit("frames: (none)")
                continue

            if lowered in {"t", "tox"}:
                toxicity = 0 if toxicity is None else (toxicity + 1) % 4
                emit(f"toxicity = {toxicity}: {TOXICITY_DESCRIPTIONS[toxicity]}")
                continue

            try:
                labels = parse_frame_numbers(command)
            except ValueError as exc:
                emit(str(exc))
                continue

            frames = apply_frame_toggle(frames, labels)
            emit("frames: " + (", ".join(frames) if frames else "(none)"))

    return {
        "saved": saved,
        "remaining": max(0, len(queue) - index),
        "quit": quit_requested,
        "output": str(output_path),
    }


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
def _cmd_annotate_sample(args: argparse.Namespace) -> int:
    if args.source == "fourplebs":
        client = FourplebsArchiveClient(
            cache_dir=args.cache_dir, sleep=args.sleep
        )
        samples = sample_fourplebs(
            random_count=args.random,
            targeted_count=args.targeted,
            months=args.months,
            seed=args.seed,
            max_pages=args.max_pages,
            include_empty=args.include_empty,
            client=client,
        )
    else:
        dataset = getattr(args, "dataset", None) or default_rotlk_dataset()
        parquet = getattr(args, "parquet", None)
        if dataset and parquet:
            raise ValueError(
                "Use only one of --dataset or --parquet when --source=rotlk"
            )
        if dataset:
            samples = sample_rotlk_stream(
                dataset,
                random_count=args.random,
                targeted_count=args.targeted,
                months=args.months,
                seed=args.seed,
                include_empty=args.include_empty,
                limit_threads=getattr(args, "limit_threads", None),
            )
        elif parquet:
            samples = sample_rotlk(
                parquet,
                random_count=args.random,
                targeted_count=args.targeted,
                months=args.months,
                seed=args.seed,
                include_empty=args.include_empty,
            )
        else:
            raise ValueError(
                "ROTLK sampling needs --dataset (or KEKLAB_ROTLK_DATASET) "
                "or --parquet"
            )

    if not samples:
        log.error("No samples produced; check the window, source and API access.")
        return 1

    write_samples(samples, args.out)
    reasons: dict[str, int] = {}
    for sample in samples:
        reason = str(sample.stratum.get("reason", "unknown"))
        reasons[reason] = reasons.get(reason, 0) + 1
    print(f"{len(samples)} samples -> {args.out}")
    print("by reason: " + json.dumps(reasons, sort_keys=True))
    return 0


def _cmd_annotate_merge(args: argparse.Namespace) -> int:
    merged, report = merge_samples(
        args.input, strict=not args.lenient
    )
    check_expected_counts(
        report,
        total=args.expect_total,
        random=args.expect_random,
        targeted=args.expect_targeted,
    )
    write_samples(merged, args.out)
    report["output"] = str(args.out)
    _print_json(report)
    return 0


def _cmd_annotate_retest(args: argparse.Namespace) -> int:
    samples = load_samples(args.input)
    selected = select_retest(
        samples, fraction=args.fraction, seed=args.seed
    )
    if not selected:
        log.error("No samples selected; check the input and fraction.")
        return 1

    write_samples(selected, args.out)
    reasons: dict[str, int] = {}
    for sample in selected:
        reason = str(sample.stratum.get("reason", "unknown"))
        reasons[reason] = reasons.get(reason, 0) + 1
    _print_json(
        {
            "input": str(args.input),
            "output": str(args.out),
            "selected": len(selected),
            "fraction": args.fraction,
            "seed": args.seed,
            "by_reason": dict(sorted(reasons.items())),
        }
    )
    return 0


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _cmd_annotate_split(args: argparse.Namespace) -> int:
    samples = load_samples(args.input)
    assignment = assign_thread_splits(
        samples,
        ratios=(args.train, args.dev, args.test),
        seed=args.seed,
    )
    if not assignment:
        log.error("No threads found in the input sample.")
        return 1

    write_split_manifest(assignment, args.out)
    _print_json(
        {
            "input": str(args.input),
            "output": str(args.out),
            "threads": len(assignment),
            "ratios": {
                "train": args.train,
                "dev": args.dev,
                "test": args.test,
            },
            "counts": split_counts(assignment),
            "seed": args.seed,
        }
    )
    return 0


def _cmd_annotate_audit(args: argparse.Namespace) -> int:
    samples = load_samples(args.input)
    report = audit_samples(
        samples,
        window_start=_parse_timestamp(args.start),
        window_end=_parse_timestamp(args.end),
    )

    if args.json:
        _print_json(report)
        return 0

    for key in (
        "posts",
        "unique_posts",
        "unique_threads",
        "duplicate_posts",
        "duplicate_threads",
        "duplicate_content_hashes",
        "empty_raw",
        "empty_clean",
        "op_posts",
        "month_count",
        "first_month",
        "last_month",
        "first_timestamp",
        "last_timestamp",
        "missing_timestamps",
        "outside_window",
    ):
        print(f"{key}: {report[key]}")
    print(f"by_reason: {json.dumps(report['by_reason'], sort_keys=True)}")
    print(f"by_source: {json.dumps(report['by_source'], sort_keys=True)}")
    print(f"top_countries: {json.dumps(report['top_countries'], sort_keys=True)}")
    print(f"text_length: {json.dumps(report['text_length'], sort_keys=True)}")
    return 0


def _cmd_annotate_run(args: argparse.Namespace) -> int:
    samples = load_samples(args.input)
    summary = run_session(
        samples,
        args.out,
        annotator=args.annotator,
        guideline=args.guideline,
        round=args.round,
        tier=args.tier,
        resume=not args.no_resume,
    )
    _print_json(summary)
    return 0


def _cmd_annotate_export(args: argparse.Namespace) -> int:
    records = load_annotations(args.input)
    if args.format == "csv":
        text = export_csv(records, args.output)
    else:
        text = export_jsonl(records, args.output)

    if args.output:
        print(args.output)
    else:
        print(text, end="")
    return 0


def _cmd_annotate_stats(args: argparse.Namespace) -> int:
    records = load_annotations(args.input)
    stats = annotation_stats(records)

    if args.json:
        _print_json(stats)
        return 0

    for key in (
        "annotations",
        "unique_posts",
        "annotators",
        "rounds",
        "guideline_versions",
        "tiers",
        "mean_frames_per_annotation",
    ):
        print(f"{key}: {stats[key]}")

    print("frame_counts:")
    for label in FRAME_LABELS:
        print(f"  {label}: {stats['frame_counts'][label]}")
    print("coarse_counts:")
    for head, count in stats["coarse_counts"].items():
        print(f"  {head}: {count}")
    print("toxicity_counts:")
    for level in range(4):
        print(f"  {level}: {stats['toxicity_counts'][str(level)]}")
    return 0


def _cmd_annotate_agreement(args: argparse.Namespace) -> int:
    records_a = load_annotations(args.a)
    records_b = load_annotations(args.b)
    report = agreement_report(records_a, records_b)

    if args.json:
        _print_json(report)
        return 0

    print(f"posts compared: {report['n_posts']}")
    print(f"only in A: {report['only_a']} | only in B: {report['only_b']}")
    print(
        "exact frame-set match: "
        f"{report['exact_frame_set_match']:.3f} | "
        f"mean Jaccard: {report['mean_jaccard']:.3f}"
    )
    print(
        "macro kappa (active frames): "
        f"{report['macro_kappa_active_frames']:.3f}"
    )
    print("per-frame kappa:")
    for label in FRAME_LABELS:
        data = report["frames"][label]
        print(
            f"  {label:<24} kappa={data['kappa']:.3f} "
            f"agreement={data['agreement']:.3f} "
            f"positive_a={data['positive_a']} positive_b={data['positive_b']}"
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
        f"multi-label F1: micro={f1['micro_f1']:.3f} macro={f1['macro_f1']:.3f}"
    )
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def add_annotate_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "annotate", help="Sample, annotate and audit the human gold set"
    )
    annotate_sub = parser.add_subparsers(
        dest="annotate_command", required=True
    )

    p_sample = annotate_sub.add_parser(
        "sample", help="Build candidate posts for annotation"
    )
    p_sample.add_argument(
        "--source", choices=["fourplebs", "rotlk"], default="fourplebs"
    )
    p_sample.add_argument("--out", required=True)
    p_sample.add_argument("--months", type=int, default=24)
    p_sample.add_argument("--random", type=int, default=20)
    p_sample.add_argument("--targeted", type=int, default=10)
    p_sample.add_argument("--seed", type=int, default=13)
    p_sample.add_argument("--max-pages", type=int, default=200)
    p_sample.add_argument("--include-empty", type=int, default=0)
    p_sample.add_argument(
        "--dataset",
        help=(
            "ROTLK NDJSON or .tar.zst archive for --source=rotlk. "
            "Defaults to KEKLAB_ROTLK_DATASET when set."
        ),
    )
    p_sample.add_argument(
        "--parquet",
        help="Canonical ROTLK parquet for --source=rotlk (alternative to --dataset)",
    )
    p_sample.add_argument(
        "--limit-threads",
        type=int,
        help="Stop after N threads (smoke tests on the real ROTLK dump)",
    )
    p_sample.add_argument("--cache-dir", help="4plebs archive cache directory")
    p_sample.add_argument("--sleep", type=float, default=1.0)
    p_sample.set_defaults(func=_cmd_annotate_sample)

    p_merge = annotate_sub.add_parser(
        "merge", help="Merge sample files and deduplicate by post/thread"
    )
    p_merge.add_argument(
        "--input", nargs="+", required=True, help="Sample JSONL files to merge"
    )
    p_merge.add_argument("--out", required=True)
    p_merge.add_argument("--expect-total", type=int)
    p_merge.add_argument("--expect-random", type=int)
    p_merge.add_argument("--expect-targeted", type=int)
    p_merge.add_argument(
        "--lenient",
        action="store_true",
        help="Skip invalid sample rows instead of failing",
    )
    p_merge.set_defaults(func=_cmd_annotate_merge)

    p_retest = annotate_sub.add_parser(
        "retest", help="Select a deterministic round-2 retest subset"
    )
    p_retest.add_argument("--input", required=True)
    p_retest.add_argument("--out", required=True)
    p_retest.add_argument("--fraction", type=float, default=0.2)
    p_retest.add_argument("--seed", type=int, default=13)
    p_retest.set_defaults(func=_cmd_annotate_retest)

    p_split = annotate_sub.add_parser(
        "split", help="Assign train/dev/test splits by thread"
    )
    p_split.add_argument("--input", required=True)
    p_split.add_argument("--out", required=True)
    p_split.add_argument("--seed", type=int, default=13)
    p_split.add_argument("--train", type=float, default=0.6)
    p_split.add_argument("--dev", type=float, default=0.2)
    p_split.add_argument("--test", type=float, default=0.2)
    p_split.set_defaults(func=_cmd_annotate_split)

    p_audit = annotate_sub.add_parser(
        "audit", help="Describe a sample file without annotations"
    )
    p_audit.add_argument("--input", required=True)
    p_audit.add_argument("--json", action="store_true")
    p_audit.add_argument("--start", help="Window start (ISO 8601)")
    p_audit.add_argument("--end", help="Window end (ISO 8601)")
    p_audit.set_defaults(func=_cmd_annotate_audit)

    p_run = annotate_sub.add_parser(
        "run", help="Annotate candidates interactively in the terminal"
    )
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--annotator", required=True)
    p_run.add_argument("--guideline", default="v1")
    p_run.add_argument("--round", type=int, default=1)
    p_run.add_argument("--tier", choices=["gold", "silver"], default="gold")
    p_run.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing annotations and revisit every sample",
    )
    p_run.set_defaults(func=_cmd_annotate_run)

    p_export = annotate_sub.add_parser(
        "export", help="Export annotations as CSV or JSONL"
    )
    p_export.add_argument("--input", required=True)
    p_export.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    p_export.add_argument("--output", help="Output file; defaults to stdout")
    p_export.set_defaults(func=_cmd_annotate_export)

    p_stats = annotate_sub.add_parser(
        "stats", help="Describe an annotation file"
    )
    p_stats.add_argument("--input", required=True)
    p_stats.add_argument("--json", action="store_true")
    p_stats.set_defaults(func=_cmd_annotate_stats)

    p_agreement = annotate_sub.add_parser(
        "agreement",
        help="Self test-retest agreement between two annotation passes",
    )
    p_agreement.add_argument("--a", required=True)
    p_agreement.add_argument("--b", required=True)
    p_agreement.add_argument("--json", action="store_true")
    p_agreement.set_defaults(func=_cmd_annotate_agreement)

    return parser
