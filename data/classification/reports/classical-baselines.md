# Classical baselines — dev metrics (threshold-selected)

This historical report is superseded by `docs/benchmarks-dev.md`, which records
the current queued re-run, updated hashes, and all classic/neural models.

Date: 2026-11-13  
Train rows: 3,000 · Dev rows: 1,000 · Test rows: 1,000  
Labels: 16 frame labels (including `none` and `unclear`) + toxicity only for `tfidf-lr`.

## Scope and test status

- These are **dev** metrics, not test metrics.
- Test predictions were generated but **not scored**. No `evaluation-test.json` exists.
- Dev was used to select one decision threshold per label. Dev metrics are therefore threshold-selected in-sample and optimistic.
- Model hyperparameters were fixed a priori and were **not tuned**. Only the per-label thresholds were selected on dev.
- Test remains behind the one-shot gate. Scoring test now would require reusing the baseline scores later or re-scoring them, because `evaluate_split("test")` currently re-evaluates every available model.

## Frame metrics — dev

| model | macro F1 | substantive macro F1 | micro precision | micro recall | micro F1 | exact set match | labels/post |
|---|---:|---:|---:|---:|---:|---:|---:|
| tfidf-lr | 0.328 | 0.313 | 0.691 | 0.670 | 0.680 | 0.701 | 1.25 |
| bow-svm | 0.303 | 0.284 | 0.707 | 0.664 | 0.685 | 0.702 | 1.21 |
| emb-lr | 0.255 | 0.229 | 0.659 | 0.650 | 0.654 | 0.690 | 1.27 |

`tfidf-lr` is the strongest classical baseline on macro and substantive F1. `bow-svm` has slightly higher micro F1 and exact set match. `emb-lr` (TF-IDF → SVD 256 → LR) is weakest.

### Reference points

- Dev `none` prevalence: **70.2%**.
- Always predicting exactly `{none}` gives exact set match: **0.702**.
- Mean true labels/post: **1.288**.
- Mean true substantive labels/post: **0.585**.

So the models’ ~0.70 exact set match is essentially the always-`none` majority baseline, not evidence of multi-label skill. Micro F1 is also not “percent of posts correct”; it pools true/false positives and negatives across all 16 label decisions.

## Toxicity metrics — dev

| model | tox QWK | tox MAE | tox binary F1 | toxicity head |
|---|---:|---:|---:|---|
| tfidf-lr | 0.544 | 0.582 | 0.609 | yes, 4-class logistic |
| bow-svm | n/a | n/a | n/a | no |
| emb-lr | n/a | n/a | n/a | no |

`n/a` means “not modeled,” not zero. `bow-svm` and `emb-lr` have no toxicity head.

## Uncertainty — dev

| model | macro F1 | 95% thread-bootstrap CI |
|---|---:|---:|
| tfidf-lr | 0.328 | 0.240–0.400 |
| bow-svm | 0.303 | 0.247–0.352 |
| emb-lr | 0.255 | 0.194–0.314 |

The interval is a percentile bootstrap over threads (1,000 resamples), not posts.

## Per-label dev F1

| label | tfidf-lr | bow-svm | emb-lr |
|---|---:|---:|---:|
| conspiracy | 0.288 | 0.321 | 0.282 |
| ethnonationalism | 0.453 | 0.382 | 0.382 |
| racism | 0.451 | 0.517 | 0.387 |
| antisemitism | 0.545 | 0.607 | 0.496 |
| islamophobia | 0.417 | 0.342 | 0.259 |
| rusophobia | 0.250 | 0.357 | 0.256 |
| sinophobia | 0.222 | 0.211 | 0.211 |
| misogyny | 0.162 | 0.214 | 0.136 |
| transphobia | 0.375 | 0.267 | 0.000 |
| homophobia | 0.308 | 0.133 | 0.000 |
| institutional_distrust | 0.370 | 0.270 | 0.375 |
| violence_glorification | 0.250 | 0.286 | 0.286 |
| accelerationism | 0.286 | 0.071 | 0.133 |
| meta_topic | 0.000 | 0.000 | 0.000 |
| none | 0.868 | 0.869 | 0.871 |
| unclear | 0.000 | 0.000 | 0.000 |

## Per-label thresholds selected on dev

A positive label is predicted when its score is at or above the label-specific cutoff. These cutoffs are not learned by the classifier; they are selected by a separate dev search that maximizes each label’s F1.

| label | tfidf-lr | bow-svm | emb-lr |
|---|---:|---:|---:|
| conspiracy | 0.562 | 0.479 | 0.516 |
| ethnonationalism | 0.541 | 0.387 | 0.574 |
| racism | 0.479 | 0.481 | 0.793 |
| antisemitism | 0.530 | 0.472 | 0.784 |
| islamophobia | 0.454 | 0.424 | 0.487 |
| rusophobia | 0.536 | 0.441 | 0.282 |
| sinophobia | 0.256 | 0.325 | 0.135 |
| misogyny | 0.574 | 0.339 | 0.272 |
| transphobia | 0.389 | 0.386 | 1.000 |
| homophobia | 0.541 | 0.469 | 1.000 |
| institutional_distrust | 0.658 | 0.390 | 0.893 |
| violence_glorification | 0.500 | 0.500 | 0.993 |
| accelerationism | 0.214 | 0.263 | 0.008 |
| meta_topic | 0.500 | 0.500 | 0.500 |
| none | 0.294 | 0.360 | 0.130 |
| unclear | 0.010 | 0.270 | 0.000 |

## Configuration

- `tfidf-lr`: TF-IDF `(1,2)`, 50k max features, `min_df=2`, sublinear TF; One-vs-rest logistic regression `C=2.0`, balanced class weights, 2,000 iterations. Includes a separate 4-class toxicity logistic head.
- `bow-svm`: binary count vectors `(1,2)`, 50k max features, `min_df=2`; One-vs-rest linear SVM `C=1.0`, balanced class weights. No toxicity head and no calibrated probabilities.
- `emb-lr`: same TF-IDF matrix → truncated SVD 256 components → standard scaling → one-vs-rest logistic regression `C=1.0`, balanced class weights. No toxicity head.
- All models trained on `train` only. Random seed: 13.

## Reproducibility

- Effective command: `PYTHONPATH=src /home/flynn/PyVenvs/NetworkAnalysis/bin/python -c "from keklab.training import baselines_runner; import json; print(json.dumps(baselines_runner.run(), indent=2))"`
- Python: 3.12.3
- scikit-learn: 1.9.0 · numpy: 2.5.0 · pandas: 3.0.3 · scipy: 1.18.0 · joblib: 1.5.3
- Git commit at documentation time: `58443a3`; tree was dirty with uncommitted training code and data.
- Modeling rows SHA-256: `d8f10b2ace3590af91680d74383be94a54eb7fa99935a6235fe9cec29273f278`
- Thread split SHA-256: `ad043bf0ed8e53f139ee53f90f27fd490bcd9e52c69c3f326d5e0eade8bd48fb`
- Frozen test-set SHA-256: `afae38a9157c64197c83839812a4846918a4506f51c02c916c51ef6f8fde21b4`
- Evaluation dev SHA-256: `3399c32d64cd5ce2e6397427a194f6161fe25ee71e8fc76f1fd882a9767e5392`
- Wall-clock runtime was not instrumented.

## Provenance and queue status

The baselines were invoked directly, outside the persistent queue, because the queued `baselines` job (`20261112164154-c637b2b2-baselines`) depends on the blocked `setup` job. `setup` cannot install a CUDA `torch` with `sm_61` because the four large CUDA wheels are corrupt.

The direct run is therefore documented separately from the queue state. It did not consume the one-shot test lock and did not evaluate test.

## Artifacts

- Predictions: `data/classification/predictions/{tfidf-lr,bow-svm,emb-lr}/{dev,test}.jsonl`
- Full dev metrics and thresholds: `data/classification/reports/evaluation-dev.json`
- Training manifest: `data/classification/manifests/classical-baselines.json`
- Journal: `Journal/Journal PLN. 24. 12-11-26.md`
