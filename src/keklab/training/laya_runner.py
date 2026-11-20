"""Laya fine-tuning and typed prediction wrappers."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from keklab.annotation.labels import FRAME_LABELS
from keklab.classification.manifest import write_manifest
from keklab.common.paths import PROJECT_ROOT
from keklab.training import data

BASE_MODEL = Path("/home/flynn/modelos_originales/laya-base")
MODEL_ROOT = data.MODELS_DIR / "laya"


def _config(params: dict[str, Any]):
    from laya.train import TrainConfig

    return TrainConfig(
        epochs=int(params.get("epochs", 4)),
        micro_batch=int(params.get("micro_batch", 4)),
        grad_accum=int(params.get("grad_accum", 4)),
        loss=str(params.get("loss", "soft-ce")),
        freeze_encoder=bool(params.get("freeze_encoder", True)),
        calib_max=400,
        calib_frac=0.1,
        calib_seed=13,
        seed=13,
        max_len=512,
        head_max_len=192,
        amp=True,
        gradient_checkpointing=False,
        label_smoothing=0.0,
        log_every=25,
        eval_data=str(data.paths()["laya_dev"]),
    )


def train(params: dict[str, Any]) -> dict[str, Any]:
    from laya.train import finetune

    run = str(params.get("run", "laya-frozen-softce"))
    out_dir = MODEL_ROOT / run
    out_dir.mkdir(parents=True, exist_ok=True)
    base_micro = int(params.get("micro_batch", 4))
    errors: list[str] = []
    for micro_batch in (base_micro, 2, 1):
        cfg = _config({**params, "micro_batch": micro_batch})
        try:
            summary = finetune(
                str(data.paths()["laya_train"]),
                str(BASE_MODEL),
                str(out_dir),
                cfg,
                device="cuda" if _cuda_ok() else "cpu",
            )
            manifest = {
                "kind": "laya_finetune",
                "run": run,
                "base_model": str(BASE_MODEL),
                "output": str(out_dir),
                "config": asdict(cfg),
                "summary": summary,
                "errors": errors,
                "git_commit": _git_commit(),
            }
            write_manifest(data.MANIFESTS_DIR / f"{run}.json", manifest)
            return manifest
        except Exception as exc:
            errors.append(f"micro_batch={micro_batch}: {type(exc).__name__}: {exc}")
            if "out of memory" not in str(exc).lower() and "cuda" not in str(exc).lower():
                raise
    raise RuntimeError("Laya training failed at every micro-batch: " + " | ".join(errors))


def _cuda_ok() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _git_commit() -> str | None:
    from keklab.classification.manifest import git_commit

    return git_commit()


def _questions() -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for label in FRAME_LABELS:
        questions[f"frame__{label}"] = {
            "type": "noul",
            "instructions": f"Does the post express the '{label}' frame?",
            "criteria": {"false": "No", "true": "Yes"},
        }
    questions["toxicity"] = {
        "type": "score",
        "instructions": "How toxic is the post?",
        "criteria": [
            "Neutral or no toxicity",
            "Mild insult or hostility",
            "Dehumanization, slur, harassment or group hate",
            "Threat, incitement or celebration of violence",
        ],
    }
    return questions


def _answer_probs(answer: dict[str, Any]) -> tuple[dict[str, float], list[float]]:
    frame_probs: dict[str, float] = {}
    for label in FRAME_LABELS:
        value = answer.get(f"frame__{label}") or {}
        frame_probs[label] = float(value.get("noul", 0.0))
    tox = answer.get("toxicity") or {}
    raw = tox.get("probabilities") or {}
    probs = [float(raw.get(str(index), 0.0)) for index in range(4)]
    total = sum(probs)
    if total <= 0:
        probs = [0.25, 0.25, 0.25, 0.25]
    else:
        probs = [value / total for value in probs]
    return frame_probs, probs


def predict(model_dir: str | Path, params: dict[str, Any]) -> dict[str, Any]:
    import laya

    agent = laya.load(str(model_dir), device="cuda" if _cuda_ok() else "cpu")
    questions = _questions()
    counts: dict[str, int] = {}
    for split in ("dev", "test"):
        rows = data.load_modeling_rows(split)
        if not rows:
            counts[split] = 0
            continue
        texts = [row.get("text_clean") or row.get("text_raw") or "" for row in rows]
        results = agent.predict_batch(texts, questions, batch_size=int(params.get("batch_size", 16)))
        out_rows = []
        for row, result in zip(rows, results):
            frame_probs, tox_probs = _answer_probs(result.get("answers") or {})
            out_rows.append(
                {
                    "model": str(params.get("run", "laya")),
                    "split": split,
                    "post_id": row["post_id"],
                    "thread_id": row["thread_id"],
                    "y_true": {label: int(label in row["frame_labels"]) for label in FRAME_LABELS},
                    "y_toxicity": row.get("toxicity"),
                    "probs": frame_probs,
                    "probs_toxicity": tox_probs,
                }
            )
        data.write_predictions(str(params.get("run", "laya")), split, out_rows)
        counts[split] = len(out_rows)
    return counts
