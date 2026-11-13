"""Cheap baselines: TF-IDF+LR, BoW+SVM and TF-IDF-SVD+LR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from keklab.classification.manifest import write_manifest
from keklab.training import data


def _matrix(rows: list[dict[str, Any]]) -> list[str]:
    return [row.get("text_clean") or row.get("text_raw") or "" for row in rows]


def _labels(rows: list[dict[str, Any]]) -> list[list[int]]:
    return [[int(label in row["frame_labels"]) for label in data.FRAME_LABELS] for row in rows]


def _toxicity(rows: list[dict[str, Any]]) -> list[int]:
    return [int(row.get("toxicity") or 0) for row in rows]


def _sigmoid(value: float) -> float:
    import math

    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _predict(model: Any, matrix: Any, *, probabilities: bool) -> Any:
    import numpy as np

    if probabilities and hasattr(model, "predict_proba"):
        return model.predict_proba(matrix)
    if hasattr(model, "decision_function"):
        raw = model.decision_function(matrix)
        raw = np.asarray(raw, dtype=float)
        if raw.ndim == 1:
            raw = raw.reshape(-1, 1)
        return np.vectorize(_sigmoid)(raw)
    return np.asarray(model.predict(matrix), dtype=float)


def _frame_probs(model: Any, matrix: Any, *, probabilities: bool) -> list[dict[str, float]]:
    import numpy as np

    values = _predict(model, matrix, probabilities=probabilities)
    values = np.asarray(values, dtype=float)
    if values.ndim == 1:
        values = values.reshape(-1, 1)
    if values.shape[1] != len(data.FRAME_LABELS):
        raise ValueError(f"expected {len(data.FRAME_LABELS)} columns, got {values.shape[1]}")
    return [
        {label: float(row[index]) for index, label in enumerate(data.FRAME_LABELS)}
        for row in values
    ]


def _save(model_name: str, split: str, rows: list[dict[str, Any]], frame_probs: list[dict[str, float]], tox_probs: list[list[float]] | None) -> None:
    out = []
    for row, probs, tox in zip(rows, frame_probs, tox_probs or [None] * len(rows)):
        out.append(
            {
                "model": model_name,
                "split": split,
                "post_id": row["post_id"],
                "thread_id": row["thread_id"],
                "y_true": {label: int(label in row["frame_labels"]) for label in data.FRAME_LABELS},
                "y_toxicity": row.get("toxicity"),
                "probs": probs,
                "probs_toxicity": tox,
            }
        )
    data.write_predictions(model_name, split, out)


def run() -> dict[str, Any]:
    import numpy as np
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC

    train = data.load_modeling_rows("train")
    dev = data.load_modeling_rows("dev")
    test = data.load_modeling_rows("test")
    y_train = _labels(train)
    tox_train = _toxicity(train)
    reports: dict[str, Any] = {}

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=50000, min_df=2, sublinear_tf=True)
    x_train = tfidf.fit_transform(_matrix(train))
    x_dev = tfidf.transform(_matrix(dev))
    x_test = tfidf.transform(_matrix(test))

    tfidf_lr = OneVsRestClassifier(LogisticRegression(max_iter=2000, C=2.0, class_weight="balanced"))
    tfidf_lr.fit(x_train, np.asarray(y_train))
    tox_lr = LogisticRegression(max_iter=2000, C=2.0, class_weight="balanced")
    tox_lr.fit(x_train, tox_train)
    for split, x_data, rows in (("dev", x_dev, dev), ("test", x_test, test)):
        tox = tox_lr.predict_proba(x_data).tolist() if len(set(tox_train)) > 1 else None
        _save("tfidf-lr", split, rows, _frame_probs(tfidf_lr, x_data, probabilities=True), tox)
    reports["tfidf-lr"] = {"features": int(x_train.shape[1]), "train_rows": len(train)}

    bow = CountVectorizer(ngram_range=(1, 2), max_features=50000, min_df=2, binary=True)
    b_train = bow.fit_transform(_matrix(train))
    b_dev = bow.transform(_matrix(dev))
    b_test = bow.transform(_matrix(test))
    svm = OneVsRestClassifier(LinearSVC(C=1.0, class_weight="balanced"))
    svm.fit(b_train, np.asarray(y_train))
    for split, x_data, rows in (("dev", b_dev, dev), ("test", b_test, test)):
        _save("bow-svm", split, rows, _frame_probs(svm, x_data, probabilities=False), None)
    reports["bow-svm"] = {"features": int(b_train.shape[1]), "train_rows": len(train)}

    svd = TruncatedSVD(n_components=min(256, max(2, x_train.shape[1] - 1)), random_state=13)
    e_train = svd.fit_transform(x_train)
    e_dev = svd.transform(x_dev)
    e_test = svd.transform(x_test)
    emb_lr = make_pipeline(StandardScaler(), OneVsRestClassifier(LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced")))
    emb_lr.fit(e_train, np.asarray(y_train))
    for split, x_data, rows in (("dev", e_dev, dev), ("test", e_test, test)):
        _save("emb-lr", split, rows, _frame_probs(emb_lr, x_data, probabilities=True), None)
    reports["emb-lr"] = {"components": int(e_train.shape[1]), "train_rows": len(train)}

    write_manifest(data.MANIFESTS_DIR / "classical-baselines.json", {"kind": "classical_baselines", "models": reports})
    return reports
