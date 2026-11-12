"""Page: Explorar (módulo removible).

Free-text search over the post text. This module can be removed without
touching the rest of the dashboard: it is the only page that reads post
bodies, and it consumes the shared service like every other page.
"""

from __future__ import annotations

import streamlit as st

from state import FilterState, show_provenance


def render(service, state: FilterState) -> None:
    st.header("Explorar")
    filters = state.to_filters()

    query = st.text_input(
        "Texto a buscar",
        value=state.query or "",
        key="explore_query",
        help="Búsqueda literal, sin distinguir mayúsculas.",
    )
    limit = st.slider("Resultados", min_value=10, max_value=200, value=50, step=10)
    offset = st.number_input("Saltar", min_value=0, value=0, step=10)

    if not query.strip():
        st.info("Escribí un texto para buscar dentro de la ventana activa.")
        return

    result = service.search_posts(
        filters.with_overrides(query=query.strip()),
        limit=int(limit),
        offset=int(offset),
    )
    rows = result["data"]
    if not rows:
        st.info("Sin coincidencias.")
        return

    st.dataframe(
        [
            {
                "post_id": row["post_id"],
                "hilo": row["thread_id"],
                "fecha": (row["timestamp_utc"] or "")[:10],
                "OP": row["is_op"],
                "texto": (row["text"] or "")[:400],
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    show_provenance(result["provenance"])
