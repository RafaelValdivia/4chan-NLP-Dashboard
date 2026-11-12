"""Page: Chat.

The chat inherits the filters of the sidebar and answers with the shared
analytics service. Tools: consultar, graficar, clasificar, resumir and
extraer_entidades.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from chat.tools import TOOL_HELP, TOOLS, run
from state import FilterState


def _render_figure(figure: dict) -> None:
    rows = figure.get("rows") or []
    if not rows:
        return
    if figure.get("kind") == "lines":
        chart = px.line(
            rows, x=figure["x"], y=figure["y"], color="marco", markers=True
        )
    else:
        chart = px.bar(rows, x=figure["x"], y=figure["y"])
    chart.update_layout(hovermode="x unified")
    st.plotly_chart(chart, width="stretch")


def render(service, state: FilterState) -> None:
    st.header("Chat")
    st.caption(
        "El chat usa los mismos filtros que el resto del panel y las mismas "
        "funciones analíticas. Comandos: "
        + ", ".join(f"`/{name}`" for name in TOOLS)
    )
    with st.expander("Qué hace cada herramienta"):
        for name, description in TOOL_HELP.items():
            st.markdown(f"- `/{name}`: {description}")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    filters = state.to_filters()
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("figure"):
                _render_figure(message["figure"])
            if message.get("table"):
                st.dataframe(message["table"], width="stretch", hide_index=True)
            if message.get("provenance"):
                st.caption(
                    f"n={message['provenance'].get('n')} · "
                    f"denominador={message['provenance'].get('denominator')} · "
                    f"run_id={message['provenance'].get('run_id')}"
                )

    question = st.chat_input("Preguntá sobre el corpus")
    if not question:
        return

    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    result = run(service, filters, question)
    with st.chat_message("assistant"):
        st.markdown(result.text)
        if result.figure:
            _render_figure(result.figure)
        if result.table:
            st.dataframe(result.table, width="stretch", hide_index=True)
        if result.provenance:
            st.caption(
                f"herramienta={result.tool} · n={result.provenance.get('n')} · "
                f"denominador={result.provenance.get('denominator')} · "
                f"run_id={result.provenance.get('run_id')}"
            )
            for warning in result.provenance.get("warnings", []):
                st.warning(warning)

    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "content": result.text,
            "figure": result.figure,
            "table": result.table,
            "provenance": result.provenance,
        }
    )
