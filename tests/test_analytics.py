from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from keklab.analytics import (
    AnalyticsService,
    EventTimeline,
    Filters,
    cluster_bootstrap_share,
    previous_window,
    wilson_interval,
)
from keklab.annotation.taxonomy import collapse_frames


def _epoch(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp())


L0_ROWS = [
    # post_id, thread_id, timestamp, is_op, text
    (1, 100, _epoch(2016, 6, 1), True, "a secret plot by elites"),
    (2, 100, _epoch(2016, 6, 1), False, "bump"),
    (3, 101, _epoch(2016, 6, 2), True, "russia is the enemy"),
    (4, 102, _epoch(2016, 7, 3), True, "we should accelerate the collapse"),
    (5, 102, _epoch(2016, 7, 3), False, "bump"),
    (6, 103, _epoch(2016, 7, 4), True, "just a normal post"),
    (7, 104, _epoch(2019, 11, 5), True, "another secret plot"),
    (8, 104, _epoch(2019, 11, 5), False, "bump"),
]

PREDICTIONS = [
    # post_id, frame_labels, toxicity
    (1, ["conspiracy"], 0),
    (2, ["none"], 0),
    (3, ["rusophobia"], 2),
    (4, ["accelerationism"], 3),
    (5, ["none"], 0),
    (6, ["none"], 0),
    (7, ["conspiracy"], 1),
    (8, ["none"], 0),
]


@pytest.fixture()
def con():
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
    for row in L0_ROWS:
        connection.execute(
            "INSERT INTO l0 VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, [], 0, 0, 1, 0, 0, 'kek', 'hist_2016_2019')",
            [row[0], row[1], datetime.fromtimestamp(row[2], tz=timezone.utc), row[3], row[4], row[0] * 7],
        )
    connection.execute(
        """
        CREATE TABLE predictions (
            post_id BIGINT,
            frame_labels VARCHAR[],
            coarse_heads VARCHAR[],
            toxicity SMALLINT,
            model VARCHAR,
            run_id VARCHAR
        )
        """
    )
    for post_id, frames, toxicity in PREDICTIONS:
        connection.execute(
            "INSERT INTO predictions VALUES (?, ?, ?, ?, 'm', 'run-1')",
            [post_id, frames, collapse_frames(frames), toxicity],
        )
    yield connection
    connection.close()


@pytest.fixture()
def service(con):
    return AnalyticsService(con, predictions_table="predictions", run_id="test-run")


def test_filters_reject_invalid_ranges():
    with pytest.raises(ValueError):
        Filters(start="2019-01-01", end="2018-01-01")
    with pytest.raises(ValueError):
        Filters(frame_level="wide")
    with pytest.raises(ValueError):
        Filters(toxicity_min=7)


def test_filters_normalize_dates_and_describe():
    filters = Filters(start="2016-06-01T10:00:00Z", end="2016-07-31", sources=("kek",))
    assert filters.start == "2016-06-01"
    assert filters.end == "2016-07-31"
    assert "fuentes=kek" in filters.describe()


def test_overview_counts_posts_and_threads(service):
    result = service.overview(Filters())
    data = result["data"]

    assert data["posts"] == len(L0_ROWS)
    assert data["threads"] == 5
    assert data["op_posts"] == 5
    assert data["months"] == 3
    assert result["provenance"]["n"] == len(L0_ROWS)
    assert result["provenance"]["run_id"] == "test-run"


def test_overview_filters_by_window(service):
    result = service.overview(Filters(start="2016-07-01", end="2016-07-31"))
    assert result["data"]["posts"] == 3
    assert result["data"]["threads"] == 2


def test_overview_reports_timestamps_in_utc(service):
    result = service.overview(Filters())
    assert result["data"]["first_post"].endswith("+00:00")
    assert result["data"]["last_post"].endswith("+00:00")


def test_volume_series_groups_by_month(service):
    result = service.volume_series(Filters())
    periods = {row["period"]: row["posts"] for row in result["data"]}

    assert periods == {"2016-06": 3, "2016-07": 3, "2019-11": 2}
    assert result["provenance"]["granularity"] == "month"


def test_frame_distribution_reports_shares_and_intervals(service):
    result = service.frame_distribution(Filters(), level="fine")
    rows = {row["label"]: row for row in result["data"]}

    assert rows["conspiracy"]["count"] == 2
    assert rows["conspiracy"]["share"] == pytest.approx(2 / 8)
    assert rows["rusophobia"]["count"] == 1
    assert rows["none"]["count"] == 4
    assert rows["conspiracy"]["wilson"]["low"] < rows["conspiracy"]["share"]
    assert rows["conspiracy"]["wilson"]["high"] > rows["conspiracy"]["share"]
    assert result["provenance"]["denominator"] == 8
    assert result["provenance"]["coverage"] == 1.0


def test_frame_distribution_can_use_labeled_denominator(service):
    july = Filters(start="2016-07-01", end="2016-07-31")
    result = service.frame_distribution(july, denominator="labeled")
    rows = {row["label"]: row for row in result["data"]}

    # Three posts in the window, all predicted.
    assert result["provenance"]["denominator"] == 3
    assert rows["accelerationism"]["share"] == pytest.approx(1 / 3)


def test_frame_distribution_coarse_uses_heads(service):
    result = service.frame_distribution(Filters(), level="coarse")
    rows = {row["label"]: row for row in result["data"]}

    assert rows["conspiracy"]["count"] == 2
    assert rows["ethnoracial_prejudice"]["count"] == 1
    assert rows["violence_acceleration"]["count"] == 1


def test_frame_distribution_warns_without_predictions(con):
    service = AnalyticsService(con, l0_table="l0")
    result = service.frame_distribution(Filters())

    assert result["data"] == []
    assert any("predicciones" in warning for warning in result["provenance"]["warnings"])


def test_toxicity_distribution_counts_levels(service):
    result = service.toxicity_distribution(Filters())
    levels = {row["level"]: row["count"] for row in result["data"]["levels"]}

    assert levels == {0: 5, 1: 1, 2: 1, 3: 1}
    assert result["data"]["toxic_count"] == 2
    assert result["data"]["toxic_share"] == pytest.approx(2 / 8)
    assert result["provenance"]["denominator"] == 8


def test_frame_series_carries_events(service, tmp_path):
    events_file = tmp_path / "events.yaml"
    events_file.write_text(
        "events:\n"
        "  - id: pizzagate\n"
        "    date: 2016-11-09\n"
        "    label: Apertura de Pizzagate\n"
        "  - id: qanon\n"
        "    date: 2016-11-04\n"
        "    label: QAnon\n",
        encoding="utf-8",
    )
    service.events = EventTimeline.from_file(events_file)

    result = service.frame_series(Filters())
    periods = [row["period"] for row in result["data"]["series"]]
    events = result["data"]["events"]

    assert periods == ["2016-06", "2016-07", "2019-11"]
    assert [event["id"] for event in events] == ["qanon", "pizzagate"]
    conspiracy = [
        frame
        for row in result["data"]["series"]
        for frame in row["frames"]
        if frame["label"] == "conspiracy"
    ]
    assert {frame["count"] for frame in conspiracy} == {1}


def test_compare_reports_delta_between_windows(service):
    baseline = Filters(start="2016-06-01", end="2016-06-30")
    target = Filters(start="2019-11-01", end="2019-11-30")

    result = service.compare(baseline, target)
    rows = {row["label"]: row for row in result["data"]}

    assert rows["conspiracy"]["baseline_count"] == 1
    assert rows["conspiracy"]["target_count"] == 1
    assert rows["conspiracy"]["baseline_share"] == pytest.approx(1 / 3)
    assert rows["conspiracy"]["target_share"] == pytest.approx(1 / 2)
    assert rows["conspiracy"]["delta"] == pytest.approx(1 / 2 - 1 / 3, abs=1e-6)
    assert result["provenance"]["baseline"]["n"] == 3


def test_search_posts_filters_and_pages(service):
    result = service.search_posts(Filters(query="bump"), limit=10)
    assert {row["post_id"] for row in result["data"]} == {2, 5, 8}

    page = service.search_posts(Filters(query="bump"), limit=2, offset=1)
    assert len(page["data"]) == 2


def test_event_timeline_validates_input(tmp_path):
    bad = tmp_path / "events.yaml"
    bad.write_text(
        "events:\n  - id: dup\n    date: 2016-01-01\n  - id: dup\n    date: 2016-02-01\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        EventTimeline.from_file(bad)

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("events:\n  - id: x\n    date: not-a-date\n", encoding="utf-8")
    with pytest.raises(ValueError):
        EventTimeline.from_file(invalid)


def test_wilson_interval_bounds():
    interval = wilson_interval(0, 0)
    assert interval.low == 0.0 and interval.high == 0.0

    interval = wilson_interval(5, 10)
    assert interval.low < 0.5 < interval.high


def test_cluster_bootstrap_resamples_threads():
    interval = cluster_bootstrap_share([(1, 10), (0, 10), (0, 10)], resamples=200, seed=1)
    assert interval.point == pytest.approx(1 / 30)
    assert interval.low <= interval.point <= interval.high


def test_previous_window_shifts_twelve_months_back():
    active = Filters(start="2019-11-05", end="2019-11-30")
    baseline = previous_window(active)

    assert baseline is not None
    assert baseline.start == "2018-11-05"
    assert baseline.end == "2019-11-04"


def test_previous_window_needs_a_start():
    assert previous_window(Filters(end="2019-11-30")) is None


def test_compare_with_previous_derives_the_baseline(service):
    active = Filters(start="2016-07-01", end="2016-07-31")
    result = service.compare_with_previous(active, months=1)

    rows = {row["label"]: row for row in result["data"]}
    assert rows["conspiracy"]["baseline_count"] == 1
    assert rows["conspiracy"]["target_count"] == 0
    assert result["provenance"]["months"] == 1
    assert result["provenance"]["baseline"]["filters"]["start"] == "2016-06-01"


def test_compare_with_previous_warns_without_start(service):
    result = service.compare_with_previous(Filters())

    assert result["data"] == []
    assert any("fecha de inicio" in warning for warning in result["provenance"]["warnings"])


def test_run_uses_and_closes_a_cursor():
    class FakeCursor:
        def __init__(self):
            self.closed = False
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))
            return self

        def fetchall(self):
            return [(1,)]

        def close(self):
            self.closed = True

    class FakeConnection:
        def __init__(self):
            self.cursors = []
            self.direct_queries = []

        def execute(self, sql, params=None):
            self.direct_queries.append(sql)
            return self

        def cursor(self):
            cursor = FakeCursor()
            self.cursors.append(cursor)
            return cursor

    connection = FakeConnection()
    service = AnalyticsService(connection, l0_table="l0")
    assert service._run("SELECT 1") == [(1,)]
    assert len(service.con.cursors) == 1
    assert service.con.cursors[0].closed is True
    assert all("SET GLOBAL" in sql for sql in connection.direct_queries)


def test_concurrent_queries_do_not_share_a_call(con):
    service = AnalyticsService(con, l0_table="l0")
    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        barrier.wait()
        try:
            rows = service._run("SELECT count(*) FROM range(50000000)")
            results.append(int(rows[0][0]))
        except BaseException as exc:  # noqa: BLE001 - the test records it
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert results == [50_000_000, 50_000_000]


def test_hive_partitioned_source_prunes_by_month(tmp_path):
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE l0 AS SELECT
            1::BIGINT AS post_id, 100::BIGINT AS thread_id,
            TIMESTAMPTZ '2016-06-15 12:00:00+00' AS timestamp_utc,
            TRUE AS is_op, 'june'::VARCHAR AS text_clean
        """
    )
    connection.execute(
        """
        INSERT INTO l0 VALUES
        (2, 100, TIMESTAMPTZ '2016-07-15 12:00:00+00', FALSE, 'july')
        """
    )
    for month in ("2016-06", "2016-07"):
        target = tmp_path / f"month={month}" / "part-00000.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        connection.execute(
            f"COPY (SELECT * FROM l0 WHERE strftime(timestamp_utc, '%Y-%m') = '{month}') "
            f"TO '{target}' (FORMAT PARQUET)"
        )
    connection.close()

    service = AnalyticsService(
        duckdb.connect(), l0_glob=str(tmp_path / "month=*" / "*.parquet")
    )
    where_sql, params = service._posts_where(Filters(start="2016-06-15", end="2016-06-20"))

    assert "p.month >= ?" in where_sql
    assert "p.month <= ?" in where_sql
    assert params[-2:] == ["2016-06", "2016-06"]
    assert service.overview(Filters(start="2016-06-15", end="2016-06-20"))["data"]["posts"] == 1
    service.close()


def test_plain_table_does_not_reference_the_month_column(con):
    service = AnalyticsService(con, l0_table="l0")
    where_sql, _ = service._posts_where(Filters(start="2016-06-01", end="2016-06-30"))
    assert "month" not in where_sql

