"""Tests for the chat tools now shared by the API and the retired dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest

from keklab.analytics import AnalyticsService, Filters
from keklab.chat.tools import (
    ENTITY_DICTIONARY,
    TOOLS,
    ToolResult,
    route,
    run,
)


def _epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


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
    rows = [
        (1, 100, _epoch(2016, 6, 1), True, "russia and putin are behind it"),
        (2, 100, _epoch(2016, 6, 1), False, "bump"),
        (3, 101, _epoch(2016, 7, 2), True, "china is the enemy"),
    ]
    for post_id, thread_id, timestamp, is_op, text in rows:
        connection.execute(
            "INSERT INTO l0 VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, [], 0, 0, 1, 0, 0, 'kek', 'hist_2016_2019')",
            [
                post_id,
                thread_id,
                datetime.fromtimestamp(timestamp, tz=timezone.utc),
                is_op,
                text,
                post_id,
            ],
        )
    yield connection
    connection.close()


@pytest.fixture()
def service(con):
    service = AnalyticsService(con, l0_table="l0", run_id="chat-test")
    from keklab.analytics import Event, EventTimeline

    service.events = EventTimeline(
        [Event(event_id="test", date="2016-06-15", label="Hito de prueba")]
    )
    return service


def test_route_prefers_an_explicit_command():
    assert route("/graficar la ventana") == "graficar"
    assert route("/entidad rusia") == "extraer_entidades"  # keywords still apply
    assert route("/no_existe") == "consultar"


def test_route_uses_spanish_keywords():
    assert route("mostrame un gráfico") == "graficar"
    assert route("qué entidades aparecen") == "extraer_entidades"
    assert route("resumime la ventana") == "resumir"
    assert route("cuántos posts hay") == "consultar"


def test_all_tools_are_registered():
    assert set(TOOLS) == {
        "consultar",
        "graficar",
        "clasificar",
        "resumir",
        "extraer_entidades",
    }


def test_consultar_reports_volume_without_predictions(service):
    result = run(service, Filters(), "cuántos posts hay")

    assert isinstance(result, ToolResult)
    assert result.tool == "consultar"
    assert "3 posts" in result.text
    assert "predicciones" in result.text
    assert result.provenance["n"] == 3


def test_graficar_falls_back_to_volume(service):
    result = run(service, Filters(), "graficame la serie")

    assert result.tool == "graficar"
    assert result.figure is not None
    assert result.figure["kind"] == "bars"
    assert {row["periodo"] for row in result.table} == {"2016-06", "2016-07"}


def test_resumir_mentions_entities_and_events(service):
    result = run(service, Filters(), "resumime la ventana")

    assert result.tool == "resumir"
    assert "Rusia" in result.text
    assert "Hitos externos" in result.text


def test_extraer_entidades_counts_the_dictionary(service):
    result = run(service, Filters(), "/extraer_entidades")

    assert result.tool == "extraer_entidades"
    counts = {row["entity"]: row["count"] for row in result.table}
    assert counts["Rusia"] >= 1
    assert counts["China"] == 1
    assert set(counts) <= set(ENTITY_DICTIONARY)


def test_clasificar_reports_a_missing_model(service):
    result = run(service, Filters(), "/clasificar esto es una prueba")

    assert result.tool == "clasificar"
    assert (
        "No puedo clasificar" in result.text
        or "no devolvió JSON" in result.text
    )
