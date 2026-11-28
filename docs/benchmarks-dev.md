# Dev benchmarks — classic and neural algorithms

Generated: 2026-11-28 UTC  
Split: 1,000 dev posts · 16 frame labels · 1,000 thread-bootstrap resamples  
Scope: 3 classical baselines + 2 trained neural models

## Status

This is a **dev-only** benchmark. Frozen test predictions exist for all five
models, but no test rows were scored and no `evaluation-test.json` exists. The
frozen test SHA-256 is unchanged:
`afae38a9157c64197c83839812a4846918a4506f51c02c916c51ef6f8fde21b4`.
`evaluate-test-once` and `comparison-report` remain blocked.

The pre-registered primary model remains `laya-frozen-softce`. The table below is
descriptive; it does not retroactively change selection. The optional Laya RLCD
and full-encoder ablations are still pending and have no predictions, so they are
not ranked here.

## Headline metrics — dev

Thresholds were selected per label on these same dev rows by maximum F1. These
are in-sample, threshold-selected numbers and are optimistic. The 95% interval is
a percentile bootstrap over threads.

| model | family | macro F1 | substantive F1 | micro P | micro R | micro F1 | exact | labels/post | 95% CI |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gliner-finetune | neural | 0.418 | 0.415 | 0.639 | 0.745 | 0.688 | 0.643 | 1.50 | 0.351–0.470 |
| tfidf-lr | classic | 0.328 | 0.313 | 0.691 | 0.670 | 0.680 | 0.701 | 1.25 | 0.240–0.400 |
| bow-svm | classic | 0.303 | 0.284 | 0.716 | 0.662 | 0.688 | 0.702 | 1.21 | 0.247–0.352 |
| emb-lr | classic | 0.255 | 0.229 | 0.659 | 0.650 | 0.654 | 0.690 | 1.27 | 0.194–0.314 |
| laya-frozen-softce | neural | 0.205 | 0.172 | 0.670 | 0.599 | 0.632 | 0.676 | 1.15 | 0.154–0.251 |

Reference points:

- Dev `none` prevalence: 70.2%.
- Always predicting exactly `{none}` gives exact set match 0.702.
- Mean true labels/post: 1.288; mean true substantive labels/post: 0.585.
- Exact set match near 0.70 is therefore close to the always-`none` baseline.
- Micro F1 pools all 16 label decisions; it is not post-level accuracy.

`gliner-finetune` has the highest dev threshold-selected frame F1, but it lacks
`none`/`unclear` scores and a toxicity head, and its exact-set match is below the
always-`none` baseline. `laya-frozen-softce` remains the protocol's primary
model despite its lower dev ranking.

## Toxicity — dev

Only `tfidf-lr` and `laya-frozen-softce` have a 0–3 toxicity head. `n/a` means
not modeled, not zero.

| model | accuracy | MAE | QWK | binary F1 | binary precision | binary recall |
|---|---:|---:|---:|---:|---:|---:|
| tfidf-lr | 0.566 | 0.582 | 0.544 | 0.609 | 0.615 | 0.603 |
| laya-frozen-softce | 0.616 | 0.546 | 0.528 | 0.541 | 0.663 | 0.457 |
| gliner-finetune | n/a | n/a | n/a | n/a | n/a | n/a |
| bow-svm | n/a | n/a | n/a | n/a | n/a | n/a |
| emb-lr | n/a | n/a | n/a | n/a | n/a | n/a |

## Per-label dev F1

| label | gliner-finetune | tfidf-lr | bow-svm | emb-lr | laya-frozen-softce |
|---|---:|---:|---:|---:|---:|
| conspiracy | 0.429 | 0.288 | 0.321 | 0.281 | 0.133 |
| ethnonationalism | 0.547 | 0.453 | 0.382 | 0.382 | 0.267 |
| racism | 0.610 | 0.451 | 0.516 | 0.387 | 0.443 |
| antisemitism | 0.728 | 0.545 | 0.607 | 0.496 | 0.407 |
| islamophobia | 0.590 | 0.417 | 0.341 | 0.259 | 0.103 |
| rusophobia | 0.341 | 0.250 | 0.357 | 0.256 | 0.065 |
| sinophobia | 0.267 | 0.222 | 0.211 | 0.211 | 0.000 |
| misogyny | 0.462 | 0.162 | 0.205 | 0.136 | 0.364 |
| transphobia | 0.476 | 0.375 | 0.286 | 0.000 | 0.154 |
| homophobia | 0.333 | 0.308 | 0.133 | 0.000 | 0.211 |
| institutional_distrust | 0.410 | 0.370 | 0.270 | 0.375 | 0.062 |
| violence_glorification | 0.400 | 0.250 | 0.286 | 0.286 | 0.000 |
| accelerationism | 0.222 | 0.286 | 0.071 | 0.133 | 0.200 |
| meta_topic | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| none | 0.865 | 0.867 | 0.869 | 0.871 | 0.880 |
| unclear | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

`meta_topic`, `unclear`, and `accelerationism` have zero or near-zero support on
dev; their F1 estimates are unstable and must not be overinterpreted.

## Dev-selected thresholds

The evaluator selects one cutoff per label on dev by maximum F1. These cutoffs
are not classifier parameters and were not applied to test.

| label | gliner-finetune | tfidf-lr | bow-svm | emb-lr | laya-frozen-softce |
|---|---:|---:|---:|---:|---:|
| conspiracy | 0.067 | 0.562 | 0.479 | 0.516 | 0.086 |
| ethnonationalism | 0.013 | 0.541 | 0.387 | 0.574 | 0.190 |
| racism | 0.034 | 0.479 | 0.481 | 0.793 | 0.197 |
| antisemitism | 0.066 | 0.530 | 0.478 | 0.784 | 0.291 |
| islamophobia | 0.052 | 0.454 | 0.424 | 0.487 | 0.297 |
| rusophobia | 0.052 | 0.536 | 0.448 | 0.282 | 0.214 |
| sinophobia | 0.006 | 0.256 | 0.324 | 0.135 | 0.270 |
| misogyny | 0.076 | 0.574 | 0.412 | 0.272 | 0.234 |
| transphobia | 0.039 | 0.389 | 0.386 | 1.000 | 0.216 |
| homophobia | 0.011 | 0.541 | 0.469 | 1.000 | 0.118 |
| institutional_distrust | 0.099 | 0.658 | 0.390 | 0.893 | 0.119 |
| violence_glorification | 0.037 | 0.500 | 0.690 | 0.993 | 0.799 |
| accelerationism | 0.003 | 0.214 | 0.263 | 0.008 | 0.200 |
| meta_topic | 0.500 | 0.500 | 0.500 | 0.500 | 0.892 |
| none | 1.000 | 0.294 | 0.360 | 0.130 | 0.446 |
| unclear | 1.000 | 0.010 | 0.270 | 0.000 | 0.011 |

GLiNER emits only the 14 substantive labels. Its `none`/`unclear` thresholds are
shown as 1.0 because those labels are absent from its prediction rows; the
fallback `none` rule still applies when no substantive label is selected.

## Algorithms

- `tfidf-lr`: TF-IDF `(1,2)`, 50,000 features, `min_df=2`, sublinear TF;
  one-vs-rest logistic regression `C=2.0`, balanced classes, 2,000 iterations;
  separate 4-class toxicity logistic head.
- `bow-svm`: binary count vectors `(1,2)`, 50,000 features, `min_df=2`;
  one-vs-rest linear SVM `C=1.0`, balanced classes; sigmoid-mapped decision
  scores; no toxicity head.
- `emb-lr`: TF-IDF `(1,2)` → truncated SVD 256 → standard scaling → one-vs-rest
  logistic regression `C=1.0`, balanced classes; no toxicity head.
- `laya-frozen-softce`: frozen ModernBERT-large encoder, soft cross-entropy, 4
  epochs, micro-batch 4, gradient accumulation 4, `max_len=512`,
  `head_max_len=192`, fp16/AMP, seed 13, 10% calibration capped at 400;
  16 frames plus 0–3 toxicity.
- `gliner-finetune`: local GLiNER multi v2.1 weights with restored
  DebertaV2 metadata, 14 substantive frames, 3 epochs, 1,125 optimizer steps,
  micro-batch 1, gradient accumulation 8, effective batch 8, fp32 CUDA,
  `token_max_length=384`, `max_width=12`, `max_types=25`; no toxicity head.

## Evaluator correction

The first dev evaluation treated absent `none`/`unclear` GLiNER scores as 0.0.
Because absent labels could satisfy a 0.0 threshold, every GLiNER post was
forced to `none` and all substantive F1 scores were 0. `select_thresholds` now
ignores absent labels and assigns them an unusable threshold of 1.0;
`_postprocess` likewise ignores labels absent from the score map. Two regression
tests were added. This correction affects GLiNER's benchmark only; models with
all 16 frame scores are unchanged.

## Reproducibility

Effective dev-evaluation command:

```bash
PYTHONPATH=src USE_TF=0 TRANSFORMERS_NO_TF=1 \
  /home/flynn/PyVenvs/NetworkAnalysis/bin/python \
  -c "from keklab.training import evaluate; import json; print(json.dumps(evaluate.evaluate_split('dev'), indent=2))"
```

The queue record is
`data/classification/queue/done/20261112164154-3421ef29-evaluate.json`.

Environment: Python 3.12.3 · scikit-learn 1.9.1 · NumPy 2.5.4 · pandas 3.0.3 ·
SciPy 1.18.0 · joblib 1.5.3 · pytest 9.2.0. Git HEAD at execution: `bf4709c`.

Full dev metrics and thresholds:
`data/classification/reports/evaluation-dev.json`, SHA-256
`1ec5dabc4d003bb78345dadc423a9b06737d7c24f923f0ac4708822002fd23bb`.

Dev prediction hashes:

| model | SHA-256 |
|---|---|
| tfidf-lr | `ffaa8980f1bb0c21330c4030081fa1b7da643e8ae38a03a512a72b32872cf004` |
| bow-svm | `4232ccfa5627ca5dfb2f639e552c95146bb13b2cde08d6804bd4ad37b5408a16` |
| emb-lr | `d78fbc825b934ac69717ddb92e8c00401fb26f6a8991fb76fea3d4249c4cf327` |
| laya-frozen-softce | `666a61a952815341b8d45c8ee1e21fddf413fbe2e7b68051db76509278c4e47a` |
| gliner-finetune | `a9d1f4a74785ea303dca82c803c196dbb6d2c788c407d08a7970022162d75ebf` |

## Queue status

Done: setup, export, Laya soft-CE, GLiNER, classical baselines, dev evaluation.
Pending: optional Laya RLCD and optional Laya full-encoder attempt. Blocked:
frozen test evaluation and final comparison report. Zero failed jobs.

## Caveats

- Silver labels are Qwen3-8B teacher outputs, not human ground truth. Agreement
  with them is teacher imitation, not human accuracy.
- Dev thresholds are selected on the same rows being scored; estimates are
  optimistic and must not be reused as independent evidence.
- The 200-post human gold set is diagnostic only and was not used for training,
  threshold selection, or model choice.
- GLiNER predicts 14 frames only and has no toxicity head.
- Rare labels have very low support; their F1 is unstable.
- No frozen test score, final comparison, or second test evaluation was run.
