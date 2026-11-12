"""Page: Línea de tiempo.

Frame shares over time with the external milestones marked on the axis.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from state import COARSE_HEADS_ES, FRAME_LABELS_ES, FilterState, show_provenance


def render(service, state: FilterState) -> None:
    st.header("Línea de tiempo")
    filters = state.to_filters()

    events = service.events_between(filters.start, filters.end)
    if events:
        st.caption(
            "Hitos externos marcados: "
            + " · ".join(f"{event.date} {event.label}" for event in events)
        )
    else:
        st.caption("Sin hitos externos dentro de la ventana.")

    if not service.has_predictions():
        st.info(
            "Todavía no hay predicciones L1: la serie de marcos por periodo se "
            "calcula cuando el clasificador se aplique a L0."
        )
        series = service.volume_series(filters, state.granularity)["data"]
        if series:
            figure = px.line(
                {
                    "periodo": [row["period"] for row in series],
                    "posts": [row["posts"] for row in series],
                },
                x="periodo",
                y="posts",
                markers=True,
                title="Volumen por periodo",
            )
            st.plotly_chart(figure, width="stretch")
        return

    result = service.frame_series(
        filters,
        granularity=state.granularity,
        level=state.level,
        denominator=state.denominator,
    )
    series = result["data"]["series"]
    labels = FRAME_LABELS_ES if state.level == "fine" else COARSE_HEADS_ES

    rows = []
    for period in series:
        for frame in period["frames"]:
            if frame["count"] == 0:
                continue
            rows.append(
                {
                    "periodo": period["period"],
                    "marco": labels.get(frame["label"], frame["label"]),
                    "share": frame["share"] * 100,
                    "posts": frame["count"],
                }
            )

    if not rows:
        st.info("Ninguna predicción cae dentro de la ventana.")
        return

    figure = px.line(
        rows,
        x="periodo",
        y="share",
        color="marco",
        markers=True,
        hover_data={"posts": True},
        title=f"Cuota por marco ({state.granularity})",
    )
    figure.update_layout(yaxis_title="% de posts", hovermode="x unified")
    for event in events:
        figure.add_vline(
            x=event.date,
            line_dash="dot",
            line_color="firebrick",
            annotation_text=event.label,
            annotation_position="top",
        )
    st.plotly_chart(figure, width="stretch")

    show_provenance(result["provenance"])
