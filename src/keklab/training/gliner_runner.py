"""GLiNER metadata restore, fine-tuning and span-to-frame prediction."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from keklab.classification.manifest import write_manifest
from keklab.training import data

BASE_MODEL = Path("/home/flynn/modelos_originales/gliner-multi-v2.1")
MODEL_ROOT = data.MODELS_DIR / "gliner"
HF_REPO = "urchade/gliner_multi-v2.1"
META_FILES = ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json")


def restore_metadata() -> dict[str, Any]:
    from huggingface_hub import hf_hub_download

    restored = []
    for name in META_FILES:
        target = BASE_MODEL / name
        if target.exists() and target.stat().st_size > 0:
            continue
        try:
            source = hf_hub_download(repo_id=HF_REPO, filename=name)
        except Exception:
            source = hf_hub_download(repo_id="microsoft/mdeberta-v3-base", filename=name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        restored.append(name)
    return {"restored": restored, "model": str(BASE_MODEL)}


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def train(params: dict[str, Any]) -> dict[str, Any]:
    from gliner import GLiNER

    metadata = restore_metadata()
    model = GLiNER.from_pretrained(str(BASE_MODEL), local_files_only=True)
    train_data = _load_dataset(data.paths()["gliner_train"])
    dev_data = _load_dataset(data.paths()["gliner_dev"])
    out_dir = MODEL_ROOT / "gliner-finetune"
    out_dir.mkdir(parents=True, exist_ok=True)
    epochs = int(params.get("epochs", 3))
    errors: list[str] = []
    for batch in (int(params.get("micro_batch", 2)), 1):
        steps = max(10, (len(train_data) * epochs) // max(1, batch))
        try:
            trainer = model.train_model(
                train_dataset=train_data,
                eval_dataset=dev_data,
                output_dir=str(out_dir),
                max_steps=steps,
                per_device_train_batch_size=batch,
                per_device_eval_batch_size=batch,
                gradient_accumulation_steps=8,
                learning_rate=float(params.get("learning_rate", 5e-5)),
                num_train_epochs=epochs,
                fp16=_cuda_ok(),
                logging_steps=10,
                save_strategy="no",
                report_to="none",
                remove_unused_columns=False,
            )
            trainer.save_model(str(out_dir))
            manifest = {
                "kind": "gliner_finetune",
                "base_model": str(BASE_MODEL),
                "output": str(out_dir),
                "metadata": metadata,
                "rows": len(train_data),
                "dev_rows": len(dev_data),
                "epochs": epochs,
                "micro_batch": batch,
                "max_steps": steps,
                "errors": errors,
            }
            write_manifest(data.MANIFESTS_DIR / "gliner-finetune.json", manifest)
            return manifest
        except Exception as exc:
            errors.append(f"micro_batch={batch}: {type(exc).__name__}: {exc}")
            if "out of memory" not in str(exc).lower():
                raise
    raise RuntimeError("GLiNER training failed: " + " | ".join(errors))


def _cuda_ok() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def predict(params: dict[str, Any]) -> dict[str, Any]:
    from gliner import GLiNER

    model = GLiNER.from_pretrained(str(MODEL_ROOT / "gliner-finetune"), local_files_only=True)
    labels = list(data.SUBSTANTIVE_FRAMES)
    counts: dict[str, int] = {}
    for split in ("dev", "test"):
        rows = data.load_modeling_rows(split)
        if not rows:
            counts[split] = 0
            continue
        texts = [row.get("text_clean") or row.get("text_raw") or "" for row in rows]
        predictions = model.inference(
            texts,
            labels,
            flat_ner=True,
            threshold=0.0,
            multi_label=True,
            return_relations=False,
            batch_size=int(params.get("batch_size", 8)),
        )
        out_rows = []
        for row, entities in zip(rows, predictions):
            scores = {label: 0.0 for label in data.SUBSTANTIVE_FRAMES}
            for entity in entities:
                label = str(entity.get("label", "")).lower()
                if label in scores:
                    scores[label] = max(scores[label], float(entity.get("score", 0.0)))
            out_rows.append(
                {
                    "model": "gliner-finetune",
                    "split": split,
                    "post_id": row["post_id"],
                    "thread_id": row["thread_id"],
                    "y_true": {label: int(label in row["frame_labels"]) for label in data.FRAME_LABELS},
                    "y_toxicity": row.get("toxicity"),
                    "probs": scores,
                    "probs_toxicity": None,
                }
            )
        data.write_predictions("gliner-finetune", split, out_rows)
        counts[split] = len(out_rows)
    return counts
