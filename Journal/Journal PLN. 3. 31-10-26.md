# Journal PLN — Entrada 3 (31-10-2026)

## Contexto

Se retoma la deuda de la Entrada 2: la capa común estaba ausente y el pipeline
no era importable. Hoy se configuró el entorno, se implementó
`keklab.common.*`, se resolvió el streaming del NDJSON y se corrió el primer
smoke test con un fixture sintético.

## Entorno

- Venv: `~/PyVenvs/NNnPLN` (Python 3.14.8).
- Dependencias instaladas desde `requirements.txt`: `duckdb 2.0.0`,
  `pandas 3.1.0`, `pydantic 2.14.2`, `httpx 0.28.1`, `tenacity 9.2.1`,
  `lark 1.3.1`, `numpy 2.5.4`.
- Todos los módulos de `keklab` importan correctamente con `PYTHONPATH=src`.

## Capa común (implementada)

| Archivo | Contenido |
|---|---|
| `common/paths.py` | `PROJECT_ROOT`, `DATA_DIR`, `RAW_DIR`, `PROCESSED_DIR`, `CACHE_DIR`, `CONFIGS_DIR`, `REPORTS_DIR`, `ensure_dirs()` |
| `common/logging.py` | `configure_logging()` / `get_logger()` |
| `common/seeds.py` | `set_seeds()` para random/NumPy/PyTorch |
| `common/io.py` | `_con`, `_src_ndjson`, `write_parquet`, `consolidate_parquet`, `ParquetPartWriter`, `iter_ndjson`, `iter_ndjson_batches`, `count_ndjson_lines` |

Pendientes de la capa común: `config.py`, `registry.py`, `cli.py`.

## Streaming NDJSON

Se confirmó que ROTLK es NDJSON (un hilo por línea). Por lo tanto:

- `ndjson_expand_to_parquet()` ya **no** usa `read_json_auto`; lee línea por
  línea con `iter_ndjson()`, aplana posts y escribe parts parquet por lote.
- `canonicalize_kek_posts_chunked()` usa `ParquetPartWriter`, eliminando la
  relectura/reescritura completa del parquet por chunk (antes O(n²) en I/O).
- Soporte para `.ndjson`, `.jsonl`, `.gz` y `.bz2`; líneas malformadas se
  omiten con warning.

## Smoke test sintético

Se usó un fixture de 2 hilos / 6 posts con: OP sin `resto`, HTML con `<br>`,
citas `&gt;&gt;`, greentext, spoilers, un post vacío y un post sin `time`.

Resultados:

- 6/6 posts expandidos y canonicalizados como `Post` válidos.
- `is_op` correcto solo en los OP.
- `canonicalize_fourplebs_thread()` produce `source="fourplebs"` y
  `period="recent_2020_plus"`.
- Limpieza: citas y greentext extraídos correctamente desde HTML crudo.

Script temporal en `/tmp/opencode/smoke_keklab.py`, no versionado.

## Correcciones realizadas

| Archivo | Corrección |
|---|---|
| `formal/schema.py` | Eliminado token `PYTHON` al final del archivo (rompía el import). |
| `ingest/kek_loader.py` | Manejo de `NaN`/`NaT` de pandas/DuckDB (`_is_missing`, `_as_text`, `_optional_text`). |
| `ingest/kek_loader.py` | Timestamps aceptan tipos NumPy; `is_op` derivado también de `post_id == thread_id`. |
| `formal/markup_regex.py` | `extract_quotes`/`count_greentext` unescapean HTML y tratan `<br>` como salto de línea. |
| `formal/cleaning.py` | Usa los extractores corregidos sin doble unescape. |

## Deuda técnica / pendientes

1. **`time` faltante:** hoy cae a `datetime.now()`; decidir si descartar el
   post o permitir `timestamp_utc` nulo.
2. **Dedupe de posts vacíos:** todos comparten `SHA256("")`; no se ejercitó con
   más de un post vacío.
3. **Features de hilo por chunk:** un hilo dividido entre chunks produce
   features parciales.
4. **GLC:** gramática presente, parser aún no implementado
   (`cite_depth_max = 0`).
5. **`config.py` / `registry.py` / `cli.py`:** pendientes.
6. **Tests:** no hay suite; el smoke test vive fuera del repo.

## Estado de los experimentos

| ID | Estado |
|---|---|
| E0 | Parcial: limpieza implementada y verificada con el fixture; falta la comparación controlada crudo vs saneado. |
| E1–E6 | No iniciados. |

## Próximos pasos

1. Corregir el dedupe de posts vacíos y decidir la política de timestamps
   faltantes.
2. Iniciar E0 (crudo vs saneado).
3. Implementar `config`/`CLI`/`registry` cuando el pipeline estable lo requiera.
