"""4chan /pol/ analytics dashboard.

Entry point: `streamlit run dashboard/app.py`.

The dashboard never re-implements analytics: every number comes from
`keklab.analytics`, the same service the chatbot uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from state import PAGES, get_service, read_sidebar  # noqa: E402
from views import (  # noqa: E402
    calidad,
    chat,
    explorar,
    marcos,
    resumen,
    timeline,
    toxicidad,
)

VIEWS = {
    "resumen": resumen.render,
    "marcos": marcos.render,
    "toxicidad": toxicidad.render,
    "timeline": timeline.render,
    "explorar": explorar.render,
    "calidad": calidad.render,
    "chat": chat.render,
}


def main() -> None:
    st.set_page_config(
        page_title="4chan /pol/ · analítica",
        page_icon="📊",
        layout="wide",
    )
    state = read_sidebar()
    service = get_service()

    label_to_key = {label: key for key, label in PAGES}
    page = label_to_key.get(state_page(), "resumen")
    st.sidebar.caption(f"Sección activa: {state_page()}")
    VIEWS[page](service, state)


def state_page() -> str:
    """The label of the section selected in the sidebar."""
    return st.session_state.get("nav_page", "Resumen")


if __name__ == "__main__":
    main()
