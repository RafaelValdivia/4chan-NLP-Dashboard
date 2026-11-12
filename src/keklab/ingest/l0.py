# Role: build L0, the canonical columnar copy of the full ROTLK corpus.
# Connects to: formal/cleaning, ingest/kek_loader, ingest/cli, analytics.
#
# L0 is the queryable form of the historical dump: one row per post, Parquet
# partitioned by month. It deliberately drops `raw_html` (recoverable from the
# dump) and keeps a compact 64-bit content hash instead of the full SHA256.

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from keklab.common.logging import get_logger
from keklab.formal.cleaning import clean_post

log = get_logger(__name__)

SCHEMA_VERSION = 2
SOURCE = "kek"
PERIOD = "hist_2016_2019"
HASH_SIZE = 8
DEFAULT_CHUNK_BYTES = 1024 * 1024 * 1024
DEFAULT_WORKERS = 4
FLUSH_ROWS = 400_000
MANIFEST_NAME = "_l0_manifest.json"

COLUMNS: tuple[str, ...] = (
    "post_id",
    "thread_id",
    "timestamp_utc",
    "is_op",
    "text_clean",
    "subject",
    "content_hash64",
    "country",
    "quotes",
    "greentext_count",
    "quote_count",
    "thread_depth",
    "thread_cite_count",
    "thread_greentext_count",
    "source",
    "period",
)

_DDL = """
CREATE TABLE l0 (
    post_id BIGINT,
    thread_id BIGINT,
    timestamp_utc TIMESTAMPTZ,
    is_op BOOLEAN,
    text_clean VARCHAR,
    subject VARCHAR,
    content_hash64 UBIGINT,
    country VARCHAR,
    quotes BIGINT[],
    greentext_count INTEGER,
    quote_count INTEGER,
    thread_depth INTEGER,
    thread_cite_count INTEGER,
    thread_greentext_count INTEGER,
    source VARCHAR,
    period VARCHAR
)
"""


def hash_text64(text: str) -> int:
    """Stable 64-bit content hash derived from `text_clean`."""
    digest = hashlib.blake2b((text or "").encode("utf-8"), digest_size=HASH_SIZE)
    return int.from_bytes(digest.digest(), "little")


def _quote_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve()).replace("'", "''")


def _as_optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _as_post_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _quote_ids(quotes: Iterable[str]) -> list[int]:
    ids: list[int] = []
    for quote in quotes:
        try:
            ids.append(int(quote))
        except (TypeError, ValueError):
            continue
    return ids


def thread_rows(thread: dict[str, Any]) -> tuple[list[tuple[Any, ...]], dict[str, int]]:
    """Canonicalize one ROTLK thread into L0 rows.

    Cleaning and thread features match `canonicalize_fourplebs_thread`, but
    are computed in a single pass to avoid re-extracting quotes four times.
    Posts without a usable id or timestamp are skipped and counted.
    """
    posts = [post for post in (thread.get("posts") or []) if isinstance(post, dict)]
    stats = {"posts": 0, "skipped_no_time": 0, "skipped_bad_id": 0}
    if not posts:
        return [], stats

    thread_id = _as_post_id(posts[0].get("no"))
    if thread_id is None:
        thread_id = _as_post_id(thread.get("no"))
    if thread_id is None:
        stats["skipped_bad_id"] += len(posts)
        return [], stats

    cleaned: list[tuple[dict[str, Any], str, list[str], int]] = []
    cite_set: set[str] = set()
    greentext_total = 0
    for post in posts:
        raw_html = str(post.get("com") or "")
        text_clean, quotes, greentext = clean_post(raw_html, source="kek")
        cite_set.update(quotes)
        greentext_total += greentext
        cleaned.append((post, text_clean, quotes, greentext))

    thread_depth = len(cleaned)
    thread_cite_count = len(cite_set)
    rows: list[tuple[Any, ...]] = []
    for post, text_clean, quotes, greentext in cleaned:
        post_id = _as_post_id(post.get("no"))
        if post_id is None:
            stats["skipped_bad_id"] += 1
            continue

        timestamp = post.get("time")
        try:
            timestamp_utc = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            stats["skipped_no_time"] += 1
            continue

        resto = post.get("resto")
        is_op = resto == 0 or post_id == thread_id
        rows.append(
            (
                post_id,
                thread_id,
                timestamp_utc,
                bool(is_op),
                text_clean,
                _as_optional_text(post.get("sub")),
                hash_text64(text_clean),
                _as_optional_text(post.get("country")),
                _quote_ids(quotes),
                int(greentext),
                len(quotes),
                thread_depth,
                thread_cite_count,
                greentext_total,
                SOURCE,
                PERIOD,
            )
        )

    stats["posts"] = len(rows)
    return rows, stats


def _open_writer() -> Any:
    import duckdb

    con = duckdb.connect()
    con.execute(_DDL)
    return con


def _flush(
    con: Any,
    out_dir: Path,
    month: str,
    chunk_id: int,
    rows: list[tuple[Any, ...]],
    *,
    flush_index: int,
) -> Path:
    import pandas as pd

    frame = pd.DataFrame.from_records(rows, columns=list(COLUMNS))
    # Quote ids overflow INT32 in the wild (troll posts quote huge numbers)
    # and DuckDB infers INT32 for Python lists, so the ids travel as text
    # and are cast to BIGINT[] in SQL.
    frame["quotes"] = [
        ",".join(str(quote) for quote in quotes) for quotes in frame["quotes"]
    ]

    con.execute("DELETE FROM l0")
    con.execute(
        """
        INSERT INTO l0
        SELECT post_id,
               thread_id,
               timestamp_utc,
               is_op,
               text_clean,
               subject,
               content_hash64,
               country,
               CASE
                   WHEN quotes = '' THEN []::BIGINT[]
                   ELSE list_transform(
                       str_split(quotes, ','),
                       lambda value: TRY_CAST(value AS BIGINT)
                   )
               END,
               greentext_count,
               quote_count,
               thread_depth,
               thread_cite_count,
               thread_greentext_count,
               source,
               period
        FROM frame
        """
    )

    # The flush index keeps the name unique: a chunk that empties the same
    # month twice must not overwrite its own first part.
    name = f"part-{chunk_id:05d}-{flush_index:03d}.parquet"
    path = out_dir / f"month={month}" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con.execute(
        f"COPY (SELECT * FROM l0) TO '{_quote_path(path)}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return path


def _process_chunk(
    input_path: str,
    out_dir: str,
    chunk_id: int,
    start: int,
    end: int,
    flush_rows: int = FLUSH_ROWS,
) -> dict[str, Any]:
    """Process one byte range of the NDJSON input and write its Parquet parts."""
    out_root = Path(out_dir)
    # A retried chunk must not leave stale parts behind.
    for stale in out_root.glob(f"month=*/part-{chunk_id:05d}-*.parquet"):
        stale.unlink()

    con = _open_writer()
    buffers: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    stats = {
        "threads": 0,
        "threads_written": 0,
        "posts": 0,
        "skipped_no_time": 0,
        "skipped_bad_id": 0,
        "bad_json": 0,
        "bad_thread": 0,
    }
    written: list[str] = []
    flush_index = 0

    def flush(month: str) -> None:
        nonlocal flush_index
        if not buffers[month]:
            return
        path = _flush(
            con,
            out_root,
            month,
            chunk_id,
            buffers[month],
            flush_index=flush_index,
        )
        flush_index += 1
        written.append(str(path))
        buffers[month] = []

    try:
        with open(input_path, "rb") as fh:
            fh.seek(start)
            if start > 0:
                fh.seek(start - 1)
                previous = fh.read(1)
                fh.seek(start)
                if previous != b"\n":
                    fh.readline()

            while True:
                line_start = fh.tell()
                if line_start >= end:
                    break
                line = fh.readline()
                if not line:
                    break
                try:
                    thread = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    stats["bad_json"] += 1
                    continue
                if not isinstance(thread, dict):
                    stats["bad_thread"] += 1
                    continue

                stats["threads"] += 1
                rows, thread_stats = thread_rows(thread)
                if thread_stats["posts"]:
                    stats["threads_written"] += 1
                stats["posts"] += thread_stats["posts"]
                stats["skipped_no_time"] += thread_stats["skipped_no_time"]
                stats["skipped_bad_id"] += thread_stats["skipped_bad_id"]

                for row in rows:
                    month = row[2].strftime("%Y-%m")
                    month_buffer = buffers[month]
                    month_buffer.append(row)
                    if len(month_buffer) >= flush_rows:
                        flush(month)

        for month in list(buffers):
            flush(month)
    finally:
        con.close()

    stats["parts"] = written
    return stats


def _plan_chunks(path: Path, chunk_bytes: int) -> list[tuple[int, int, int]]:
    size = path.stat().st_size
    if size <= 0:
        return []
    chunks: list[tuple[int, int, int]] = []
    chunk_id = 0
    start = 0
    while start < size:
        end = min(start + chunk_bytes, size)
        chunks.append((chunk_id, start, end))
        chunk_id += 1
        start = end
    return chunks


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _aggregate(manifest: dict[str, Any]) -> None:
    totals = {
        "threads": 0,
        "threads_written": 0,
        "posts": 0,
        "skipped_no_time": 0,
        "skipped_bad_id": 0,
        "bad_json": 0,
        "bad_thread": 0,
    }
    for stats in manifest.get("chunk_stats", {}).values():
        for key in totals:
            totals[key] += int(stats.get(key, 0))
    manifest["totals"] = totals


def _new_manifest(
    input_path: Path,
    out_dir: Path,
    chunks: list[tuple[int, int, int]],
    chunk_bytes: int,
    flush_rows: int = FLUSH_ROWS,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "input": str(input_path),
        "input_bytes": input_path.stat().st_size,
        "out_dir": str(out_dir),
        "chunk_bytes": chunk_bytes,
        "flush_rows": int(flush_rows),
        "chunks_total": len(chunks),
        "chunk_stats": {},
        "chunks_failed": [],
        "started_utc": now,
        "updated_utc": now,
        "status": "running",
        "totals": {
            "threads": 0,
            "threads_written": 0,
            "posts": 0,
            "skipped_no_time": 0,
            "skipped_bad_id": 0,
            "bad_json": 0,
            "bad_thread": 0,
        },
    }


def build_l0(
    input_path: str | Path,
    out_dir: str | Path,
    *,
    workers: int = DEFAULT_WORKERS,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    resume: bool = True,
    max_chunks: int | None = None,
    flush_rows: int = FLUSH_ROWS,
) -> dict[str, Any]:
    """Build the L0 Parquet warehouse from an expanded ROTLK NDJSON file.

    The input is split into byte ranges processed independently. Each chunk
    writes `month=YYYY-MM/part-<chunk>-<flush>.parquet` parts, so a crashed
    run can resume without redoing completed chunks. The manifest records
    per-chunk counts and is the source of truth for the build.
    """
    source = Path(input_path).expanduser()
    if not source.exists():
        raise FileNotFoundError(source)
    target = Path(out_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)

    chunks = _plan_chunks(source, max(1, int(chunk_bytes)))
    manifest_path = target / MANIFEST_NAME
    manifest = _read_manifest(manifest_path) if resume else None
    if (
        manifest is None
        or manifest.get("input_bytes") != source.stat().st_size
        or manifest.get("chunk_bytes") != chunk_bytes
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("flush_rows") != int(flush_rows)
    ):
        manifest = _new_manifest(source, target, chunks, chunk_bytes, flush_rows)
        _atomic_json(manifest_path, manifest)

    done = set(manifest.get("chunk_stats", {}))
    pending = [
        chunk for chunk in chunks if str(chunk[0]) not in done
    ]
    if max_chunks is not None:
        pending = pending[: int(max_chunks)]

    log.info(
        "L0 build: %d chunks total, %d pending, %d workers",
        len(chunks),
        len(pending),
        workers,
    )

    started = datetime.now(timezone.utc)
    completed_now = 0

    def record(chunk_id: int, stats: dict[str, Any]) -> None:
        manifest["chunk_stats"][str(chunk_id)] = {
            key: value for key, value in stats.items() if key != "parts"
        }
        manifest.setdefault("parts_written", []).extend(stats.get("parts", []))
        manifest["chunks_failed"] = [
            failed for failed in manifest.get("chunks_failed", []) if failed != chunk_id
        ]
        _aggregate(manifest)
        manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
        _atomic_json(manifest_path, manifest)

    if workers <= 1 or len(pending) <= 1:
        for chunk_id, start, end in pending:
            stats = _process_chunk(
                str(source), str(target), chunk_id, start, end, flush_rows
            )
            record(chunk_id, stats)
            completed_now += 1
            log.info(
                "L0 chunk %d/%d done (%d posts, %d skipped)",
                completed_now,
                len(pending),
                stats["posts"],
                stats["skipped_no_time"] + stats["skipped_bad_id"],
            )
    else:
        with ProcessPoolExecutor(max_workers=int(workers)) as pool:
            futures = {
                pool.submit(
                    _process_chunk,
                    str(source),
                    str(target),
                    chunk_id,
                    start,
                    end,
                    flush_rows,
                ): chunk_id
                for chunk_id, start, end in pending
            }
            for future in as_completed(futures):
                chunk_id = futures[future]
                try:
                    stats = future.result()
                except Exception as exc:  # one bad chunk must not kill the build
                    log.error("L0 chunk %d failed: %s", chunk_id, exc)
                    failed = manifest.setdefault("chunks_failed", [])
                    if chunk_id not in failed:
                        failed.append(chunk_id)
                    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
                    _atomic_json(manifest_path, manifest)
                    continue
                record(chunk_id, stats)
                completed_now += 1
                log.info(
                    "L0 chunk %d/%d done (%d posts, %d skipped)",
                    completed_now,
                    len(pending),
                    stats["posts"],
                    stats["skipped_no_time"] + stats["skipped_bad_id"],
                )

    remaining = [
        chunk[0] for chunk in chunks if str(chunk[0]) not in manifest["chunk_stats"]
    ]
    manifest["status"] = "done" if not remaining and not manifest.get("chunks_failed") else "partial"
    manifest["remaining_chunks"] = remaining
    manifest["elapsed_s"] = round(
        (datetime.now(timezone.utc) - started).total_seconds(), 1
    )
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _aggregate(manifest)
    _atomic_json(manifest_path, manifest)
    return manifest


def l0_stats(out_dir: str | Path) -> dict[str, Any]:
    """Query the built L0 warehouse and return corpus-level counts.

    The manifest is the source of truth of the build, so its totals are
    compared against what is actually on disk: a part that overwrote
    another one leaves the manifest correct and the warehouse short.
    """
    import duckdb

    root = Path(out_dir).expanduser()
    pattern = _quote_path(root / "month=*" / "*.parquet")
    connection = duckdb.connect()
    try:
        connection.execute("SET TimeZone='UTC'")
        rows = connection.execute(
            f"""
            SELECT count(*) AS posts,
                   count(DISTINCT thread_id) AS threads,
                   count(*) FILTER (WHERE is_op) AS op_posts,
                   count(DISTINCT content_hash64) AS unique_hashes,
                   count(DISTINCT month) AS months,
                   min(timestamp_utc) AS first_post,
                   max(timestamp_utc) AS last_post
            FROM read_parquet('{pattern}', hive_partitioning = true)
            """
        ).fetchall()
    finally:
        connection.close()
    row = rows[0]
    stats = {
        "posts": int(row[0]),
        "threads": int(row[1]),
        "op_posts": int(row[2]),
        "unique_hashes": int(row[3]),
        "months": int(row[4]),
        "first_post": row[5].isoformat() if row[5] else None,
        "last_post": row[6].isoformat() if row[6] else None,
    }

    manifest = _read_manifest(root / MANIFEST_NAME)
    if manifest:
        expected_posts = int(manifest.get("totals", {}).get("posts", 0))
        expected_threads = int(
            manifest.get("totals", {}).get("threads_written")
            or manifest.get("totals", {}).get("threads", 0)
        )
        parts_written = len(manifest.get("parts_written", []))
        parts_on_disk = len(list(root.glob("month=*/*.parquet")))
        stats["manifest_status"] = manifest.get("status")
        stats["manifest_posts"] = expected_posts
        stats["manifest_threads"] = expected_threads
        stats["parts_written"] = parts_written
        stats["parts_on_disk"] = parts_on_disk
        stats["posts_match_manifest"] = expected_posts == stats["posts"]
        stats["threads_match_manifest"] = expected_threads == stats["threads"]
        stats["parts_match_manifest"] = parts_written == parts_on_disk
        stats["ok"] = bool(
            stats["posts_match_manifest"]
            and stats["threads_match_manifest"]
            and stats["parts_match_manifest"]
        )
    return stats
