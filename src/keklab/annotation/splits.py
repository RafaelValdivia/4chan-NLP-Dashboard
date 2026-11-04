# Role: leak-free train/dev/test assignment by thread.
# Connects to: annotation/schema, annotation/cli, docs/evaluation_protocol.

from __future__ import annotations

import math
import random
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from keklab.annotation.schema import SamplePost
from keklab.annotation.store import _atomic_write_rows

SPLIT_NAMES: tuple[str, str, str] = ("train", "dev", "test")


def assign_thread_splits(
    samples: Iterable[SamplePost],
    *,
    ratios: Sequence[float] = (0.6, 0.2, 0.2),
    seed: int = 13,
) -> dict[str, str]:
    """Assign every thread to exactly one split.

    Splitting by `thread_id` prevents posts from the same thread (OP and
    replies) from leaking across train/dev/test. The assignment is
    deterministic for a given input and seed.
    """
    if len(ratios) != len(SPLIT_NAMES):
        raise ValueError(f"ratios must have {len(SPLIT_NAMES)} values")
    if any(value < 0 for value in ratios):
        raise ValueError("ratios must be non-negative")
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("ratios must sum to 1.0")

    threads = sorted({sample.thread_id for sample in samples})
    if not threads:
        return {}

    targets = [int(math.floor(len(threads) * value)) for value in ratios]
    remainder = len(threads) - sum(targets)
    for index in range(remainder):
        targets[index % len(targets)] += 1

    # Keep every requested split non-empty when there are enough threads.
    for index, ratio in enumerate(ratios):
        if ratio > 0 and targets[index] == 0 and len(threads) >= sum(
            1 for value in ratios if value > 0
        ):
            donor = max(range(len(targets)), key=lambda i: targets[i])
            targets[donor] -= 1
            targets[index] += 1

    rng = random.Random(seed)
    shuffled = list(threads)
    rng.shuffle(shuffled)

    assignment: dict[str, str] = {}
    start = 0
    for name, count in zip(SPLIT_NAMES, targets):
        for thread_id in shuffled[start : start + count]:
            assignment[thread_id] = name
        start += count
    return assignment


def split_counts(assignment: dict[str, str]) -> dict[str, int]:
    counts = Counter(assignment.values())
    return {name: counts.get(name, 0) for name in SPLIT_NAMES}


def write_split_manifest(
    assignment: dict[str, str],
    path: str | Path,
) -> Path:
    """Write `{"thread_id", "split"}` rows atomically, sorted by thread."""
    rows = [
        {"thread_id": thread_id, "split": assignment[thread_id]}
        for thread_id in sorted(assignment)
    ]
    return _atomic_write_rows(path, rows)
