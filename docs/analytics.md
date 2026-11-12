# Capa de analítica (`keklab.analytics`)

Fuente única de verdad analítica. El dashboard y el chatbot **no** reimplementan
análisis: ambos llaman a este módulo. Un número verificado en la terminal es el
mismo número que muestra el panel.

## Capas de datos

| Capa | Qué es | Dónde vive | Para qué |
|---|---|---|---|
| L0 | Corpus canónico completo (134,5 M posts) | Parquet mensual en disco externo | Volumen, denominadores, búsqueda |
| L1 | Predicciones del clasificador sobre L0 | Tabla o parquet de predicciones | Agregados de marcos y toxicidad |
| L2 | 5.000 silver + 200 gold | `data/classification/` | Entrenamiento y evaluación |

L0 no lleva etiquetas: son los denominadores honestos. L1 es lo que permite
hablar de prevalencia de marcos.

## Filtros

`Filters` es declarativo y serializable (`Filters.as_dict()`). El servicio lo
traduce a predicciones SQL, así que el frontend nunca escribe consultas.

| Campo | Significado |
|---|---|
| `start`, `end` | Ventana temporal (fechas ISO, inclusiva al final) |
| `sources` | `kek`, `fourplebs` |
| `periods` | `hist_2016_2019`, `recent_2020_plus` |
| `is_op` | Solo posts que abren hilo |
| `min_text_length` | Corte por longitud del texto limpio |
| `query` | Búsqueda literal sin distinguir mayúsculas |
| `frames` + `frame_level` | Marcos finos (16) o cabezas gruesas (7) |
| `toxicity_min`, `toxicity_max` | Rango de toxicidad ordinal 0–3 |
| `thread_ids` | Hilos concretos |

## Denominadores

Todo se puede leer de dos formas y el modo es explícito:

- `all`: el denominador son **todos** los posts de la ventana. Es el valor por
  defecto porque responde "¿qué fraction del tráfico del board lleva este
  marco?".
- `labeled`: el denominador son solo los posts **con predicción**. Responde
  "entre lo que el modelo miró, ¿qué fracción tiene este marco?".

Cuando hay L1, cada respuesta declara la `coverage`: qué fracción de los posts
de la ventana tiene predicción. Sin L1, el servicio lo dice con un aviso en
lugar de devolver ceros silenciosos.

## Proveniencia

Ninguna respuesta va sin contexto. Cada método devuelve
`{"data": ..., "provenance": {...}}` con:

| Campo | Contenido |
|---|---|
| `run_id` | Identificador de la corrida |
| `generated_utc` | Momento de la consulta |
| `filters` | Eco de los filtros aplicados |
| `n` | Número de observaciones usadas |
| `denominator` | Denominador de la cuota |
| `warnings` | Avisos: celdas chicas, cobertura parcial, filtro vacío |

## Incertidumbre

- **Wilson**: intervalo de 95 % para una proporción binomial. Es el intervalo
  por defecto de cada cuota.
- **Bootstrap por hilo**: el post es la unidad de análisis pero el hilo es la
  unidad de correlación, así que el bootstrap resamplea hilos completos. Se
  usa `cluster_bootstrap_share` sobre los conteos por hilo.
- **Celdas chicas**: con `n < 30` la cuota se marca como inestable y aparece un
  aviso. El umbral es `analytics.stats.MIN_CELL`.

## Funciones

| Método | Pregunta que responde |
|---|---|
| `overview(filters)` | Volumen y forma de la ventana |
| `volume_series(filters, granularity)` | Posts e hilos por periodo |
| `frame_distribution(filters, level, denominator)` | Cuota de cada marco |
| `toxicity_distribution(filters, denominator)` | Distribución ordinal y cuota tóxica |
| `frame_series(filters, granularity, level)` | Cuotas a lo largo del tiempo |
| `compare(baseline, target, level)` | Diferencia entre dos ventanas |
| `search_posts(filters, limit, offset)` | Búsqueda de texto libre (módulo removible) |
| `term_counts(filters, dictionary)` | Menciones léxicas de un diccionario |
| `events_between(start, end)` | Hitos externos del rango |

## Hitos externos

`configs/events.yaml` es ground truth curado a mano: eventos del mundo, no
etiquetas del modelo. Se dibujan sobre la línea de tiempo y no entran en
ninguna lógica de clasificación. La extracción automática desde el corpus es
una mejora futura, no un requisito.

## CLI

```bash
keklab analytics overview --l0 '<glob l0>'
keklab analytics frames --l0 '<glob l0>' --predictions <tabla|parquet> --level fine
keklab analytics toxicity --l0 '<glob l0>' --predictions <parquet>
keklab analytics series --l0 '<glob l0>' --granularity month
keklab analytics search --l0 '<glob l0>' --query 'QAnon'
keklab analytics events
```

## Chat

El chat del dashboard expone cinco herramientas sobre este mismo servicio:

| Herramienta | Qué hace |
|---|---|
| `consultar` | Conteos y distribuciones de la ventana activa |
| `graficar` | Serie temporal con o sin predicciones |
| `clasificar` | Etiqueta un texto con el modelo local (si está disponible) |
| `resumir` | Resumen descriptivo: volumen, meses, entidades, toxicidad |
| `extraer_entidades` | Menciones de un diccionario curado |

El enrutado es por reglas: los comandos explícitos (`/graficar`) ganan sobre
las palabras clave. Cuando el modelo local no está en la máquina, `clasificar`
lo dice explícitamente en vez de inventar una etiqueta.
