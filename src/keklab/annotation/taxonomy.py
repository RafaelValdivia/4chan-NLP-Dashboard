# Role: coarse modeling taxonomy over the fine annotation frames.
# Connects to: annotation/labels, annotation/store, docs/evaluation_protocol.

from __future__ import annotations

from collections import Counter
from typing import Iterable

from keklab.annotation.labels import FRAME_LABELS, normalize_frame_labels

# Order is canonical for exports, stats and modeling heads.
COARSE_HEADS: tuple[str, ...] = (
    "conspiracy",
    "ethnoracial_prejudice",
    "gender_sexuality_prejudice",
    "eugenics_ableism",
    "institutional_distrust",
    "violence_acceleration",
    "meta_topic",
    "no_frame",
)

# Every fine frame maps to exactly one coarse head. A post can still activate
# several heads when it carries several fine frames.
FINE_TO_COARSE: dict[str, str] = {
    "conspiracy": "conspiracy",
    "ethnonationalism": "ethnoracial_prejudice",
    "racism": "ethnoracial_prejudice",
    "antisemitism": "ethnoracial_prejudice",
    "islamophobia": "ethnoracial_prejudice",
    "rusophobia": "ethnoracial_prejudice",
    "sinophobia": "ethnoracial_prejudice",
    "eugenics": "eugenics_ableism",
    "ableism": "eugenics_ableism",
    "antifeminism": "gender_sexuality_prejudice",
    "transphobia": "gender_sexuality_prejudice",
    "homophobia": "gender_sexuality_prejudice",
    "institutional_distrust": "institutional_distrust",
    "violence_glorification": "violence_acceleration",
    "accelerationism": "violence_acceleration",
    "meta_topic": "meta_topic",
    "none": "no_frame",
    "unclear": "no_frame",
}

# Import-time guard: the fine vocabulary and the mapping cannot drift apart.
if set(FINE_TO_COARSE) != set(FRAME_LABELS):
    missing = sorted(set(FRAME_LABELS) - set(FINE_TO_COARSE))
    unknown = sorted(set(FINE_TO_COARSE) - set(FRAME_LABELS))
    raise RuntimeError(
        "FINE_TO_COARSE does not match FRAME_LABELS "
        f"(missing={missing}, unknown={unknown})"
    )
if set(FINE_TO_COARSE.values()) != set(COARSE_HEADS):
    raise RuntimeError("FINE_TO_COARSE must cover exactly the coarse heads")


def collapse_frames(frames: Iterable[str]) -> list[str]:
    """Map fine frame labels to canonical coarse heads.

    The input must be a valid, non-empty annotation label set. Output order
    follows `COARSE_HEADS`, and duplicate heads are collapsed.
    """
    fine = normalize_frame_labels(frames)
    selected = {FINE_TO_COARSE[label] for label in fine}
    return [head for head in COARSE_HEADS if head in selected]


def coarse_counts(frames_per_record: Iterable[Iterable[str]]) -> dict[str, int]:
    """Count coarse heads across annotation frame sets."""
    counts: Counter[str] = Counter()
    for frames in frames_per_record:
        counts.update(collapse_frames(frames))
    return {head: counts.get(head, 0) for head in COARSE_HEADS}
