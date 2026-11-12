# Role: command-line access to the shared analytics service.
# Connects to: analytics/service, analytics/filters, analytics/events.
#
# The CLI is a thin shell over `AnalyticsService`: the dashboard and the
# chatbot use the same service, so a number checked here is the number the
# UI shows.

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from keklab.analytics.events import EventTimeline
from keklab.analytics.filters import Filters
from keklab.analytics.service import AnalyticsService
from keklab.common.paths import CONFIGS_DIR

DEFAULT_EVENTS = CONFIGS_DIR / "events.yaml"


def _predictions_source(value: str | None) -> tuple[str | None, str | None]:
    """Split a `--predictions` argument into (table, glob)."""
    if not value:
        return None, None
    if value.endswith(".parquet") or "*" in value:
        return None, value
    return value, None


def _build_service(args: argparse.Namespace) -> AnalyticsService:
    import duckdb

    table, glob = _predictions_source(getattr(args, "predictions", None))
    events = EventTimeline()
    events_path = getattr(args, "events", None) or DEFAULT_EVENTS
    if events_path and Path(events_path).exists():
        events = EventTimeline.from_file(events_path)
    connection = duckdb.connect()
    return AnalyticsService(
        connection,
        l0_glob=args.l0,
        predictions_table=table,
        predictions_glob=glob,
        events=events,
    )


def _filters(args: argparse.Namespace) -> Filters:
    frames = tuple(getattr(args, "frames", ()) or ())
    return Filters(
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        sources=tuple(getattr(args, "sources", ()) or ()),
        query=getattr(args, "query", None),
        frames=frames,
        frame_level=getattr(args, "level", "fine"),
        toxicity_min=getattr(args, "toxicity_min", None),
        toxicity_max=getattr(args, "toxicity_max", None),
    )


def _print(args: argparse.Namespace, payload: Any) -> int:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    data = payload.get("data", payload)
    if isinstance(data, list):
        for row in data:
            print(json.dumps(row, ensure_ascii=False, default=str))
    elif isinstance(data, dict) and "series" in data:
        for row in data["series"]:
            print(json.dumps(row, ensure_ascii=False, default=str))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    provenance = payload.get("provenance") if isinstance(payload, dict) else None
    if provenance:
        print(
            f"# n={provenance.get('n')} denominador={provenance.get('denominator')} "
            f"run_id={provenance.get('run_id')}"
        )
        for warning in provenance.get("warnings", []):
            print(f"# aviso: {warning}")
    return 0


def _cmd_analytics_overview(args: argparse.Namespace) -> int:
    return _print(args, _build_service(args).overview(_filters(args)))


def _cmd_analytics_frames(args: argparse.Namespace) -> int:
    service = _build_service(args)
    return _print(
        args,
        service.frame_distribution(
            _filters(args),
            level=args.level,
            denominator=args.denominator,
        ),
    )


def _cmd_analytics_toxicity(args: argparse.Namespace) -> int:
    service = _build_service(args)
    return _print(
        args,
        service.toxicity_distribution(_filters(args), denominator=args.denominator),
    )


def _cmd_analytics_series(args: argparse.Namespace) -> int:
    service = _build_service(args)
    if service.has_predictions():
        return _print(
            args,
            service.frame_series(
                _filters(args),
                granularity=args.granularity,
                level=args.level,
                denominator=args.denominator,
            ),
        )
    # Without L1 there are no frame shares to plot, but the volume series is
    # still real: report it instead of an empty answer.
    result = service.volume_series(_filters(args), args.granularity)
    result["provenance"]["warnings"] = list(
        result["provenance"].get("warnings", [])
    ) + ["Sin predicciones: se muestra el volumen, no cuotas de marcos"]
    return _print(args, result)


def _cmd_analytics_search(args: argparse.Namespace) -> int:
    service = _build_service(args)
    return _print(
        args,
        service.search_posts(_filters(args), limit=args.limit, offset=args.offset),
    )


def _cmd_analytics_events(args: argparse.Namespace) -> int:
    events_path = getattr(args, "events", None) or DEFAULT_EVENTS
    timeline = EventTimeline()
    if events_path and Path(events_path).exists():
        timeline = EventTimeline.from_file(events_path)
    events = timeline.in_range(args.start, args.end)
    payload = [event.as_dict() for event in events]
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for event in payload:
            print(f"{event['date']}  {event['id']}: {event['label']}")
    return 0


def add_analytics_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "analytics", help="Consultas analíticas sobre L0 y predicciones"
    )
    analytics_sub = parser.add_subparsers(
        dest="analytics_command", required=True
    )

    def common(sub: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sub.add_argument("--l0", required=True, help="Glob del parquet L0")
        sub.add_argument(
            "--predictions",
            default=None,
            help="Tabla o parquet con predicciones (L1)",
        )
        sub.add_argument("--events", default=None, help="YAML de hitos externos")
        sub.add_argument("--start", default=None, help="Fecha inicial (YYYY-MM-DD)")
        sub.add_argument("--end", default=None, help="Fecha final (YYYY-MM-DD)")
        sub.add_argument("--sources", nargs="*", default=None, help="Orígenes a incluir")
        sub.add_argument("--query", default=None, help="Búsqueda de texto libre")
        sub.add_argument("--frames", nargs="*", default=None, help="Marcos o cabezas")
        sub.add_argument(
            "--level", choices=["fine", "coarse"], default="fine", help="Nivel de marco"
        )
        sub.add_argument("--toxicity-min", type=int, default=None)
        sub.add_argument("--toxicity-max", type=int, default=None)
        sub.add_argument(
            "--denominator",
            choices=["all", "labeled"],
            default="all",
            help="Denominador: todos los posts o solo los predichos",
        )
        sub.add_argument("--json", action="store_true")
        return sub

    p_overview = common(
        analytics_sub.add_parser("overview", help="Volumen del corpus filtrado")
    )
    p_overview.set_defaults(func=_cmd_analytics_overview)

    p_frames = common(
        analytics_sub.add_parser("frames", help="Distribución de marcos")
    )
    p_frames.set_defaults(func=_cmd_analytics_frames)

    p_toxicity = common(
        analytics_sub.add_parser("toxicity", help="Distribución de toxicidad")
    )
    p_toxicity.set_defaults(func=_cmd_analytics_toxicity)

    p_series = common(
        analytics_sub.add_parser("series", help="Serie temporal de marcos")
    )
    p_series.add_argument(
        "--granularity", choices=["month", "week", "day"], default="month"
    )
    p_series.set_defaults(func=_cmd_analytics_series)

    p_search = common(analytics_sub.add_parser("search", help="Búsqueda de posts"))
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--offset", type=int, default=0)
    p_search.set_defaults(func=_cmd_analytics_search)

    p_events = analytics_sub.add_parser("events", help="Hitos externos")
    p_events.add_argument("--events", default=None, help="YAML de hitos externos")
    p_events.add_argument("--start", default=None)
    p_events.add_argument("--end", default=None)
    p_events.add_argument("--json", action="store_true")
    p_events.set_defaults(func=_cmd_analytics_events)

    return parser
