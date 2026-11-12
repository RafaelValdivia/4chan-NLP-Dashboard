"""API contract tests over a small partitioned L0/L1 fixture."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from keklab.annotation.taxonomy import collapse_frames
from keklab.api.app import create_app
from keklab.api.settings import Settings

L0_ROWS = [
    # post_id, thread_id, timestamp, is_op, text
    (1, 100, datetime(2016, 6, 1, 12, tzinfo=timezone.utc), True, "a secret plot by elites"),
    (2, 100, datetime(2016, 6, 1, 13, tzinfo=timezone.utc), False, "bump"),
    (3, 101, datetime(2016, 6, 2, 12, tzinfo=timezone.utc), True, "russia is the enemy"),
    (4, 102, datetime(2016, 7, 3, 12, tzinfo=timezone.utc), True, "we should accelerate the collapse"),
    (5, 102, datetime(2016, 7, 3, 13, tzinfo=timezone.utc), False, "bump"),
    (6, 103, datetime(2016, 7, 4, 12, tzinfo=timezone.utc), True, "just a normal post"),
    (7, 104, datetime(2019, 11, 5, 12, tzinfo=timezone.utc), True, "another secret plot"),
    (8, 104, datetime(2019, 11, 5, 13, tzinfo=timezone.utc), False, "bump"),
]

PREDICTIONS = [
    (1, ["conspiracy"], 0),
    (2, ["none"], 0),
    (3, ["rusophobia"], 2),
    (4, ["accelerationism"], 3),
    (5, ["none"], 0),
    (6, ["none"], 0),
    (7, ["conspiracy"], 1),
    (8, ["none"], 0),
]


def _write_l0(root: Path) -> None:
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
    for post_id, thread_id, timestamp, is_op, text in L0_ROWS:
        connection.execute(
            "INSERT INTO l0 VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, [], 0, 0, 1, 0, 0, 'kek', 'hist_2016_2019')",
            [post_id, thread_id, timestamp, is_op, text, post_id * 7],
        )
    for month in sorted({row[2].strftime("%Y-%m") for row in L0_ROWS}):
        target = root / f"month={month}" / "part-00000.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        connection.execute(
            f"COPY (SELECT * FROM l0 WHERE strftime(timestamp_utc, '%Y-%m') = '{month}') "
            f"TO '{target}' (FORMAT PARQUET)"
        )
    connection.close()


def _write_predictions(root: Path) -> None:
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE predictions (
            post_id BIGINT,
            frame_labels VARCHAR[],
            coarse_heads VARCHAR[],
            toxicity SMALLINT,
            model VARCHAR,
            run_id VARCHAR,
            predicted_utc VARCHAR
        )
        """
    )
    for post_id, frames, toxicity in PREDICTIONS:
        connection.execute(
            "INSERT INTO predictions VALUES (?, ?, ?, ?, 'fixture', 'run-1', '2019-12-01T00:00:00+00:00')",
            [post_id, frames, collapse_frames(frames), toxicity],
        )
    months: dict[str, list[int]] = {}
    for post_id, _, timestamp, _, _ in L0_ROWS:
        months.setdefault(timestamp.strftime("%Y-%m"), []).append(post_id)
    for month, post_ids in months.items():
        target = root / f"month={month}" / "part-00000.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        ids = ", ".join(str(post_id) for post_id in post_ids)
        connection.execute(
            f"COPY (SELECT * FROM predictions WHERE post_id IN ({ids})) "
            f"TO '{target}' (FORMAT PARQUET)"
        )
    connection.close()


@pytest.fixture()
def corpus(tmp_path):
    l0_root = tmp_path / "l0"
    _write_l0(l0_root)
    return l0_root


def _settings(tmp_path, corpus, predictions: bool = False) -> Settings:
    predictions_glob = None
    if predictions:
        predictions_root = tmp_path / "predictions"
        _write_predictions(predictions_root)
        predictions_glob = str(predictions_root / "month=*" / "*.parquet")
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>panel</title>", encoding="utf-8")
    return Settings(
        l0_glob=str(corpus / "month=*" / "*.parquet"),
        predictions=predictions_glob,
        events=Path(__file__).resolve().parents[1] / "configs" / "events.yaml",
        web_dir=web,
    )


@pytest.fixture()
def client(tmp_path, corpus):
    return TestClient(create_app(_settings(tmp_path, corpus)))


@pytest.fixture()
def labeled_client(tmp_path, corpus):
    return TestClient(create_app(_settings(tmp_path, corpus, predictions=True)))


def test_health_works_without_corpus(tmp_path):
    settings = Settings(l0_glob=str(tmp_path / "missing" / "*.parquet"))
    response = TestClient(create_app(settings)).get("/api/health")

    assert response.status_code == 200
    assert response.json()["l0_available"] is False


def test_meta_describes_frames_tools_and_events(client):
    payload = client.get("/api/meta").json()
    data = payload["data"]

    assert data["corpus"]["available"] is True
    assert len(data["frames"]["fine"]) == 16
    assert len(data["frames"]["coarse"]) == 7
    assert len(data["tools"]) == 5
    assert any(event["id"] == "pizzagate" for event in data["events"])


def test_overview_returns_data_and_provenance(client):
    response = client.get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["posts"] == 8
    assert payload["data"]["threads"] == 5
    assert payload["provenance"]["n"] == 8
    assert payload["provenance"]["run_id"]


def test_missing_corpus_returns_503(tmp_path):
    settings = Settings(l0_glob=str(tmp_path / "missing" / "*.parquet"))
    response = TestClient(create_app(settings)).get("/api/overview")

    assert response.status_code == 503
    assert "L0" in response.json()["detail"]


def test_invalid_filter_returns_400(client):
    response = client.get("/api/overview", params={"start": "2019-01-01", "end": "2018-01-01"})

    assert response.status_code == 400
    assert "after" in response.json()["detail"]


def test_invalid_granularity_returns_400(client):
    response = client.get("/api/series", params={"granularity": "year"})

    assert response.status_code == 400
    assert "Parámetros inválidos" in response.json()["detail"]


def test_frames_without_predictions_warns(client):
    payload = client.get("/api/frames").json()

    assert payload["data"] == []
    assert any("predicciones" in warning for warning in payload["provenance"]["warnings"])


def test_series_falls_back_to_volume(client):
    payload = client.get("/api/series").json()

    assert payload["mode"] == "volume"
    assert {row["period"] for row in payload["data"]} == {"2016-06", "2016-07", "2019-11"}
    assert any("Sin predicciones" in warning for warning in payload["provenance"]["warnings"])


def test_search_requires_a_query(client):
    response = client.get("/api/search")
    assert response.status_code == 400


def test_search_returns_matching_posts(client):
    payload = client.get("/api/search", params={"query": "russia"}).json()

    assert [row["post_id"] for row in payload["data"]] == [3]
    assert "russia" in payload["data"][0]["text"]


def test_compare_uses_the_previous_window(client):
    payload = client.get(
        "/api/compare",
        params={"start": "2016-07-01", "end": "2016-07-31", "months": 1, "level": "fine"},
    ).json()

    assert payload["provenance"]["months"] == 1
    assert payload["provenance"]["baseline"]["filters"]["start"] == "2016-06-01"


def test_compare_without_start_warns(client):
    payload = client.get("/api/compare").json()

    assert payload["data"] == []
    assert any("fecha de inicio" in warning for warning in payload["provenance"]["warnings"])


def test_quality_reads_the_manifest(tmp_path, corpus):
    (corpus / "_l0_manifest.json").write_text(
        json.dumps({"status": "done", "totals": {"posts": 8}}), encoding="utf-8"
    )
    payload = TestClient(create_app(_settings(tmp_path, corpus))).get("/api/quality").json()

    assert payload["data"]["manifest"]["status"] == "done"
    assert payload["data"]["corpus"]["posts"] == 8
    assert payload["data"]["parts_on_disk"] == 3


def test_chat_answers_with_the_shared_service(client):
    response = client.post("/api/chat", json={"question": "cuántos posts hay"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["tool"] == "consultar"
    assert "8 posts" in payload["data"]["text"]
    assert payload["provenance"]["n"] == 8


def test_chat_rejects_invalid_filters(client):
    response = client.post(
        "/api/chat",
        json={"question": "cuántos posts hay", "filters": {"start": "2019-01-01", "end": "2018-01-01"}},
    )

    assert response.status_code == 400


def test_labeled_frames_series_and_toxicity(labeled_client):
    frames = labeled_client.get("/api/frames").json()
    rows = {row["label"]: row for row in frames["data"]}
    assert rows["conspiracy"]["count"] == 2
    assert frames["provenance"]["coverage"] == 1.0

    toxicity = labeled_client.get("/api/toxicity").json()
    levels = {row["level"]: row["count"] for row in toxicity["data"]["levels"]}
    assert levels == {0: 5, 1: 1, 2: 1, 3: 1}

    series = labeled_client.get("/api/series").json()
    assert series["mode"] == "frames"
    assert series["data"]["series"]


def test_plotly_asset_is_served_locally(client):
    response = client.get("/static/plotly.min.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert len(response.content) > 1_000_000


def test_index_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "panel" in response.text
