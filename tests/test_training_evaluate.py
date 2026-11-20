from __future__ import annotations

from keklab.annotation.labels import FRAME_LABELS
from keklab.training import evaluate


def _row(post_id: str, label: str, score: float, truth: int = 1) -> dict:
    probs = {name: 0.0 for name in FRAME_LABELS}
    probs[label] = score
    return {
        "post_id": post_id,
        "thread_id": post_id,
        "y_true": {name: int(name == label and truth) for name in FRAME_LABELS},
        "probs": probs,
        "y_toxicity": 0,
        "probs_toxicity": [1.0, 0.0, 0.0, 0.0],
    }


def test_select_thresholds_prefers_separable_score() -> None:
    rows = [
        _row("1", "racism", 0.9, 1),
        _row("2", "racism", 0.8, 1),
        _row("3", "racism", 0.1, 0),
        _row("4", "racism", 0.2, 0),
    ]
    thresholds = evaluate.select_thresholds(rows)
    assert thresholds["racism"] > 0.2


def test_postprocess_keeps_special_labels_exclusive() -> None:
    probs = {name: 0.0 for name in FRAME_LABELS}
    probs["none"] = 0.9
    probs["racism"] = 0.8
    thresholds = {name: 0.5 for name in FRAME_LABELS}
    assert evaluate._postprocess(probs, thresholds) == {"none"}


def test_qwk_perfect_and_reversed() -> None:
    assert evaluate._qwk([0, 1, 2, 3], [0, 1, 2, 3]) == 1.0
    assert (evaluate._qwk([0, 1, 2, 3], [3, 2, 1, 0]) or 0.0) < 0.0
