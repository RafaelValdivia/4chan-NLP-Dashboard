# Journal PLN. 23. 12-11-26

Hoy se documenta el diagnóstico de la búsqueda de texto sobre el corpus real y
se cierra el hito con un journal nuevo.

## 1. El caso

El analista ejecutó la búsqueda del panel con la palabra `nigger` y reportó:

- La consulta era **muy lenta**.
- Al navegar entre páginas de resultados parecía que **tenía que cargar algo de
  nuevo** (re-ejecutando la query, en efecto).

## 2. Diagnóstico

La query SQL implementada en `keklab.analytics.service.search_posts` es correcta:

```sql
SELECT p.post_id, p.thread_id, p.timestamp_utc, p.is_op, p.text_clean, p.subject
FROM <l0_source> p
WHERE <predicates>          -- incluido: p.text_clean ILIKE '%nigger%'
ORDER BY p.timestamp_utc DESC, p.post_id DESC
LIMIT ? OFFSET ?
```

El predicado de texto sí llega (`Filters.post_predicates` → `text_clean ILIKE ?`),
así que no hay bug de filtrado: la palabra se aplica.

El costo se explica por diseño:

1. **Sin índice de texto completo.** DuckDB no puede usar índice para un patrón
   con comodín al inicio (`%…%`). Toda búsqueda = scan completo de los
   particiones del filtro + evaluación.
2. **Orden + LIMIT/OFFSET.** Cada página ejecuta la query de nuevo, con el
   `ORDER BY` y el `OFFSET` completos.

## 3. Veredicto

- **No es un problema de hardware.** Es un problema de diseño/ineficiencia
  esperable: scan-bound sobre 134 M posts.
- **No es un bug.** La implementación hace lo que promete; el coste es inherente a
  la falta de índice FTS en DuckDB para este patrón.

Con ventana podada (por ejemplo `2016-11-01 → 2016-11-30`) la misma búsqueda es
del orden de ~1 s; sobre el corpus completo quedó en ~27 s para `pizza`.

## 4. Estado

- Frontend: FastAPI + HTML/JS servido por `keklab api serve`.
- Journal: `Journal PLN. 22. 12-11-26.md` cerró la migración; este `Journal
  PLN. 23. 12-11-26.md` cierra el diagnóstico de búsqueda.

## 5. Siguiente paso

Evaluar un índice de tokens/n-gramas o precomputación para búsquedas, cuando la
ventana reciente de 4plebs esté lista y el caso de uso real exija más velocidad.
