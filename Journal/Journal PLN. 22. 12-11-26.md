# Journal PLN. 22. 12-11-26

Hoy se cierra la migración del panel: se verificó el frontend nuevo contra el
corpus real, se retira Streamlit y se actualizan dependencias y documentación.
El journal se escribe antes de los commits de cierre, como siempre.

## 1. La verificación del frontend nuevo

El front en `web/` (HTML + CSS + ES modules + Plotly local) se levantó con
`keklab api serve` contra el L0 real y se probó en Chromium headless, no solo con
`curl`.

| Chequeo | Resultado |
|---|---|
| `GET /` | Sirve `index.html` (200, HTML). |
| `GET /js/main.js`, `GET /css/styles.css`, `GET /static/plotly.min.js` | Sirven (JS 8.4 KB, CSS 14.8 KB, Plotly 4.8 MB). Plotly sin CDN. |
| Vistas `summary`, `frames`, `toxicity`, `timeline`, `explore`, `quality`, `chat` | Renderizan contra la API real, sin errores de consola. |
| Métricas y tablas | Los valores salen de los endpoints con `data` + `provenance`; los números del panel coinciden con la API (por ejemplo 5.020.305 posts en `2016-11`). |
| Plotly | Renderiza en el DOM con `.js-plotly-plot`; el eje de periodos quedó en categoría después de la corrección (`2016-11` se lee como texto, no como fecha). |
| Interacción | Navegación por pestaña, cambio `level=fine → coarse` (16 → 7 marcos) y reset de filtros funcionan. La URL refleja vista y filtros. |
| Abort | `AbortController` por vista: el render con token de generación evita pisarse. |
| Fixture L1 | Con corpus + predicciones sintéticos (4 meses, 182 posts), las vistas de marcos, toxicidad y línea de tiempo renderizan cuotas reales (frames con shares, toxicidad 0–3, series con modo `frames`). |

Dos desvíos de UI se corrigieron durante la verificación:

- Los ejes de Plotly interpretaban los buckets como fechas (`23:59:59.999Oct 31, 2016`).
  Ahora son categoría.
- El título de la serie de volumen decía "por month"; ahora dice "por mes".

## 2. Tiempos sobre el corpus real

| Consulta | Tiempo |
|---|---|
| `GET /api/overview` completo | 28.5 s |
| `GET /api/overview` podado a `2016-11` | 1.1 s |
| `GET /api/volume` podado | 2.6 s |
| `GET /api/series` completo (fallback a volumen, sin L1) | 23.7 s |
| `GET /api/quality` | 35.4 s |
| `GET /api/search?query=pizza` | 27.0 s |
| `POST /api/chat` (consultar) | 30.0 s |

El podado a un mes corta los tiempos drásticamente: 1.1 s contra 28.5 s sin
podar, porque DuckDB hace pruning por la partición `month=`. Con L1 cargado las
cuotas se sirven sin recálculo adicional en el mismo proceso.

## 3. Retiro de Streamlit

Con el front nuevo con paridad verificada (siete vistas, chat, interacción, URL,
abort), se retira el panel viejo:

- Se borran `dashboard/` y `tests/test_dashboard.py`.
- `requirements.txt` y `pyproject.toml` entran `fastapi` y `uvicorn`; sale
  `streamlit`.
- `README.md` y `docs/dashboard.md` describen el arranque nuevo:
  `keklab api serve --host 127.0.0.1 --port 8000`.

Quedan vivos: `tests/test_api.py`, `tests/test_chat_tools.py` y la suite de
`keklab.analytics`.

## 4. Documentación

- `docs/dashboard.md` pasa a documentar el contrato API, el front, variables de
  entorno y las decisiones vigentes.
- `docs/reporte_progreso.md` y su PDF se regeneraron (fecha y estados actualizados:
  backend FastAPI y panel web en producción; faltan L1 y la ventana reciente).

## 5. Estado de git

- `5ccfa4a`: verificación del panel sobre el corpus real.
- `dcc62dc`: menciones de entidades en una sola pasada.
- `c66b819`: verificación de L0 en journal 20.
- `87fee6f`: timestamps UTC y fallback a volumen en la serie.
- `60cd652`: journal 21, la migración a FastAPI + HTML/JS.

Este journal (`Journal PLN. 22. 12-11-26.md`) se commitea junto al cierre.

## 6. Siguiente paso

1. Commit del código y tests de la migración (`refactor` + `chore: retiro de
   Streamlit`), por separado de docs y data.
2. Commit de docs (`docs: journal 22 ...`, regeneración de reporte).
3. Push.
4. Sigue bloqueada la ventana reciente de 4plebs y el self test-retest del oro
   hasta el clasificador L1.
