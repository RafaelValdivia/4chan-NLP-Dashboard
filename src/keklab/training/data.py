"""Data preparation shared by the training jobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.labels import FRAME_LABELS
from keklab.annotation.proposal import evidence_in_text
from keklab.annotation.schema import AnnotationRecord, SamplePost
from keklab.annotation.splits import (
    assign_thread_splits,
    read_split_manifest,
    write_split_manifest,
)
from keklab.annotation.store import (
    _atomic_write_rows,
    load_annotations,
    load_samples,
    load_tasks,
    write_annotations,
)
from keklab.classification.dataset import build_modeling_rows
from keklab.classification.manifest import sha256_file, write_manifest
from keklab.classification.silver import convert_raw_rows
from keklab.common.io import iter_ndjson
from keklab.common.paths import DATA_DIR, PROJECT_ROOT

CLASSIFICATION_DIR = DATA_DIR / "classification"
SILVER_PATH = CLASSIFICATION_DIR / "silver" / "rotlk_5000.qwen3-8b-q4_k_m.silver.jsonl"
SPLIT_PATH = CLASSIFICATION_DIR / "splits" / "rotlk_5000_threads.jsonl"
MODELING_PATH = CLASSIFICATION_DIR / "modeling" / "rotlk_5000.jsonl"
LAYAP_DIR = CLASSIFICATION_DIR / "laya"
GLINER_DIR = CLASSIFICATION_DIR / "gliner"
PREDICTIONS_DIR = CLASSIFICATION_DIR / "predictions"
REPORTS_DIR = CLASSIFICATION_DIR / "reports"
MANIFESTS_DIR = CLASSIFICATION_DIR / "manifests"
MODELS_DIR = CLASSIFICATION_DIR / "models"

SUBSTANTIVE_FRAMES = tuple(label for label in FRAME_LABELS if label not in {"none", "unclear"})
TOXICITY_LEVELS = (0, 1, 2, 3)


def paths() -> dict[str, Path]:
    return {
        "raw": CLASSIFICATION_DIR / "llm" / "raw" / "rotlk_5000.v3.qwen3-8b-q4_k_m.raw.jsonl",
        "tasks": CLASSIFICATION_DIR / "tasks" / "rotlk_5000.jsonl",
        "samples": CLASSIFICATION_DIR / "samples" / "rotlk_5000.jsonl",
        "silver": SILVER_PATH,
        "splits": SPLIT_PATH,
        "modeling": MODELING_PATH,
        "laya_train": LAYAP_DIR / "train.jsonl",
        "laya_dev": LAYAP_DIR / "dev.jsonl",
        "gliner_train": GLINER_DIR / "train.jsonl",
        "gliner_dev": GLINER_DIR / "dev.jsonl",
        "test_hash": CLASSIFICATION_DIR / "splits" / "rotlk_5000_test.sha256",
    }


def _remap_raw(raw_path: Path, tasks_path: Path) -> list[dict[str, Any]]:
    tasks = load_tasks(tasks_path)
    by_id = {task.task_id: task for task in tasks}
    by_post = {task.post_id: task for task in tasks}
    rows: list[dict[str, Any]] = []
    for row in iter_ndjson(raw_path, skip_errors=False):
        task = by_id.get(str(row.get("task_id") or ""))
        if task is None:
            task = by_post.get(str(row.get("post_id") or ""))
        if task is None:
            raise ValueError(f"raw row without task: {row.get('task_id')!r}/{row.get('post_id')!r}")
        fixed = dict(row)
        fixed["task_id"] = task.task_id
        fixed["post_id"] = task.post_id
        rows.append(fixed)
    return rows


def export_all() -> dict[str, Any]:
    p = paths()
    for path in (SILVER_PATH, SPLIT_PATH, MODELING_PATH, LAYAP_DIR, GLINER_DIR):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(p["tasks"])
    raw_rows = _remap_raw(p["raw"], p["tasks"])
    annotations, silver_report = convert_raw_rows(
        raw_rows, tasks, model="qwen3-8b-q4_k_m", provider="llama.cpp"
    )
    if len(annotations) < 4900:
        raise ValueError(f"too few silver annotations: {len(annotations)}")
    write_annotations(annotations, SILVER_PATH)

    samples = load_samples(p["samples"])
    assignment = assign_thread_splits(samples, seed=13)
    write_split_manifest(assignment, SPLIT_PATH)

    evidence_by_post = _annotation_evidence(annotations)
    rows, dataset_report = build_modeling_rows(annotations, samples, split_assignment=assignment)
    for row in rows:
        row["notes_evidence"] = evidence_by_post.get(row["post_id"], [])
    _atomic_write_rows(MODELING_PATH, rows)
    by_split = {name: [row for row in rows if row.get("split") == name] for name in ("train", "dev", "test")}
    if len(by_split["test"]) == 0:
        raise ValueError("empty test split")

    test_payload = "\n".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in sorted(by_split["test"], key=lambda r: r["post_id"])
    )
    test_hash = hashlib.sha256(test_payload.encode("utf-8")).hexdigest()
    p["test_hash"].write_text(test_hash + "\n", encoding="utf-8")

    laya_questions = _laya_questions()
    for split in ("train", "dev"):
        _write_rows(p[f"laya_{split}"], [_laya_row(row, laya_questions) for row in by_split[split]])
    for split in ("train", "dev"):
        _write_rows(p[f"gliner_{split}"], [_gliner_row(row) for row in by_split[split]])

    manifest = {
        "kind": "silver_export",
        "raw": str(p["raw"]),
        "tasks": str(p["tasks"]),
        "samples": str(p["samples"]),
        "silver": str(SILVER_PATH),
        "splits": str(SPLIT_PATH),
        "modeling": str(MODELING_PATH),
        "silver_report": silver_report,
        "dataset_report": dataset_report,
        "test_sha256": test_hash,
        "prompt_sha256": sorted({task.prompt_sha256 for task in tasks if task.prompt_sha256}),
        "annotation_count": len(annotations),
        "rows": len(rows),
        "split_rows": {name: len(value) for name, value in by_split.items()},
        "thread_splits": {name: sum(1 for value in assignment.values() if value == name) for name in ("train", "dev", "test")},
    }
    write_manifest(MANIFESTS_DIR / "silver-export.json", manifest)
    return manifest


def _annotation_evidence(annotations: Iterable[AnnotationRecord]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for annotation in annotations:
        try:
            notes = json.loads(annotation.notes or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        evidence = notes.get("evidence") if isinstance(notes, dict) else None
        if isinstance(evidence, list):
            result[annotation.post_id] = [str(item) for item in evidence if str(item).strip()]
    return result


def load_modeling_rows(split: str | None = None) -> list[dict[str, Any]]:
    rows = [row for row in iter_ndjson(MODELING_PATH, skip_errors=False)]
    if split is not None:
        rows = [row for row in rows if row.get("split") == split]
    return rows


def _write_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_rows(path, rows)


def _laya_questions() -> dict[str, dict[str, Any]]:
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


def _laya_row(row: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    expected = {f"frame__{label}": int(label in row["frame_labels"]) for label in FRAME_LABELS}
    expected["toxicity"] = int(row["toxicity"] if row.get("toxicity") is not None else 0)
    return {
        "post_id": row["post_id"],
        "state": row.get("text_clean") or row.get("text_raw") or "",
        "questions": questions,
        "expected": expected,
    }


def _word_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for word in text.split():
        start = text.find(word, cursor)
        if start < 0:
            start = cursor
        end = start + len(word)
        spans.append((start, end))
        cursor = end
    return spans


def _span_to_words(text: str, start: int, end: int, word_spans: list[tuple[int, int]]) -> tuple[int, int] | None:
    chosen = [index for index, (left, right) in enumerate(word_spans) if right > start and left < end]
    if not chosen:
        return None
    return chosen[0], chosen[-1]


def _gliner_row(row: dict[str, Any]) -> dict[str, Any]:
    text = row.get("text_clean") or row.get("text_raw") or ""
    words = text.split()
    word_spans = _word_spans(text)
    labels = set(row.get("frame_labels") or [])
    ner: list[list[Any]] = []
    evidence = row.get("notes_evidence") or []
    for label in SUBSTANTIVE_FRAMES:
        if label not in labels:
            continue
        found = False
        for fragment in evidence:
            if not evidence_in_text(str(fragment), [text]):
                continue
            start = text.find(str(fragment))
            end = start + len(str(fragment))
            mapped = _span_to_words(text, start, end, word_spans)
            if mapped is not None:
                ner.append([mapped[0], mapped[1], label])
                found = True
        if not found and words:
            ner.append([0, len(words) - 1, label])
    return {"tokenized_text": words, "ner": ner, "ner_labels": list(SUBSTANTIVE_FRAMES)}


def prediction_path(model: str, split: str) -> Path:
    return PREDICTIONS_DIR / model / f"{split}.jsonl"


def write_predictions(model: str, split: str, rows: Iterable[dict[str, Any]]) -> Path:
    path = prediction_path(model, split)
    _write_rows(path, rows)
    return path


def read_predictions(path: str | Path) -> list[dict[str, Any]]:
    return [row for row in iter_ndjson(path, skip_errors=False)]


def sha(path: str | Path) -> str | None:
    p = Path(path).expanduser()
    return sha256_file(p) if p.exists() and p.is_file() else None
