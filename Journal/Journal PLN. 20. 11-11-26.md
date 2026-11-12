# Journal PLN. 20. 11-11-26

Hoy se cerró el almacén canónico (L0), se escribió la capa de analítica
compartida y se levantó el panel. También se encontraron dos bugs de
construcción que habrían contaminado cualquier número del dashboard.

## 1. L0: el almacén canónico

El dump ROTLK vive en un disco externo. La construcción tiene tres etapas:

| Etapa | Qué | Costo |
|---|---|---|
| Extracción | `.tar.zst` → NDJSON de 107 GB | 377 s |
| Construcción | NDJSON → Parquet mensual | 213 trozos de 512 MB, 4 workers |
| Verificación | Conteos por DuckDB | minutos |

El esquema es una fila por post, en `month=YYYY-MM/part-<trozo>-<flush>.parquet`:

- `text_clean` ya limpiado, sin `raw_html` (recuperable del dump).
- `content_hash64`: blake2b de 8 bytes, suficiente para deduplicar.
- `subject`, `country`, `quotes` (BIGINT[]), `is_op`.
- Features de hilo: `thread_depth`, `thread_cite_count`, `thread_greentext_count`.
- `source=kek`, `period=hist_2016_2019`.

El constructor trocea el archivo por rangos de bytes, así cada trozo se puede
procesar solo y el run se reanuda desde `_l0_manifest.json`. El manifiesto es
la fuente de verdad: guarda conteos por trozo y los trozos completados.

### Bug 1: las citas no entran en INT32

En ROTLK hay posts que citan `>>191919191919191`. DuckDB infiere `INT32` para
una lista de Python y la conversión fallaba en **todos** los trozos con
`Python Conversion Failure: Value out of range for type INT`.

Las citas viajan ahora como texto y se castean a `BIGINT[]` en SQL. El test
incluye un post con cita de 15 dígitos para que no vuelva a pasar.

### Bug 2: los parts se sobrescribían entre sí

El nombre del archivo era `part-<trozo>.parquet`, sin distinguir flushes. Un
trozo que vaciaba el mismo mes dos veces (el buffer se vacía cada 400.000
filas) **reemplazaba su primer part**. El primer build completo terminó sin
errores y con el conteo del manifiesto correcto (134.529.233 posts), pero en
disco quedaban 54.929.233: **59 % de los posts perdidos**. La pista fue que
el manifiesto contaba 465 flushes y solo existían 266 archivos.

El arreglo: el nombre lleva el índice de flush
(`part-<trozo>-<flush>.parquet`), el manifiesto registra el tamaño de flush y
`SCHEMA_VERSION` sube a 2 para invalidar manifiestos viejos. Hay un test de
regresión que fuerza varios flushes del mismo mes y comprueba que no se
pierde ninguna fila.

La lección: **el manifiesto no alcanza, hay que contrastarlo con el disco**.
`ingest l0-stats` es la verificación que faltaba.

### Verificación final

`keklab ingest l0-stats` contrasta el manifiesto con lo que hay en disco:

```text
posts: 134529233        threads: 3397911         op_posts: 3397911
unique_hashes: 113561056   months: 42
first_post: 2016-06-30T03:14:20+00:00
last_post:  2019-11-01T10:15:36+00:00
parts_written: 465      parts_on_disk: 465
posts_match_manifest: True   threads_match_manifest: True
parts_match_manifest: True   ok: True
```

Lo que dice el almacén:

| Métrica | Valor |
|---|---:|
| Posts | 134.529.233 |
| Hilos | 3.397.911 |
| Posts de OP | 3.397.911 (uno por hilo, exacto) |
| Hashes de contenido únicos | 113.561.056 (84,4 %) |
| Meses | 42 (2016-06 → 2019-11) |
| Partes | 465 |
| Tamaño en disco | 8,4 GB |
| Tiempo de construcción | 3.321 s (55 min, 4 workers) |
| JSON inválido / posts saltados | 0 / 0 |

El 15,6 % de posts repetidos es el phenomenon que ya se conocía: respuestas
de una palabra ("bump", "kek") repetidas en hilos distintos. El corpus tiene
**7.997.480 posts con texto limpio vacío (5,9 %)**: el panel lo avisa y
ofrece excluirlos del denominador.

La primera semana de julio de 2016 trae 3,7 M de posts y noviembre de 2016
trae 5,0 M, el mes más denso del corpus, el de Pizzagate.

### Cambios de entorno

- **DuckDB 2.0.0**: `relation.fetchone()` ya no existe (usar `fetchall()`), y
  la sintaxis `x -> expr` de las lambdas está deprecada (`lambda x: expr`).
- **`pytz` como dependencia**: pandas 3 ya no lo arrastra, y DuckDB lo
  necesita para materializar `TIMESTAMPTZ` como datetime de Python. Sin él,
  toda lectura de timestamps falla.
- `pyarrow` quedó instalado de paso, aunque el parquet se sigue escribiendo
  con DuckDB.

## 2. `keklab.analytics`: la fuente única

El dashboard y el chatbot no pueden tener cada uno su propia lógica. El
módulo nuevo concentra filtros, cuotas, series y procedencia.

- `Filters` es declarativo y serializable; el servicio lo traduce a SQL.
- **Denominadores explícitos**: `all` (todos los posts de la ventana) o
  `labeled` (solo los predichos). Con L1 cargado, cada respuesta declara la
  `coverage`.
- **Provenance en cada respuesta**: `n`, `denominator`, `coverage`, `run_id`,
  filtros aplicados y avisos.
- **Incertidumbre**: intervalo de Wilson por cuota y bootstrap por hilo (el
  post es la unidad de análisis, el hilo la de correlación). Las celdas con
  `n < 30` se marcan como inestables.
- **Hitos externos** en `configs/events.yaml`: ground truth curado a mano
  (Pizzagate, hackeo del restaurante, inauguración, Cambridge Analytica,
  Christchurch, informe Mueller). Son eventos del mundo, no etiquetas.
- **CLI**: `keklab analytics overview|frames|toxicity|series|search|events`.

Es el mismo patrón que ya usan `fourplebs_client` y `classification`, y deja
`docs/pipeline_draft.md` alineado con lo que realmente existe.

## 3. El panel

Siete secciones en Streamlit con Plotly: Resumen, Marcos, Toxicidad, Línea
de tiempo, Explorar, Calidad y Chat.

- Los filtros viven en el `session_state`: todas las secciones, incluido el
  chat, ven la misma ventana.
- Marcos ofrece los 16 marcos finos como casillas y las 7 cabezas como nivel
  derivado, y compara contra los 12 meses previos a la ventana activa.
- Explorar es el módulo removible de búsqueda de texto libre.
- El chat expone cinco herramientas (`consultar`, `graficar`, `clasificar`,
  `resumir`, `extraer_entidades`) sobre el mismo servicio. El enrutado es por
  reglas y los comandos explícitos (`/graficar`) ganan sobre las palabras
  clave. `clasificar` usa el modelo local cuando está y, cuando no, lo dice.

Mientras no exista L1, las secciones de marcos y toxicidad avisan que no hay
predicciones y muestran volumen. No inventan cuotas.

## Decisiones

| Decisión | Motivo |
|---|---|
| Denominador por defecto `all` | Responde la pregunta del analista: qué fracción del tráfico del board lleva este marco. El modo `labeled` queda disponible. |
| Bootstrap por hilo y no por post | Los posts de un hilo no son independientes; el hilo es la unidad de correlación. |
| Aviso con `n < 30` en vez de ocultar | Una cuota de 4 Posts no es un número, pero sí es una señal. |
| Hitos curados a mano | La extracción automática es una mejora futura, no un requisito. |
| Un solo `app.py` con navegación propia | Los filtros compartidos entre secciones son más simples de mantener que el multipage nativo. |

## Lo que no se hizo

- No se aplicó ningún modelo al corpus: **L1 sigue vacío**, así que las
  cuotas de marcos y toxicidad no se pueden mostrar todavía.
- No se descargó la ventana reciente de 4plebs, así que no hay comparación
  temporal.
- No hay FastAPI: el backend es el servicio importado por el panel.
- El chat no razona con un LLM todavía: enruta por reglas. El modelo local
  solo se usa para `clasificar`.
- `extraer_entidades` es extracción léxica por diccionario curado, no NER.
- No se corrió el self test-retest de 40 posts del oro.

## Verificación del panel sobre el corpus real

El servicio responde sobre los 134,5 M posts:

```text
keklab analytics overview --l0 '<glob>'   → 30 s
keklab analytics search --query 'QAnon'   → 25 s (escaneo completo)
keklab analytics series --granularity month → volumen por mes
```

Sin L1, `series` devuelve el volumen en lugar de cuotas y lo dice en un aviso:
el panel no inventa números.

## Estado de git

- `583506e` · `204f17c` · `66dc453`: L0 (constructor, citas BIGINT, parts
  únicos).
- `72ac717`: el verificador contrasta manifiesto y disco.
- `b0b6cc6` · `730f67d` · `fd969e8`: capa de analítica y CLI.
- `17e69f0` · `663d12b`: panel y herramientas del chat.
- `702675e`: almacén de L1.
- `7c6c7ca`: dedupe de contenido en el sampler de 4plebs.
- `44ed38f` · `df57494` · `fbc0ffd`: deduplicación de contenido, journal 19.

## Siguiente paso

1. Cuando termine la plata, exportar el dataset y aplicar el modelo sobre L0
   para producir L1; el panel ya lo lee.
2. Descargar la ventana reciente de 4plebs y compararla con la histórica.
3. Cerrar el self test-retest de 40 posts del oro.
