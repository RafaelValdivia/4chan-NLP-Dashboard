"""Page: Resumen.

Volume and shape of the selected slice of the corpus.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from state import FilterState, show_provenance


def render(service, state: FilterState) -> None:
    st.header("Resumen")
    filters = state.to_filters()

    overview = service.overview(filters)
    data = overview["data"]

    columns = st.columns(5)
    columns[0].metric("Posts", f"{data['posts']:,}")
    columns[1].metric("Hilos", f"{data['threads']:,}")
    columns[2].metric(
        "Posts de OP",
        f"{data['op_posts']:,}",
        help="Posts que abren el hilo.",
    )
    columns[3].metric(
        "Longitud mediana",
        f"{data['median_length']:.0f}" if data["median_length"] else "—",
        help="Caracteres del texto limpio.",
    )
    columns[4].metric("Meses cubiertos", f"{data['months']:,}")

    if data["first_post"]:
        st.caption(
            f"Ventana del corpus: {data['first_post'][:10]} → {data['last_post'][:10]}"
        )

    series = service.volume_series(filters, state.granularity)["data"]
    if series:
        frame = {
            "period": [row["period"] for row in series],
            "posts": [row["posts"] for row in series],
            "hilos": [row["threads"] for row in series],
        }
        figure = px.line(
            frame,
            x="period",
            y=["posts", "hilos"],
            markers=True,
            title=f"Volumen por {state.granularity}",
        )
        figure.update_layout(hovermode="x unified")
        st.plotly_chart(figure, width="stretch")
    else:
        st.info("El filtro no devuelve datos.")

    show_provenance(overview["provenance"])
