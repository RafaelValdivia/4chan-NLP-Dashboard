# Role: canonical filesystem locations.
# Connects to: ingest, classic, generative, eval, dashboard.

from __future__ import annotations

import os
from pathlib import Path

# src/keklab/common/paths.py -> parents[3] == repository root
PROJECT_ROOT = Path(os.environ.get("KEKLAB_ROOT", Path(__file__).resolve().parents[3]))

DATA_DIR = Path(os.environ.get("KEKLAB_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = Path(os.environ.get("KEKLAB_RAW_DIR", DATA_DIR / "raw"))
PROCESSED_DIR = Path(os.environ.get("KEKLAB_PROCESSED_DIR", DATA_DIR / "processed"))
CACHE_DIR = Path(os.environ.get("KEKLAB_CACHE_DIR", DATA_DIR / "cache"))
CONFIGS_DIR = Path(os.environ.get("KEKLAB_CONFIGS_DIR", PROJECT_ROOT / "configs"))
REPORTS_DIR = Path(os.environ.get("KEKLAB_REPORTS_DIR", PROJECT_ROOT / "reports"))


def ensure_dirs(*dirs: str | Path) -> None:
    """Create the given directories (and parents) if they do not exist."""
    for directory in dirs:
        Path(directory).expanduser().mkdir(parents=True, exist_ok=True)
