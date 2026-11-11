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

# Local model weights are never versioned. `KEKLAB_MODELS_DIR` lets the target
# machine point at a different disk without changing the commands.
MODELS_DIR = Path(os.environ.get("KEKLAB_MODELS_DIR", PROJECT_ROOT / "models" / "gguf"))
DEFAULT_LLM_MODEL = MODELS_DIR / "qwen3-8b-q4_k_m.gguf"

ROTLK_DATASET_ENV = "KEKLAB_ROTLK_DATASET"


def default_rotlk_dataset() -> Path | None:
    """Return the external ROTLK dump path from the environment, if set.

    The dump is intentionally not copied into the repository; point this at
    the mounted archive (for example a `.tar.zst` file).
    """
    value = os.environ.get(ROTLK_DATASET_ENV)
    return Path(value).expanduser() if value else None


def ensure_dirs(*dirs: str | Path) -> None:
    """Create the given directories (and parents) if they do not exist."""
    for directory in dirs:
        Path(directory).expanduser().mkdir(parents=True, exist_ok=True)
