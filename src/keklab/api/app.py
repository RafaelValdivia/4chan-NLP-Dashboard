# Role: HTTP contract over the shared analytics service.
# Connects to: api/settings, analytics/service, chat/tools, web/.
#
# The API never re-implements analytics: every endpoint returns the service
# payload (`data` + `provenance`) as-is. The frontend only paints it.

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from keklab import __version__
from keklab.analytics import AnalyticsService, Filters
from keklab.annotation.labels import FRAME_LABELS, FRAME_LABELS_ES, TOXICITY_LABELS_ES
from keklab.annotation.taxonomy import COARSE_HEADS, COARSE_HEADS_ES
from keklab.api.settings import Settings
from keklab.chat.tools import TOOL_HELP, TOOLS, run as run_tool


def _split_values(value: Any) -> list[str]:
    """Accept repeated params and comma-separated values."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = [value]
    else:
        try:
            raw = list(value)
        except TypeError:
            return []
    result: list[str] = []
    for item in raw:
        result.extend(part.strip() for part in str(item).split(",") if part.strip())
    return result


class FilterQuery(BaseModel):
    """Filters and reading options carried in the query string."""

    start: str | None = None
    end: str | None = None
    sources: list[str] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=list)
    is_op: bool | None = None
    min_text_length: int | None = None
    query: str | None = None
    frames: list[str] = Field(default_factory=list)
    level: Literal["fine", "coarse"] = "fine"
    toxicity_min: int | None = None
    toxicity_max: int | None = None
    thread_ids: list[str] = Field(default_factory=list)
    denominator: Literal["all", "labeled"] = "all"
    granularity: Literal["month", "week", "day"] = "month"

    @field_validator("sources", "periods", "frames", "thread_ids", mode="before")
    @classmethod
    def _split(cls, value: Any) -> list[str]:
        return _split_values(value)

    def to_filters(self) -> Filters:
        try:
            return Filters(
                start=self.start,
                end=self.end,
                sources=tuple(self.sources),
                periods=tuple(self.periods),
                is_op=self.is_op,
                min_text_length=self.min_text_length,
                query=self.query,
                frames=tuple(self.frames),
                frame_level=self.level,
                toxicity_min=self.toxicity_min,
                toxicity_max=self.toxicity_max,
                thread_ids=tuple(self.thread_ids),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    filters: dict[str, Any] = Field(default_factory=dict)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _build_service(settings: Settings) -> AnalyticsService:
    import duckdb

    table, pattern = settings.predictions_source()
    return AnalyticsService(
        duckdb.connect(),
        l0_glob=settings.l0_glob,
        predictions_table=table,
        predictions_glob=pattern,
        events=settings.events_timeline(),
    )


def get_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[AnalyticsService]:
    """One connection per request, closed when the response is done."""
    if not settings.l0_available():
        raise HTTPException(
            status_code=503,
            detail=(
                f"No se encontró el almacén L0 en {settings.l0_glob}. "
                "Construilo con `keklab ingest l0` o ajustá `KEKLAB_L0_GLOB`."
            ),
        )
    service = _build_service(settings)
    try:
        yield service
    finally:
        service.close()


def _predictions_available(settings: Settings) -> bool:
    if not settings.l0_available():
        return False
    service = _build_service(settings)
    try:
        return service.has_predictions()
    finally:
        service.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="keklab · analítica de /pol/",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        parts = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ())[1:])
            parts.append(f"{location}: {error.get('msg', 'valor inválido')}")
        detail = "Parámetros inválidos: " + "; ".join(parts) if parts else "Parámetros inválidos"
        return JSONResponse(status_code=400, content={"detail": detail})

    # -- metadata ---------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "l0_available": settings.l0_available(),
            "predictions_configured": bool(settings.predictions),
        }

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        timeline = settings.events_timeline()
        events = timeline.as_list()
        return {
            "data": {
                "corpus": {
                    "available": settings.l0_available(),
                    "glob": settings.l0_glob,
                },
                "predictions": {
                    "configured": bool(settings.predictions),
                    "available": _predictions_available(settings),
                },
                "frames": {
                    "fine": [
                        {"id": label, "label": FRAME_LABELS_ES.get(label, label)}
                        for label in FRAME_LABELS
                    ],
                    "coarse": [
                        {"id": head, "label": COARSE_HEADS_ES.get(head, head)}
                        for head in COARSE_HEADS
                    ],
                },
                "toxicity_levels": [
                    {"level": level, "label": TOXICITY_LABELS_ES[level]}
                    for level in range(4)
                ],
                "granularities": ["month", "week", "day"],
                "denominators": ["all", "labeled"],
                "tools": [
                    {"name": name, "help": TOOL_HELP[name]} for name in TOOLS
                ],
                "events": events,
            },
            "provenance": {"n": len(events), "warnings": []},
        }

    # -- analytics --------------------------------------------------------

    @app.get("/api/overview")
    def overview(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
    ) -> dict[str, Any]:
        return service.overview(params.to_filters())

    @app.get("/api/volume")
    def volume(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
    ) -> dict[str, Any]:
        return service.volume_series(params.to_filters(), params.granularity)

    @app.get("/api/frames")
    def frames(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
    ) -> dict[str, Any]:
        return service.frame_distribution(
            params.to_filters(),
            level=params.level,
            denominator=params.denominator,
        )

    @app.get("/api/toxicity")
    def toxicity(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
    ) -> dict[str, Any]:
        return service.toxicity_distribution(
            params.to_filters(), denominator=params.denominator
        )

    @app.get("/api/series")
    def series(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
    ) -> dict[str, Any]:
        filters = params.to_filters()
        if service.has_predictions():
            result = service.frame_series(
                filters,
                granularity=params.granularity,
                level=params.level,
                denominator=params.denominator,
            )
            result["mode"] = "frames"
            return result
        # No L1: the volume series is real, frame shares are not. Say so
        # instead of returning an empty chart.
        result = service.volume_series(filters, params.granularity)
        result["provenance"].setdefault("warnings", []).append(
            "Sin predicciones: se muestra el volumen, no cuotas de marcos"
        )
        result["mode"] = "volume"
        return result

    @app.get("/api/search")
    def search(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        filters = params.to_filters()
        if not filters.query:
            raise HTTPException(status_code=400, detail="Falta el texto a buscar")
        return service.search_posts(filters, limit=limit, offset=offset)

    @app.get("/api/compare")
    def compare(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
        months: int = Query(12, ge=1, le=120),
    ) -> dict[str, Any]:
        return service.compare_with_previous(
            params.to_filters(),
            months=months,
            level=params.level,
            denominator=params.denominator,
        )

    @app.get("/api/events")
    def events(params: Annotated[FilterQuery, Depends()]) -> dict[str, Any]:
        filters = params.to_filters()
        selected = settings.events_timeline().in_range(filters.start, filters.end)
        payload = [event.as_dict() for event in selected]
        return {
            "data": payload,
            "provenance": {
                "n": len(payload),
                "filters": filters.as_dict(),
                "warnings": [],
            },
        }

    @app.get("/api/quality")
    def quality(
        params: Annotated[FilterQuery, Depends()],
        service: Annotated[AnalyticsService, Depends(get_service)],
    ) -> dict[str, Any]:
        overview = service.overview(params.to_filters())
        manifest = settings.manifest()
        manifest_path = settings.manifest_path()
        return {
            "data": {
                "corpus": overview["data"],
                "manifest": manifest,
                "manifest_path": str(manifest_path) if manifest_path else None,
                "parts_on_disk": settings.parts_on_disk(),
                "predictions_available": service.has_predictions(),
                "predictions_configured": bool(settings.predictions),
            },
            "provenance": overview["provenance"],
        }

    # -- chat -------------------------------------------------------------

    @app.post("/api/chat")
    def chat(
        payload: ChatRequest,
        service: Annotated[AnalyticsService, Depends(get_service)],
    ) -> dict[str, Any]:
        try:
            filters = Filters.from_dict(payload.filters)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = run_tool(service, filters, payload.question)
        return {
            "data": {
                "tool": result.tool,
                "text": result.text,
                "figure": result.figure,
                "table": result.table,
            },
            "provenance": result.provenance,
        }

    # -- static assets ----------------------------------------------------

    @app.get("/static/plotly.min.js", include_in_schema=False)
    def plotly_js() -> FileResponse:
        import plotly

        path = (
            Path(plotly.__file__).resolve().parent
            / "package_data"
            / "plotly.min.js"
        )
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail="plotly.min.js no está instalado (pip install plotly)",
            )
        return FileResponse(path, media_type="application/javascript")

    if settings.web_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=settings.web_dir, html=True),
            name="web",
        )

    return app


app = create_app()
