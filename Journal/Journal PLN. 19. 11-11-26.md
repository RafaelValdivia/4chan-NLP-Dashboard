# Journal PLN — Entrada 19 (11-11-2026)

## Contexto

La entrada 18 dejó lista la infraestructura de clasificación plata y el
pre-registro del maestro. Esta entrada cierra dos frentes que quedaron
abiertos: la muestra real de 5.000 posts y la arquitectura del dashboard.
La muestra se generó, se auditó y **falló un criterio del protocolo**; la
arquitectura se diseñó completa a partir de los ground truths del proyecto.

No se entrenó ningún clasificador ni se construyó todavía el dashboard.

## Muestra de 5.000: ejecución y auditoría

### Ejecución

```text
keklab annotate sample --source rotlk \
  --dataset /run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst \
  --start 2016-06-01T00:00:00Z --end 2019-11-01T23:59:59Z \
  --random 5000 --targeted 0 --seed 17 \
  --out data/classification/samples/rotlk_5000.jsonl
```

Resultado: **5.000 samples, 100 % `reason=random`**, en **2.049 s (34,1 min)**
sobre 3.397.911 hilos y 134.529.233 posts. El tiempo confirma que el costo está
en la pasada completa del dump y no en la cantidad de posts elegidos.

Archivo: `data/classification/samples/rotlk_5000.jsonl`, 6.216.637 bytes,
`sha256 3186e1e7eec5c37620d973aea0552a8683c00fbee843cdf1cc8d90607387f195`.

### Auditoría

Pasan:

- 5.000 filas, 5.000 `post_id` únicos, 5.000 `thread_id` únicos.
- 0 `text_clean` vacíos.
- 0 posts fuera de la ventana exacta.
- 42 meses calendario (2016-06 a 2019-11), cuotas mensuales 119–120.
- `stratum.month` coincide con el mes del timestamp en todos los casos.
- `source=kek`, `period=hist_2016_2019`.
- 0 warnings durante la pasada.

Falla:

- **64 filas con `content_hash` duplicado** (y 64 con `text_clean` duplicado):
  27 grupos, 91 filas implicadas. Son copypasta en hilos distintos. El
  protocolo exige 0 duplicados porque el split es por `thread_id`: el mismo
  texto puede caer en train y en test y filtrar información.

Los grupos son posts degenerados, no copypasta largos:

| Texto | Hilos | Meses |
|---|---:|---|
| `bump` | 15 | 2016-07 a 2019-08 |
| `kek` | 6 | 2016-07 a 2018-12 |
| `?` | 4 | 2016-06 a 2018-09 |
| `RARE` | 2 | 2016-06 |
| `Thoughts?` | 3 | 2016-08 a 2019-05 |

El sampler solo deduplicaba por `post_id` y `thread_id`, no por contenido
(hallazgo A2 de la auditoría de código). Además, si un mes quedaba corto tras
descartar duplicados, no había redistribución (A3).

### Decisión: congelar la muestra, deduplicar al exportar

La muestra ya estaba siendo etiquetada por `Qwen3-8B-Q4_K_M` en otra máquina.
Regenerarla habría invalidado ese trabajo (30–45 h de GPU), así que **no se
remuestrea**:

- `data/classification/samples/rotlk_5000.jsonl` queda **congelado**.
- El etiquetado sigue por `post_id`, sin interrupciones.
- La deduplicación por `content_hash` se aplica en el **export del dataset**
  (`build_modeling_rows`): colapsa cada grupo a un representante determinista
  (el `post_id` numérico menor) y reporta `duplicate_groups` y
  `duplicate_rows_removed`. El split sigue siendo por `thread_id`, pero sobre
  filas ya sin texto repetido.
- El dataset esperado ronda las **4.936 filas** (64 etiquetas de posts vacíos
  se descartan), y el reporte declara la diferencia.
- Se corrigió igual `sample_rotlk_stream` para muestreos futuros:
  deduplicación global por `content_hash` y redistribución del faltante mensual
  entre meses con candidatos sobrantes. No se vuelve a correr sobre el dump
  histórico.
- `docs/silver_classification_protocol.md` registra la enmienda: la garantía de
  “0 duplicados” pasa del muestreo al export del dataset.

## Arquitectura del dashboard

### Decisiones tomadas

| Decisión | Valor |
|---|---|
| Alcance inicial | Solo histórico ROTLK 2016–2019; `period` queda en el esquema para sumar 4plebs después. |
| UI | Streamlit, uso local, sin autenticación. |
| Gráficos | Plotly. |
| Chat | Página dedicada que hereda los filtros activos. |
| Marcos | Los 16 finos como checkboxes; las 7 cabezas se derivan al vuelo. |
| Buscador | Búsqueda libre permitida, implementada como módulo removible. |
| Eventos | `events.yaml` curado a mano como ground truth; extracción automática futura como mejora opcional. |
| Backend | Sin FastAPI en el MVP: Streamlit importa la capa de servicios en proceso. |

### Tres niveles de datos

| Nivel | Contenido | Ubicación | Rol |
|---|---|---|---|
| L0 | 134,5 M posts canónicos en Parquet por mes | disco externo | volumen, actividad, buscador, denominadores |
| L1 | predicciones del modelo barato sobre L0 | disco externo | marcos y toxicidad del dashboard |
| L2 | 5.000 plata + 200 oro | repo | entrenar y evaluar; nunca denominador |

L0 no guarda `raw_html`; se recupera del dump si hace falta. Estimado: 12–18 GB.
El disco que contiene el `.tar.zst` tiene espacio suficiente.

La razón de L0 es doble: el buscador libre necesita algo que indexar, y los
agregados del dashboard necesitan denominadores reales. Sobre la muestra de
5.000 cada mes tendría ~120 posts y los intervalos de confianza taparían
cualquier tendencia. El LLM no procesa el corpus completo: entrena sobre la
plata y el modelo barato se aplica a L0.

### Capas

```text
L0/L1 Parquet -> keklab.analytics -> app/ (Streamlit)
                          \-------> keklab/chat/ (tools)
```

`analytics` es la única fuente de verdad: filtros, agregados, estadística,
series y búsqueda. La UI no reimplementa cálculos y el chatbot invoca las
mismas funciones. Si más adelante se agrega una API o un frontend distinto,
es un wrapper sobre esta capa.

### Páginas

1. Resumen: KPIs, estado del run, cobertura y advertencias.
2. Marcos: 16 finos, 7 cabezas, co-ocurrencia y evolución.
3. Toxicidad: niveles 0–3, evolución y cruce con marcos.
4. Línea de tiempo: serie mensual con marcadores de `events.yaml`.
5. Explorar: búsqueda libre y detalle con contexto.
6. Calidad: oro 200, test-retest, imitación de plata y deriva.
7. Chat: página dedicada, consciente de los filtros.
8. Comparación: oculta tras `ENABLE_COMPARISON=false` hasta tener 4plebs.

### Reglas de la capa analítica

| Decisión | Valor |
|---|---|
| Denominador por defecto | % de todos los posts del período, incluidos `none`/`unclear`. |
| Alternancia | Toggle explícito “sobre posts etiquetados”. |
| Incertidumbre | Wilson y bootstrap por `thread_id`. |
| Celdas chicas | `n < 30` atenuadas con `n` visible. |
| Ventanas | Comparaciones de igual longitud cuando exista el período reciente. |
| Provenance | Toda respuesta lleva filtros, `n`, denominador, `run_id` y advertencias. |

### Buscador removible

El buscador libre vive solo en `app/pages/5_Explorar.py` y
`keklab/analytics/posts.py`, detrás de `ENABLE_POST_EXPLORER`. Nada más depende
de esas piezas: borrarlo es eliminar esos archivos y el flag, sin tocar
agregados, chat ni tests. Se incluye un banner de advertencia de contenido.

### Chat

Herramientas sobre `analytics`: `consultar`, `graficar`, `clasificar`,
`resumir`, `extraer_entidades`. Sin SQL libre. Cada respuesta cita `n`,
intervalo y `run_id`. Si el LLM local no está disponible, degrada a un
constructor determinista de consultas.

### Eventos

`events.yaml` versionado con `date`, `name`, `description`, `source_url` y
`show_by_default`. Se carga como tabla `events` y se dibuja como líneas
verticales. No son etiquetas del modelo. La extracción automática desde alguna
fuente externa queda como mejora posterior; si se implementa, se evalúa si
reemplaza o complementa al YAML.

## Lo que no se hizo

- No se remuestreó la muestra: se congeló a propósito para no invalidar el
  etiquetado en curso.
- No se construyó L0 ni `keklab.analytics`.
- No se escribió ninguna página de Streamlit.
- No se entrenó el baseline ni se aplicó ningún modelo a L0.
- No se descargó la ventana reciente de 4plebs.
- No se instaló `llama-cpp-python` ni se corrió el maestro.

## Siguiente paso

1. Cuando termine el etiquetado, exportar el dataset y verificar que reporta
   `duplicate_groups=27` y `duplicate_rows_removed=64`.
2. Construir L0 en el disco externo.
3. Implementar `keklab.analytics` con DB de fixture y tests.
4. Páginas 1–4 de Streamlit.
5. Buscador, calidad y chat.

## Estado de git

La corrección de código y sus tests quedaron en `44ed38f`. Esta entrada y la
enmienda al protocolo quedaron en `df57494`. La muestra de 5.000 no se modificó:
sigue siendo el archivo de `7ee0099`.
