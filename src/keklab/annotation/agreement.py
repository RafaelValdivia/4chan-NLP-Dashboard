# Role: annotation agreement metrics (self test-retest, kappa, multi-label F1).
# Connects to: annotation/schema, annotation/labels, annotation/cli.

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Sequence

from keklab.annotation.labels import FRAME_LABELS
from keklab.annotation.schema import annotation_sample_key
from keklab.formal.schema import Annotation


# ---------------------------------------------------------------------------
# Nominal agreement
# ---------------------------------------------------------------------------
def cohens_kappa(
    a: Sequence[Any],
    b: Sequence[Any],
    *,
    labels: Sequence[Any] | None = None,
) -> float:
    """Cohen's kappa for two equally long nominal sequences.

    Degenerate case: when expected agreement is 1.0, kappa is undefined.
    Return 1.0 if observed agreement is also 1.0, otherwise 0.0.
    """
    if len(a) != len(b):
        raise ValueError("a and b must have the same length")
    n = len(a)
    if n == 0:
        raise ValueError("cannot compute kappa on empty sequences")

    categories = list(labels) if labels is not None else sorted(
        set(a) | set(b), key=str
    )
    index = {value: position for position, value in enumerate(categories)}
    matrix = [[0] * len(categories) for _ in categories]
    for left, right in zip(a, b):
        matrix[index[left]][index[right]] += 1

    observed = sum(matrix[i][i] for i in range(len(categories))) / n
    rows = [sum(row) for row in matrix]
    cols = [sum(matrix[i][j] for i in range(len(categories))) for j in range(len(categories))]
    expected = sum(row * col for row, col in zip(rows, cols)) / (n * n)

    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def quadratic_weighted_kappa(
    a: Sequence[int],
    b: Sequence[int],
    *,
    min_rating: int = 0,
    max_rating: int = 3,
) -> float:
    """Quadratic weighted kappa for ordinal ratings."""
    if len(a) != len(b):
        raise ValueError("a and b must have the same length")
    n = len(a)
    if n == 0:
        raise ValueError("cannot compute kappa on empty sequences")
    if max_rating <= min_rating:
        raise ValueError("max_rating must be greater than min_rating")

    size = max_rating - min_rating + 1
    for value in list(a) + list(b):
        if not isinstance(value, int) or not (min_rating <= value <= max_rating):
            raise ValueError(
                f"rating {value!r} outside [{min_rating}, {max_rating}]"
            )

    observed = [[0] * size for _ in range(size)]
    for left, right in zip(a, b):
        observed[left - min_rating][right - min_rating] += 1

    rows = [sum(row) for row in observed]
    cols = [sum(observed[i][j] for i in range(size)) for j in range(size)]
    expected = [[rows[i] * cols[j] / n for j in range(size)] for i in range(size)]

    span = max_rating - min_rating
    numerator = 0.0
    denominator = 0.0
    for i in range(size):
        for j in range(size):
            weight = ((i - j) ** 2) / (span**2)
            numerator += weight * observed[i][j]
            denominator += weight * expected[i][j]

    if denominator == 0.0:
        return 1.0 if numerator == 0.0 else 0.0
    return 1.0 - numerator / denominator


# ---------------------------------------------------------------------------
# Multi-label F1
# ---------------------------------------------------------------------------
def multilabel_f1(
    gold: Sequence[Iterable[str]],
    pred: Sequence[Iterable[str]],
) -> dict[str, Any]:
    """Per-label, micro and macro F1 for multi-label sets.

    Labels absent from both gold and prediction are excluded from the macro
    average; this avoids penalising rare labels that the sample never uses.
    """
    if len(gold) != len(pred):
        raise ValueError("gold and pred must have the same length")
    if not gold:
        raise ValueError("cannot compute F1 on empty sequences")

    gold_sets = [set(item) for item in gold]
    pred_sets = [set(item) for item in pred]
    labels = sorted(set().union(*gold_sets, *pred_sets)) if gold_sets else []

    per_label: dict[str, dict[str, float | int]] = {}
    tp_total = fp_total = fn_total = 0
    for label in labels:
        tp = sum(1 for g, p in zip(gold_sets, pred_sets) if label in g and label in p)
        fp = sum(1 for g, p in zip(gold_sets, pred_sets) if label not in g and label in p)
        fn = sum(1 for g, p in zip(gold_sets, pred_sets) if label in g and label not in p)
        tp_total += tp
        fp_total += fp
        fn_total += fn

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_label[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": tp + fn,
            "predicted": tp + fp,
        }

    micro_precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else 0.0
    micro_recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if (micro_precision + micro_recall)
        else 0.0
    )
    macro_f1 = (
        sum(item["f1"] for item in per_label.values()) / len(per_label)
        if per_label
        else 0.0
    )

    return {
        "per_label": per_label,
        "micro_f1": micro_f1,
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "macro_f1": macro_f1,
        "labels_evaluated": labels,
    }


# ---------------------------------------------------------------------------
# Annotation-level agreement
# ---------------------------------------------------------------------------
RecordKey = tuple[str, str | None, str | None]


def _records_by_sample(records: Iterable[Annotation]) -> dict[RecordKey, Annotation]:
    result: dict[RecordKey, Annotation] = {}
    for record in records:
        key = annotation_sample_key(record)
        if key in result:
            raise ValueError(
                "duplicate annotation for "
                f"post={key[0]} thread={key[1]} source={key[2]}"
            )
        result[key] = record
    return result


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set & right_set) / len(left_set | right_set)


def _frame_agreement(
    left: Sequence[Annotation],
    right: Sequence[Annotation],
    label: str,
) -> dict[str, Any]:
    y_left = [1 if label in record.frame_labels else 0 for record in left]
    y_right = [1 if label in record.frame_labels else 0 for record in right]
    return {
        "kappa": cohens_kappa(y_left, y_right, labels=[0, 1]),
        "agreement": sum(
            1 for a, b in zip(y_left, y_right) if a == b
        )
        / len(left),
        "positive_a": sum(y_left),
        "positive_b": sum(y_right),
        "positive_both": sum(1 for a, b in zip(y_left, y_right) if a and b),
    }


def agreement_report(
    annotations_a: Iterable[Annotation],
    annotations_b: Iterable[Annotation],
) -> dict[str, Any]:
    """Compare two annotation passes over the same posts.

    Intended for self test-retest: pass `round=1` and `round=2` files.
    """
    by_a = _records_by_sample(annotations_a)
    by_b = _records_by_sample(annotations_b)
    common: list[RecordKey] = sorted(set(by_a) & set(by_b))

    left = [by_a[key] for key in common]
    right = [by_b[key] for key in common]

    n = len(common)
    frames = {
        label: (
            _frame_agreement(left, right, label)
            if n
            else {
                "kappa": 0.0,
                "agreement": 0.0,
                "positive_a": 0,
                "positive_b": 0,
                "positive_both": 0,
            }
        )
        for label in FRAME_LABELS
    }

    active = [
        label
        for label, data in frames.items()
        if data["positive_a"] or data["positive_b"]
    ]
    macro_kappa = (
        sum(frames[label]["kappa"] for label in active) / len(active)
        if active
        else 0.0
    )

    toxicity_a = [
        record.toxicity for record in left if record.toxicity is not None
    ]
    toxicity_b = [
        record.toxicity for record in right if record.toxicity is not None
    ]
    toxicity_pairs = [
        (record_a.toxicity, record_b.toxicity)
        for record_a, record_b in zip(left, right)
        if record_a.toxicity is not None and record_b.toxicity is not None
    ]
    if toxicity_pairs:
        tox_a = [pair[0] for pair in toxicity_pairs]
        tox_b = [pair[1] for pair in toxicity_pairs]
        toxicity = {
            "n": len(toxicity_pairs),
            "quadratic_weighted_kappa": quadratic_weighted_kappa(tox_a, tox_b),
            "exact_agreement": sum(1 for a, b in toxicity_pairs if a == b)
            / len(toxicity_pairs),
            "mean_absolute_error": sum(abs(a - b) for a, b in toxicity_pairs)
            / len(toxicity_pairs),
        }
    else:
        toxicity = {
            "n": 0,
            "quadratic_weighted_kappa": 0.0,
            "exact_agreement": 0.0,
            "mean_absolute_error": 0.0,
        }

    return {
        "n_posts": n,
        "only_a": len(set(by_a) - set(by_b)),
        "only_b": len(set(by_b) - set(by_a)),
        "frames": frames,
        "macro_kappa_active_frames": macro_kappa,
        "active_frames": active,
        "exact_frame_set_match": (
            sum(1 for a, b in zip(left, right) if set(a.frame_labels) == set(b.frame_labels))
            / n
            if n
            else 0.0
        ),
        "mean_jaccard": (
            sum(_jaccard(a.frame_labels, b.frame_labels) for a, b in zip(left, right))
            / n
            if n
            else 0.0
        ),
        "toxicity": toxicity,
        "multilabel_f1": (
            multilabel_f1(
                [record.frame_labels for record in left],
                [record.frame_labels for record in right],
            )
            if n
            else {"per_label": {}, "micro_f1": 0.0, "macro_f1": 0.0}
        ),
        "toxicity_counts_a": dict(
            sorted(
                {
                    str(level): sum(1 for value in toxicity_a if value == level)
                    for level in range(4)
                }.items()
            )
        ),
        "toxicity_counts_b": dict(
            sorted(
                {
                    str(level): sum(1 for value in toxicity_b if value == level)
                    for level in range(4)
                }.items()
            )
        ),
    }
