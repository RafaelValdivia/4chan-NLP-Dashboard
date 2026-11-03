from __future__ import annotations

import pytest

from keklab.annotation.agreement import (
    agreement_report,
    cohens_kappa,
    multilabel_f1,
    quadratic_weighted_kappa,
)
from keklab.annotation.schema import AnnotationRecord


def make_annotation(
    post_id: str,
    frames: tuple[str, ...],
    toxicity: int,
    *,
    round: int = 1,
    annotator: str = "tester",
) -> AnnotationRecord:
    return AnnotationRecord(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="fourplebs",
        content_hash=f"hash-{post_id}",
        frame_labels=list(frames),
        toxicity=toxicity,
        annotator=annotator,
        round=round,
        guideline_version="v0",
    )


def test_cohens_kappa_perfect_and_known_value():
    assert cohens_kappa([0, 0, 1, 1], [0, 0, 1, 1]) == 1.0
    # po=0.75, pe=0.5 -> kappa=0.5
    assert cohens_kappa([1, 1, 0, 0], [1, 1, 0, 1]) == pytest.approx(0.5)


def test_cohens_kappa_degenerate_and_validation():
    assert cohens_kappa([1, 1], [1, 1]) == 1.0
    with pytest.raises(ValueError):
        cohens_kappa([1], [1, 0])
    with pytest.raises(ValueError):
        cohens_kappa([], [])


def test_quadratic_weighted_kappa():
    assert quadratic_weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3]) == 1.0

    value = quadratic_weighted_kappa([0, 0, 1, 3], [0, 1, 1, 3])
    assert 0.0 <= value < 1.0

    with pytest.raises(ValueError):
        quadratic_weighted_kappa([0, 4], [0, 1])
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([0], [0], min_rating=1, max_rating=1)


def test_multilabel_f1():
    result = multilabel_f1(
        gold=[{"a"}, {"a", "b"}],
        pred=[{"a"}, {"b"}],
    )

    # micro: tp=2, fp=0, fn=1 -> f1=0.8
    assert result["micro_f1"] == pytest.approx(0.8)
    assert result["per_label"]["a"]["f1"] == pytest.approx(2 / 3)
    assert result["per_label"]["b"]["f1"] == 1.0
    assert result["macro_f1"] == pytest.approx(5 / 6)

    with pytest.raises(ValueError):
        multilabel_f1([{"a"}], [])


def test_agreement_report_for_self_test_retest():
    round1 = [
        make_annotation("1", ("conspiracy", "antifeminism"), 1),
        make_annotation("2", ("none",), 0),
        make_annotation("3", ("rusophobia",), 2),
    ]
    round2 = [
        make_annotation("1", ("conspiracy",), 1, round=2),
        make_annotation("2", ("none",), 1, round=2),
        make_annotation("3", ("rusophobia", "antifeminism"), 2, round=2),
    ]

    report = agreement_report(round1, round2)

    assert report["n_posts"] == 3
    assert report["only_a"] == 0
    assert report["only_b"] == 0
    assert report["frames"]["conspiracy"]["kappa"] == 1.0
    assert report["frames"]["conspiracy"]["positive_both"] == 1
    assert report["frames"]["antifeminism"]["kappa"] < 1.0
    assert report["toxicity"]["n"] == 3
    assert report["toxicity"]["exact_agreement"] == pytest.approx(2 / 3)
    assert 0.0 <= report["toxicity"]["quadratic_weighted_kappa"] < 1.0
    assert report["exact_frame_set_match"] == pytest.approx(1 / 3)
    assert "micro_f1" in report["multilabel_f1"]


def test_agreement_report_without_overlap():
    report = agreement_report(
        [make_annotation("1", ("none",), 0)],
        [make_annotation("2", ("none",), 0, round=2)],
    )
    assert report["n_posts"] == 0
    assert report["only_a"] == 1
    assert report["only_b"] == 1
    assert report["exact_frame_set_match"] == 0.0


def test_agreement_report_rejects_duplicate_keys():
    record = make_annotation("1", ("none",), 0)
    with pytest.raises(ValueError, match="duplicate annotation"):
        agreement_report([record, record], [record])
