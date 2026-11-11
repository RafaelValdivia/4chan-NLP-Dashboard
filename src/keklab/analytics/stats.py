# Role: uncertainty estimates for the dashboard.
# Connects to: analytics/service, analytics/filters.
#
# Shares are reported with Wilson intervals and, when the unit of analysis is
# the post but the correlation unit is the thread, a cluster bootstrap that
# resamples threads.

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

# Cells below this size are shown but flagged as unstable.
MIN_CELL = 30

# z for a 95% interval.
Z_95 = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    low: float
    high: float
    point: float
    method: str

    def as_dict(self) -> dict[str, float | str]:
        return {
            "low": round(self.low, 6),
            "high": round(self.high, 6),
            "point": round(self.point, 6),
            "method": self.method,
        }


def wilson_interval(successes: int, total: int, z: float = Z_95) -> Interval:
    """Wilson score interval for a binomial proportion."""
    if total <= 0:
        return Interval(low=0.0, high=0.0, point=0.0, method="wilson")
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = proportion + z**2 / (2 * total)
    margin = z * math.sqrt(
        (proportion * (1 - proportion) + z**2 / (4 * total)) / total
    )
    return Interval(
        low=max(0.0, (centre - margin) / denominator),
        high=min(1.0, (centre + margin) / denominator),
        point=proportion,
        method="wilson",
    )


def cluster_bootstrap_distribution(
    thread_counts: Sequence[tuple[int, int]],
    *,
    resamples: int = 1000,
    seed: int = 13,
) -> list[float]:
    """Share estimates obtained by resampling whole threads."""
    if not thread_counts:
        return []
    rng = random.Random(seed)
    size = len(thread_counts)
    shares: list[float] = []
    for _ in range(resamples):
        positives = 0
        counts = 0
        for _ in range(size):
            thread_positives, thread_total = thread_counts[rng.randrange(size)]
            positives += thread_positives
            counts += thread_total
        if counts:
            shares.append(positives / counts)
    return shares


def cluster_bootstrap_share(
    thread_counts: Sequence[tuple[int, int]],
    *,
    resamples: int = 1000,
    seed: int = 13,
    alpha: float = 0.05,
) -> Interval:
    """Bootstrap the share of positives resampling whole threads.

    `thread_counts` holds `(positives, total)` per thread. Threads are the
    correlation unit, so resampling them keeps the interval honest when a
    thread contains many posts.
    """
    total_positives = sum(positives for positives, _ in thread_counts)
    total = sum(count for _, count in thread_counts)
    if total <= 0:
        return Interval(low=0.0, high=0.0, point=0.0, method="cluster_bootstrap")
    point = total_positives / total
    shares = cluster_bootstrap_distribution(
        thread_counts, resamples=resamples, seed=seed
    )
    if not shares:
        return Interval(low=point, high=point, point=point, method="cluster_bootstrap")
    shares.sort()
    low = shares[max(0, int(math.floor((alpha / 2) * len(shares))))]
    high = shares[min(len(shares) - 1, int(math.ceil((1 - alpha / 2) * len(shares))) - 1)]
    return Interval(low=low, high=high, point=point, method="cluster_bootstrap")


def attenuation_warning(count: int, label: str = "celda") -> str | None:
    """Warning for cells too small to read as a stable estimate."""
    if count < MIN_CELL:
        return f"{label} con n={count} (< {MIN_CELL}): estimación inestable"
    return None
