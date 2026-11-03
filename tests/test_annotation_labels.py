from __future__ import annotations

import pytest

from keklab.annotation.labels import (
    FRAME_DESCRIPTIONS,
    FRAME_INDEX,
    FRAME_LABELS,
    TARGETED_SEARCH_TERMS,
    apply_frame_toggle,
    normalize_frame_labels,
    parse_frame_numbers,
)


def test_vocabulary_is_unique_and_indexed():
    assert len(FRAME_LABELS) == 18
    assert len(set(FRAME_LABELS)) == len(FRAME_LABELS)
    assert FRAME_INDEX[1] == "conspiracy"
    assert FRAME_INDEX[18] == "unclear"
    assert {
        "racism",
        "eugenics",
        "ableism",
        "transphobia",
        "homophobia",
    } <= set(FRAME_LABELS)


def test_every_frame_has_a_description():
    assert set(FRAME_DESCRIPTIONS) == set(FRAME_LABELS)


def test_targeted_search_terms_use_known_frames():
    assert set(TARGETED_SEARCH_TERMS) <= set(FRAME_LABELS)
    assert {
        "racism",
        "eugenics",
        "ableism",
        "transphobia",
        "homophobia",
    } <= set(TARGETED_SEARCH_TERMS)


def test_normalize_is_case_insensitive_and_deduplicates():
    labels = normalize_frame_labels([" Conspiracy ", "conspiracy", "GENDER"])
    assert labels == ["conspiracy", "gender"]


def test_new_prejudice_frames_are_accepted():
    assert normalize_frame_labels(
        ["Racism", "Eugenics", "Ableism", "Transphobia", "Homophobia"]
    ) == [
        "racism",
        "eugenics",
        "ableism",
        "transphobia",
        "homophobia",
    ]


def test_unknown_label_is_rejected():
    with pytest.raises(ValueError, match="Unknown frame label"):
        normalize_frame_labels(["not_a_frame"])


def test_empty_label_list_is_rejected():
    with pytest.raises(ValueError, match="At least one frame"):
        normalize_frame_labels([])


def test_none_and_unclear_are_exclusive():
    assert normalize_frame_labels(["none"]) == ["none"]
    assert normalize_frame_labels(["unclear"]) == ["unclear"]

    with pytest.raises(ValueError, match="cannot be combined"):
        normalize_frame_labels(["none", "conspiracy"])
    with pytest.raises(ValueError, match="cannot be combined"):
        normalize_frame_labels(["unclear", "gender"])


def test_toggle_frames_and_exclusive_flags():
    selected = apply_frame_toggle([], ["conspiracy", "gender"])
    assert selected == ["conspiracy", "gender"]

    selected = apply_frame_toggle(selected, ["conspiracy"])
    assert selected == ["gender"]

    selected = apply_frame_toggle(selected, ["none"])
    assert selected == ["none"]

    selected = apply_frame_toggle(selected, ["conspiracy"])
    assert selected == ["conspiracy"]

    selected = apply_frame_toggle(selected, ["unclear"])
    assert selected == ["unclear"]


def test_parse_frame_numbers():
    assert parse_frame_numbers("1, 4 18") == [
        "conspiracy",
        "antisemitism",
        "unclear",
    ]
    assert parse_frame_numbers("") == []

    with pytest.raises(ValueError, match="Invalid frame number"):
        parse_frame_numbers("x")
    with pytest.raises(ValueError, match="out of range"):
        parse_frame_numbers("99")
