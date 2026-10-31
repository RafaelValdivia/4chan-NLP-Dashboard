# Journal PLN — Entrada 2 (27-10-2026)

> Entrada redactada el 31-10-2026 a partir de la implementación del 27-10-2026
> (capas `formal` e `ingest`). Documenta lo efectivamente construido, lo que se
> desvía del plan de la entrada 1 y lo que queda pendiente.

## Resumen

Se implementaron las capas **formal** (esquemas, limpieza, normalización,
features, gramática GLC) e **ingest** (carga ROTLK, cliente 4plebs, muestreo,
deduplicación). El pipeline **todavía no corre end-to-end**: la capa común
(`keklab.common.*`), que el orden de ejecución asume como pasos 1–7, no existe
y es importada por casi todos los módulos implementados.

## Capa formal (implementada)

### Archivos

| Archivo | Contenido |
|---|---|
| `formal/schema.py` | Modelos Pydantic `Post`, `Thread`, `Annotation`, `Entity`. Post como unidad, thread como agrupación. |
| `formal/markup_regex.py` | Detección de HTML, citas (`>>id`), greentext, spoilers, backlinks, blockquotes, `<br>`, tags. |
| `formal/normalize.py` | NFKC, eliminación de URLs, colapso de puntuación, colapso de whitespace. |
| `formal/cleaning.py` | `clean_post(text, source)` unificado para `kek` vs `fourplebs`. |
| `formal/features.py` | Features estructurales por post y por hilo. |
| `formal/glc_grammar.lark` | Gramática GLC mínima (post → líneas: greentext, quote, plaintext, blank). |
| `formal/__init__.py` | Solo comentarios de rol/conexiones; no exporta símbolos. |

### Decisiones y comportamiento

- **Post + hilo:** la unidad de análisis es el post; las features de hilo se
  calculan sobre el hilo completo y se inyectan en cada post.
- **Limpieza por fuente:** `fourplebs` asume HTML y usa `strip_markup`; `kek`
  detecta HTML (`has_html`) y usa `strip_markup` o `strip_markup_plain`.
- **Citas y greentext** se extraen del texto *unescaped* (crudo), no del texto
  ya limpiado, para no perder `>>id` ni líneas `>`.
- **Normalización:** pipeline `NFKC → strip_urls → normalize_punct →
  normalize_whitespace`.
- **Esquema:** `source: kek | fourplebs`; `period: hist_2016_2019 |
  recent_2020_plus`; `Annotation.tier: gold | silver`; `Entity.method:
  gliner | spacy | rules`.

### GLC

La gramática se incorpora como artefacto de primera clase, pero **el parser
Lark no está implementado**. En consecuencia:

- `features.post_structural_features()` devuelve `cite_depth_max = 0`
  (`TODO: calcular desde AST GLC`).
- No hay validación estructural real de posts truncados (~2000 chars), aunque
  la gramática declara tolerancia a truncamiento.

## Capa ingest (implementada)

### Archivos

| Archivo | Contenido |
|---|---|
| `ingest/kek_loader.py` | Expansión ROTLK con DuckDB, iteración por chunks, canonicalización a `Post`, canonicalización de threads 4plebs. |
| `ingest/fourplebs_client.py` | Cliente HTTP con caché en disco, reintentos y fallback `httpx` → `urllib`. |
| `ingest/sample.py` | Censo por mes y muestreo estratificado a nivel hilo. |
| `ingest/dedupe.py` | Deduplicación por `content_hash` y por `(thread_id, post_id)`. |
| `ingest/__init__.py` | Solo comentarios de rol/conexiones. |

### Flujo ROTLK

- `ndjson_expand_to_parquet()`: un hilo por línea → un post por fila mediante
  `COPY (SELECT ... UNNEST(t.posts)) TO parquet (ZSTD)`. No materializa el
  dump completo en memoria.
- `iter_kek_posts_chunked()`: lee el parquet expandido con
  `fetch_df_chunk`, agrupa por `thread_id`, limpia cada post y construye
  objetos `Post` con features de post y de hilo.
- `canonicalize_kek_posts_chunked()`: vuelca los chunks a un parquet canónico.
- `load_kek_ndjson()` queda **DEPRECATED**: solo funciona con
  `limit_threads` (inspección/debug); con el corpus completo lanza error.
- `save_canonical()`: guarda el DataFrame canónico a parquet.

### Flujo 4plebs

- `FourplebsClient` con `cache_dir`, `sleep`, `timeout`; caché JSON en
  `RAW_DIR/fourplebs_cache`; reintentos con `tenacity` (5 intentos,
  backoff exponencial 2–30 s) o bucle manual si `tenacity` no está disponible.
- Base usada: `https://a.4cdn.org/pol` (comentario en el código: “ajustar según
  endpoint real”). Métodos: `get_catalog`, `get_archive_list`, `get_thread`.
- `canonicalize_fourplebs_thread()` mapea un thread de la API al esquema
  canónico usando `clean_post(..., source="fourplebs")`.

### Muestreo

- `census_and_group_by_month()`: agrupa hilos por mes del OP (`%Y-%m`) y cuenta
  en una sola pasada.
- `stratified_sample_threads()`: toma todos los hilos si el mes tiene
  ≤ `target_per_month` (50 por defecto); si no, muestrea con
  `random.Random(1234)`.
- El muestreo es **a nivel hilo**, para preservar el contexto conversacional.

### Deduplicación

- `content_hash()` = SHA256 de `text_clean`.
- Se deduplica primero por `content_hash` y luego por la clave natural
  `(thread_id, post_id)`.
- Queda pendiente verificar el caso de posts vacíos (ver deuda técnica).

## Capa común (pendiente, bloqueante)

El orden de ejecución del pipeline (`docs/pipeline_draft.md`) asume estos
módulos como pasos 1–7, pero **no existen en el repositorio**:

| Módulo esperado | Rol | Estado |
|---|---|---|
| `common/paths.py` | Rutas base (`RAW_DIR`, data, configs, reports) | No implementado |
| `common/seeds.py` | Semillas random/numpy/torch | No implementado |
| `common/logging.py` | Logging estructurado (`get_logger`) | No implementado |
| `common/io.py` | I/O parquet/ndjson/duckdb (`_con`, `_src_ndjson`, `write_parquet`) | No implementado |
| `common/registry.py` | Registro de modelos/datos | No implementado |
| `common/config.py` | Carga YAML + validación Pydantic | No implementado |
| `common/cli.py` | CLI `keklab` | No implementado |

Importaciones actuales que fallan: `keklab.common.io` (en `kek_loader.py`),
`keklab.common.logging` (en `dedupe.py`, `fourplebs_client.py`,
`kek_loader.py`, `sample.py`) y `keklab.common.paths` (en
`fourplebs_client.py`).

Consecuencia: `import keklab.ingest.*` falla en tiempo de import; no se puede
ejecutar ningún flujo del pipeline todavía.

## Estado de los experimentos

| ID | Estado | Nota |
|---|---|---|
| E0 | **Parcial** | Existe la limpieza regex por fuente; falta la comparación controlada crudo vs saneado. |
| E1 | No iniciado | Sin competencia de maestros ni LLM local/Laya/GLiClass. |
| E2 | No iniciado | Sin TF-IDF/BoW/embeddings ni LR/SVM. |
| E3 | No iniciado | Sin comparación clásicos vs transformers/LLM. |
| E4 | No iniciado | Sin evaluación de deriva temporal. |
| E5 | No iniciado | Sin chatbot ni suite de preguntas. |
| E6 | No iniciado | Sin extracción de entidades con GLiNER. |

## Estado del producto

- **Dashboard:** sin código; la tecnología de UI sigue pendiente.
- **Chatbot con tool calling:** sin código; solo están definidas las
  herramientas objetivo (`consultar`, `graficar`, `clasificar`, `resumir`,
  `extraer_entidades`).

## Deuda técnica y pendientes

1. **Implementar `keklab.common.*`** (pasos 1–7) para que el pipeline sea
   ejecutable.
2. **Parser GLC** para calcular `cite_depth_max` y validar estructura;
   actualmente el feature queda fijo en 0.
3. **`thread_link_count`** está en el esquema pero ningún flujo lo completa.
4. **Semántica de `thread_depth`:** hoy es el número de posts del hilo, no la
   profundidad de anidamiento; el nombre induce a error. Documentar o renombrar.
5. **Features de hilo por chunk:** un hilo partido entre chunks produce features
   parciales (`thread_depth`, citas y greentext incompletos).
6. **`canonicalize_kek_posts_chunked`:** en cada chunk relee el parquet
   acumulado completo y lo reescribe; el costo crece de forma cuadrática en I/O
   y no es apto para el corpus completo. Conviene escribir particiones y
   consolidar al final.
7. **Deduplicación de posts vacíos:** los posts sin texto comparten
   `content_hash = SHA256("")`, por lo que `drop_duplicates(content_hash)` los
   colapsa a uno. El “fix” declarado en el borrador no cubre este caso; excluir
   `text_clean == ""` del dedupe por hash (o deduplicar solo por
   `(thread_id, post_id)` cuando no hay texto).
8. **`is_op`:** se deriva de `resto == 0`; en la API de 4chan el OP
   normalmente no trae `resto`, por lo que quedaría `False`. Verificar contra
   datos reales y, si corresponde, derivar de `post_id == thread_id`.
9. **Endpoints 4plebs:** `FOURPLEBS_BASE` apunta a `a.4cdn.org/pol`; confirmar
   el endpoint archivado definitivo y su cobertura de los últimos 24 meses.
10. **Timestamps:** si falta `time`, se usa `datetime.now()`, lo que introduce
    ruido temporal; decidir si descartar el post o marcar el timestamp como
    faltante.
11. **Sin tests ni archivo de dependencias** en el repositorio; conviene fijar
    versiones y agregar pruebas mínimas de limpieza, features y muestreo.

## Próximos pasos sugeridos

1. Implementar `keklab.common.*` (paths, io, logging, seeds; luego config/CLI).
2. Correr un smoke test de punta a punta con un subconjunto pequeño de ROTLK.
3. Corregir deduplicación de vacíos e `is_op` antes de generar el corpus
   canónico.
4. Recién después avanzar con E0 (comparación crudo vs saneado) y E2.
