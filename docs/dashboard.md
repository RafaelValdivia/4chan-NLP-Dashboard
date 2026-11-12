# Dashboard

Panel de analítica de `/pol/`. Es una aplicación Streamlit con Plotly.

```bash
pip install -r requirements.txt
streamlit run dashboard/app.py
```

Variables de entorno:

| Variable | Por defecto | Para qué |
|---|---|---|
| `KEKLAB_L0_GLOB` | `/run/media/flynnso/Archivos/l0/month=*/*.parquet` | Corpus canónico |
| `KEKLAB_PREDICTIONS` | vacío | Tabla o parquet con L1 |
| `KEKLAB_EVENTS` | `configs/events.yaml` | Hitos externos |

## Estructura

```
dashboard/
  app.py              punto de entrada y navegación
  config.py           rutas y variables de entorno
  state.py            filtros compartidos, sidebar, procedencia
  views/              una página por sección
  chat/tools.py       herramientas del chat sobre keklab.analytics
```

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
  `keklab.analytics`, el mismo módulo que usa el chat. Si el panel y el chat
  se contradicen, es un bug del servicio, no dos implementaciones.
- **Los filtros viven en el `session_state`.** Todas las secciones, incluido
  el chat, ven la misma ventana.
- **16 marcos finos y 7 cabezas.** El selector del sidebar ofrece los 16
  como casillas y las 7 como nivel derivado.
- **Explorar es removible.** Es el único módulo que lee cuerpos de posts y
  está aislado en `views/explorar.py`.
- **Sin FastAPI.** En el MVP el backend es el propio servicio, importado por
  el panel. FastAPI queda para cuando el chatbot necesite una API propia.

## Sin predicciones todavía

Mientras no exista L1, las secciones de Marcos, Toxicidad y Línea de tiempo
lo dicen con un aviso y muestran volumen. No inventan cuotas.
