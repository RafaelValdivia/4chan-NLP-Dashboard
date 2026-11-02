# Role: command-line entry point (`keklab`).
# Connects to: common/config, common/registry, ingest/kek_loader, ingest/dedupe.
#
# Usage examples:
#   keklab config show --json
#   keklab ingest expand raw/threads.ndjson data/expanded.parquet
#   keklab ingest canonicalize data/expanded.parquet data/canonical.parquet
#   keklab registry add dataset rotlk --path data/raw/rotlk.ndjson
#   keklab registry list --kind dataset

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from keklab import __version__
from keklab.common.config import dump_config, load_config, resolve_config_path
from keklab.common.logging import configure_logging, get_logger
from keklab.common.registry import (
    VALID_KINDS,
    get_artifact,
    list_artifacts,
    register_artifact,
)

log = get_logger(__name__)


def _quote_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve()).replace("'", "''")


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _kv_pairs(pairs: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in pairs or []:
        if "=" not in item:
            raise ValueError(f"Expected KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _metric_pairs(pairs: list[str] | None) -> dict[str, float]:
    return {key: float(value) for key, value in _kv_pairs(pairs).items()}


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
def _cmd_config_show(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    data = config.model_dump(mode="json")

    if args.json:
        _print_json(data)
    else:
        from yaml import safe_dump

        print(safe_dump(data, sort_keys=False, allow_unicode=True), end="")
    return 0


def _cmd_config_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    source = resolve_config_path(args.config) or "built-in defaults"
    print(f"OK: {source} (name={config.name}, seed={config.seed})")
    return 0


def _cmd_config_dump(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    out = dump_config(config, args.output)
    print(out)
    return 0


# ---------------------------------------------------------------------------
# ingest / dedupe
# ---------------------------------------------------------------------------
def _cmd_ingest_expand(args: argparse.Namespace) -> int:
    from keklab.ingest.kek_loader import ndjson_expand_to_parquet

    config = load_config(args.config)
    batch_size = args.batch_size or config.ingest.batch_size
    ndjson_expand_to_parquet(args.input, args.output, batch_size=batch_size)
    print(args.output)
    return 0


def _cmd_ingest_canonicalize(args: argparse.Namespace) -> int:
    from keklab.ingest.kek_loader import canonicalize_kek_posts_chunked

    config = load_config(args.config)
    chunk_size = args.chunk_size or config.ingest.chunk_size
    canonicalize_kek_posts_chunked(args.input, args.output, chunk_size=chunk_size)
    print(args.output)
    return 0


def _cmd_ingest_stats(args: argparse.Namespace) -> int:
    import duckdb

    path = _quote_path(args.input)
    row = duckdb.sql(
        f"""
        SELECT count(*) AS posts,
               count(DISTINCT thread_id) AS threads,
               count(*) FILTER (WHERE is_op) AS op_posts,
               min(epoch(timestamp_utc)) AS first_epoch,
               max(epoch(timestamp_utc)) AS last_epoch
        FROM read_parquet('{path}')
        """
    ).fetchall()[0]

    def _iso(epoch: float | None) -> str | None:
        if epoch is None:
            return None
        from datetime import datetime, timezone

        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()

    stats = {
        "posts": int(row[0]),
        "threads": int(row[1]),
        "op_posts": int(row[2]),
        "first_post": _iso(row[3]),
        "last_post": _iso(row[4]),
    }

    if args.json:
        _print_json(stats)
    else:
        for key, value in stats.items():
            print(f"{key}: {value}")
    return 0


def _cmd_dedupe(args: argparse.Namespace) -> int:
    import duckdb

    from keklab.common.io import write_parquet
    from keklab.ingest.dedupe import dedupe_posts_df

    df = duckdb.sql(
        f"SELECT * FROM read_parquet('{_quote_path(args.input)}')"
    ).df()
    deduped = dedupe_posts_df(df)
    write_parquet(deduped, args.output)
    print(f"{len(df)} -> {len(deduped)} rows -> {args.output}")
    return 0


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
def _cmd_registry_add(args: argparse.Namespace) -> int:
    record = register_artifact(
        args.kind,
        args.name,
        args.path,
        source=args.source,
        params=_kv_pairs(args.param),
        metrics=_metric_pairs(args.metric),
        notes=args.notes,
        registry_file=args.registry_file,
    )
    print(record.id)
    return 0


def _cmd_registry_list(args: argparse.Namespace) -> int:
    records = list_artifacts(
        kind=args.kind, name=args.name, registry_file=args.registry_file
    )
    if args.json:
        _print_json([record.model_dump(mode="json") for record in records])
        return 0

    if not records:
        print("(empty)")
        return 0

    for record in records:
        created = record.created_utc.strftime("%Y-%m-%d %H:%M")
        print(f"{record.id}  {record.kind:<8}  {record.name}  {created}  {record.path or ''}")
    return 0


def _cmd_registry_show(args: argparse.Namespace) -> int:
    record = get_artifact(args.artifact_id, registry_file=args.registry_file)
    if record is None:
        log.error("Artifact not found: %s", args.artifact_id)
        return 1

    if args.json:
        _print_json(record.model_dump(mode="json"))
    else:
        for key, value in record.model_dump(mode="json").items():
            print(f"{key}: {value}")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keklab",
        description="keklab — 4chan /pol/ NLP pipeline",
    )
    parser.add_argument("--config", help="Path to a YAML/JSON config file")
    parser.add_argument("--log-level", help="Override the logging level")
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command", required=True)

    # config
    p_config = sub.add_parser("config", help="Inspect and validate configuration")
    config_sub = p_config.add_subparsers(dest="config_command", required=True)
    p_show = config_sub.add_parser("show", help="Print the effective config")
    p_show.add_argument("--json", action="store_true", help="Emit JSON instead of YAML")
    p_show.set_defaults(func=_cmd_config_show)
    p_validate = config_sub.add_parser("validate", help="Validate the config")
    p_validate.set_defaults(func=_cmd_config_validate)
    p_dump = config_sub.add_parser("dump", help="Write the effective config to a file")
    p_dump.add_argument("output")
    p_dump.set_defaults(func=_cmd_config_dump)

    # ingest
    p_ingest = sub.add_parser("ingest", help="ROTLK/4plebs ingestion")
    ingest_sub = p_ingest.add_subparsers(dest="ingest_command", required=True)

    p_expand = ingest_sub.add_parser("expand", help="Flatten ROTLK NDJSON to parquet")
    p_expand.add_argument("input")
    p_expand.add_argument("output")
    p_expand.add_argument("--batch-size", type=int, default=None)
    p_expand.set_defaults(func=_cmd_ingest_expand)

    p_canon = ingest_sub.add_parser(
        "canonicalize", help="Canonicalize expanded parquet to Post rows"
    )
    p_canon.add_argument("input")
    p_canon.add_argument("output")
    p_canon.add_argument("--chunk-size", type=int, default=None)
    p_canon.set_defaults(func=_cmd_ingest_canonicalize)

    p_stats = ingest_sub.add_parser("stats", help="Summarize a canonical parquet")
    p_stats.add_argument("input")
    p_stats.add_argument("--json", action="store_true")
    p_stats.set_defaults(func=_cmd_ingest_stats)

    # dedupe
    p_dedupe = sub.add_parser("dedupe", help="Deduplicate a posts parquet")
    p_dedupe.add_argument("input")
    p_dedupe.add_argument("output")
    p_dedupe.set_defaults(func=_cmd_dedupe)

    # registry
    p_registry = sub.add_parser("registry", help="Datasets/models/runs registry")
    registry_sub = p_registry.add_subparsers(dest="registry_command", required=True)

    p_add = registry_sub.add_parser("add", help="Register an artifact")
    p_add.add_argument("kind", choices=VALID_KINDS)
    p_add.add_argument("name")
    p_add.add_argument("--path")
    p_add.add_argument("--source")
    p_add.add_argument("--param", action="append", metavar="KEY=VALUE")
    p_add.add_argument("--metric", action="append", metavar="KEY=VALUE")
    p_add.add_argument("--notes")
    p_add.add_argument("--registry-file", help="Override the registry JSONL path")
    p_add.set_defaults(func=_cmd_registry_add)

    p_list = registry_sub.add_parser("list", help="List registered artifacts")
    p_list.add_argument("--kind", choices=VALID_KINDS)
    p_list.add_argument("--name")
    p_list.add_argument("--json", action="store_true")
    p_list.add_argument("--registry-file")
    p_list.set_defaults(func=_cmd_registry_list)

    p_reg_show = registry_sub.add_parser("show", help="Show one artifact by id")
    p_reg_show.add_argument("artifact_id")
    p_reg_show.add_argument("--json", action="store_true")
    p_reg_show.add_argument("--registry-file")
    p_reg_show.set_defaults(func=_cmd_registry_show)

    sub.add_parser("version", help="Print the version").set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    try:
        return int(args.func(args) or 0)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log.error("%s: %s", type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
