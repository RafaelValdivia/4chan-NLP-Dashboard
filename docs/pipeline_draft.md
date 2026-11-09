# Pipeline (borrador para documentación del proyecto)

Orden de ejecución lógico del pipeline actual y decisiones de implementación.

> **Nota (09-11-2026).** Este documento conserva el diseño original del piloto.
> Las secciones que describen 18 marcos finos y 8 cabezas gruesas (incluida
> `eugenics_ableism`) están **superadas** por el codebook v0.2: 16 marcos y 7
> cabezas, tras retirar `eugenics` y `ableism`. La referencia vigente es
> `docs/annotation_guidelines.md`; la decisión está en
> `Journal/Journal PLN. 16. 09-11-26.md`.

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
| `src/keklab/annotation/labels.py` | Vocabulario canónico de 18 marcos, descripciones, reglas de exclusividad (`none`/`unclear`) y toggles. |
| `src/keklab/annotation/schema.py` | `SamplePost`, `SampleContext`, `ContextPost` y `AnnotationRecord`; claves de reanudación. |
| `src/keklab/annotation/store.py` | JSONL atómico, upsert por clave, reanudación, export CSV/JSONL y estadísticas. |
| `src/keklab/annotation/sampler.py` | Cliente de archivo 4plebs (index/thread/search), muestreo aleatorio estratificado y dirigido, muestreo desde parquet canónico de ROTLK y muestreo directo desde el dump `.tar.zst` sin extraerlo. |
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
  10 dirigidos a marcos raros (`rusophobia`, `sinophobia`, `accelerationism`,
  `racism`, `eugenics`, `ableism`, `misogyny`, `transphobia`,
  `homophobia`) mediante
  búsqueda. Se guarda el OP y los posts citados como contexto. El cliente usa
  `curl` cuando está disponible porque el archivo rechaza la huella TLS de
  `httpx`/`urllib`; mantiene caché en disco y límite de tasa.
- **ROTLK:** el mismo contrato sobre parquet canónico o, preferentemente,
  directamente sobre el `.tar.zst` externo. La ventana se calcula desde el
  último timestamp del corpus, no desde la fecha actual, y se filtra por
  timestamp exacto, no solo por mes. El muestreo directo hace una sola pasada y
  mantiene reservorios por mes y por término; no materializa el corpus ni
  escribe parquet intermedio. Los posts cuyo texto limpio queda vacío se
  descartan, y el cupo dirigido se reparte entre marcos.
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

La suite queda en 87 pruebas. Las nuevas cubren vocabulario y exclusividad,
validación de esquema, upsert/reanudación/export, parsing de la API de archivo,
muestreo 4plebs y ROTLK con fixtures sintéticos, kappa/F1, la CLI interactiva y
el streaming de archivos `.tar.zst`/NDJSON comprimido.

## Actualización: ROTLK real (02-11-2026)

El dump está en un disco externo ya montado:

```
/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst
```

- 22.4 GiB comprimidos; un frame zstd con un único miembro tar,
  `pol_062016-112019_labeled.ndjson`, de 113.86 GB descomprimidos.
- Cada línea es un hilo con `posts`; el sample inicial confirma UTF-8/JSON
  válidos y cobertura 2016-06 → 2019-11.
- Los posts incluyen `perspectives` (Perspective API) y `entities`/`entitites`
  (NER), además de campos de 4chan. **No hay etiquetas humanas de marcos**, así
  que la anotación sigue siendo necesaria.
- Descomprimir el archivo completo tarda ~155 s; una pasada de muestreo con
  parseo JSON y búsqueda de términos tarda decenas de minutos. Por eso el
  sampler directo usa reservorios y no escribe una copia canónica.
- `KEKLAB_ROTLK_DATASET` apunta al archivo; `--dataset` lo puede sobrescribir.
  `--limit-threads` sirve para smoke tests sin recorrer el corpus completo.

```bash
export KEKLAB_ROTLK_DATASET=/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst
keklab annotate sample --source rotlk --months 24 --random 20 --targeted 10 \
  --seed 13 --out data/samples/rotlk_pilot.jsonl
```

La ruta alternativa `--parquet` sigue disponible para cuando exista un parquet
canónico; el dump crudo no se copia al repositorio.

Piloto final: 3,397,911 hilos / 134,529,233 posts en 2,025 s, ventana
`2017-11-11T10:15Z → 2019-11-01T10:15Z`, 30 samples (20 aleatorios + 10
dirigidos), sin posts fuera de ventana ni textos limpios vacíos. Los aleatorios
cubren 20 meses distintos; los dirigidos quedaron 4 `rusophobia`, 3
`sinophobia` y 3 `accelerationism`.


## Actualización: vocabulario y presupuesto de etiquetas (03-11-2026)

`gender` se reemplazó por `antifeminism` en el índice 10. El cambio estrecha la
etiqueta: antes cubría roles de género, masculinidad y temas LGBTQ+ generales;
ahora se limita a hostilidad u oposición al feminismo o a los derechos de las
mujeres. `transphobia` y `homophobia` dejan de ser sustitutos de `gender` y
pasan a ser ejes independientes que pueden coexistir con `antifeminism`. Se
agregaron términos dirigidos para el marco nuevo (`feminism`, `feminist`,
`femoid`, `suffragette`, `misandry`, `women's rights`, `female privilege`).

> Nota (06-11-2026): este marco se renombró a `misogyny` y se amplió su
> definición para incluir objetificación y hostilidad hacia las mujeres como
> clase. Las menciones a `antifeminism` en esta sección son históricas. Ver la
> enmienda en `docs/evaluation_protocol.md`.

### Chequeo de infradeterminación

Con 18 marcos, 16 de ellos no exclusivos más `none` y `unclear`, el espacio de
etiquetas posibles es:

```
2^16 + 2 = 65,538 conjuntos de marcos
```

El piloto tiene 30 posts, así que como máximo observa 30 de esos conjuntos. Eso
no invalida la anotación, pero sí limita lo que se puede aprender de ella. Para
un marco con prevalencia `p`, la probabilidad de no ver ningún positivo en 30
posts y el número de posts necesario para esperar 10 positivos son:

| Prevalencia | Positivos esperados (n=30) | P(0 positivos) | P(≥5 positivos) | n para 10 positivos |
|---:|---:|---:|---:|---:|
| 1% | 0.3 | 0.740 | 0.000 | 1,000 |
| 2% | 0.6 | 0.545 | 0.000 | 500 |
| 5% | 1.5 | 0.215 | 0.016 | 200 |
| 10% | 3.0 | 0.042 | 0.175 | 100 |
| 15% | 4.5 | 0.008 | 0.476 | 67 |
| 20% | 6.0 | 0.001 | 0.745 | 50 |

El self test-retest del 20% son **6 posts**. Un kappa por marco calculado sobre
6 decisiones no es estimable para marcos raros: con 0 o 1 positivos, el valor
depende de casos degenerados. Además, 18 cabezas binarias sobre un encoder de
768 dimensiones implican ~13,800 parámetros de salida, entrenados con 30
ejemplos.

En el piloto actual, la búsqueda de términos semilla encuentra:

| Marco | Posts con término semilla (n=30) |
|---|---:|
| `racism` | 2 |
| `ableism` | 1 |
| `eugenics` | 0 |
| `transphobia` | 0 |
| `homophobia` | 0 |
| `misogyny` | 0 |

Esto es solo un proxy de candidatos, no prevalencia anotada, pero confirma que
los marcos nuevos tendrán muy pocos positivos en este piloto.

### Recomendación

Separar la **taxonomía de anotación** (fina, 18 marcos) de la **taxonomía de
modelado** (gruesa). La anotación fina conserva el detalle analítico; el modelo
agrupa marcos que comparten señal y que el tamaño de muestra no permite
distinguir. Una propuesta de 8 cabezas:

| Cabeza de modelado | Marcos finos |
|---|---|
| `conspiracy` | `conspiracy` |
| `ethnoracial_prejudice` | `ethnonationalism`, `racism`, `antisemitism`, `islamophobia`, `rusophobia`, `sinophobia` |
| `gender_sexuality_prejudice` | `misogyny`, `transphobia`, `homophobia` |
| `eugenics_ableism` | `eugenics`, `ableism` |
| `institutional_distrust` | `institutional_distrust` |
| `violence_acceleration` | `violence_glorification`, `accelerationism` |
| `meta_topic` | `meta_topic` |
| `no_frame` | `none`, `unclear` |

Reglas asociadas:

1. Un marco fino solo entra a E0/E2 si tiene **≥30 positivos en train** y **≥5
   en test**; si no, se reporta solo de forma descriptiva.
2. La muestra aleatoria estima prevalencia; la dirigida solo entrena/calibra.
3. Si se necesitan marcos finos, el piloto debe crecer según la tabla de tamaño
   muestral de abajo; para el esquema grueso, 200 posts pueden alcanzar si la
   prevalencia es ≥15%, y 1,000 si ronda el 5%.
4. La alternativa jerárquica es una cabeza gruesa más una cabeza hija solo para
   los marcos que superen el umbral de soporte.

Esta separación evita que 18 etiquetas con 30 ejemplos produzcan un modelo
infradeterminado sin renunciar al codebook fino.

> Actualización (09-11-2026): el chequeo se repitió con los 200 posts
> anotados. El modelo fino de 18 marcos sigue infradeterminado: 17 de 18 marcos
> no alcanzan ≥30 positivos en train y ≥5 en test. En el esquema grueso solo
> `ethnoracial_prejudice` (30/12) y `no_frame` (70/22) cumplen; las otras 6
> cabezas no. El piloto alcanza para un proof-of-concept binario de
> `ethnoracial_prejudice`, no para las 8 cabezas. Ver
> `Journal/Journal PLN. 15. 09-11-26.md` y la enmienda de
> `docs/evaluation_protocol.md`.

### Cuántos posts faltan

No hay un número único: depende de la prevalencia `p` del marco más raro que se
quiera modelar y del mínimo `K` de positivos por marco. La relación es
`n = K / p`; los adicionales sobre los 30 actuales son `n - 30`.

| `p` del marco más raro | K=10 (evaluar) | K=30 | K=50 (entrenar) | K=100 |
|---:|---:|---:|---:|---:|
| 1% | 1,000 (970) | 3,000 (2,970) | 5,000 (4,970) | 10,000 (9,970) |
| 2% | 500 (470) | 1,500 (1,470) | 2,500 (2,470) | 5,000 (4,970) |
| 5% | 200 (170) | 600 (570) | 1,000 (970) | 2,000 (1,970) |
| 10% | 100 (70) | 300 (270) | 500 (470) | 1,000 (970) |
| 20% | 50 (20) | 150 (120) | 250 (220) | 500 (470) |

Cada celda es `n total (posts adicionales sobre 30)`.

Para el **esquema grueso de 8 cabezas**, el objetivo final depende de la
prevalencia observada. Con 200 posts (170 más) se esperan ~10 positivos a 5%,
~20 a 10%, ~30 a 15% y ~40 a 20%. Eso alcanza para la primera estimación de
`p_hat` y, si los marcos están en ~15–20%, para una primera versión del modelo
grueso; si rondan el 5%, el objetivo sigue siendo **1,000 posts aleatorios**
(970 más) para ~50 positivos por cabeza. La tanda de 200 es un primer corte
para reemplazar supuestos por datos, no el tamaño final garantizado.

Para el **esquema fino de 18 marcos**, si el marco más raro tiene ~1–2%, el
objetivo de 50 positivos exige **2,500–5,000 posts aleatorios** (2,470–4,970
más). Eso no es viable con anotación humana únicamente; la alternativa es
muestreo dirigido por marco raro o quedarse con el esquema grueso.

El número exacto se debe recalcular después de una primera tanda. Procedimiento:

1. Anotar 200 posts aleatorios (170 más).
2. Calcular `p_hat` por marco o cabeza.
3. Reemplazar `p` por `p_hat` en `n = K / p_hat`.
4. Seguir en tandas de 100–200 hasta que cada marco modelado llegue a `K`
   positivos; si un marco no llega a 5 positivos tras 1,000 posts, sacarlo del
   modelo y reportarlo solo descriptivamente.

Para el acuerdo, el test-retest plano del 20% no alcanza: con 1,000 posts son
200 pares y una cabeza del 5% tendría ~10 positivos. Conviene un **retest
estratificado**: incluir todos los positivos de marcos raros más una muestra
aleatoria de negativos, hasta ≥20 pares por marco modelado.

### Decisión: primera tanda de 200 posts (03-11-2026)

Se adopta la **opción A con 200 posts en total**: conservar la muestra ya
auditada de 30 (20 aleatorios + 10 dirigidos) y agregar **170 aleatorios**
sobre la misma ventana `2017-11-11T10:15:36Z → 2019-11-01T10:15:36Z`. La mezcla
final queda en **190 aleatorios + 10 dirigidos = 200 posts y 200 hilos únicos**.

Razones:

- 200 es el primer punto donde `K=10` es alcanzable para un marco con
  prevalencia ≥5% (`n = K / p = 10 / 0.05 = 200`).
- Si los marcos están en 15–20%, la tanda produce 30–40 positivos por marco y
  permite una primera versión del modelo grueso.
- Conserva los 30 posts ya verificados y evita descartar trabajo de auditoría.
- Los 10 dirigidos se excluyen de toda estimación de prevalencia; solo
  entrenan/calibran.

Comando de muestreo (una pasada completa del dump, ~34 minutos):

```bash
export KEKLAB_ROTLK_DATASET=/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst
keklab annotate sample --source rotlk --months 24 \
  --random 170 --targeted 0 --seed 17 \
  --out data/samples/rotlk_pilot_extra.jsonl
```

Fusión y verificación:

1. Unir `rotlk_pilot.jsonl` (30) con `rotlk_pilot_extra.jsonl` (170).
2. Deduplicar por `post_id` y `thread_id`; si hay colisiones, reponer desde el
   reservorio antes de fijar el tamaño.
3. Escribir `data/samples/rotlk_pilot_200.jsonl` y conservar el archivo de 30
   como procedencia.
4. Aceptar solo si se cumple: 200 posts únicos, 200 hilos únicos, 190
   aleatorios + 10 dirigidos, 0 timestamps fuera de la ventana, 0 `text_clean`
   vacíos y cobertura de todos los meses calendario de la ventana (25 buckets,
   porque noviembre de 2017 y noviembre de 2019 son parciales).

Soporte esperado a n=200 (probabilidad binomial de alcanzar `K` positivos):

| Prevalencia | Positivos esperados | P(≥10) | P(≥20) | P(≥30) |
|---:|---:|---:|---:|---:|
| 5% | 10 | 0.545 | 0.003 | 0.000 |
| 10% | 20 | 0.996 | 0.534 | 0.016 |
| 15% | 30 | 1.000 | 0.985 | 0.530 |
| 20% | 40 | 1.000 | 1.000 | 0.972 |

Después de anotar, se calcula `p_hat` por marco y se aplica `n = K / p_hat`
para decidir la siguiente tanda. Los marcos que queden por debajo de 5
positivos tras 1,000 posts se reportan solo de forma descriptiva.

### Resultado de la tanda de 200 (03-11-2026)

El muestreo adicional terminó en 1,703.6 s:

```
3,397,911 hilos / 134,529,233 posts
170 samples -> data/samples/rotlk_pilot_extra.jsonl
by reason: {"random": 170}
```

La fusión no tuvo colisiones: 0 posts y 0 hilos compartidos entre la muestra
base y la adicional. El archivo final es
`data/samples/rotlk_pilot_200.jsonl` (262 KB) y el de 30 se conserva como
procedencia.

Chequeos de aceptación, todos pasados:

| Chequeo | Resultado |
|---|---:|
| Posts totales | 200 |
| Posts únicos | 200 |
| Hilos únicos | 200 |
| Aleatorios | 190 |
| Dirigidos | 10 |
| `text_clean` vacíos | 0 |
| Timestamps fuera de ventana | 0 |
| Meses calendario cubiertos | 25 (6–10 posts cada uno) |
| Duplicados de `content_hash` | 0 |
| Duplicados de `text_raw` | 0 |

Los 10 dirigidos se excluyen de las estimaciones de prevalencia. La siguiente
acción es anotar los 200 y calcular `p_hat` por marco para fijar la próxima
tanda.

## Actualización: herramientas sin anotaciones (04-11-2026)

Con la muestra de 200 cerrada y la anotación todavía pendiente, se implementó
todo lo que no depende del oro: reproducibilidad del muestreo, taxonomía gruesa,
partición pre-registrada, auditoría y selección del retest.

### Reproducibilidad

La fusión que produjo `rotlk_pilot_200.jsonl` ya no es un script inline. Ahora
existe `keklab annotate merge`, que:

- valida cada fila con `SamplePost`;
- conserva la primera aparición y deduplica por `post_id` y `thread_id`;
- reporta filas leídas, duplicados, razones, fuentes, meses y rango temporal;
- permite exigir conteos con `--expect-total`, `--expect-random` y
  `--expect-targeted`.

Regenerar el archivo desde las dos fuentes produce exactamente las mismas 200
filas, en el mismo orden:

```bash
keklab annotate merge \
  --input data/samples/rotlk_pilot.jsonl data/samples/rotlk_pilot_extra.jsonl \
  --out /tmp/rotlk_pilot_200_remerged.jsonl \
  --expect-total 200 --expect-random 190 --expect-targeted 10
```

### Auditoría

`keklab annotate audit` describe cualquier archivo de candidatos sin necesidad
de anotaciones: posts/hilos únicos, duplicados, textos vacíos, OP/reply,
razones, fuentes, países, meses, rango temporal y longitud de texto. También
acepta `--start`/`--end` para contar posts fuera de la ventana.

Auditoría del piloto de 200:

| Métrica | Valor |
|---|---:|
| Posts / hilos únicos | 200 / 200 |
| Aleatorios / dirigidos | 190 / 10 |
| Posts con `text_clean` vacío | 0 |
| Posts fuera de ventana | 0 |
| Meses calendario | 25 |
| OP | 44 |
| Longitud mediana (`text_clean`) | 76.5 caracteres |
| Países con más posts | US 104, CA 15, GB 9 |

### Taxonomía gruesa

`src/keklab/annotation/taxonomy.py` define las 8 cabezas y el mapeo desde los
18 marcos finos. El import valida que el vocabulario fino y el mapeo no se
desincronicen. `annotate export` agrega `coarse_labels` y columnas one-hot
`coarse_*`; `annotate stats` reporta `coarse_counts`.

### Split y retest pre-registrados

- `keklab annotate split` asigna train/dev/test **por hilo** (60/20/20) con
  semilla 13. El manifiesto del piloto quedó en
  `data/splits/rotlk_pilot_200_threads.jsonl`: 120/40/40.
- `keklab annotate retest` selecciona el 20% para la ronda 2 de forma
  determinista. Sobre los 200 selecciona 40 (39 aleatorios + 1 dirigido); el
  dirigido no se usa para prevalencia.

El protocolo completo, con métricas, reglas de soporte y definición de E0/E2,
está en `docs/evaluation_protocol.md`.

### Tests

La suite pasó de 87 a **109 pruebas**. Los tests nuevos cubren taxonomía,
fusión/deduplicación, retest, split por hilo, auditoría y los cuatro comandos
nuevos de la CLI.
