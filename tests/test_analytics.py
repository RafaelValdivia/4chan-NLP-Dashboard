from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from keklab.analytics import (
    AnalyticsService,
    EventTimeline,
    Filters,
    cluster_bootstrap_share,
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
