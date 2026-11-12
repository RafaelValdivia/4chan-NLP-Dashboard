"""Shared configuration for the dashboard.

The dashboard never re-implements analytics: it reads the same L0 warehouse
and the same predictions as the chatbot, through `keklab.analytics`.
"""

from __future__ import annotations

import os
from pathlib import Path

from keklab.common.paths import CONFIGS_DIR

DEFAULT_L0_GLOB = "/run/media/flynnso/Archivos/l0/month=*/*.parquet"
DEFAULT_EVENTS = CONFIGS_DIR / "events.yaml"


def l0_glob() -> str:
    """Glob of the L0 Parquet warehouse."""
    return os.environ.get("KEKLAB_L0_GLOB", DEFAULT_L0_GLOB)


def predictions_source() -> str | None:
    """Table name or Parquet glob with the L1 predictions, if any."""
    return os.environ.get("KEKLAB_PREDICTIONS", "") or None


def events_path() -> Path:
    """YAML with the curated external milestones."""
    return Path(os.environ.get("KEKLAB_EVENTS", str(DEFAULT_EVENTS)))


def l0_available() -> bool:
    """True when the L0 warehouse exists on disk."""
    import glob

    return bool(glob.glob(l0_glob()))
