"""Shared state for the dashboard pages.

Filters live in the session state so every page (including the chat) sees
the same slice of the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import streamlit as st

from keklab.analytics import AnalyticsService, EventTimeline, Filters
from keklab.annotation.labels import FRAME_LABELS
from keklab.annotation.taxonomy import COARSE_HEADS

from config import events_path, l0_available, l0_glob, predictions_source

PAGES: tuple[tuple[str, str], ...] = (
    ("resumen", "Resumen"),
    ("marcos", "Marcos"),
    ("toxicidad", "Toxicidad"),
    ("timeline", "Línea de tiempo"),
    ("explorar", "Explorar"),
    ("calidad", "Calidad"),
    ("chat", "Chat"),
)

# Labels shown next to the checkboxes, in the canonical order.
FRAME_LABELS_ES = {
    "conspiracy": "Conspiración",
    "ethnonationalism": "Etnonacionalismo",
    "racism": "Racismo",
    "antisemitism": "Antisemitismo",
    "islamophobia": "Islamofobia",
    "rusophobia": "Rusofobia",
    "sinophobia": "Sinofobia",
    "misogyny": "Misoginia",
    "transphobia": "Transfobia",
    "homophobia": "Homofobia",
    "institutional_distrust": "Desconfianza institucional",
    "violence_glorification": "Glorificación de la violencia",
    "accelerationism": "Aceleracionismo",
    "meta_topic": "Meta del board",
    "none": "Ninguno",
    "unclear": "Incierto",
}

COARSE_HEADS_ES = {
    "conspiracy": "Conspiración",
    "ethnoracial_prejudice": "Prejuicio etnoracial",
    "gender_sexuality_prejudice": "Prejuicio de género y sexualidad",
    "institutional_distrust": "Desconfianza institucional",
    "violence_acceleration": "Violencia y aceleración",
    "meta_topic": "Meta del board",
    "no_frame": "Sin marco",
}


def get_service() -> AnalyticsService:
    """One DuckDB connection and one service for the whole session."""
    if "analytics_service" not in st.session_state:
        import duckdb

        connection = duckdb.connect()
        table, glob = None, None
        source = predictions_source()
        if source:
            if source.endswith(".parquet") or "*" in source:
                glob = source
            else:
                table = source
        timeline = EventTimeline()
        path = events_path()
        if path.exists():
            timeline = EventTimeline.from_file(path)
        st.session_state.analytics_service = AnalyticsService(
            connection,
            l0_glob=l0_glob(),
            predictions_table=table,
            predictions_glob=glob,
            events=timeline,
        )
    return st.session_state.analytics_service


def require_corpus() -> AnalyticsService | None:
    """Return the service, or explain that the warehouse is missing."""
    if not l0_available():
        st.error(
            "No se encontró el almacén L0 en "
            f"`{l0_glob()}`. Construilo con `keklab ingest l0` o ajustá "
            "la variable `KEKLAB_L0_GLOB`."
        )
        return None
    return get_service()


@dataclass
class FilterState:
    start: str | None = None
    end: str | None = None
    sources: tuple[str, ...] = ()
    denominator: str = "all"
    level: str = "fine"
    granularity: str = "month"
    frames: tuple[str, ...] = ()
    toxicity_min: int | None = None
    toxicity_max: int | None = None
    query: str | None = None
    min_text_length: int | None = None

    def to_filters(self) -> Filters:
        return Filters(
            start=self.start,
            end=self.end,
            sources=self.sources,
            frames=self.frames,
            frame_level=self.level,
            toxicity_min=self.toxicity_min,
            toxicity_max=self.toxicity_max,
            query=self.query,
            min_text_length=self.min_text_length,
        )


def read_sidebar() -> FilterState:
    """Render the sidebar and return the filters it produced."""
    st.sidebar.title("4chan /pol/ · analítica")

    page = st.sidebar.radio(
        "Sección",
        [label for _, label in PAGES],
        index=0,
        key="nav_page",
    )

    st.sidebar.divider()
    st.sidebar.subheader("Ventana")

    col_a, col_b = st.sidebar.columns(2)
    start = col_a.date_input("Desde", value=None, key="start_date")
    end = col_b.date_input("Hasta", value=None, key="end_date")

    sources = st.sidebar.multiselect(
        "Origen",
        options=["kek", "fourplebs"],
        default=[],
        key="sources",
        help="Vacío = todos los orígenes disponibles.",
    )

    st.sidebar.divider()
    st.sidebar.subheader("Lectura")

    denominator = st.sidebar.radio(
        "Denominador",
        ["all", "labeled"],
        format_func=lambda value: (
            "Todos los posts" if value == "all" else "Solo posts predichos"
        ),
        key="denominator",
    )

    level = st.sidebar.radio(
        "Nivel de marco",
        ["fine", "coarse"],
        format_func=lambda value: "16 marcos finos" if value == "fine" else "7 cabezas",
        key="level",
    )

    granularity = st.sidebar.selectbox(
        "Granularidad",
        ["month", "week", "day"],
        format_func=lambda value: {"month": "Mes", "week": "Semana", "day": "Día"}[value],
        key="granularity",
    )

    st.sidebar.divider()
    st.sidebar.subheader("Marcos")
    frame_options = FRAME_LABELS if level == "fine" else COARSE_HEADS
    frame_names = FRAME_LABELS_ES if level == "fine" else COARSE_HEADS_ES
    selected_frames = st.sidebar.multiselect(
        "Marcos o cabezas",
        options=list(frame_options),
        format_func=lambda value: frame_names.get(value, value),
        key="frames",
        help="Vacío = todos los marcos.",
    )

    toxicity = st.sidebar.slider(
        "Toxicidad (0–3)",
        min_value=0,
        max_value=3,
        value=(0, 3),
        key="toxicity",
    )

    query = st.sidebar.text_input("Buscar texto", value="", key="query")
    query = query.strip() or None

    drop_empty = st.sidebar.checkbox(
        "Excluir posts sin texto",
        value=False,
        key="drop_empty",
        help=(
            "El corpus tiene ~6 %% de posts cuyo texto limpio queda vacío "
            "(respuestas de una palabra, bumps). Apagado, cuentan en el "
            "denominador."
        ),
    )

    return FilterState(
        start=start.isoformat() if start else None,
        end=end.isoformat() if end else None,
        sources=tuple(sources),
        denominator=denominator,
        level=level,
        granularity=granularity,
        frames=tuple(selected_frames),
        toxicity_min=None if toxicity[0] == 0 else toxicity[0],
        toxicity_max=None if toxicity[1] == 3 else toxicity[1],
        query=query,
        min_text_length=1 if drop_empty else None,
    )


def show_provenance(provenance: dict[str, Any]) -> None:
    """Render the provenance footer of every answer."""
    if not provenance:
        return
    warnings = provenance.get("warnings", [])
    denominator = provenance.get("denominator")
    st.caption(
        f"n={provenance.get('n')} · denominador={denominator} · "
        f"run_id={provenance.get('run_id')} · generado {provenance.get('generated_utc')}"
    )
    for warning in warnings:
        st.warning(warning)


def previous_window(filters: Filters, months: int = 12) -> Filters | None:
    """The window of `months` right before the active one.

    Returns None when the active window has no explicit start, because there
    is nothing to shift.
    """
    if not filters.start:
        return None
    start = date.fromisoformat(filters.start)
    end = date.fromisoformat(filters.end) if filters.end else start
    baseline_end = start - timedelta(days=1)
    baseline_start = _shift_months(start, -months)
    return filters.with_overrides(
        start=baseline_start.isoformat(),
        end=baseline_end.isoformat(),
    )


def _shift_months(value: date, months: int) -> date:
    month_index = value.year * 12 + (value.month - 1) + months
    year, month = divmod(month_index, 12)
    day = min(value.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month])
    return date(year, month + 1, day)


def to_csv(rows: list[dict[str, Any]]) -> str:
    """Render a table as CSV so an analyst can take the numbers away."""
    import csv
    import io

    buffer = io.StringIO()
    if not rows:
        return ""
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
