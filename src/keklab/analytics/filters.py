# Role: filter objects shared by the dashboard, the chatbot and the CLI.
# Connects to: analytics/service, ingest/l0, annotation/taxonomy.
#
# Filters are declarative. The service turns them into SQL predicates so the
# UI never has to build queries itself.

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Iterable

FRAME_LEVELS: tuple[str, ...] = ("fine", "coarse")


def _as_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    # Accept a full timestamp and keep only the day part.
    return text[:10]


@dataclass(frozen=True)
class Filters:
    """A reproducible description of the slice of the corpus under analysis."""

    start: str | None = None
    end: str | None = None
    sources: tuple[str, ...] = ()
    periods: tuple[str, ...] = ()
    is_op: bool | None = None
    min_text_length: int | None = None
    query: str | None = None
    frames: tuple[str, ...] = ()
    frame_level: str = "fine"
    toxicity_min: int | None = None
    toxicity_max: int | None = None
    thread_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _as_iso_date(self.start))
        object.__setattr__(self, "end", _as_iso_date(self.end))
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "periods", tuple(self.periods))
        object.__setattr__(self, "frames", tuple(self.frames))
        object.__setattr__(self, "thread_ids", tuple(str(tid) for tid in self.thread_ids))
        if self.frame_level not in FRAME_LEVELS:
            raise ValueError(
                f"Unknown frame level {self.frame_level!r}; expected one of: "
                f"{', '.join(FRAME_LEVELS)}"
            )
        if self.start and self.end and self.start > self.end:
            raise ValueError(f"start {self.start} is after end {self.end}")
        if self.toxicity_min is not None and not 0 <= self.toxicity_min <= 3:
            raise ValueError("toxicity_min must be between 0 and 3")
        if self.toxicity_max is not None and not 0 <= self.toxicity_max <= 3:
            raise ValueError("toxicity_max must be between 0 and 3")

    # -- derived views ----------------------------------------------------

    def with_overrides(self, **overrides: Any) -> "Filters":
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "sources": list(self.sources),
            "periods": list(self.periods),
            "is_op": self.is_op,
            "min_text_length": self.min_text_length,
            "query": self.query,
            "frames": list(self.frames),
            "frame_level": self.frame_level,
            "toxicity_min": self.toxicity_min,
            "toxicity_max": self.toxicity_max,
            "thread_ids": list(self.thread_ids),
        }

    def describe(self) -> str:
        parts: list[str] = []
        if self.start or self.end:
            parts.append(f"{self.start or 'inicio'}→{self.end or 'fin'}")
        if self.sources:
            parts.append(f"fuentes={','.join(self.sources)}")
        if self.periods:
            parts.append(f"periodos={','.join(self.periods)}")
        if self.frames:
            level = "cabeceras" if self.frame_level == "coarse" else "marcos"
            parts.append(f"{level}={','.join(self.frames)}")
        if self.query:
            parts.append(f"texto~{self.query!r}")
        if self.toxicity_min is not None or self.toxicity_max is not None:
            parts.append(
                f"toxicidad={self.toxicity_min if self.toxicity_min is not None else 0}"
                f"-{self.toxicity_max if self.toxicity_max is not None else 3}"
            )
        return ", ".join(parts) if parts else "sin filtros"

    # -- SQL --------------------------------------------------------------

    def post_predicates(self, alias: str = "p") -> list[tuple[str, list[Any]]]:
        """Predicates that only need the L0 post columns."""
        predicates: list[tuple[str, list[Any]]] = []
        if self.start:
            predicates.append((f"{alias}.timestamp_utc >= ?", [f"{self.start} 00:00:00+00"]))
        if self.end:
            predicates.append((f"{alias}.timestamp_utc < ?", [f"{self.end} 23:59:59.999999+00"]))
        if self.sources:
            placeholders = ", ".join("?" for _ in self.sources)
            predicates.append((f"{alias}.source IN ({placeholders})", list(self.sources)))
        if self.periods:
            placeholders = ", ".join("?" for _ in self.periods)
            predicates.append((f"{alias}.period IN ({placeholders})", list(self.periods)))
        if self.is_op is not None:
            predicates.append((f"{alias}.is_op = ?", [self.is_op]))
        if self.min_text_length is not None:
            predicates.append(
                (f"length({alias}.text_clean) >= ?", [int(self.min_text_length)])
            )
        if self.query:
            predicates.append((f"{alias}.text_clean ILIKE ?", [f"%{self.query}%"]))
        if self.thread_ids:
            placeholders = ", ".join("?" for _ in self.thread_ids)
            predicates.append((f"CAST({alias}.thread_id AS VARCHAR) IN ({placeholders})", list(self.thread_ids)))
        return predicates

    def prediction_predicates(self, alias: str = "q") -> list[tuple[str, list[Any]]]:
        """Predicates that need the L1 prediction columns."""
        predicates: list[tuple[str, list[Any]]] = []
        if self.frames:
            column = (
                f"{alias}.coarse_heads" if self.frame_level == "coarse" else f"{alias}.frame_labels"
            )
            conditions = " OR ".join(f"list_contains({column}, ?)" for _ in self.frames)
            predicates.append((f"({conditions})", list(self.frames)))
        if self.toxicity_min is not None:
            predicates.append((f"{alias}.toxicity >= ?", [int(self.toxicity_min)]))
        if self.toxicity_max is not None:
            predicates.append((f"{alias}.toxicity <= ?", [int(self.toxicity_max)]))
        return predicates


def where_clause(
    predicates: Iterable[tuple[str, list[Any]]],
) -> tuple[str, list[Any]]:
    """Join predicates into a WHERE fragment and a flat parameter list."""
    fragments: list[str] = []
    params: list[Any] = []
    for sql, values in predicates:
        fragments.append(sql)
        params.extend(values)
    if not fragments:
        return "", []
    return " AND ".join(fragments), params
