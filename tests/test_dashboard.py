"""Smoke tests for the dashboard pages.

`streamlit.testing.v1.AppTest` runs the app headless, so these tests catch
import errors, broken views and exceptions with real filters.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def _epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


@pytest.fixture()
def l0_fixture(tmp_path, monkeypatch):
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
    rows = [
        (1, 100, _epoch(2016, 6, 1), True, "a secret plot by elites", 11),
        (2, 100, _epoch(2016, 6, 2), False, "bump", 12),
        (3, 101, _epoch(2016, 6, 3), True, "russia is the enemy", 13),
    ]
    for post_id, thread_id, timestamp, is_op, text, digest in rows:
        connection.execute(
            "INSERT INTO l0 VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, [], 0, 0, 1, 0, 0, 'kek', 'hist_2016_2019')",
            [
                post_id,
                thread_id,
                datetime.fromtimestamp(timestamp, tz=timezone.utc),
                is_op,
                text,
                digest,
            ],
        )
    connection.execute(f"COPY l0 TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    connection.close()

    monkeypatch.setenv("KEKLAB_L0_GLOB", str(tmp_path / "month=*" / "*.parquet"))
    monkeypatch.delenv("KEKLAB_PREDICTIONS", raising=False)
    return tmp_path


def _app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(DASHBOARD))


def test_dashboard_renders_the_summary(l0_fixture):
    app = _app()
    app.run()

    assert not app.exception
    assert app.title[0].value == "4chan /pol/ · analítica"
    assert any("Posts" in metric.label for metric in app.metric)


def test_dashboard_pages_render_without_predictions(l0_fixture):
    app = _app()
    app.run()

    for label in ("Marcos", "Toxicidad", "Línea de tiempo", "Explorar", "Calidad", "Chat"):
        app.sidebar.radio[0].set_value(label).run()
        assert not app.exception, label


def test_chat_answers_with_the_shared_service(l0_fixture):
    app = _app()
    app.run()
    app.sidebar.radio[0].set_value("Chat").run()

    app.chat_input[0].set_value("cuántos posts hay").run()

    assert not app.exception
    assert any("posts" in message.value.lower() for message in app.markdown)


def test_chat_extracts_entities(l0_fixture):
    app = _app()
    app.run()
    app.sidebar.radio[0].set_value("Chat").run()

    app.chat_input[0].set_value("/extraer_entidades").run()

    assert not app.exception
    texts = [message.value for message in app.markdown]
    assert any("Rusia" in text for text in texts)
