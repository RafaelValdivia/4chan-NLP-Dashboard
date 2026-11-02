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
keklab annotate run --input data/samples/pilot_fourplebs.jsonl \
  --annotator flynnso --guideline v0 --out data/annotations/pilot_r1.jsonl
keklab annotate stats --input data/annotations/pilot_r1.jsonl
keklab annotate export --input data/annotations/pilot_r1.jsonl --format csv
keklab annotate agreement --a data/annotations/pilot_r1.jsonl \
  --b data/annotations/pilot_r2.jsonl
```

La anotación es interactiva por terminal. Los marcos son binarios multi-label;
la toxicidad es ordinal `0–3`. El piloto usa self test-retest sobre ~20% de la
muestra; el codebook y sus limitaciones están en `docs/annotation_guidelines.md`.

La configuración se selecciona con `--config`, la variable `KEKLAB_CONFIG` o
`configs/default.yaml`, en ese orden. Las rutas relativas se resuelven contra la
raíz del repositorio y las variables `${VAR}` se expanden desde el entorno.

## Tests

```bash
~/PyVenvs/NNnPLN/bin/python -m pytest -q
```

La validación con el corpus real de ROTLK está pospuesta; los tests usan
fixtures sintéticos que reproducen su contrato.
