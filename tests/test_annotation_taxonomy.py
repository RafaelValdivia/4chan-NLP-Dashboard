from __future__ import annotations

import pytest

from keklab.annotation.labels import FRAME_LABELS
from keklab.annotation.taxonomy import (
    COARSE_HEADS,
    FINE_TO_COARSE,
    coarse_counts,
    collapse_frames,
)


def test_every_fine_frame_maps_to_a_coarse_head():
    assert set(FINE_TO_COARSE) == set(FRAME_LABELS)
    assert set(FINE_TO_COARSE.values()) == set(COARSE_HEADS)
    assert len(COARSE_HEADS) == 8


def test_collapse_frames_returns_canonical_order_and_deduplicates():
    assert collapse_frames(
        ["sinophobia", "conspiracy", "racism"]
    ) == ["conspiracy", "ethnoracial_prejudice"]

    assert collapse_frames(["antifeminism", "homophobia"]) == [
        "gender_sexuality_prejudice"
    ]


def test_no_frame_is_exclusive_and_maps_to_no_frame():
    assert collapse_frames(["none"]) == ["no_frame"]
    assert collapse_frames(["unclear"]) == ["no_frame"]
    with pytest.raises(ValueError):
        collapse_frames(["none", "conspiracy"])


def test_collapse_requires_at_least_one_frame():
    with pytest.raises(ValueError):
        collapse_frames([])


def test_coarse_counts_cover_every_head():
    counts = coarse_counts(
        [["conspiracy"], ["racism", "ableism"], ["none"]]
    )
    assert counts["conspiracy"] == 1
    assert counts["ethnoracial_prejudice"] == 1
    assert counts["eugenics_ableism"] == 1
    assert counts["no_frame"] == 1
    assert set(counts) == set(COARSE_HEADS)
