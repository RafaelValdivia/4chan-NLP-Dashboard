"""Tools for the chat page.

Every tool reads the shared analytics service, so an answer in the chat and
the same number in the dashboard cannot drift apart. The chat never queries
the warehouse with its own SQL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from keklab.analytics import AnalyticsService, Filters
from keklab.annotation.labels import FRAME_LABELS, TOXICITY_DESCRIPTIONS
from keklab.annotation.taxonomy import collapse_frames

# Small curated dictionary. The extraction is lexical, not a trained NER: it
# counts mentions, it does not resolve them. The corpus is in English, so
# every entity carries its English aliases too.
ENTITY_DICTIONARY: dict[str, tuple[str, ...]] = {
    "Rusia": ("rusia", "ruso", "russia", "russian", "putin", "kremlin", "moscow", "moscu"),
    "China": ("china", "chino", "chinese", "pekin", "beijing", "ccp"),
    "EE.UU.": (
        "eeuu",
        "estados unidos",
        "united states",
        "americano",
        "american",
        "washington",
        "trump",
    ),
    "Ucrania": ("ucrania", "ucraniano", "ukraine", "ukrainian", "kiev", "kyiv", "zelensky"),
    "Europa": ("europa", "europeo", "european", "europe", "union europea", "bruselas", "brussels"),
    "OTAN": ("otan", "nato"),
    "ONU": ("onu", "naciones unidas", "united nations"),
    "FBI": ("fbi",),
    "CNN": ("cnn",),
    "Fox News": ("fox news",),
    "QAnon": ("qanon", "q anon", "q-anon"),
    "Pizzagate": ("pizzagate", "comet ping pong", "pizza"),
    "Jeffrey Epstein": ("epstein",),
    "Israel": ("israel", "israeli", "israelí", "tel aviv"),
    "Irán": ("iran", "iranies", "iraní", "iranian"),
    "Corea del Norte": ("corea del norte", "north korea", "corea del sur", "south korea"),
    "Venezuela": ("venezuela", "maduro"),
    "Pedro Castillo": ("pedro castillo", "abuelo"),
}


@dataclass
class ToolResult:
    """What a tool returns to the chat UI."""

    text: str
    figure: dict[str, Any] | None = None
    table: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] | None = None
    tool: str = ""


# ---------------------------------------------------------------------------
# consultar
# ---------------------------------------------------------------------------

def consultar(service: AnalyticsService, filters: Filters, question: str) -> ToolResult:
    """Counts and distributions for the active slice."""
    overview = service.overview(filters)
    data = overview["data"]
    lines = [
        f"En la ventana activa hay {data['posts']:,} posts en {data['threads']:,} hilos.",
        f"Longitud mediana del texto limpio: {data['median_length']:.0f} caracteres."
        if data["median_length"]
        else "",
    ]

    if service.has_predictions():
        distribution = service.frame_distribution(filters, level="fine")
        top = sorted(
            (row for row in distribution["data"] if row["count"] > 0),
            key=lambda row: row["count"],
            reverse=True,
        )[:5]
        if top:
            lines.append("Marcos más frecuentes:")
            for row in top:
                lines.append(
                    f"  · {row['label']}: {row['count']:,} posts ({row['share']:.2%})"
                )
        toxicity = service.toxicity_distribution(filters)
        toxic = toxicity["data"]["toxic_count"]
        lines.append(f"Posts con toxicidad ≥ 2: {toxic:,}.")
        return ToolResult(
            text="\n".join(line for line in lines if line),
            table=[
                {"marco": row["label"], "posts": row["count"], "cuota": row["share"]}
                for row in top
            ],
            provenance=overview["provenance"],
            tool="consultar",
        )

    lines.append(
        "Todavía no hay predicciones del clasificador sobre el corpus, así que "
        "solo puedo informar volumen."
    )
    return ToolResult(
        text="\n".join(line for line in lines if line),
        provenance=overview["provenance"],
        tool="consultar",
    )


# ---------------------------------------------------------------------------
# graficar
# ---------------------------------------------------------------------------

def graficar(service: AnalyticsService, filters: Filters, question: str) -> ToolResult:
    """Build a chart of the active slice."""
    granularity = "month"
    if "semana" in question.lower():
        granularity = "week"
    elif "día" in question.lower() or "dia" in question.lower():
        granularity = "day"

    if service.has_predictions():
        series = service.frame_series(
            filters, granularity=granularity, level="fine"
        )["data"]["series"]
        rows = []
        for period in series:
            for frame in period["frames"]:
                if frame["count"]:
                    rows.append(
                        {
                            "periodo": period["period"],
                            "marco": frame["label"],
                            "cuota": frame["share"] * 100,
                            "posts": frame["count"],
                        }
                    )
        if rows:
            return ToolResult(
                text=f"Serie de cuotas por marco ({granularity}).",
                figure={"kind": "lines", "rows": rows, "x": "periodo", "y": "cuota"},
                table=rows,
                tool="graficar",
            )

    series = service.volume_series(filters, granularity)["data"]
    rows = [
        {
            "periodo": row["period"],
            "posts": row["posts"],
            "hilos": row["threads"],
        }
        for row in series
    ]
    return ToolResult(
        text=f"Volumen por {granularity}.",
        figure={"kind": "bars", "rows": rows, "x": "periodo", "y": "posts"},
        table=rows,
        tool="graficar",
    )


# ---------------------------------------------------------------------------
# clasificar
# ---------------------------------------------------------------------------

def clasificar(service: AnalyticsService, filters: Filters, question: str) -> ToolResult:
    """Classify a short text with the local model, when it is available."""
    from keklab.annotation.prompts import (
        GUIDELINE_VERSION,
        PROMPT_VERSION,
        output_schema,
        render_prompt,
    )
    from keklab.annotation.proposal import TaskRecord
    from keklab.annotation.schema import SamplePost
    from keklab.classification.backends import LlamaCppBackend

    text = question.strip()
    if not text:
        return ToolResult(text="No hay texto para clasificar.", tool="clasificar")

    sample = SamplePost(
        post_id="chat",
        thread_id="chat",
        source="kek",
        text_raw=text,
        text_clean=text,
        content_hash="chat",
    )
    task = TaskRecord.from_sample(
        sample, guideline_version=GUIDELINE_VERSION, prompt_version=PROMPT_VERSION
    )
    prompt = render_prompt(task)

    try:
        raw = LlamaCppBackend().generate(prompt, schema=output_schema())
    except Exception as exc:  # model or llama-cpp-python missing
        return ToolResult(
            text=(
                "No puedo clasificar con el modelo local en esta máquina: "
                f"{exc}. El clasificador corre en la máquina con GPU."
            ),
            tool="clasificar",
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ToolResult(
            text=f"El modelo no devolvió JSON válido: {raw[:400]}",
            tool="clasificar",
        )

    frames = [label for label in payload.get("frame_labels", []) if label in FRAME_LABELS]
    toxicity = payload.get("toxicity")
    heads = collapse_frames(frames) if frames else []
    lines = [f"Marcos: {', '.join(frames) if frames else 'ninguno'}"]
    if heads:
        lines.append(f"Cabeceras: {', '.join(heads)}")
    if isinstance(toxicity, int):
        lines.append(
            f"Toxicidad: {toxicity} — {TOXICITY_DESCRIPTIONS.get(toxicity, 'sin descripción')}"
        )
    rationale = payload.get("rationale")
    if rationale:
        lines.append(f"Razonamiento: {rationale}")
    return ToolResult(text="\n".join(lines), tool="clasificar")


# ---------------------------------------------------------------------------
# resumir
# ---------------------------------------------------------------------------

def resumir(service: AnalyticsService, filters: Filters, question: str) -> ToolResult:
    """Describe the slice: volume, months, entities and toxicity."""
    overview = service.overview(filters)
    data = overview["data"]
    series = service.volume_series(filters, "month")["data"]
    top_months = sorted(series, key=lambda row: row["posts"], reverse=True)[:3]
    entities = service.term_counts(filters, ENTITY_DICTIONARY)["data"]

    lines = [
        f"Ventana: {data['first_post'][:10] if data['first_post'] else '—'} → "
        f"{data['last_post'][:10] if data['last_post'] else '—'}.",
        f"{data['posts']:,} posts, {data['threads']:,} hilos, {data['months']} meses.",
        f"Longitud mediana: {data['median_length']:.0f} caracteres."
        if data["median_length"]
        else "",
    ]
    if top_months:
        lines.append(
            "Meses con más actividad: "
            + ", ".join(f"{row['period']} ({row['posts']:,})" for row in top_months)
        )
    if entities:
        lines.append(
            "Entidades más mencionadas: "
            + ", ".join(
                f"{row['entity']} ({row['count']:,})"
                for row in entities[:5]
            )
        )
    if service.has_predictions():
        toxicity = service.toxicity_distribution(filters)["data"]
        lines.append(
            f"Toxicidad ≥ 2: {toxicity['toxic_count']:,} posts "
            f"({toxicity['toxic_share']:.2%})."
        )
    return ToolResult(
        text="\n".join(line for line in lines if line),
        table=entities,
        provenance=overview["provenance"],
        tool="resumir",
    )


# ---------------------------------------------------------------------------
# extraer_entidades
# ---------------------------------------------------------------------------

def extraer_entidades(
    service: AnalyticsService, filters: Filters, question: str
) -> ToolResult:
    """Count mentions of the curated entity dictionary in the active slice."""
    result = service.term_counts(filters, ENTITY_DICTIONARY)
    rows = result["data"]
    if not rows:
        return ToolResult(
            text="Ninguna entidad del diccionario aparece en la ventana.",
            provenance=result["provenance"],
            tool="extraer_entidades",
        )
    lines = [
        "Menciones por entidad (extracción léxica por diccionario, no NER):",
        *[f"  · {row['entity']}: {row['count']:,} posts" for row in rows],
    ]
    return ToolResult(
        text="\n".join(lines),
        table=rows,
        provenance=result["provenance"],
        tool="extraer_entidades",
    )


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------

TOOLS = {
    "consultar": consultar,
    "graficar": graficar,
    "clasificar": clasificar,
    "resumir": resumir,
    "extraer_entidades": extraer_entidades,
}

TOOL_HELP = {
    "consultar": "conteos y distribuciones de la ventana activa",
    "graficar": "serie temporal de la ventana activa",
    "clasificar": "etiqueta un texto con el modelo local",
    "resumir": "resumen descriptivo de la ventana activa",
    "extraer_entidades": "menciones de entidades del diccionario",
}

_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("graficar", ("gráfico", "grafico", "grafica", "serie", "evolución", "evolucion", "curva")),
    ("extraer_entidades", ("entidad", "entidades", "menciones", "quién", "quien", "menciona")),
    ("clasificar", ("clasifica", "etiqueta", "etiquetar", "toxicidad de", "que marco")),
    ("resumir", ("resumen", "resume", "resumir", "de que trata", "qué trata")),
    ("consultar", ("cuántos", "cuantas", "cuanto", "cuanta", "hay", "posts", "hilos", "consulta")),
)


def route(question: str) -> str:
    """Pick the tool for a question. Explicit `/tool` wins over keywords."""
    text = question.strip()
    if text.startswith("/"):
        candidate = text[1:].split()[0].lower() if text[1:].split() else ""
        if candidate in TOOLS:
            return candidate
    lowered = text.lower()
    for tool, keywords in _KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return tool
    return "consultar"


def run(service: AnalyticsService, filters: Filters, question: str) -> ToolResult:
    tool = route(question)
    return TOOLS[tool](service, filters, question)
