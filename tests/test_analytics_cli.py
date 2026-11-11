from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from keklab.common.cli import main


def _epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


@pytest.fixture()
def l0_parquet(tmp_path):
    import duckdb

    path = tmp_path / "month=2016-06" / "part-00000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
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
    for row in [
        (1, 100, _epoch(2016, 6, 1), True, "a secret plot", None, 11, None, [], 0, 0, 1, 0, 0, "kek", "hist_2016_2019"),
        (2, 100, _epoch(2016, 6, 2), False, "bump", None, 12, None, [], 0, 0, 2, 0, 0, "kek", "hist_2016_2019"),
    ]:
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
    connection.execute(
        f"COPY l0 TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    connection.close()
    return tmp_path


def test_analytics_overview_reports_posts(l0_parquet, capsys):
    assert (
        main(
            [
                "analytics",
                "overview",
                "--l0",
                str(l0_parquet / "month=*" / "*.parquet"),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["posts"] == 2
    assert payload["data"]["threads"] == 1
    assert payload["provenance"]["run_id"]


def test_analytics_search_filters_by_query(l0_parquet, capsys):
    assert (
        main(
            [
                "analytics",
                "search",
                "--l0",
                str(l0_parquet / "month=*" / "*.parquet"),
                "--query",
                "bump",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert [row["post_id"] for row in payload["data"]] == [2]


def test_analytics_events_reads_the_curated_file(tmp_path, capsys):
    events = tmp_path / "events.yaml"
    events.write_text(
        "events:\n"
        "  - id: pizzagate\n"
        "    date: 2016-11-04\n"
        "    label: Pizzagate\n",
        encoding="utf-8",
    )

    assert main(["analytics", "events", "--events", str(events), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["id"] == "pizzagate"


def test_analytics_events_filter_by_window(tmp_path, capsys):
    events = tmp_path / "events.yaml"
    events.write_text(
        "events:\n"
        "  - id: pizzagate\n"
        "    date: 2016-11-04\n"
        "    label: Pizzagate\n"
        "  - id: christchurch\n"
        "    date: 2019-03-15\n"
        "    label: Christchurch\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "analytics",
                "events",
                "--events",
                str(events),
                "--start",
                "2019-01-01",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert [event["id"] for event in payload] == ["christchurch"]
