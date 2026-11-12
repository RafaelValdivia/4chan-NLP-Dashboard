# Role: environment-driven configuration for the analytics API.
# Connects to: api/app, common/paths, analytics/events.

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keklab.analytics.events import EventTimeline
from keklab.common.paths import CONFIGS_DIR, PROJECT_ROOT

DEFAULT_L0_GLOB = "/run/media/flynnso/Archivos/l0/month=*/*.parquet"
DEFAULT_EVENTS = CONFIGS_DIR / "events.yaml"
DEFAULT_WEB_DIR = PROJECT_ROOT / "web"


@dataclass(frozen=True)
class Settings:
    """Everything the app needs to find the corpus and the frontend."""

    l0_glob: str = DEFAULT_L0_GLOB
    predictions: str | None = None
    events: Path = DEFAULT_EVENTS
    web_dir: Path = DEFAULT_WEB_DIR

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            l0_glob=os.environ.get("KEKLAB_L0_GLOB", DEFAULT_L0_GLOB),
            predictions=os.environ.get("KEKLAB_PREDICTIONS", "") or None,
            events=Path(os.environ.get("KEKLAB_EVENTS", str(DEFAULT_EVENTS))),
            web_dir=Path(os.environ.get("KEKLAB_WEB_DIR", str(DEFAULT_WEB_DIR))),
        )

    # -- corpus -----------------------------------------------------------

    def l0_available(self) -> bool:
        """True when the L0 glob matches at least one Parquet part."""
        return bool(glob.glob(self.l0_glob))

    def predictions_source(self) -> tuple[str | None, str | None]:
        """Split `KEKLAB_PREDICTIONS` into (table, glob)."""
        value = self.predictions
        if not value:
            return None, None
        if value.endswith(".parquet") or "*" in value:
            return None, value
        return value, None

    def events_timeline(self) -> EventTimeline:
        if self.events.exists():
            return EventTimeline.from_file(self.events)
        return EventTimeline()

    # -- data quality -----------------------------------------------------

    def manifest_path(self) -> Path | None:
        """Locate `_l0_manifest.json` next to the L0 warehouse."""
        pattern = self.l0_glob
        if "month=" in pattern:
            root = Path(pattern.split("month=")[0])
        else:
            root = Path(pattern).parent
        manifest = root / "_l0_manifest.json"
        return manifest if manifest.exists() else None

    def manifest(self) -> dict[str, Any] | None:
        path = self.manifest_path()
        if path is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def parts_on_disk(self) -> int:
        return len(glob.glob(self.l0_glob))
