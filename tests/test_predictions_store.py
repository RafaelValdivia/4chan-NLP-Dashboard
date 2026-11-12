from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb
import pytest

from keklab.analytics import AnalyticsService, Filters
from keklab.classification.predictions import (
    load_predictions,
    normalize_prediction,
    write_predictions,
)


def _epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


@pytest.fixture()
def l0_table():
    connection = duckdb.connect()
    connection.execute(
        """
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
    )
    rows = [
        (1, 100, _epoch(2016, 6, 1), True, "a secret plot", None, 11, None, [], 0, 0, 1, 0, 0, "kek", "hist_2016_2019"),
        (2, 100, _epoch(2016, 6, 2), False, "bump", None, 12, None, [], 0, 0, 2, 0, 0, "kek", "hist_2016_2019"),
        (3, 101, _epoch(2016, 7, 3), True, "russia is the enemy", None, 13, None, [], 0, 0, 1, 0, 0, "kek", "hist_2016_2019"),
    ]
    for row in rows:
        connection.execute(
            "INSERT INTO l0 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                row[0],
                row[1],
                datetime.fromtimestamp(row[2], tz=timezone.utc),
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                row[11],
                row[12],
                row[13],
                row[14],
                row[15],
            ],
        )
    yield connection
    connection.close()


def test_normalize_prediction_rejects_bad_payloads():
    assert normalize_prediction({"post_id": "1", "frame_labels": ["none"], "toxicity": 0})
    assert normalize_prediction({"post_id": "", "frame_labels": ["none"], "toxicity": 0}) is None
    assert normalize_prediction({"post_id": "1", "frame_labels": ["none"]}) is None
    assert normalize_prediction({"post_id": "1", "frame_labels": ["none"], "toxicity": 9}) is None
    assert normalize_prediction({"post_id": "1", "frame_labels": ["nope"], "toxicity": 0}) is None


def test_write_predictions_partitions_by_month(tmp_path):
    rows = [
        {"post_id": "1", "frame_labels": ["conspiracy"], "toxicity": 0, "timestamp_utc": "2016-06-01"},
        {"post_id": "3", "frame_labels": ["rusophobia"], "toxicity": 2, "timestamp_utc": "2016-07-03"},
        {"post_id": "", "frame_labels": ["none"], "toxicity": 0},
    ]

    manifest = write_predictions(rows, tmp_path / "l1", model="m", run_id="run-1")

    assert manifest["rows"] == 2
    assert manifest["rows_skipped"] == 1
    assert manifest["months"] == ["2016-06", "2016-07"]
    assert (tmp_path / "l1" / "month=2016-06" / "part-00000.parquet").exists()

    loaded = load_predictions(tmp_path / "l1")
    by_post = {row["post_id"]: row for row in loaded}
    assert by_post[1]["frame_labels"] == ["conspiracy"]
    assert by_post[1]["coarse_heads"] == ["conspiracy"]
    assert by_post[3]["toxicity"] == 2
    assert by_post[3]["model"] == "m"


def test_analytics_reads_the_stored_predictions(l0_table, tmp_path):
    """The stored L1 shape is exactly what the analytics service expects."""
    write_predictions(
        [
            {"post_id": "1", "frame_labels": ["conspiracy"], "toxicity": 0},
            {"post_id": "2", "frame_labels": ["none"], "toxicity": 0},
            {"post_id": "3", "frame_labels": ["rusophobia"], "toxicity": 2},
        ],
        tmp_path / "l1",
        model="m",
        run_id="run-1",
    )

    service = AnalyticsService(
        l0_table,
        l0_table="l0",
        predictions_glob=str(tmp_path / "l1" / "month=*" / "*.parquet"),
    )
    assert service.has_predictions()

    distribution = service.frame_distribution(Filters(), level="fine")
    rows = {row["label"]: row for row in distribution["data"]}

    assert rows["conspiracy"]["count"] == 1
    assert rows["rusophobia"]["count"] == 1
    assert rows["none"]["count"] == 1
    assert distribution["provenance"]["labeled_posts"] == 3
    assert distribution["provenance"]["coverage"] == 1.0

    toxicity = service.toxicity_distribution(Filters())
    assert toxicity["data"]["toxic_count"] == 1


def test_store_command_writes_predictions(tmp_path, capsys):
    from keklab.common.cli import main

    source = tmp_path / "predictions.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"post_id": "1", "frame_labels": ["conspiracy"], "toxicity": 1},
                {"post_id": "2", "frame_labels": ["none"], "toxicity": 0},
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out = tmp_path / "l1"
    assert main(["classify", "store", "--input", str(source), "--out", str(out), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["rows"] == 2
    assert payload["parts"]
