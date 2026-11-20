# Journal PLN — Entrada 28 (12-11-2026)

## Contexto

Se publica el estado actual del repositorio en una rama nueva, `training`, para
conservar y compartir el trabajo de exportación de plata, splits, baselines y
protocolo de fine-tuning sin tocar `master`. La rama se crea desde
`refactor/readability-20261112-235059` (`47c8ca2`), que contiene los 7 commits
locales previos (5 de `master` + 2 de refactor).

## Divergencia con `origin/master`

El punto de bifurcación es `7ee0099` ("Sampled 5000 posts for training").
`origin/master` ha avanzado 31 commits desde entonces (backend FastAPI en
`040bc30`, entradas 22 y 23 propias). La rama `training` queda **11 commits por
delante y 31 por detrás** de `origin/master`: es una instantánea lateral, no un
fast-forward.

Aviso: `origin/master` ya tiene archivos `Journal/Journal PLN. 22. 12-11-26.md`
y `Journal/Journal PLN. 23. 12-11-26.md` con contenido distinto a los locales.
Al fusionar habrá que resolver la colisión de nombres; no se renombran aquí
porque las entradas locales ya se citan entre sí.

## Commits publicados

Heredados (ya existían en la rama de origen):

| Commit | Asunto |
|---|---|
| `0e7f981` | feat: add llama-server backend, error taxonomy and context guard |
| `513cc11` | fix: strip wbr and real HTML tags from cleaned post text |
| `9708c34` | feat: send only the cleaned text in the annotation prompt (v3) |
| `83e8f9b` | data: rebuild the silver sample and tasks with prompt v3 |
| `58443a3` | docs: record journal entries 19-22 and the wbr issue |
| `6f810cd` | chore: snapshot pre-refactor source state |
| `47c8ca2` | refactor(annotation): consolidate record loaders in store and document JSONL contract |

Nuevos (creados para esta publicación):

| Commit | Asunto |
|---|---|
| `3964493` | chore(models): clear stale checksums pending re-verification |
| `aad7d88` | refactor(annotation): add shared review commit helper |
| `7cd3e3c` | docs: record journals 23-24, fine-tuning protocol and wheelhouse request |
| `52c9e41` | data: export v3 silver, splits, modeling sets and baseline artifacts |
| tip | docs: record the training branch push (esta entrada) |

## Contenido versionado

### Código

- `src/keklab/training/` completo (1.896 líneas): `gliner_runner`,
  `laya_runner`, `baselines_runner`, `data`, `evaluate`, `jobs`, `queue`,
  `cli`.
- `src/keklab/annotation/review.py`: helper `commit()` (todavía sin conectar).
- `src/keklab/annotation/store.py`: refactor de loaders (`47c8ca2`).
- `src/keklab/common/cli.py`: subcomando `training`.

### Documentación

- Journal 19 actualizado a prompt v3, hash `ef251abe…`.
- Journals 23 (plan Laya/GLiNER), 24 (baselines clásicas), 25 (esta entrada).
- `docs/finetuning_protocol.md`: enmienda de pre-registro congelada antes de
  puntuar dev/test.
- `torch-wheelhouse-request.md`.

### Datos

| Archivo | Filas | SHA-256 (prefijo) |
|---|---:|---|
| `silver/rotlk_5000.qwen3-8b-q4_k_m.silver.jsonl` | 5.000 | `fcd6dd21…` |
| `splits/rotlk_5000_threads.jsonl` | 5.000 | `ad043bf0…` |
| `splits/rotlk_5000_test.sha256` | 1 | `d988513c…` (hash congelado `afae38a9…`) |
| `modeling/rotlk_5000.jsonl` | 5.000 | `d8f10b2a…` |
| `gliner/train.jsonl` | 3.000 | `f16142b0…` |
| `gliner/dev.jsonl` | 1.000 | `e4bd07d4…` |
| `laya/train.jsonl` | 3.000 | `cf839b96…` |
| `laya/dev.jsonl` | 1.000 | `594af1ce…` |
| `manifests/silver-export.json` | — | `b587a168…` |
| `manifests/classical-baselines.json` | — | `ea65d90d…` |
| `manifests/qwen3-v3-5000.json` | — | `cda55a90…` |

También se versionan `reports/classical-baselines.md`,
`reports/evaluation-dev.json` y el estado de la cola (`queue/`: jobs pendientes
y `setup` bloqueado en `running/`).

### No versionado (política de `.gitignore`)

- `data/classification/llm/raw/` y `data/classification/predictions/`.
- Pesos `models/gguf/*`.
- Cachés (`data/cache/`, respuestas crudas de fourplebs).

## Límites conocidos

1. `models/SHA256SUMS` queda vacío: se borraron los hashes sin re-verificar; los
   pesos no se re-hashean en esta rama.
2. El helper `commit()` de `review.py` no se usa todavía (refactor incompleto).
3. Laya y GLiNER siguen sin entrenar: `setup` está bloqueado por wheels CUDA sin
   `sm_61`; la GPU está libre.
4. Test congelado (`afae38a9…`) y no evaluado.
5. Dos `task_id` remapeados por `post_id` (`115110323`, `207330062`).
6. `training` no está rebasada sobre `origin/master` (31 commits de diferencia).

## Publicación

```bash
git push -u origin training
```

- Remoto: `https://github.com/RafaelValdivia/4chan-NLP-Dashboard.git`
- Rama: `training` (nueva; no toca `master`).
- Verificación: `git ls-remote origin refs/heads/training` debe devolver el tip
  de esta rama.
