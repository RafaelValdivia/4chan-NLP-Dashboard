# Role: external milestones shown on the temporal axis.
# Connects to: analytics/service, dashboard, docs/reporte_progreso.
#
# The events are hand-curated ground truth: they are not model labels and
# never feed the classifier. Automatic extraction from the corpus is a future
# improvement, not a dependency.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml


@dataclass(frozen=True)
class Event:
    event_id: str
    date: str
    label: str
    scope: str = "global"
    note: str = ""
    url: str = ""

    @property
    def year(self) -> int:
        return int(self.date[:4])

    @property
    def month(self) -> str:
        return self.date[:7]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "date": self.date,
            "label": self.label,
            "scope": self.scope,
            "note": self.note,
            "url": self.url,
        }


def _parse_date(value: Any, event_id: str) -> str:
    text = str(value).strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Event {event_id!r} has an invalid date: {value!r}") from exc
    return parsed.isoformat()


class EventTimeline:
    """A curated list of external events, ordered by date."""

    def __init__(self, events: Iterable[Event] | None = None) -> None:
        self._events: list[Event] = sorted(
            events or [], key=lambda event: (event.date, event.event_id)
        )

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)

    @classmethod
    def from_file(cls, path: str | Path) -> "EventTimeline":
        source = Path(path).expanduser()
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        raw_events = payload.get("events") or []
        if not isinstance(raw_events, list):
            raise ValueError(f"{source}: 'events' must be a list")
        events: list[Event] = []
        seen: set[str] = set()
        for raw in raw_events:
            event_id = str(raw.get("id", "")).strip()
            if not event_id:
                raise ValueError(f"{source}: every event needs an 'id'")
            if event_id in seen:
                raise ValueError(f"{source}: duplicated event id {event_id!r}")
            seen.add(event_id)
            events.append(
                Event(
                    event_id=event_id,
                    date=_parse_date(raw.get("date"), event_id),
                    label=str(raw.get("label", event_id)),
                    scope=str(raw.get("scope", "global")),
                    note=str(raw.get("note", "")),
                    url=str(raw.get("url", "")),
                )
            )
        return cls(events)

    def in_range(self, start: str | None = None, end: str | None = None) -> list[Event]:
        selected: list[Event] = []
        for event in self._events:
            if start and event.date < start:
                continue
            if end and event.date > end:
                continue
            selected.append(event)
        return selected

    def as_list(self) -> list[dict[str, Any]]:
        return [event.as_dict() for event in self._events]
