# Journal PLN. 21. 11-11-26

Hoy se decide reemplazar Streamlit por FastAPI + HTML/JS, y se escribe este
journal **antes** de tocar el código. La razón es simple: el panel funciona,
pero el modelo de ejecución de Streamlit ya mostró un fallo que no se arregla
con un parche y que además deja al chatbot sin backend propio.

## 1. El síntoma

La búsqueda de texto libre sobre el corpus completo tarda unos 25 s. Mientras
esa consulta corre, cualquier otra interacción de la página —cambiar un filtro,
abrir otra sección, mandar un mensaje al chat— dispara un *rerun*. Ese rerun
reutiliza la misma conexión DuckDB guardada en `st.session_state` y falla:

```text
_duckdb.ResourceInUseException: Connection Error: connection is busy with another call
```

El camino exacto es:

```text
dashboard/views/explorar.py:32  →  service.search_posts
src/keklab/analytics/service.py:257  →  AnalyticsService._run
src/keklab/analytics/service.py:99  →  con.execute(...).fetchall()
```

No es un bug de la consulta: es el modelo de Streamlit. Cada interacción
vuelve a ejecutar el script entero, en un hilo distinto, y el `session_state`
comparte un objeto que **no es seguro entre hilos**. Una conexión de DuckDB
admite cursores concurrentes, pero no dos llamadas simultáneas sobre la misma
conexión.

### Lo que esto enseña

- El problema no se resuelve "haciendo la consulta más rápida". Aunque baje a
  2 s, dos reruns pueden solaparse.
- El estado de la aplicación no puede ser un objeto de Python vivo. Tiene que
  ser **serializable y reconstruible** en cada request.
- Un panel que se re-ejecuta entero no es un backend: el chatbot necesita
  endpoints, no una sesión de navegador.

## 2. La decisión

**FastAPI + HTML plano + módulos ES + Plotly.** Sin build step, sin Node, sin
framework de frontend.

| Pieza | Elección | Motivo |
|---|---|---|
| Backend | FastAPI + Uvicorn | Contrato HTTP explícito, validación, docs automáticas, `TestClient` para tests |
| Frontend | HTML + CSS + ES modules | No hay web developer en el proyecto; un build step es deuda que nadie va a mantener |
| Gráficos | Plotly servido desde el paquete instalado | Funciona sin internet; ya es dependencia |
| Estado | Query string de la URL | Enlaces compartibles y reproducibles; el navegador es el dueño del estado |
| Concurrencia | Una conexión por request + cursor propio | Aísla las consultas; no hay estado compartido entre hilos |
| Auth | Ninguna | Herramienta de LAN, un solo analista |

### Por qué no otro framework

- **Streamlit** ya falló por su modelo de rerun. No se arregla desde afuera.
- **Dash** trae el mismo acoplamiento entre layout y callback, y un grafo de
  callbacks que se vuelve difícil de razonar.
- **Next/React** exige toolchain, bundler y alguien que lo mantenga. El
  proyecto no lo tiene.
- **HTML plano** obliga a escribir un poco más de JS, pero cada archivo se lee
  de arriba a abajo y no hay magia que depurar.

## 3. Lo que se conserva

La migración es de **framework**, no de semántica. Nada de lo siguiente se
reinterpreta:

- `keklab.analytics`: `Filters`, predicados SQL, denominadores `all`/`labeled`,
  Wilson, bootstrap por hilo, avisos de celda chica.
- `Filters` sigue siendo la descripción serializable de la ventana.
- La procedencia (`n`, `denominator`, `coverage`, `run_id`, filtros, avisos)
  viaja en **cada** respuesta.
- Los hitos de `configs/events.yaml` siguen siendo ground truth curado a mano,
  no etiquetas del modelo.
- Las 16 etiquetas finas y las 7 cabezas no cambian.
- Las cinco herramientas del chat (`consultar`, `graficar`, `clasificar`,
  `resumir`, `extraer_entidades`) y su enrutado por reglas se mudan tal cual,
  con la misma forma de resultado.

Las tres decisiones que se reemplazan son solo de framework: Streamlit como
host, siete secciones como navegación interna y el chat dentro de la sesión.
La analítica subyacente queda intacta.

## 4. Lo que cambia

### Backend

Nuevo paquete `src/keklab/api/`:

```text
settings.py    KEKLAB_L0_GLOB, KEKLAB_PREDICTIONS, KEKLAB_EVENTS, KEKLAB_WEB_DIR
app.py         create_app(), endpoints y montaje de estáticos
cli.py         keklab api serve --host --port
```

Contrato inicial:

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/meta` | corpus disponible, predicciones, niveles, hitos, rangos |
| GET | `/api/overview` | volumen y forma de la ventana |
| GET | `/api/volume` | serie de volumen |
| GET | `/api/frames` | distribución de marcos |
| GET | `/api/toxicity` | distribución ordinal |
| GET | `/api/series` | cuotas por periodo, o volumen si no hay L1 |
| GET | `/api/search` | búsqueda literal |
| GET | `/api/compare` | ventana activa contra la anterior |
| GET | `/api/events` | hitos del rango |
| GET | `/api/quality` | manifiesto L0 y cobertura |
| GET | `/api/health` | vivo |
| POST | `/api/chat` | herramienta + texto + tabla + figura + procedencia |

Cada `GET` devuelve `{"data": ..., "provenance": ...}` **tal cual lo produce
el servicio**. La API no recalcula ni redondea: si el número está mal, está mal
en un solo lugar.

Los errores de filtro (fecha inválida, nivel desconocido) vuelven como `400`
con un mensaje en español; la falta de corpus, como `503`. El front nunca
recibe un stack trace.

Por decisión de diseño, `/api/series` elige en el servidor: si hay L1 devuelve
cuotas de marcos; si no, volumen con un aviso explícito y un campo `mode`.
Así el front no tiene que saber si el clasificador corrió.

### Concurrencia y poda de particiones

Dos arreglos que van en la capa compartida, no en la API:

1. **Cursor por consulta.** `_run` y `has_predictions` toman
   `con.cursor()`, consultan y cierran. `SET GLOBAL TimeZone='UTC'` se aplica
   una vez para que los cursores hereden UTC. Un test de concurrencia lanza dos
   consultas solapadas y exige que ambas terminen.
2. **Poda por mes.** Si la fuente es un glob de Parquet, se usa
   `read_parquet(..., hive_partitioning=true)` y se agrega un predicado sobre
   la columna de partición `month`. Una consulta de un mes pasa de 9,3 s a
   0,0 s. El predicado solo se agrega cuando la fuente es glob: las tablas de
   los fixtures no tienen `month`.

Además, `previous_window` y `compare_with_previous` bajan de `dashboard/state.py`
al servicio, para que la comparación histórica sea una operación del backend y
no lógica de la interfaz.

### Frontend

`web/` sin build:

```text
index.html
css/styles.css
js/api.js        fetch + AbortController
js/state.js      filtros ↔ query string
js/ui.js         helpers de DOM, tablas, procedencia, CSV
js/charts.js     figuras Plotly
js/main.js       router de vistas
js/views/        summary, frames, toxicity, timeline, explore, quality, chat
```

Reglas de la interfaz:

- **La URL es el estado.** Fechas, nivel, denominador, granularidad, marcos y
  búsqueda se leen y escriben en el query string. Un enlace reproduce la vista.
- **`AbortController` cancela la request anterior.** Si el analista cambia de
  filtro mientras carga, la respuesta vieja no pisa la nueva.
- **Los avisos de procedencia no se esconden.** Van debajo de cada vista, con
  `n`, denominador, `run_id` y advertencias.
- **Sin L1 no se inventan cuotas.** Marcos, toxicidad y línea de tiempo avisan
  y muestran volumen, igual que hoy.
- **Plotly se sirve local** desde `plotly/package_data/plotly.min.js` (4,8 MB).
  No hay CDN: el panel tiene que funcionar sin internet.

## 5. Plan de migración

El orden importa: primero el contrato, después la interfaz.

1. **Journal y commit de docs.** Este archivo, solo.
2. **Capa compartida.** Cursor por consulta, poda por partición,
   `compare_with_previous`, y sus tests. Sin tocar la API todavía.
3. **Mudanza del chat.** `dashboard/chat/tools.py` →
   `src/keklab/chat/tools.py`; el panel viejo importa desde la ubicación nueva
   hasta que se retire.
4. **API.** `settings.py`, `app.py`, `cli.py`, `keklab api serve`.
5. **Tests de API.** `TestClient` sobre un L0 de fixture: cada endpoint, el
   chat, el 400 de un filtro inválido, el 503 sin corpus y la concurrencia.
6. **Frontend.** Las siete vistas contra la API, con paridad de números y de
   procedencia.
7. **Retiro de Streamlit.** Cuando el front alcance paridad se borra
   `dashboard/` y `tests/test_dashboard.py`; quedan `tests/test_chat_tools.py`
   y `tests/test_api.py`.
8. **Dependencias y docs.** `requirements.txt` y `pyproject.toml` cambian:
   entran `fastapi` y `uvicorn`, sale `streamlit`; `docs/dashboard.md` y el
   README describen el nuevo arranque.
9. **Verificación sobre el corpus real.** Los mismos números de journal 20 y
   los tiempos de la poda por mes.
10. **Commit de código y tests por separado del journal y de los datos.**

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El front repite lógica del backend | Cada vista solo pinta `data` y `provenance`; no hay SQL ni cálculos en JS |
| La API cambia y rompe el chat | El contrato es el mismo `ToolResult` que ya usa el panel; los tests fijan la forma |
| Dos requests pisan el DOM | `AbortController` con un contador de generación por vista |
| El servidor se cae con el corpus ausente | `/api/meta` y `/api/health` responden; las vistas muestran el 503 como aviso |
| Se pierde la reproducibilidad de un enlace | Todos los filtros viven en la URL; se prueba ida y vuelta |
| El panel deja de funcionar sin internet | Plotly local, sin fuentes ni CDN externos |

## 7. Lo que no se hace en esta migración

- No se agrega autenticación ni multiusuario: es una herramienta de LAN.
- No se agrega un LLM al chat: el enrutado sigue siendo por reglas.
- No se toca el clasificador, ni el oro, ni el esquema de etiquetas.
- No se descarga la ventana reciente de 4plebs.
- No se inventan cuotas cuando falta L1.
- No se borra Streamlit hasta que el front tenga paridad verificada.

## 8. Estado de git

- `5ccfa4a`: verificación del panel sobre el corpus real.
- `dcc62dc`: menciones de entidades en una sola pasada.
- `c66b819`: verificación de L0 en journal 20.
- `87fee6f`: timestamps UTC y fallback a volumen en la serie.

Este journal se commitea solo, antes de cualquier cambio de código.

## 9. Siguiente paso

1. Implementar la capa compartida (cursor, poda, comparación) con tests.
2. Mudar las herramientas del chat y levantar la API con `TestClient`.
3. Construir el front por vistas y verificar paridad de números.
4. Retirar Streamlit, actualizar dependencias y docs, y correr la suite
   completa sobre el corpus real.
