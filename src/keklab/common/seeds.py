# Role: deterministic seeds for sampling and training.
# Connects to: ingest/sample, classic, generative, eval.

from __future__ import annotations

import os
import random

DEFAULT_SEED = 1234


def set_seeds(seed: int | None = None) -> int:
    """
    Seed Python's RNG and, when available, NumPy and PyTorch.

    Returns the seed actually used.
    """
    resolved = int(seed if seed is not None else os.environ.get("KEKLAB_SEED", DEFAULT_SEED))
    random.seed(resolved)

    try:
        import numpy as np  # type: ignore[import-not-found]

        np.random.seed(resolved)
    except ImportError:
        pass

    try:
        import torch  # type: ignore[import-not-found]

        torch.manual_seed(resolved)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(resolved)
    except ImportError:
        pass

    return resolved
