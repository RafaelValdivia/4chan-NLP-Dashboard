# Dashboard

Panel de analítica de `/pol/`. Es una aplicación **FastAPI + HTML/JS** con Plotly
(servido por el propio backend). No hay build step, no framework de frontend.

```bash
pip install -r requirements.txt
keklab api serve --host 127.0.0.1 --port 8000
```

La app expone la API en `/api/...` y sirve el front desde `web/` en la raíz.

## Endpoints

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/health` | vivo |
| GET | `/api/meta` | corpus, predicciones, frames, niveles, hitos, herramientas |
| GET | `/api/overview` | volumen y forma de la ventana |
| GET | `/api/volume` | serie de volumen |
| GET | `/api/frames` | distribución de marcos |
| GET | `/api/toxicity` | distribución ordinal |
| GET | `/api/series` | cuotas por periodo, o volumen si no hay L1 (`mode`) |
| GET | `/api/search` | búsqueda literal |
| GET | `/api/compare` | ventana activa contra la anterior |
| GET | `/api/events` | hitos del rango |
| GET | `/api/quality` | manifiesto L0 y cobertura |
| POST | `/api/chat` | herramienta + texto + tabla + figura + procedencia |

Cada `GET` devuelve `{"data": ..., "provenance": ...}` **tal cual lo produce el
servicio**. La API no recalcula ni redondea: si el número está mal, está mal en
un solo lugar.

## Frontend (`web/`)

```
web/
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
- **Los avisos de procedencia no se esconden.** Van debajo de cada vista, con `n`,
  denominador, `run_id` y advertencias.
- **Sin L1 no se inventan cuotas.** Marcos, toxicidad y línea de tiempo avisan y
  muestran volumen, igual que antes.

Variables de entorno:

| Variable | Por defecto | Para qué |
|---|---|---|
| `KEKLAB_L0_GLOB` | `/run/media/flynnso/Archivos/l0/month=*/*.parquet` | Corpus canónico |
| `KEKLAB_PREDICTIONS` | vacío | Tabla o parquet con L1 |
| `KEKLAB_EVENTS` | `configs/events.yaml` | Hitos externos |
| `KEKLAB_WEB_DIR` | `web/` | Directorio servido como front |

## Secciones

| Sección | Qué muestra |
|---|---|
| Resumen | Volumen de la ventana, hilos, longitud mediana, serie de volumen |
| Marcos | Cuota de los 16 marcos finos o de las 7 cabezas, con IC y comparación contra la ventana previa |
| Toxicidad | Distribución ordinal 0–3 y cuota tóxica |
| Línea de tiempo | Cuotas por periodo con los hitos externos marcados |
| Explorar | Búsqueda de texto libre (módulo removible) |
| Calidad | Cobertura del corpus, manifiesto de L0, avisos del servicio |
| Chat | Herramientas sobre el servicio compartido |

## Decisiones

- **El panel no reimplementa análisis.** Cada número sale de
  `keklab.analytics`, el mismo módulo que usa el chat. Si el panel y el chat se
  contradicen, es un bug del servicio, no dos implementaciones.
- **Los filtros viven en la URL.** Es el state compartido por diseño: enlaces
  reproducibles, navegador como dueño del estado.
- **16 marcos finos y 7 cabezas.** El selector ofrece los 16 como casillas y las
  7 como nivel derivado.
- **Explorar es removible.** Es el único módulo que lee cuerpos de posts y está
  aislado en `js/views/explore.js`.

## Sin predicciones todavía

Mientras no exista L1, las secciones de Marcos, Toxicidad y Línea de tiempo lo
dicen con un aviso y muestran volumen. No inventan cuotas.
