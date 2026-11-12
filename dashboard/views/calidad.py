"""Page: Calidad.

Data quality: what the warehouse holds, how much of it is covered by
predictions, and which warnings the shared service raised.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from state import FilterState, show_provenance


def _manifest() -> dict | None:
    from config import l0_glob

    pattern = l0_glob()
    root = Path(pattern.split("month=")[0]) if "month=" in pattern else Path(pattern).parent
    manifest = root / "_l0_manifest.json"
    if not manifest.exists():
        return None
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def render(service, state: FilterState) -> None:
    st.header("Calidad")
    filters = state.to_filters()

    overview = service.overview(filters)
    data = overview["data"]

    st.subheader("Cobertura del corpus")
    columns = st.columns(4)
    columns[0].metric("Posts", f"{data['posts']:,}")
    columns[1].metric("Hilos", f"{data['threads']:,}")
    columns[2].metric("Posts sin texto", f"{data['empty_posts']:,}")
    columns[3].metric("Meses", f"{data['months']:,}")

    if data["first_post"]:
        st.caption(
            f"Desde {data['first_post']} hasta {data['last_post']}"
        )

    manifest = _manifest()
    if manifest:
        st.subheader("Manifiesto de construcción (L0)")
        totals = manifest.get("totals", {})
        columns = st.columns(4)
        columns[0].metric("Estado", manifest.get("status", "?"))
        columns[1].metric(
            "Troces", f"{len(manifest.get('chunk_stats', {}))}/{manifest.get('chunks_total', 0)}"
        )
        columns[2].metric("Posts escritos", f"{totals.get('posts', 0):,}")
        columns[3].metric("JSON inválido", f"{totals.get('bad_json', 0):,}")
        st.caption(
            f"Entrada: {manifest.get('input')} · bytes: {manifest.get('input_bytes'):,} "
            f"· duración: {manifest.get('elapsed_s')} s"
        )
    else:
        st.info("No se encontró el manifiesto de construcción de L0.")

    st.subheader("Predicciones")
    if service.has_predictions():
        st.success("Hay predicciones cargadas para esta sesión.")
    else:
        st.info(
            "Sin predicciones cargadas: el corpus se puede consultar por volumen y "
            "búsqueda, pero no por marco ni toxicidad."
        )

    st.subheader("Avisos del servicio")
    show_provenance(overview["provenance"])
