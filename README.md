# keklab

Pipeline de PLN sobre `/pol/` de 4chan: capas **formal** (limpieza y features
deterministas) e **ingest** (ROTLK histórico y API de 4plebs), con una capa
común de configuración, I/O y registro de artefactos.

## Estructura

```
src/keklab/
  common/    paths, logging, seeds, io, config, registry, cli
  formal/    schema, cleaning, normalize, markup_regex, features, GLC
  ingest/    kek_loader, fourplebs_client, sample, dedupe
  annotation/ labels, schema, store, sampler, agreement, cli
tests/       suite de pytest
configs/     configuración YAML
docs/        notas del pipeline y codebook de anotación
Journal/     bitácora del proyecto
```

## Instalación

```bash
python -m venv ~/PyVenvs/NNnPLN
~/PyVenvs/NNnPLN/bin/python -m pip install -e ".[dev,ingest,formal]"
```

Sin instalación editable también se puede ejecutar con:

```bash
PYTHONPATH=src python -m keklab.common.cli --help
```

## Uso

```bash
keklab config show                 # configuración efectiva (YAML)
keklab config show --json          # configuración efectiva (JSON)
keklab config validate             # valida configs/default.yaml

keklab ingest expand raw/threads.ndjson data/expanded.parquet
keklab ingest canonicalize data/expanded.parquet data/canonical.parquet
keklab ingest stats data/canonical.parquet --json
keklab dedupe data/canonical.parquet data/deduped.parquet

keklab registry add dataset rotlk --path raw/threads.ndjson --source rotlk
keklab registry list --kind dataset
keklab registry show <artifact-id>

# anotación humana (ver docs/annotation_guidelines.md)
keklab annotate sample --source fourplebs --months 24 --random 20 --targeted 10 \
  --out data/samples/pilot_fourplebs.jsonl

# ROTLK real: se lee el .tar.zst montado en el disco externo, sin copiarlo
export KEKLAB_ROTLK_DATASET=/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst
keklab annotate sample --source rotlk --months 24 --random 20 --targeted 10 \
  --seed 13 --out data/samples/rotlk_pilot.jsonl
keklab annotate run --input data/samples/pilot_fourplebs.jsonl \
  --annotator flynnso --guideline v0.2 --out data/annotations/pilot_r1.jsonl
keklab annotate stats --input data/annotations/pilot_r1.jsonl
keklab annotate export --input data/annotations/pilot_r1.jsonl --format csv
keklab annotate agreement --a data/annotations/pilot_r1.jsonl \
  --b data/annotations/pilot_r2.jsonl

# herramientas del piloto: fusión, auditoría, split y retest
keklab annotate merge --input a.jsonl b.jsonl --out merged.jsonl \
  --expect-total 200 --expect-random 190 --expect-targeted 10
keklab annotate audit --input merged.jsonl \
  --start 2017-11-11T10:15:36Z --end 2019-11-01T10:15:36Z
keklab annotate split --input merged.jsonl --out splits.jsonl --seed 13
keklab annotate retest --input merged.jsonl --out retest.jsonl \
  --fraction 0.2 --seed 13
```

La anotación fina usa 16 marcos; el modelado los agrupa en 7 cabezas
(`src/keklab/annotation/taxonomy.py`). El CSV exporta ambos niveles
(`frame_labels`/`coarse_labels` y sus one-hot). El protocolo de evaluación
pre-registrado está en `docs/evaluation_protocol.md`.

La anotación es interactiva por terminal. Los marcos son binarios multi-label;
la toxicidad es ordinal `0–3`. El piloto usa self test-retest sobre ~20% de la
muestra; el codebook y sus limitaciones están en `docs/annotation_guidelines.md`.

## Pre-anotación asistida por IA

El flujo `keklab annotate ai` permite que un agente proponga etiquetas para
posts pendientes. Las propuestas **no son oro**: solo una persona puede
aceptarlas o editarlas desde la revisión por terminal. La generación es
file-based (tareas → propuestas → importación), sin llamadas a una API de LLM
desde `keklab`.

```bash
# 1. construir tareas para los posts sin oro
keklab annotate ai task \
  --input data/samples/rotlk_pilot_200.jsonl \
  --gold data/annotations/rotlk_pilot_r1.jsonl \
  --out data/annotations/tasks/rotlk_pending_148.jsonl

# 2. importar las propuestas que escribió el agente
keklab annotate ai import \
  --tasks data/annotations/tasks/rotlk_pending_148.jsonl \
  --input data/annotations/proposals/big-pickle.jsonl \
  --out data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl

# 3. validar humanamente (a = aceptar, e = editar, r = rechazar, s = saltar)
keklab annotate ai review \
  --tasks data/annotations/tasks/rotlk_pending_148.jsonl \
  --proposals data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl \
  --gold data/annotations/rotlk_pilot_r1.jsonl \
  --reviews data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl \
  --reviewer flynnso

# 4. cobertura, decisiones y calibración
keklab annotate ai stats \
  --tasks data/annotations/tasks/rotlk_pending_148.jsonl \
  --proposals data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl \
  --reviews data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl
```

El contrato completo, incluida la regla **text-only** (sin OP, quotes, asunto ni
estrato de muestreo), está en `docs/ai_annotation_protocol.md`.

Para un agente relevo, las instrucciones operativas están en
`docs/handoff_llm_annotation.md` y el prompt vigente en
`docs/prompts/annotation_prompt_v2.txt`.

La configuración se selecciona con `--config`, la variable `KEKLAB_CONFIG` o
`configs/default.yaml`, en ese orden. Las rutas relativas se resuelven contra la
raíz del repositorio y las variables `${VAR}` se expanden desde el entorno.

## Tests

```bash
~/PyVenvs/NNnPLN/bin/python -m pytest -q
```

El sampler de ROTLK se validó contra el dump real
(`pol_0616-1119_labeled.tar.zst`, 113.86 GB descomprimidos) leyéndolo en sitio
con `zstd` + `tarfile`: no se extrae ni se copia al repositorio. Los tests usan
fixtures sintéticos que reproducen el contrato y también construyen archivos
`.tar.zst` pequeños para probar el streaming. El piloto real quedó en
`data/samples/rotlk_pilot_200.jsonl`: 200 posts y 200 hilos únicos (190
aleatorios + 10 dirigidos) en la ventana `2017-11-11 → 2019-11-01`, con 25
meses calendario cubiertos. El archivo de 30 se conserva como procedencia y el
split por hilo está en `data/splits/rotlk_pilot_200_threads.jsonl`.
