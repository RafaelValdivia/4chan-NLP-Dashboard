# Pipeline (borrador para documentación del proyecto)

Orden de ejecución lógico del pipeline actual y decisiones de implementación.

## Orden de ejecución

| Orden | Módulo/Archivo | Función | Notas |
|---|---|---|---|
| 1 | `src/keklab/common/paths.py` | Rutas base (data, configs, reports) | Usado por todo. |
| 2 | `src/keklab/common/seeds.py` | Semillas (random/numpy/torch) | Antes de muestreo/entrenamiento. |
| 3 | `src/keklab/common/logging.py` | Logging estructurado | Infra compartida. |
| 4 | `src/keklab/common/io.py` | I/O parquet/ndjson/duckdb | Lectura/escritura columnar. |
| 5 | `src/keklab/common/registry.py` | Registro de modelos/datos | Metadatos. |
| 6 | `src/keklab/common/config.py` | Carga YAML + validación Pydantic | Por experimento. |
| 7 | `src/keklab/common/cli.py` | CLI `keklab` | Entry point. |
| 8 | `src/keklab/formal/schema.py` | Contratos `Post/Thread/Annotation/Entity` | Post como unidad, agrupado por `thread_id`. |
| 9 | `src/keklab/formal/markup_regex.py` | Marcas 4chan (`>>`, greentext, spoilers, backlinks) | Extrae citas, cuenta greentext, strip markup. |
| 10 | `src/keklab/formal/normalize.py` | Unicode NFKC, URLs, espacios, puntuación | Normalización. |
| 11 | `src/keklab/formal/glc_grammar.lark` | Gramática GLC (first-class) | Tolerante a truncamiento (~2000). AST -> `profundidad_anidamiento`, `n_citas`, `tags_usados`. |
| 12 | `src/keklab/ingest/dedupe.py` | Deduplicación | Por `content_hash` y `(thread_id, post_id)`. |
| 13 | `src/keklab/ingest/kek_loader.py` | Carga ROTLK/ndjson | Hilos con posts; mapea a `Post`, `source=kek`, `period=hist_2016_2019`. |
| 14 | `src/keklab/ingest/fourplebs_client.py` | Cliente 4plebs/4chan API | Catálogo/archivo/hilo, cache disco, `tenacity`, reintentos. |
| 15 | `src/keklab/ingest/sample.py` | Censo + muestreo estratificado | Por mes/hilo, preservar contexto conversacional. |

## Decisiones de implementación y justificación

### Arquitectura
- **Tres capas**: formal (determinista), clásico (alto volumen), generativo (etiquetado/asistencia/chatbot). El LLM no procesa millones de posts.
- **Post + hilo**: unidad de análisis = post; agrupación = hilo. Features de hilo inyectados en post.
- **GLC first-class**: `glc_grammar.lark` no decorativo; AST alimenta extractor de citas y features estructurales.
- **Servicios compartidos**: `core/` será fuente única para dashboard y chatbot (lógica no reimplementada en UI).

### Ingesta
- **ROTLK ndjson**: cada línea = hilo completo con lista de posts. Claves flexibles (`no`/`post_id`, `com`/`comment`/`text`, `time`, `resto`, `sub`, `filename`, `country`).
- **4plebs**: usar API de 4chan (`a.4cdn.org/pol`). Sin volumen total conocido -> censo ligero primero, luego muestreo estratificado por mes. Cache en disco + reintentos exponenciales.
- **Deduplicación defensiva**: `content_hash` sobre `text_clean` + `(thread_id, post_id)`.
- **Periodo**: `period = hist_2016_2019` (Kek) o `recent_2020_plus` (4plebs). `source` distingue origen.

### Formal
- **Marcas 4chan**: `>>id` (citas), greentext (`>` línea), spoilers, backlinks, `<br>`, bloques.
- **Normalización**: NFKC, URLs -> espacio, colapso whitespace, normalización de puntuación.
- **GLC tolerante**: parse parcial en truncamiento (~2000 chars) con nodo incompleto marcado.

## Actualización: conexión formal <-> ingest (27-10-2026)

### Cambios realizados
| Archivo | Cambio |
|---|---|
| `src/keklab/formal/__init__.py` | Creado |
| `src/keklab/formal/schema.py` | Creado (Post/Thread/Annotation/Entity + features estructurales) |
| `src/keklab/formal/markup_regex.py` | Creado (detección HTML, quotes, greentext, strip markup) |
| `src/keklab/formal/normalize.py` | Creado (Unicode NFKC, URLs, whitespace) |
| `src/keklab/formal/cleaning.py` | Creado (unificado por fuente: kek vs fourplebs) |
| `src/keklab/formal/features.py` | Creado (features post/hilo) |
| `src/keklab/formal/glc_grammar.lark` | Creado (GLC first-class) |
| `src/keklab/ingest/kek_loader.py` | Conectado a `formal.cleaning` + `formal.features`, añadido `canonicalize_fourplebs_thread()` |
| `src/keklab/ingest/dedupe.py` | Corregido (no colapsa posts vacíos) |
| `src/keklab/ingest/sample.py` | Añadido `census_and_group_by_month()` |
| `src/keklab/ingest/fourplebs_client.py` | Añadido fallback urllib, cache, reintentos |

### Lógica formal-ingest
- ROTLK: detecta HTML (defensivo). Usa `clean_post(text, source="kek")`
- 4plebs: siempre HTML. Usa `clean_post(text, source="fourplebs")`. Quotes extraídos de texto unescaped
- Features a nivel hilo calculados sobre hilo completo e inyectados en cada post
- Sin cargar dump ROTLK completo en memoria (DuckDB UNNEST + chunks)
