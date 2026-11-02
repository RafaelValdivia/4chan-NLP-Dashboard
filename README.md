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
tests/       suite de pytest
configs/     configuración YAML
docs/        notas del pipeline
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
```

La configuración se selecciona con `--config`, la variable `KEKLAB_CONFIG` o
`configs/default.yaml`, en ese orden. Las rutas relativas se resuelven contra la
raíz del repositorio y las variables `${VAR}` se expanden desde el entorno.

## Tests

```bash
~/PyVenvs/NNnPLN/bin/python -m pytest -q
```

La validación con el corpus real de ROTLK está pospuesta; los tests usan
fixtures sintéticos que reproducen su contrato.
