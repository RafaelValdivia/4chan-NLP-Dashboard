from __future__ import annotations

import pytest

from keklab.annotation.labels import (
    FRAME_ALIASES,
    FRAME_DESCRIPTIONS,
    FRAME_INDEX,
    FRAME_LABELS,
    RETIRED_FRAME_LABELS,
    TARGETED_SEARCH_TERMS,
    apply_frame_toggle,
    normalize_frame_labels,
    parse_frame_numbers,
)


def test_vocabulary_is_unique_and_indexed():
    assert len(FRAME_LABELS) == 16
    assert len(set(FRAME_LABELS)) == len(FRAME_LABELS)
    assert FRAME_INDEX[1] == "conspiracy"
    assert FRAME_INDEX[16] == "unclear"
    assert {
        "racism",
        "misogyny",
        "transphobia",
        "homophobia",
    } <= set(FRAME_LABELS)
    assert "eugenics" not in FRAME_LABELS
    assert "ableism" not in FRAME_LABELS
    assert "gender" not in FRAME_LABELS
    assert "antifeminism" not in FRAME_LABELS
    assert RETIRED_FRAME_LABELS == {"eugenics", "ableism"}


def test_every_frame_has_a_description():
    assert set(FRAME_DESCRIPTIONS) == set(FRAME_LABELS)


def test_targeted_search_terms_use_known_frames():
    assert set(TARGETED_SEARCH_TERMS) <= set(FRAME_LABELS)
    assert {
        "racism",
        "misogyny",
        "transphobia",
        "homophobia",
    } <= set(TARGETED_SEARCH_TERMS)
    assert "eugenics" not in TARGETED_SEARCH_TERMS
    assert "ableism" not in TARGETED_SEARCH_TERMS


def test_legacy_antifeminism_is_aliased_to_misogyny():
    assert FRAME_ALIASES["antifeminism"] == "misogyny"
    assert normalize_frame_labels(["antifeminism"]) == ["misogyny"]
    assert normalize_frame_labels([" AntiFeminism "]) == ["misogyny"]
    assert apply_frame_toggle([], ["antifeminism"]) == ["misogyny"]


def test_normalize_is_case_insensitive_and_deduplicates():
    labels = normalize_frame_labels(
        [" Conspiracy ", "conspiracy", "MISOGYNY"]
    )
    assert labels == ["conspiracy", "misogyny"]


def test_prejudice_frames_are_accepted():
    assert normalize_frame_labels(
        [
            "Racism",
            "Misogyny",
            "Transphobia",
            "Homophobia",
        ]
    ) == [
        "racism",
        "misogyny",
        "transphobia",
        "homophobia",
    ]


def test_retired_frames_are_dropped_for_legacy_records():
    assert normalize_frame_labels(["eugenics"]) == ["none"]
    assert normalize_frame_labels(["ableism"]) == ["none"]
    assert normalize_frame_labels(["racism", "ableism"]) == ["racism"]
    assert normalize_frame_labels(["ableism", "unclear"]) == ["unclear"]
    assert normalize_frame_labels(["eugenics", "ableism"]) == ["none"]


def test_retired_frames_cannot_be_selected_interactively():
    with pytest.raises(ValueError, match="Unknown frame label"):
        apply_frame_toggle([], ["ableism"])
    with pytest.raises(ValueError, match="Unknown frame label"):
        apply_frame_toggle([], ["eugenics"])


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
        normalize_frame_labels(["unclear", "misogyny"])


def test_toggle_frames_and_exclusive_flags():
    selected = apply_frame_toggle([], ["conspiracy", "misogyny"])
    assert selected == ["conspiracy", "misogyny"]

    selected = apply_frame_toggle(selected, ["conspiracy"])
    assert selected == ["misogyny"]

    selected = apply_frame_toggle(selected, ["none"])
    assert selected == ["none"]

    selected = apply_frame_toggle(selected, ["conspiracy"])
    assert selected == ["conspiracy"]

    selected = apply_frame_toggle(selected, ["unclear"])
    assert selected == ["unclear"]


def test_parse_frame_numbers():
    assert parse_frame_numbers("1, 4 16") == [
        "conspiracy",
        "antisemitism",
        "unclear",
    ]
    assert parse_frame_numbers("") == []

    with pytest.raises(ValueError, match="Invalid frame number"):
        parse_frame_numbers("x")
    with pytest.raises(ValueError, match="out of range"):
        parse_frame_numbers("99")
