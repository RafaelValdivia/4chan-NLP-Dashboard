"""Dev threshold selection, test metrics and bootstrap uncertainty."""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.labels import FRAME_LABELS
from keklab.classification.manifest import write_manifest
from keklab.training import data

SPECIAL_LABELS = ("none", "unclear")


def _prf(y_true: list[int], y_pred: list[int]) -> dict[str, float | int]:
    tp = sum(1 for truth, pred in zip(y_true, y_pred) if truth == 1 and pred == 1)
    fp = sum(1 for truth, pred in zip(y_true, y_pred) if truth == 0 and pred == 1)
    fn = sum(1 for truth, pred in zip(y_true, y_pred) if truth == 1 and pred == 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _f1(y_true: list[int], y_pred: list[int]) -> float:
    return float(_prf(y_true, y_pred)["f1"])


def select_thresholds(rows: list[dict[str, Any]]) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for label in FRAME_LABELS:
        scored_rows = [row for row in rows if label in (row.get("probs") or {})]
        if not scored_rows:
            thresholds[label] = 1.0
            continue
        truth = [int(row["y_true"].get(label, 0)) for row in scored_rows]
        scores = [float(row["probs"][label]) for row in scored_rows]
        candidates = {0.5}
        candidates.update(round(value, 6) for value in scores)
        best_threshold = 0.5
        best_f1 = -1.0
        for threshold in sorted(candidates):
            predicted = [int(score >= threshold) for score in scores]
            score = _f1(truth, predicted)
            if score > best_f1 + 1e-12 or (abs(score - best_f1) <= 1e-12 and threshold > best_threshold):
                best_f1 = score
                best_threshold = threshold
        thresholds[label] = best_threshold
    return thresholds


def _postprocess(probs: dict[str, float], thresholds: dict[str, float]) -> set[str]:
    selected = {
        label
        for label in FRAME_LABELS
        if label in probs and float(probs[label]) >= thresholds.get(label, 0.5)
    }
    specials = [label for label in SPECIAL_LABELS if label in selected]
    if specials:
        keep = max(specials, key=lambda label: float(probs.get(label, 0.0)))
        selected = {keep}
    if not selected:
        selected = {"none"}
    return selected


def _tox_confusion(truth: list[int], pred: list[int]) -> list[list[int]]:
    matrix = [[0 for _ in range(4)] for _ in range(4)]
    for actual, predicted in zip(truth, pred):
        if 0 <= actual < 4 and 0 <= predicted < 4:
            matrix[actual][predicted] += 1
    return matrix


def _qwk(truth: list[int], pred: list[int]) -> float | None:
    matrix = _tox_confusion(truth, pred)
    total = sum(sum(row) for row in matrix)
    if total == 0:
        return None
    actual = [sum(matrix[i]) for i in range(4)]
    predicted = [sum(matrix[i][j] for i in range(4)) for j in range(4)]
    numerator = 0.0
    denominator = 0.0
    for i in range(4):
        for j in range(4):
            weight = ((i - j) ** 2) / 9.0
            numerator += weight * matrix[i][j]
            denominator += weight * actual[i] * predicted[j] / total
    if denominator == 0:
        return None
    return 1.0 - numerator / denominator


def _toxicity_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (int(row["y_toxicity"]), max(range(4), key=lambda index: float((row.get("probs_toxicity") or [0, 0, 0, 0])[index])))
        for row in rows
        if row.get("y_toxicity") is not None and row.get("probs_toxicity")
    ]
    if not pairs:
        return {"available": False}
    truth = [actual for actual, _ in pairs]
    pred = [predicted for _, predicted in pairs]
    binary_truth = [int(value >= 2) for value in truth]
    binary_pred = [int(value >= 2) for value in pred]
    return {
        "available": True,
        "n": len(pairs),
        "accuracy": sum(1 for actual, predicted in pairs if actual == predicted) / len(pairs),
        "mae": sum(abs(actual - predicted) for actual, predicted in pairs) / len(pairs),
        "qwk": _qwk(truth, pred),
        "binary": _prf(binary_truth, binary_pred),
        "confusion": _tox_confusion(truth, pred),
    }


def _macro_f1(rows: list[dict[str, Any]], predictions: list[set[str]]) -> float:
    scores = []
    for label in FRAME_LABELS:
        truth = [int(row["y_true"].get(label, 0)) for row in rows]
        pred = [int(label in predicted) for predicted in predictions]
        scores.append(_f1(truth, pred))
    return sum(scores) / len(scores)


def _bootstrap(rows: list[dict[str, Any]], predictions: list[set[str]], *, seed: int = 13, reps: int = 1000) -> dict[str, float | None]:
    by_thread: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_thread[str(row.get("thread_id") or row["post_id"])].append(index)
    threads = list(by_thread)
    if len(threads) < 2:
        return {"low": None, "high": None, "reps": 0}
    rng = random.Random(seed)
    values = []
    for _ in range(reps):
        sampled_rows: list[dict[str, Any]] = []
        sampled_predictions: list[set[str]] = []
        for _ in range(len(threads)):
            index = rng.choice(threads)
            for item in by_thread[index]:
                sampled_rows.append(rows[item])
                sampled_predictions.append(predictions[item])
        values.append(_macro_f1(sampled_rows, sampled_predictions))
    values.sort()
    return {
        "low": values[int(0.025 * (len(values) - 1))],
        "high": values[int(0.975 * (len(values) - 1))],
        "reps": reps,
        "threads": len(threads),
    }


def evaluate_model(model: str, split: str, thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    path = data.prediction_path(model, split)
    if not path.exists():
        return {"model": model, "split": split, "available": False}
    rows = data.read_predictions(path)
    if not rows:
        return {"model": model, "split": split, "available": False, "rows": 0}
    if thresholds is None:
        thresholds = select_thresholds(rows)
    predictions = [_postprocess(row.get("probs", {}), thresholds) for row in rows]
    per_label = {}
    for label in FRAME_LABELS:
        truth = [int(row["y_true"].get(label, 0)) for row in rows]
        pred = [int(label in item) for item in predictions]
        per_label[label] = {**_prf(truth, pred), "support": sum(truth), "predicted": sum(pred)}
    macro = sum(float(value["f1"]) for value in per_label.values()) / len(per_label)
    micro_scores = _prf(
        [int(row["y_true"].get(label, 0)) for row in rows for label in FRAME_LABELS],
        [int(label in predicted) for predicted in predictions for label in FRAME_LABELS],
    )
    substantive = [label for label in FRAME_LABELS if label not in SPECIAL_LABELS]
    substantive_macro = sum(float(per_label[label]["f1"]) for label in substantive) / len(substantive)
    return {
        "model": model,
        "split": split,
        "available": True,
        "rows": len(rows),
        "thresholds": thresholds,
        "macro_f1": macro,
        "substantive_macro_f1": substantive_macro,
        "micro": micro_scores,
        "per_label": per_label,
        "bootstrap_macro_f1": _bootstrap(rows, predictions),
        "toxicity": _toxicity_metrics(rows),
        "exact_match": sum(1 for row, predicted in zip(rows, predictions) if predicted == {label for label in FRAME_LABELS if row["y_true"].get(label)}) / len(rows),
        "mean_labels_predicted": sum(len(item) for item in predictions) / len(predictions),
    }


def available_models(split: str) -> list[str]:
    root = data.PREDICTIONS_DIR
    if not root.exists():
        return []
    names = []
    for directory in sorted(root.iterdir()):
        if directory.is_dir() and (directory / f"{split}.jsonl").exists():
            names.append(directory.name)
    return names


def evaluate_split(split: str) -> dict[str, Any]:
    models = available_models(split)
    if not models:
        raise FileNotFoundError(f"no predictions available for {split}")
    dev_thresholds: dict[str, dict[str, float]] = {}
    if split == "test":
        for model in models:
            dev_path = data.prediction_path(model, "dev")
            if dev_path.exists():
                dev_thresholds[model] = select_thresholds(data.read_predictions(dev_path))
    results = {}
    for model in models:
        thresholds = dev_thresholds.get(model)
        if thresholds is None and split == "test":
            continue
        results[model] = evaluate_model(model, split, thresholds)
    if not results:
        raise ValueError(f"no model had dev predictions for test thresholds: {models}")
    report = {
        "kind": f"evaluation_{split}",
        "split": split,
        "models": results,
        "ranking_dev_threshold": (
            "macro_f1" if split == "dev" else "dev-selected-thresholds applied once to frozen test"
        ),
    }
    write_manifest(data.REPORTS_DIR / f"evaluation-{split}.json", report)
    return report


def compare(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for model, result in report["models"].items():
        if not result.get("available"):
            continue
        toxi = result.get("toxicity") or {}
        rows.append(
            {
                "model": model,
                "macro_f1": result["macro_f1"],
                "substantive_macro_f1": result["substantive_macro_f1"],
                "micro_f1": result["micro"]["f1"],
                "exact_match": result["exact_match"],
                "mean_labels": result["mean_labels_predicted"],
                "toxicity_qwk": toxi.get("qwk"),
                "toxicity_mae": toxi.get("mae"),
                "toxicity_binary_f1": (toxi.get("binary") or {}).get("f1"),
                "macro_f1_low": result["bootstrap_macro_f1"].get("low"),
                "macro_f1_high": result["bootstrap_macro_f1"].get("high"),
            }
        )
    return sorted(rows, key=lambda item: float(item["macro_f1"]), reverse=True)


def write_comparison(dev: dict[str, Any], test: dict[str, Any] | None) -> Path:
    dev_rows = compare(dev)
    test_rows = compare(test) if test else []
    lines = [
        "# Fine-tuning comparison",
        "",
        "Silver labels are teacher outputs, not human ground truth. Test was frozen before training.",
        "",
        "## Dev ranking",
        "",
        "| model | macro F1 | substantive F1 | micro F1 | exact | labels/post | tox QWK | tox MAE | 95% CI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in dev_rows:
        ci = f"{row['macro_f1_low']:.3f}–{row['macro_f1_high']:.3f}" if row["macro_f1_low"] is not None else "n/a"
        qwk = f"{row['toxicity_qwk']:.3f}" if row["toxicity_qwk"] is not None else "n/a"
        mae = f"{row['toxicity_mae']:.3f}" if row["toxicity_mae"] is not None else "n/a"
        lines.append(
            f"| {row['model']} | {row['macro_f1']:.3f} | {row['substantive_macro_f1']:.3f} | "
            f"{row['micro_f1']:.3f} | {row['exact_match']:.3f} | {row['mean_labels']:.2f} | "
            f"{qwk} | {mae} | {ci} |"
        )
    if test_rows:
        lines.extend(
            [
                "",
                "## Frozen test (dev thresholds)",
                "",
                "| model | macro F1 | substantive F1 | micro F1 | exact | tox QWK | tox MAE | 95% CI |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in test_rows:
            ci = f"{row['macro_f1_low']:.3f}–{row['macro_f1_high']:.3f}" if row["macro_f1_low"] is not None else "n/a"
            qwk = f"{row['toxicity_qwk']:.3f}" if row["toxicity_qwk"] is not None else "n/a"
            mae = f"{row['toxicity_mae']:.3f}" if row["toxicity_mae"] is not None else "n/a"
            lines.append(
                f"| {row['model']} | {row['macro_f1']:.3f} | {row['substantive_macro_f1']:.3f} | "
                f"{row['micro_f1']:.3f} | {row['exact_match']:.3f} | {qwk} | {mae} | {ci} |"
            )
    lines.extend(["", "## Per-label dev F1", "", "| label | " + " | ".join(item["model"] for item in dev_rows) + " |", "|---|" + "---:|" * len(dev_rows)])
    for label in FRAME_LABELS:
        cells = [f"{float(dev['models'][item['model']]['per_label'][label]['f1']):.3f}" for item in dev_rows]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Qwen labels are teacher imitation targets; agreement with them is not accuracy against human truth.",
            "- Rare labels (accelerationism, meta_topic, unclear) have very low support; their F1 is unstable.",
            "- Laya frozen runs may be primary if the full fine-tune OOMs; check manifests.",
            "- GLiNER predicts 14 substantive frames only and has no toxicity head.",
            "",
        ]
    )
    path = data.REPORTS_DIR / "comparison.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
