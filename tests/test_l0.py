from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from keklab.ingest.l0 import build_l0, hash_text64, l0_stats


def _epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


THREADS = [
    {
        "posts": [
            {
                "no": 1,
                "time": _epoch(2016, 6, 15),
                "resto": 0,
                "com": "OP text &gt;&gt;2",
                "sub": "Subject",
                "country": "US",
            },
            {
                "no": 2,
                "time": _epoch(2016, 6, 16),
                "resto": 1,
                "com": "reply &gt;&gt;1",
            },
        ]
    },
    {
        "posts": [
            {"no": 3, "time": _epoch(2017, 1, 10), "resto": 0, "com": "Second thread"},
        ]
    },
    {
        "posts": [
            {"no": 4, "time": _epoch(2017, 1, 11), "resto": 0, "com": ""},
        ]
    },
    {
        "posts": [
            {"no": 5, "resto": 0, "com": "no timestamp"},
        ]
    },
    {
        "posts": [
            {
                "no": 6,
                "time": _epoch(2018, 5, 5),
                "resto": 0,
                "com": ">>191919191919191 troll",
            },
        ]
    },
]


def _write_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "threads.ndjson"
    path.write_text(
        "\n".join(json.dumps(thread) for thread in THREADS) + "\n",
        encoding="utf-8",
    )
    return path


def _read(out_dir: Path):
    pattern = str(out_dir / "month=*" / "*.parquet")
    return duckdb.sql(
        f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true) "
        "ORDER BY post_id"
    ).fetchall(), [
        column[0]
        for column in duckdb.sql(
            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true) LIMIT 0"
        ).description
    ]


def test_build_l0_writes_partitioned_posts(tmp_path):
    source = _write_fixture(tmp_path)
    out = tmp_path / "l0"

    manifest = build_l0(source, out, workers=1, chunk_bytes=180, resume=False)

    assert manifest["status"] == "done"
    assert manifest["totals"]["posts"] == 5
    assert manifest["totals"]["threads"] == 5
    assert manifest["totals"]["skipped_no_time"] == 1
    assert len(manifest["chunk_stats"]) == manifest["chunks_total"]

    rows, columns = _read(out)
    by_id = {row[columns.index("post_id")]: dict(zip(columns, row)) for row in rows}

    assert set(by_id) == {1, 2, 3, 4, 6}
    assert {by_id[value]["month"] for value in by_id} == {
        "2016-06",
        "2017-01",
        "2018-05",
    }

    op = by_id[1]
    reply = by_id[2]
    assert op["is_op"] is True
    assert reply["is_op"] is False
    assert op["text_clean"] == "OP text >>2"
    assert op["quotes"] == [2]
    assert reply["quotes"] == [1]
    assert op["content_hash64"] == hash_text64(op["text_clean"])
    assert op["thread_depth"] == 2
    assert op["thread_cite_count"] == 2
    assert op["subject"] == "Subject"
    assert op["country"] == "US"
    assert op["source"] == "kek"
    assert op["period"] == "hist_2016_2019"

    # Quote ids above INT32 must survive the round trip as BIGINT.
    assert by_id[6]["quotes"] == [191919191919191]
    assert reply["subject"] is None


def test_build_l0_is_resumable(tmp_path):
    source = _write_fixture(tmp_path)
    out = tmp_path / "l0"

    first = build_l0(source, out, workers=1, chunk_bytes=180, resume=False, max_chunks=1)
    assert first["status"] == "partial"
    assert len(first["chunk_stats"]) == 1

    second = build_l0(source, out, workers=1, chunk_bytes=180, resume=True)
    assert second["status"] == "done"
    assert second["totals"]["posts"] == 5
    assert len(second["chunk_stats"]) == second["chunks_total"]

    files = list(out.glob("month=*/*.parquet"))
    assert len(files) == len({path.name for path in files})


def test_build_l0_rerun_does_not_duplicate_posts(tmp_path):
    source = _write_fixture(tmp_path)
    out = tmp_path / "l0"

    build_l0(source, out, workers=1, chunk_bytes=180, resume=False)
    stats = l0_stats(out)
    assert stats["posts"] == 5

    again = build_l0(source, out, workers=1, chunk_bytes=180, resume=True)
    assert again["status"] == "done"
    assert l0_stats(out)["posts"] == 5
