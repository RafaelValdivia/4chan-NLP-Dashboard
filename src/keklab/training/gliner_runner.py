"""GLiNER metadata restore, fine-tuning and span-to-frame prediction."""

from __future__ import annotations

import json
import os
import shutil
from math import ceil
from pathlib import Path
from typing import Any

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

from keklab.classification.manifest import write_manifest
from keklab.training import data

BASE_MODEL = Path("/home/flynn/modelos_originales/gliner-multi-v2.1")
MODEL_ROOT = data.MODELS_DIR / "gliner"
HF_REPO = "urchade/gliner_multi-v2.1"
META_FILES = ("config.json", "tokenizer_config.json", "spm.model")


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

    tokenizer_config = BASE_MODEL / "tokenizer_config.json"
    config = json.loads(tokenizer_config.read_text(encoding="utf-8"))
    if config.get("tokenizer_class") != "DebertaV2Tokenizer":
        config["tokenizer_class"] = "DebertaV2Tokenizer"
        restored.append("tokenizer_class")
    if config.get("model_max_length") != 384:
        config["model_max_length"] = 384
        restored.append("model_max_length")
    if "tokenizer_class" in restored or "model_max_length" in restored:
        tokenizer_config.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return {"restored": restored, "model": str(BASE_MODEL)}


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _cuda_device() -> Any:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; GLiNER jobs do not fall back to CPU")
    return torch.device("cuda")


def _guard_oom_skips() -> None:
    import gliner.training.trainer as gliner_trainer

    logger = gliner_trainer.logger
    warning = logger.warning
    if getattr(warning, "_keklab_oom_guard", False):
        return

    def guarded(message: Any, *args: Any, **kwargs: Any) -> Any:
        rendered = f"{message} {' '.join(str(arg) for arg in args)}".lower()
        if "out of memory" in rendered or "oom" in rendered:
            raise RuntimeError("CUDA OOM during GLiNER training; refusing to skip batch")
        return warning(message, *args, **kwargs)

    guarded._keklab_oom_guard = True
    logger.warning = guarded


def train(params: dict[str, Any]) -> dict[str, Any]:
    from gliner import GLiNER

    device = _cuda_device()
    _guard_oom_skips()
    metadata = restore_metadata()
    train_data = _load_dataset(data.paths()["gliner_train"])
    dev_data = _load_dataset(data.paths()["gliner_dev"])
    out_dir = MODEL_ROOT / "gliner-finetune"
    out_dir.mkdir(parents=True, exist_ok=True)
    epochs = int(params.get("epochs", 3))
    grad_accum = max(1, int(params.get("gradient_accumulation_steps", 8)))
    device_used = str(device)
    errors: list[str] = []
    for batch in dict.fromkeys((int(params.get("micro_batch", 1)), 1)):
        model = GLiNER.from_pretrained(str(BASE_MODEL), local_files_only=True)
        model.to(device)
        steps = max(1, ceil(len(train_data) * epochs / (batch * grad_accum)))
        try:
            trainer = model.train_model(
                train_dataset=train_data,
                eval_dataset=dev_data,
                output_dir=str(out_dir),
                max_steps=steps,
                per_device_train_batch_size=batch,
                per_device_eval_batch_size=batch,
                gradient_accumulation_steps=grad_accum,
                learning_rate=float(params.get("learning_rate", 5e-5)),
                num_train_epochs=epochs,
                fp16=False,
                use_cpu=False,
                dataloader_num_workers=0,
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
                "gradient_accumulation_steps": grad_accum,
                "max_steps": steps,
                "precision": "fp32",
                "device": device_used,
                "token_max_length": 384,
                "errors": errors,
            }
            write_manifest(data.MANIFESTS_DIR / "gliner-finetune.json", manifest)
            return manifest
        except Exception as exc:
            errors.append(f"micro_batch={batch}: {type(exc).__name__}: {exc}")
            if "out of memory" not in str(exc).lower():
                raise
    raise RuntimeError("GLiNER training failed: " + " | ".join(errors))


def predict(params: dict[str, Any]) -> dict[str, Any]:
    from gliner import GLiNER

    device = _cuda_device()
    model = GLiNER.from_pretrained(str(MODEL_ROOT / "gliner-finetune"), local_files_only=True)
    model.to(device)
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
