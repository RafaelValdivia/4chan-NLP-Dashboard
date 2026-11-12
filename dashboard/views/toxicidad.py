"""Page: Toxicidad.

Ordinal toxicity (0–3) and the share of posts that cross the toxic threshold.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from state import FilterState, show_provenance, to_csv


def render(service, state: FilterState) -> None:
    st.header("Toxicidad")
    filters = state.to_filters()

    if not service.has_predictions():
        st.info(
            "Todavía no hay predicciones L1 sobre el corpus: la distribución de "
            "toxicidad aparecerá con el primer run del clasificador."
        )
        overview = service.overview(filters)
        columns = st.columns(2)
        columns[0].metric("Posts", f"{overview['data']['posts']:,}")
        columns[1].metric("Hilos", f"{overview['data']['threads']:,}")
        show_provenance(overview["provenance"])
        return

    distribution = service.toxicity_distribution(
        filters, denominator=state.denominator
    )
    data = distribution["data"]

    columns = st.columns(4)
    columns[0].metric("Posts predichos", f"{distribution['provenance']['n']:,}")
    columns[1].metric(
        "Toxicos (>=2)",
        f"{data['toxic_count']:,}",
        help=f"{data['toxic_share']:.2%} del denominador",
    )
    columns[2].metric(
        "IC 95% de la cuota tóxica",
        f"{data['toxic_wilson']['low']:.2%}–{data['toxic_wilson']['high']:.2%}",
    )
    columns[3].metric(
        "Cobertura",
        f"{distribution['provenance']['coverage']:.1%}",
        help="Posts del filtro que tienen predicción.",
    )

    frame = {
        "nivel": [row["level"] for row in data["levels"]],
        "posts": [row["count"] for row in data["levels"]],
        "share": [row["share"] * 100 for row in data["levels"]],
    }
    figure = px.bar(
        frame,
        x="nivel",
        y="posts",
        hover_data={"share": ":.2f"},
        title="Distribución de toxicidad (0 = neutro, 3 = amenaza o incitación)",
    )
    st.plotly_chart(figure, width="stretch")

    table = [
        {
            "nivel": row["level"],
            "posts": row["count"],
            "share": f"{row['share']:.2%}",
            "IC 95%": f"{row['wilson']['low']:.2%}–{row['wilson']['high']:.2%}",
        }
        for row in data["levels"]
    ]
    st.dataframe(table, width="stretch", hide_index=True)
    st.download_button(
        "Descargar CSV",
        data=to_csv(table),
        file_name="toxicidad.csv",
        mime="text/csv",
    )

    show_provenance(distribution["provenance"])
