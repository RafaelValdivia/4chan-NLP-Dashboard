from __future__ import annotations

import gzip
import json

import duckdb
import pandas as pd
import pytest

from keklab.common.io import count_ndjson_lines, iter_ndjson, iter_ndjson_batches
from keklab.formal.cleaning import clean_post
from keklab.formal.features import post_structural_features
from keklab.formal.schema import Post
from keklab.ingest.dedupe import content_hash, dedupe_posts_df
from keklab.ingest.kek_loader import (
    canonicalize_fourplebs_thread,
    canonicalize_kek_posts_chunked,
    ndjson_expand_to_parquet,
)

THREADS = [
    {
        "no": 1001,
        "posts": [
            {
                "no": 1001,
                "time": 1500000000,
                "sub": "OP subject",
                "country": "US",
                "com": 'Hello <a href="#p1002" class="quotelink">&gt;&gt;1002</a><br>'
                       "&gt;greentext line<br>"
                       '<span class="spoiler">hidden</span> tail http://example.com',
                "filename": "image.jpg",
                "tim": 1500000000123,
            },
            {
                "no": 1002,
                "resto": 1001,
                "time": 1500000100,
                "com": "Reply with <b>bold</b> and &gt;&gt;1001",
                "country": "CA",
            },
            {
                "no": 1003,
                "resto": 1001,
                "time": 1500000200,
                "com": "",
            },
            {
                "no": 1004,
                "resto": 1001,
                "com": "image only, no time",
                "filename": "pic.png",
                "tim": 1500000300456,
            },
        ],
    },
    {
        "no": 2001,
        "posts": [
            {
                "no": 2001,
                "time": 1600000000,
                "com": "Second thread OP",
            },
            {
                "no": 2002,
                "resto": 2001,
                "time": 1600000100,
                "com": "&gt;&gt;2001 second reply",
            },
        ],
    },
]


@pytest.fixture()
def ndjson_file(tmp_path):
    path = tmp_path / "threads.ndjson"
    path.write_text(
        "\n".join(json.dumps(thread) for thread in THREADS) + "\n",
        encoding="utf-8",
    )
    return path


def _read_parquet(path):
    return duckdb.sql(f"SELECT * FROM read_parquet('{path}')").df()


def test_iter_ndjson_streams_and_skips_malformed(tmp_path):
    path = tmp_path / "bad.ndjson"
    path.write_text('{"no": 1}\nnot-json\n\n{"no": 2}\n', encoding="utf-8")

    assert [obj["no"] for obj in iter_ndjson(path)] == [1, 2]
    assert [len(batch) for batch in iter_ndjson_batches(path, batch_size=1)] == [1, 1]
    assert count_ndjson_lines(path) == 3


def test_iter_ndjson_reads_gzip(tmp_path):
    path = tmp_path / "threads.ndjson.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for thread in THREADS:
            fh.write(json.dumps(thread) + "\n")

    assert [thread["no"] for thread in iter_ndjson(path)] == [1001, 2001]


def test_clean_post_extracts_quotes_and_greentext():
    text_clean, quotes, greentext_count = clean_post(
        "&gt;&gt;1002<br>&gt;green line<br>plain", source="kek"
    )

    assert quotes == ["1002"]
    assert greentext_count == 1
    assert "green line" in text_clean


def test_post_structural_features_on_raw_html():
    features = post_structural_features("&gt;&gt;1002<br>&gt;green<br>plain")

    assert features["quote_count"] == 1
    assert features["greentext_count"] == 1


def test_post_allows_missing_timestamp():
    post = Post(
        post_id="1",
        thread_id="1",
        content_hash="hash",
        timestamp_utc=None,
    )

    assert post.timestamp_utc is None


def test_expand_and_canonicalize(ndjson_file, tmp_path):
    expanded = tmp_path / "expanded.parquet"
    ndjson_expand_to_parquet(ndjson_file, expanded, batch_size=2)
    exp_df = _read_parquet(expanded)

    assert len(exp_df) == 6
    assert set(exp_df["thread_id"]) == {"1001", "2001"}

    canonical = tmp_path / "canonical.parquet"
    canonicalize_kek_posts_chunked(expanded, canonical, chunk_size=2)
    can_df = _read_parquet(canonical)

    assert len(can_df) == 6
    assert set(can_df["post_id"]) == {"1001", "1002", "1003", "1004", "2001", "2002"}

    op_ids = {"1001", "2001"}
    assert can_df[can_df["post_id"].isin(op_ids)]["is_op"].all()
    assert not can_df[~can_df["post_id"].isin(op_ids)]["is_op"].any()

    op = can_df.loc[can_df["post_id"] == "1001"].iloc[0]
    assert list(op["quotes"]) == ["1002"]
    assert op["greentext_count"] == 1
    assert op["thread_depth"] == 4
    assert op["timestamp_utc"] is not None
    assert not pd.isna(op["timestamp_utc"])

    empty = can_df.loc[can_df["post_id"] == "1003"].iloc[0]
    assert empty["text_clean"] == ""

    missing_time = can_df.loc[can_df["post_id"] == "1004"].iloc[0]
    assert pd.isna(missing_time["timestamp_utc"])


def test_dedupe_keeps_empty_posts_but_collapses_duplicate_text():
    df = pd.DataFrame(
        [
            {"thread_id": "1", "post_id": "1", "text_clean": "same",
             "content_hash": content_hash("same")},
            {"thread_id": "2", "post_id": "2", "text_clean": "same",
             "content_hash": content_hash("same")},
            {"thread_id": "1", "post_id": "3", "text_clean": "",
             "content_hash": content_hash("")},
            {"thread_id": "2", "post_id": "4", "text_clean": "",
             "content_hash": content_hash("")},
        ]
    )

    out = dedupe_posts_df(df)

    assert len(out) == 3
    assert set(out["post_id"]) == {"1", "3", "4"}


def test_dedupe_collapses_natural_key():
    df = pd.DataFrame(
        [
            {"thread_id": "1", "post_id": "1", "text_clean": "a",
             "content_hash": content_hash("a")},
            {"thread_id": "1", "post_id": "1", "text_clean": "b",
             "content_hash": content_hash("b")},
        ]
    )

    out = dedupe_posts_df(df)

    assert len(out) == 1


def test_canonicalize_fourplebs_thread():
    rows = canonicalize_fourplebs_thread(THREADS[0])

    assert len(rows) == 4
    assert rows[0]["post_id"] == "1001"
    assert rows[0]["is_op"] is True
    assert rows[0]["source"] == "fourplebs"
    assert rows[0]["period"] == "recent_2020_plus"
    assert rows[1]["is_op"] is False
    assert rows[3]["timestamp_utc"] is None
