# Role: shared analytics service used by the dashboard and the chatbot.
# Connects to: analytics/filters, analytics/stats, analytics/events, ingest/l0.
#
# The dashboard and the chatbot must not reimplement analysis: both call this
# service. Every response carries provenance (n, denominator, run_id, warnings)
# so a number can always be traced back to the data it came from.

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from keklab.analytics.events import Event, EventTimeline
from keklab.analytics.filters import Filters, where_clause
from keklab.analytics.stats import (
    MIN_CELL,
    attenuation_warning,
    cluster_bootstrap_distribution,
    wilson_interval,
)
from keklab.annotation.labels import FRAME_LABELS
from keklab.annotation.taxonomy import COARSE_HEADS

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PERIOD_FORMATS = {
    "month": "%Y-%m",
    "week": "%Y-W%W",
    "day": "%Y-%m-%d",
}


def _quote(value: str) -> str:
    return str(value).replace("'", "''")


def _safe_identifier(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


class AnalyticsService:
    """Queries over L0 (canonical posts) and L1 (model predictions)."""

    def __init__(
        self,
        con: Any,
        *,
        l0_glob: str | Path | None = None,
        l0_table: str = "l0",
        predictions_table: str | None = None,
        events: EventTimeline | None = None,
        run_id: str | None = None,
        seed: int = 13,
        bootstrap_resamples: int = 1000,
    ) -> None:
        self.con = con
        self._posts_source = (
            f"read_parquet('{_quote(str(Path(l0_glob).expanduser()))}')"
            if l0_glob is not None
            else _safe_identifier(l0_table)
        )
        self._predictions_table = (
            _safe_identifier(predictions_table) if predictions_table else None
        )
        self.events = events or EventTimeline()
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.seed = seed
        self.bootstrap_resamples = bootstrap_resamples

    # -- infrastructure ---------------------------------------------------

    def has_predictions(self) -> bool:
        if self._predictions_table is None:
            return False
        rows = self.con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?",
            [self._predictions_table],
        ).fetchall()
        return bool(rows and rows[0][0])

    def _run(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        return self.con.execute(sql, list(params or [])).fetchall()

    def _posts_where(self, filters: Filters) -> tuple[str, list[Any]]:
        return where_clause(filters.post_predicates("p"))

    def _scoped_join(self, filters: Filters) -> tuple[str, str, list[Any]]:
        """FROM/WHERE for posts joined with predictions."""
        if self._predictions_table is None:
            raise RuntimeError("No predictions table configured")
        combined_sql, combined_params = where_clause(
            list(filters.post_predicates("p")) + list(filters.prediction_predicates("q"))
        )
        return (
            f"FROM {self._posts_source} p "
            f"JOIN {self._predictions_table} q ON q.post_id = p.post_id",
            combined_sql,
            combined_params,
        )

    def _provenance(
        self,
        filters: Filters,
        *,
        n: int,
        denominator: int,
        warnings: Iterable[str] = (),
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "filters": filters.as_dict(),
            "n": n,
            "denominator": denominator,
            "warnings": list(warnings),
        }
        if extra:
            payload.update(extra)
        return payload

    # -- corpus level -----------------------------------------------------

    def overview(self, filters: Filters) -> dict[str, Any]:
        """Volume and shape of the slice under analysis."""
        where_sql, params = self._posts_where(filters)
        sql = f"""
            SELECT count(*) AS posts,
                   count(DISTINCT p.thread_id) AS threads,
                   count(*) FILTER (WHERE p.is_op) AS op_posts,
                   count(*) FILTER (WHERE coalesce(p.text_clean, '') = '') AS empty_posts,
                   avg(length(coalesce(p.text_clean, ''))) AS avg_length,
                   median(length(coalesce(p.text_clean, ''))) AS median_length,
                   count(DISTINCT strftime(p.timestamp_utc, '%Y-%m')) AS months,
                   min(p.timestamp_utc) AS first_post,
                   max(p.timestamp_utc) AS last_post
            FROM {self._posts_source} p
            {f'WHERE {where_sql}' if where_sql else ''}
        """
        row = self._run(sql, params)[0]
        posts, threads, op_posts, empty_posts = int(row[0]), int(row[1]), int(row[2]), int(row[3])
        warnings: list[str] = []
        if posts == 0:
            warnings.append("El filtro no devuelve ningún post")
        if empty_posts:
            warnings.append(
                f"{empty_posts} posts con texto limpio vacío incluidos en el denominador"
            )
        if self.has_predictions():
            labeled, coverage = self._labeled_counts(filters)
            warnings.extend(
                f"cobertura de predicciones: {coverage:.1%} de los posts del filtro"
                for _ in [0]
                if coverage < 1.0
            )
        else:
            labeled = 0
            warnings.append("Sin tabla de predicciones: solo métricas de volumen")
        return {
            "data": {
                "posts": posts,
                "threads": threads,
                "op_posts": op_posts,
                "empty_posts": empty_posts,
                "avg_length": round(float(row[4]), 2) if row[4] is not None else None,
                "median_length": float(row[5]) if row[5] is not None else None,
                "months": int(row[6]),
                "first_post": row[7].isoformat() if row[7] else None,
                "last_post": row[8].isoformat() if row[8] else None,
                "labeled_posts": labeled,
            },
            "provenance": self._provenance(
                filters, n=posts, denominator=posts, warnings=warnings
            ),
        }

    def volume_series(
        self, filters: Filters, granularity: str = "month"
    ) -> dict[str, Any]:
        """Posts and threads per period."""
        if granularity not in _PERIOD_FORMATS:
            raise ValueError(
                f"Unknown granularity {granularity!r}; expected one of: "
                f"{', '.join(_PERIOD_FORMATS)}"
            )
        where_sql, params = self._posts_where(filters)
        sql = f"""
            SELECT strftime(p.timestamp_utc, '{_PERIOD_FORMATS[granularity]}') AS bucket,
                   count(*) AS posts,
                   count(DISTINCT p.thread_id) AS threads,
                   count(*) FILTER (WHERE p.is_op) AS op_posts
            FROM {self._posts_source} p
            {f'WHERE {where_sql}' if where_sql else ''}
            GROUP BY bucket
            ORDER BY bucket
        """
        rows = self._run(sql, params)
        series = [
            {
                "period": row[0],
                "posts": int(row[1]),
                "threads": int(row[2]),
                "op_posts": int(row[3]),
            }
            for row in rows
        ]
        total = sum(item["posts"] for item in series)
        return {
            "data": series,
            "provenance": self._provenance(
                filters,
                n=total,
                denominator=total,
                warnings=[] if series else ["Sin datos en el rango pedido"],
                extra={"granularity": granularity},
            ),
        }

    def search_posts(
        self,
        filters: Filters,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Free-text search over the post text (removable module)."""
        where_sql, params = self._posts_where(filters)
        sql = f"""
            SELECT p.post_id,
                   p.thread_id,
                   p.timestamp_utc,
                   p.is_op,
                   p.text_clean,
                   p.subject
            FROM {self._posts_source} p
            {f'WHERE {where_sql}' if where_sql else ''}
            ORDER BY p.timestamp_utc DESC, p.post_id DESC
            LIMIT ? OFFSET ?
        """
        rows = self._run(sql, params + [int(limit), int(offset)])
        results = [
            {
                "post_id": int(row[0]),
                "thread_id": int(row[1]),
                "timestamp_utc": row[2].isoformat() if row[2] else None,
                "is_op": bool(row[3]),
                "text": row[4],
                "subject": row[5],
            }
            for row in rows
        ]
        return {
            "data": results,
            "provenance": self._provenance(
                filters,
                n=len(results),
                denominator=None,
                warnings=[],
                extra={"limit": int(limit), "offset": int(offset)},
            ),
        }

    # -- label level ------------------------------------------------------

    def _labeled_counts(self, filters: Filters) -> tuple[int, float]:
        """Posts with predictions inside the filter and the coverage share."""
        join_sql, where_sql, params = self._scoped_join(filters)
        labeled = int(
            self._run(
                f"SELECT count(*) {join_sql} {f'WHERE {where_sql}' if where_sql else ''}",
                params,
            )[0][0]
        )
        posts = self._count_posts(filters)
        coverage = (labeled / posts) if posts else 0.0
        return labeled, coverage

    def _count_posts(self, filters: Filters) -> int:
        where_sql, params = self._posts_where(filters)
        row = self._run(
            f"SELECT count(*) FROM {self._posts_source} p "
            f"{f'WHERE {where_sql}' if where_sql else ''}",
            params,
        )[0]
        return int(row[0])

    def _thread_label_counts(
        self, filters: Filters, level: str
    ) -> tuple[dict[str, int], dict[str, list[tuple[int, int]]], int]:
        """Positives per label, per-thread totals and the labeled post count.

        Returns `(per_label, thread_counts, labeled_posts)`. `thread_counts`
        maps a label to `(positives, total)` pairs, one per thread.
        """
        column = "coarse_heads" if level == "coarse" else "frame_labels"
        join_sql, where_sql, params = self._scoped_join(filters)
        sql = f"""
            WITH scoped AS (
                SELECT p.thread_id AS thread_id, q.{column} AS values
                {join_sql}
                {f'WHERE {where_sql}' if where_sql else ''}
            ),
            exploded AS (
                SELECT thread_id, unnest(values) AS value FROM scoped
            )
            SELECT thread_id, value, count(*) AS n
            FROM exploded
            GROUP BY GROUPING SETS ((thread_id, value), (thread_id))
        """
        rows = self._run(sql, params)

        per_label: dict[str, int] = {}
        thread_totals: dict[Any, int] = {}
        per_thread_label: dict[tuple[Any, str], int] = {}
        for thread_id, value, count in rows:
            count = int(count)
            if value is None:
                thread_totals[thread_id] = count
                continue
            per_label[value] = per_label.get(value, 0) + count
            per_thread_label[(thread_id, value)] = count

        labels = COARSE_HEADS if level == "coarse" else FRAME_LABELS
        thread_counts: dict[str, list[tuple[int, int]]] = {}
        for label in labels:
            pairs = [
                (per_thread_label.get((thread_id, label), 0), total)
                for thread_id, total in thread_totals.items()
            ]
            thread_counts[label] = pairs
        labeled_posts = sum(thread_totals.values())
        return per_label, thread_counts, labeled_posts

    def frame_distribution(
        self,
        filters: Filters,
        *,
        level: str = "fine",
        denominator: str = "all",
        bootstrap: bool = True,
    ) -> dict[str, Any]:
        """Share of posts carrying each frame, with uncertainty."""
        if level not in ("fine", "coarse"):
            raise ValueError("level must be 'fine' or 'coarse'")
        if denominator not in ("all", "labeled"):
            raise ValueError("denominator must be 'all' or 'labeled'")
        if not self.has_predictions():
            return {
                "data": [],
                "provenance": self._provenance(
                    filters,
                    n=0,
                    denominator=0,
                    warnings=["Sin tabla de predicciones: no hay distribución de marcos"],
                ),
            }

        per_label, thread_counts, labeled_posts = self._thread_label_counts(
            filters, level
        )
        posts = self._count_posts(filters)
        base = posts if denominator == "all" else labeled_posts
        labels = COARSE_HEADS if level == "coarse" else FRAME_LABELS

        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        for label in labels:
            positives = per_label.get(label, 0)
            share = (positives / base) if base else 0.0
            interval = wilson_interval(positives, base)
            entry: dict[str, Any] = {
                "label": label,
                "count": positives,
                "share": round(share, 6),
                "wilson": interval.as_dict(),
            }
            if bootstrap and thread_counts.get(label):
                shares = cluster_bootstrap_distribution(
                    thread_counts[label],
                    resamples=self.bootstrap_resamples,
                    seed=self.seed,
                )
                if shares:
                    shares.sort()
                    entry["bootstrap"] = {
                        "low": round(shares[int(0.025 * len(shares))], 6),
                        "high": round(shares[min(len(shares) - 1, int(0.975 * len(shares)))], 6),
                        "method": "cluster_bootstrap_thread",
                    }
            warning = attenuation_warning(positives, f"marco {label}")
            if warning:
                warnings.append(warning)
            rows.append(entry)

        coverage = (labeled_posts / posts) if posts else 0.0
        if coverage < 1.0:
            warnings.append(
                f"solo el {coverage:.1%} de los posts del filtro tiene predicción"
            )
        return {
            "data": rows,
            "provenance": self._provenance(
                filters,
                n=labeled_posts,
                denominator=base,
                warnings=warnings,
                extra={
                    "level": level,
                    "denominator_mode": denominator,
                    "labeled_posts": labeled_posts,
                    "posts_in_scope": posts,
                    "coverage": round(coverage, 6),
                },
            ),
        }

    def toxicity_distribution(
        self,
        filters: Filters,
        *,
        denominator: str = "all",
    ) -> dict[str, Any]:
        """Ordinal toxicity distribution and the share of toxic posts."""
        if not self.has_predictions():
            return {
                "data": {"levels": [], "toxic_share": None},
                "provenance": self._provenance(
                    filters,
                    n=0,
                    denominator=0,
                    warnings=["Sin tabla de predicciones: no hay distribución de toxicidad"],
                ),
            }
        join_sql, where_sql, params = self._scoped_join(filters)
        rows = self._run(
            f"""
            SELECT q.toxicity AS level, count(*) AS n
            {join_sql}
            {f'WHERE {where_sql}' if where_sql else ''}
            GROUP BY level
            ORDER BY level
            """,
            params,
        )
        counts = {int(row[0]): int(row[1]) for row in rows if row[0] is not None}
        labeled_posts = sum(counts.values())
        posts = self._count_posts(filters)
        base = posts if denominator == "all" else labeled_posts

        levels = []
        warnings: list[str] = []
        for level in range(4):
            count = counts.get(level, 0)
            warning = attenuation_warning(count, f"toxicidad {level}")
            if warning:
                warnings.append(warning)
            levels.append(
                {
                    "level": level,
                    "count": count,
                    "share": round(count / base, 6) if base else 0.0,
                    "wilson": wilson_interval(count, base).as_dict(),
                }
            )

        toxic = sum(counts.get(level, 0) for level in (2, 3))
        coverage = (labeled_posts / posts) if posts else 0.0
        if coverage < 1.0:
            warnings.append(
                f"solo el {coverage:.1%} de los posts del filtro tiene predicción"
            )
        return {
            "data": {
                "levels": levels,
                "toxic_share": round(toxic / base, 6) if base else 0.0,
                "toxic_count": toxic,
                "toxic_wilson": wilson_interval(toxic, base).as_dict(),
            },
            "provenance": self._provenance(
                filters,
                n=labeled_posts,
                denominator=base,
                warnings=warnings,
                extra={
                    "denominator_mode": denominator,
                    "labeled_posts": labeled_posts,
                    "posts_in_scope": posts,
                    "coverage": round(coverage, 6),
                },
            ),
        }

    def frame_series(
        self,
        filters: Filters,
        *,
        granularity: str = "month",
        level: str = "fine",
        denominator: str = "all",
    ) -> dict[str, Any]:
        """Frame shares over time, with the events of each period."""
        if granularity not in _PERIOD_FORMATS:
            raise ValueError(
                f"Unknown granularity {granularity!r}; expected one of: "
                f"{', '.join(_PERIOD_FORMATS)}"
            )
        if not self.has_predictions():
            return {
                "data": [],
                "provenance": self._provenance(
                    filters,
                    n=0,
                    denominator=0,
                    warnings=["Sin tabla de predicciones: no hay serie de marcos"],
                ),
            }
        column = "coarse_heads" if level == "coarse" else "frame_labels"
        join_sql, where_sql, params = self._scoped_join(filters)
        rows = self._run(
            f"""
            WITH scoped AS (
                SELECT strftime(p.timestamp_utc, '{_PERIOD_FORMATS[granularity]}') AS bucket,
                       q.{column} AS values
                {join_sql}
                {f'WHERE {where_sql}' if where_sql else ''}
            ),
            exploded AS (
                SELECT bucket, unnest(values) AS value FROM scoped
            )
            SELECT bucket, value, count(*) AS n
            FROM exploded
            GROUP BY bucket, value
            ORDER BY bucket, value
            """,
            params,
        )

        post_rows = self._run(
            f"""
            SELECT strftime(p.timestamp_utc, '{_PERIOD_FORMATS[granularity]}') AS bucket,
                   count(*) AS posts
            FROM {self._posts_source} p
            {f'WHERE {self._posts_where(filters)[0]}' if self._posts_where(filters)[0] else ''}
            GROUP BY bucket
            ORDER BY bucket
            """,
            self._posts_where(filters)[1],
        )
        posts_by_period = {row[0]: int(row[1]) for row in post_rows}
        labeled_rows = self._run(
            f"""
            SELECT strftime(p.timestamp_utc, '{_PERIOD_FORMATS[granularity]}') AS bucket,
                   count(*) AS posts
            {join_sql}
            {f'WHERE {where_sql}' if where_sql else ''}
            GROUP BY bucket
            """,
            params,
        )
        labeled_by_period = {row[0]: int(row[1]) for row in labeled_rows}

        counts: dict[tuple[str, str], int] = {}
        for period, value, count in rows:
            if value is None:
                continue
            counts[(period, value)] = int(count)

        periods = sorted(set(posts_by_period) | set(labeled_by_period))
        series: list[dict[str, Any]] = []
        for period in periods:
            base = (
                posts_by_period.get(period, 0)
                if denominator == "all"
                else labeled_by_period.get(period, 0)
            )
            entry = {
                "period": period,
                "posts": posts_by_period.get(period, 0),
                "labeled_posts": labeled_by_period.get(period, 0),
                "denominator": base,
                "frames": [],
            }
            for value, count in sorted(counts.items()):
                if value[0] != period:
                    continue
                label = value[1]
                entry["frames"].append(
                    {
                        "label": label,
                        "count": count,
                        "share": round(count / base, 6) if base else 0.0,
                    }
                )
            series.append(entry)

        events = self.events.in_range(filters.start, filters.end)
        return {
            "data": {"series": series, "events": [event.as_dict() for event in events]},
            "provenance": self._provenance(
                filters,
                n=sum(labeled_by_period.values()),
                denominator=sum(posts_by_period.values()),
                warnings=[],
                extra={
                    "granularity": granularity,
                    "level": level,
                    "denominator_mode": denominator,
                },
            ),
        }

    # -- comparison -------------------------------------------------------

    def compare(
        self,
        baseline: Filters,
        target: Filters,
        *,
        level: str = "fine",
        denominator: str = "all",
    ) -> dict[str, Any]:
        """Compare two windows frame by frame."""
        left = self.frame_distribution(
            baseline, level=level, denominator=denominator
        )
        right = self.frame_distribution(target, level=level, denominator=denominator)
        left_rows = {row["label"]: row for row in left["data"]}
        right_rows = {row["label"]: row for row in right["data"]}

        rows: list[dict[str, Any]] = []
        for label in left_rows:
            base_row = left_rows[label]
            target_row = right_rows.get(label, {"count": 0, "share": 0.0})
            delta = target_row["share"] - base_row["share"]
            rows.append(
                {
                    "label": label,
                    "baseline_count": base_row["count"],
                    "baseline_share": base_row["share"],
                    "target_count": target_row.get("count", 0),
                    "target_share": target_row.get("share", 0.0),
                    "delta": round(delta, 6),
                    "baseline_wilson": base_row["wilson"],
                    "target_wilson": target_row.get("wilson"),
                }
            )

        warnings = list(left["provenance"]["warnings"]) + list(
            right["provenance"]["warnings"]
        )
        return {
            "data": rows,
            "provenance": self._provenance(
                target,
                n=right["provenance"]["n"],
                denominator=right["provenance"]["denominator"],
                warnings=warnings,
                extra={
                    "baseline": left["provenance"],
                    "target": right["provenance"],
                    "level": level,
                    "denominator_mode": denominator,
                },
            ),
        }

    # -- events -----------------------------------------------------------

    def events_between(self, start: str | None = None, end: str | None = None) -> list[Event]:
        return self.events.in_range(start, end)
