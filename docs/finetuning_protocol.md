# Fine-tuning and comparison protocol (pre-registration amendment)

Status: frozen before any dev/test model scoring. Date: 2026-11-12.

This amendment covers training and comparison on the 5,000-post Qwen3-8B silver
set. Silver labels are teacher imitation targets, not human ground truth.

## Data and splits

- Source posts: `data/classification/samples/rotlk_5000.jsonl`.
- Silver annotations: validated Qwen3-8B outputs, prompt v3, converted by
  `keklab.classification.silver`.
- Splits are assigned by `thread_id` with seed 13 and ratios 60/20/20. Posts
  from one thread never cross splits.
- Test is frozen by a SHA-256 over the sorted test JSONL rows before training.
  It is scored once, after all model selection is complete.
- The 200-post human gold set is a diagnostic reference only. It is not the
  test set, and no model is selected on it.

## Targets

- Laya: 16 fine frame labels plus one 0-3 toxicity score per post. The 16
  `noul` answers are independent; `none` and `unclear` are exclusive after
  prediction.
- GLiNER: 14 substantive frames only. Evidence spans come from the silver
  annotations when they are verbatim; otherwise the whole post is used. GLiNER
  has no toxicity head.
- Classical baselines: TF-IDF + logistic regression, bag-of-words + linear SVM,
  and TF-IDF-SVD + logistic regression. They predict the same 16 frames; the
  TF-IDF model also predicts toxicity.

## Training

- Laya base: `answerdotai/ModernBERT-large`, restored into
  `/home/flynn/modelos_originales/laya-base`.
- Primary Laya run: frozen encoder, soft cross-entropy, 4 epochs, `max_len=512`,
  `head_max_len=192`, `max_prefixes=6`, 10% calibration capped at 400,
  `label_smoothing=0.0`, fp16/AMP on the GTX 1070 Ti.
- Ablation: frozen encoder with RLCD loss.
- Attempt: full-encoder fine-tune with micro-batch 1 and gradient accumulation.
  If it OOMs, the frozen run remains primary and the OOM is recorded.
- GLiNER base: `microsoft/mdeberta-v3-base` config with the local
  `gliner-multi-v2.1` weights; `max_len=384`, `max_width=12`, `max_types=25`.
  Missing tokenizer/config metadata is restored from the base repository.
- No test rows are used for training, calibration, threshold selection, early
  stopping, or hyper-parameter selection.

## Selection and evaluation

- Dev thresholds are selected per label by maximum F1. Test uses the dev
  thresholds unchanged and is not tuned.
- Laya toxicity uses the argmax over four levels.
- Primary metrics: macro F1 over 16 frames, substantive-only macro F1, micro F1,
  exact-set match, labels per post, toxicity quadratic weighted kappa, toxicity
  MAE, and binary toxicity F1.
- Uncertainty is a 95% percentile bootstrap over threads (1,000 resamples).
- The ranking table is descriptive. The frozen Laya soft-CE run is the primary
  pre-registered model; the table does not retroactively change that choice.
- Rare labels (`accelerationism`, `meta_topic`, `unclear`) have very low
  support and unstable estimates.
- GLiNER and baselines without toxicity heads are reported as `n/a` for
  toxicity, not as zero.

## Reproducibility and stopping

- Every run writes a manifest with the git commit, configuration, data hashes,
  and output paths.
- The queue is resumable and idempotent. A one-shot test lock prevents a second
  test score; a failed test run is not silently repeated.
- If CUDA cannot be made compatible with `sm_61`, GPU jobs stop rather than
  falling back to an unregistered CPU result.
