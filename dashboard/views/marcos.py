"""Page: Marcos.

Distribution of the 16 fine frames and the 7 coarse heads, with the
uncertainty attached to every number.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from state import (
    COARSE_HEADS_ES,
    FRAME_LABELS_ES,
    FilterState,
    previous_window,
    show_provenance,
)


def _labels_es(level: str) -> dict[str, str]:
    return FRAME_LABELS_ES if level == "fine" else COARSE_HEADS_ES


def render(service, state: FilterState) -> None:
    st.header("Marcos")
    filters = state.to_filters()

    if not service.has_predictions():
        st.info(
            "Todavía no hay predicciones L1 sobre el corpus: el clasificador aún no "
            "se aplicó a L0. Esta página mostrará la distribución de marcos en "
            "cuanto exista el primer run de predicciones."
        )
        overview = service.overview(filters)
        st.subheader("Mientras tanto: volumen de la ventana")
        columns = st.columns(3)
        columns[0].metric("Posts", f"{overview['data']['posts']:,}")
        columns[1].metric("Hilos", f"{overview['data']['threads']:,}")
        columns[2].metric("Meses", f"{overview['data']['months']:,}")
        show_provenance(overview["provenance"])
        return

    distribution = service.frame_distribution(
        filters, level=state.level, denominator=state.denominator
    )
    rows = [row for row in distribution["data"] if row["count"] > 0]
    labels = _labels_es(state.level)

    if rows:
        frame = {
            "marco": [labels.get(row["label"], row["label"]) for row in rows],
            "posts": [row["count"] for row in rows],
            "share": [row["share"] * 100 for row in rows],
        }
        figure = px.bar(
            frame,
            x="marco",
            y="share",
            hover_data={"posts": True, "share": ":.2f"},
            title=(
                "Marcos finos" if state.level == "fine" else "Cabeceras gruesas"
            )
            + f" (denominador: {'todos los posts' if state.denominator == 'all' else 'solo predichos'})",
        )
        figure.update_layout(yaxis_title="% de posts")
        st.plotly_chart(figure, width="stretch")

        table = [
            {
                "marco": labels.get(row["label"], row["label"]),
                "posts": row["count"],
                "share": f"{row['share']:.2%}",
                "IC 95%": f"{row['wilson']['low']:.2%}–{row['wilson']['high']:.2%}",
            }
            for row in rows
        ]
        st.dataframe(table, width="stretch", hide_index=True)
    else:
        st.info("Ninguna predicción cae dentro del filtro.")

    st.divider()
    st.subheader("Comparación entre ventanas")
    st.caption(
        "La línea base son los 12 meses anteriores a la ventana activa; "
        "el objetivo es la ventana activa."
    )
    baseline = previous_window(filters)
    if baseline is None:
        st.info("Definí una fecha de inicio para comparar con la ventana previa.")
    else:
        comparison = service.compare(
            baseline,
            filters,
            level=state.level,
            denominator=state.denominator,
        )
        if comparison["data"]:
            frame = {
                "marco": [
                    labels.get(row["label"], row["label"]) for row in comparison["data"]
                ],
                "base": [row["baseline_share"] * 100 for row in comparison["data"]],
                "objetivo": [row["target_share"] * 100 for row in comparison["data"]],
            }
            figure = px.bar(
                frame,
                x="marco",
                y=["base", "objetivo"],
                barmode="group",
                title="Base vs objetivo",
            )
            figure.update_layout(yaxis_title="% de posts")
            st.plotly_chart(figure, width="stretch")
        show_provenance(comparison["provenance"])

    show_provenance(distribution["provenance"])
