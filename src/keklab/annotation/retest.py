# Role: deterministic round-2 (self test-retest) subsampling.
# Connects to: annotation/schema, annotation/store, annotation/cli.

from __future__ import annotations

import math
import random
from typing import Iterable

from keklab.annotation.schema import SamplePost, sample_key


def retest_size(total: int, fraction: float) -> int:
    """Number of posts in a retest subset, at least one when total > 0."""
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")
    if total <= 0:
        return 0
    return min(total, max(1, math.floor(total * fraction + 0.5)))


def select_retest(
    samples: Iterable[SamplePost],
    *,
    fraction: float = 0.2,
    seed: int = 13,
) -> list[SamplePost]:
    """Pick a deterministic random subset for a second annotation pass.

    Selection is reproducible for a given (input order, fraction, seed) and
    preserves the original sample order. Duplicate sample keys are ignored.
    """
    unique: list[SamplePost] = []
    seen: set[tuple[str, str, str]] = set()
    for sample in samples:
        key = sample_key(sample)
        if key in seen:
            continue
        seen.add(key)
        unique.append(sample)

    target = retest_size(len(unique), fraction)
    if target == 0:
        return []
    rng = random.Random(seed)
    indices = sorted(rng.sample(range(len(unique)), target))
    return [unique[index] for index in indices]
