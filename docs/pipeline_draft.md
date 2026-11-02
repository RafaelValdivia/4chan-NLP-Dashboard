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

## Actualización: infraestructura de ejecución (02-11-2026)

### Módulos nuevos

| Archivo | Contenido |
|---|---|
| `src/keklab/common/config.py` | Carga YAML/JSON con `load_config()`, expansión de `${VAR}`, overrides por deep-merge y validación Pydantic (`KeklabConfig`). |
| `src/keklab/common/registry.py` | Registro append-only en JSONL (`ArtifactRecord`) para datasets/modelos/runs/reports, con SHA256 y tamaño de archivo. |
| `src/keklab/common/cli.py` | CLI `keklab`: `config`, `ingest`, `dedupe`, `registry` y `version`. |
| `src/keklab/__init__.py` | Versión del paquete (`0.1.0`). |
| `configs/default.yaml` | Configuración por defecto (rutas, ingest, formal, logging). |
| `pyproject.toml` | Empaquetado `src/`, dependencias y entry point `keklab = keklab.common.cli:main`. |

### Configuración

Precedencia: `--config` > `KEKLAB_CONFIG` > `configs/default.yaml` > defaults
internos. Las rutas relativas se resuelven contra la raíz del repo y las
variables `${VAR}` se expanden desde el entorno antes de validar. Cada sección
usa `extra="forbid"` para detectar claves desconocidas.

### CLI

| Comando | Función |
|---|---|
| `keklab config show [--json]` | Imprime la configuración efectiva. |
| `keklab config validate` | Valida el archivo seleccionado. |
| `keklab config dump <salida>` | Guarda la configuración efectiva. |
| `keklab ingest expand <ndjson> <parquet>` | Aplana ROTLK a un post por fila. |
| `keklab ingest canonicalize <parquet> <parquet>` | Canonicaliza a `Post`. |
| `keklab ingest stats <parquet> [--json]` | Conteos de posts/hilos/OP y rango temporal. |
| `keklab dedupe <parquet> <parquet>` | Aplica `dedupe_posts_df()`. |
| `keklab registry add/list/show` | Registra y consulta artefactos. |

### Tests

La suite queda en 30 pruebas (streaming NDJSON, limpieza, canonicalización,
dedupe, timestamps nulos, configuración, registro y CLI).

## Actualización: capa de anotación humana (02-11-2026)

### Módulos nuevos

| Archivo | Contenido |
|---|---|
| `src/keklab/annotation/labels.py` | Vocabulario canónico de 13 marcos, descripciones, reglas de exclusividad (`none`/`unclear`) y toggles. |
| `src/keklab/annotation/schema.py` | `SamplePost`, `SampleContext`, `ContextPost` y `AnnotationRecord`; claves de reanudación. |
| `src/keklab/annotation/store.py` | JSONL atómico, upsert por clave, reanudación, export CSV/JSONL y estadísticas. |
| `src/keklab/annotation/sampler.py` | Cliente de archivo 4plebs (index/thread/search), muestreo aleatorio estratificado y dirigido, y muestreo desde parquet canónico de ROTLK. |
| `src/keklab/annotation/agreement.py` | Kappa de Cohen, kappa cuadrática ponderada, F1 macro/micro y reporte self test-retest. |
| `src/keklab/annotation/cli.py` | CLI interactiva `keklab annotate` con auto-guardado y reanudación. |
| `docs/annotation_guidelines.md` | Codebook v0: definiciones, ejemplos, solapamientos, toxicidad y limitaciones. |

### Esquema

- `Annotation.threat` se elimina.
- `Annotation.toxicity` pasa a entero ordinal `0–3`.
- `Annotation` incorpora `thread_id`, `source`, `period`, `content_hash` y
  `annotated_utc`.
- `AnnotationRecord` valida el vocabulario y exige toxicidad.
- Los marcos son **binarios multi-label**; no hay escala Likert.
- `none` y `unclear` son excluyentes con cualquier otro marco y entre sí.
- `content_hash` une candidato y anotación y detecta cambios de texto.

### Muestreo

- **4plebs:** ventana de 24 meses; 20 posts aleatorios estratificados por mes y
  10 dirigidos a `rusophobia`, `sinophobia` y `accelerationism` mediante
  búsqueda. Se guarda el OP y los posts citados como contexto. El cliente usa
  `curl` cuando está disponible porque el archivo rechaza la huella TLS de
  `httpx`/`urllib`; mantiene caché en disco y límite de tasa.
- **ROTLK:** el mismo contrato sobre parquet canónico. La ventana se calcula
  desde el último timestamp del corpus, no desde la fecha actual.
- La muestra aleatoria sirve para prevalencia; la dirigida solo para
  entrenamiento/calibración.

### CLI

| Comando | Función |
|---|---|
| `keklab annotate sample` | Genera candidatos desde 4plebs o ROTLK. |
| `keklab annotate run` | Anotación interactiva por terminal, con reanudación por ronda/anotador. |
| `keklab annotate export` | Exporta CSV (one-hot por marco) o JSONL. |
| `keklab annotate stats` | Conteos, distribución de marcos y toxicidad. |
| `keklab annotate agreement` | Kappa por marco, kappa cuadrática de toxicidad y F1 macro/micro. |

### Acuerdo

El piloto usa **self test-retest** sobre ~20% de la muestra, con al menos una
semana de separación. Mide consistencia intra-anotador, no acuerdo
inter-anotador. Un kappa bajo obliga a revisar el codebook antes de congelar
`v1` y escalar el conjunto oro.

### Tests

La suite queda en 68 pruebas. Las nuevas cubren vocabulario y exclusividad,
validación de esquema, upsert/reanudación/export, parsing de la API de archivo,
muestreo 4plebs y ROTLK con fixtures sintéticos, kappa/F1 y la CLI interactiva.

La validación del sampler de ROTLK con el dump real sigue bloqueada hasta que el
dump esté disponible; los tests usan parquet sintético.

