# Journal PLN — Entrada 4 (02-11-2026)

## Decisión: posponer la validación con ROTLK

Se decide continuar el desarrollo sin ejecutar el pipeline sobre el dump real
de ROTLK. La validación con el corpus histórico queda pospuesta hasta que el
archivo esté disponible y su esquema pueda verificarse contra el contrato de
`Post`.

## Qué se pospone

- `ndjson_expand_to_parquet()` y `canonicalize_kek_posts_chunked()` sobre ROTLK.
- El smoke test con datos reales.
- El cierre de E0 (crudo vs saneado) con el corpus histórico.
- Mediciones de volumen/tiempos sobre el corpus completo.

## Cómo se valida mientras tanto

- Fixtures sintéticos que reproducen el contrato: hilo con `posts`, `no`,
  `time`, `resto`, `com`, `sub`, `country`, `filename`, `tim`.
- El smoke test sintético pasa a ser la red de seguridad del pipeline.
- Los tests se versionan en `tests/` con pytest.

## Decisiones

- **Timestamps faltantes:** `Post.timestamp_utc` pasa a ser nullable. Si el post
  no trae `time`, se guarda `None`; no se inventa una fecha con
  `datetime.now()`.
- **Dedupe de vacíos:** el dedupe por `content_hash` solo aplica a posts con
  `text_clean` no vacío. Los posts vacíos se conservan y se deduplican
  únicamente por `(thread_id, post_id)`.

## Qué se puede avanzar sin ROTLK

1. Dedupe de posts vacíos (`content_hash = SHA256("")`).
2. Política de timestamps faltantes.
3. Tests del pipeline (streaming, limpieza, canonicalización, dedupe).
4. `config.py`, `registry.py`, `cli.py`.
5. Esqueleto de E0/E2 desacoplado del corpus.

## Criterios para retomar

1. Disponer del NDJSON de ROTLK.
2. Correr el smoke test real contra el contrato de `Post`.
3. Verificar conteos, timestamps e `is_op`.
4. Recién entonces correr E0/E2 sobre el corpus.

## Estado

- E0: bloqueado para resultados reales; el harness puede prepararse con
  fixtures.
- E1–E6: no iniciados.

## Actualización: infraestructura de ejecución

Se completa la capa común pendiente de la Entrada 3 (`config.py`,
`registry.py`, `cli.py`) y el paquete queda instalable/ejecutable.

### Configuración (`common/config.py`)

- Carga YAML o JSON con `load_config()` y validación Pydantic
  (`KeklabConfig` → `PathsConfig`, `IngestConfig`, `FormalConfig`,
  `LoggingConfig`).
- Precedencia: `--config` > `KEKLAB_CONFIG` > `configs/default.yaml` >
  defaults internos.
- Expansión de `${VAR}`/`$VAR` desde el entorno y resolución de rutas
  relativas contra la raíz del repositorio.
- Overrides por deep-merge y `extra="forbid"` en cada sección para detectar
  claves desconocidas.
- `dump_config()` permite guardar la configuración efectiva de una corrida.
- Archivo por defecto versionado: `configs/default.yaml`.

### Registro (`common/registry.py`)

- Registro append-only en JSONL (`data/registry.jsonl` por defecto,
  configurable con `KEKLAB_REGISTRY_PATH`).
- `ArtifactRecord` valida `kind` (`dataset`, `model`, `run`, `report`,
  `config`), nombre, ruta, origen, parámetros y métricas.
- Calcula SHA256 y tamaño de archivos existentes; permite registrar salidas
  todavía no generadas.
- API: `register_artifact()`, `load_registry()`, `list_artifacts()`,
  `get_artifact()`, `latest_artifact()`.

### CLI (`common/cli.py`)

`keklab` queda como entry point (`pyproject.toml`):

| Comando | Función |
|---|---|
| `config show/validate/dump` | Configuración efectiva y validación. |
| `ingest expand/canonicalize/stats` | Flujo ROTLK desde NDJSON hasta parquet canónico. |
| `dedupe` | Deduplicación sobre parquet. |
| `registry add/list/show` | Alta y consulta de artefactos. |

`ingest stats` reporta posts, hilos, OP y rango temporal usando DuckDB sin
materializar el corpus en pandas.

### Empaquetado y tests

- `pyproject.toml` declara paquete `src/`, dependencias base y extras
  `ingest`, `formal` y `dev`.
- Se agregó `PyYAML` a las dependencias.
- La suite pasa a **30 tests**: pipeline, configuración, registro y CLI.
- El paquete se instaló en modo editable en `~/PyVenvs/NNnPLN` y el comando
  `keklab` responde.

### Próximo paso

Esqueleto de E0/E2 desacoplado del corpus: comparación crudo vs saneado y
representación + clasificador clásico sobre fixtures, sin resultados reales de
ROTLK todavía.
